"""
File tree widget for folder comparison display.

Provides a tree view with:
- File/folder icons
- Status indicators
- Filtering support
- Context menus
- Drag and drop
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any, List

from PyQt6.QtCore import (
    Qt, QModelIndex, QAbstractItemModel, QSortFilterProxyModel,
    pyqtSignal, QMimeData, QUrl, QVariant
)
from PyQt6.QtGui import (
    QIcon, QColor, QBrush, QFont, QDrag, QAction,
    QStandardItemModel, QStandardItem
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeView, QHeaderView,
    QMenu, QLineEdit, QHBoxLayout, QPushButton,
    QComboBox, QCheckBox, QStyle, QApplication
)

from app.core.models import (
    FileStatus, FileType, FileCompareResult, FolderCompareNode,
    FolderCompareResult
)


class FileTreeItem:
    """
    Item in the file tree model.
    
    Represents a file or folder with comparison status.
    """
    
    def __init__(
        self,
        data: FileCompareResult,
        parent: Optional['FileTreeItem'] = None
    ):
        self._data = data
        self._parent = parent
        self._children: list['FileTreeItem'] = []
    
    @property
    def data(self) -> FileCompareResult:
        return self._data
    
    @property
    def parent(self) -> Optional['FileTreeItem']:
        return self._parent
    
    @property
    def children(self) -> list['FileTreeItem']:
        return self._children
    
    def add_child(self, child: 'FileTreeItem') -> None:
        child._parent = self
        self._children.append(child)
    
    def child(self, row: int) -> Optional['FileTreeItem']:
        if 0 <= row < len(self._children):
            return self._children[row]
        return None
    
    def child_count(self) -> int:
        return len(self._children)
    
    def row(self) -> int:
        if self._parent:
            return self._parent._children.index(self)
        return 0
    
    @property
    def name(self) -> str:
        return self._data.name
    
    @property
    def status(self) -> FileStatus:
        return self._data.status
    
    @property
    def is_directory(self) -> bool:
        return self._data.is_directory
    
    @property
    def path(self) -> str:
        return self._data.relative_path
    
    def has_differences(self) -> bool:
        """Check if this item or any children have differences."""
        if self._data.status != FileStatus.IDENTICAL:
            return True
        return any(child.has_differences() for child in self._children)


class FileTreeModel(QAbstractItemModel):
    """
    Model for file tree display.
    
    Columns:
    - Name
    - Status
    - Left Size
    - Right Size
    - Left Modified
    - Right Modified
    """
    
    COLUMNS = ['Name', 'Status', '% Match', 'Left Size', 'Right Size', 'Left Modified', 'Right Modified']
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._root: Optional[FileTreeItem] = None
        self._icons = self._load_icons()
    
    def _load_icons(self) -> dict:
        """Load status and type icons."""
        style = QApplication.style()
        return {
            'folder': style.standardIcon(QStyle.StandardPixmap.SP_DirIcon),
            'file': style.standardIcon(QStyle.StandardPixmap.SP_FileIcon),
            'identical': QIcon(),  # No icon for identical
            'modified': style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning),
            'left_only': style.standardIcon(QStyle.StandardPixmap.SP_ArrowLeft),
            'right_only': style.standardIcon(QStyle.StandardPixmap.SP_ArrowRight),
            'error': style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxCritical),
        }
    
    def set_result(self, result: FolderCompareResult) -> None:
        """Set the comparison result to display."""
        self.beginResetModel()
        self._root = self._build_tree(result.root)
        self.endResetModel()
    
    def _build_tree(self, node: FolderCompareNode) -> FileTreeItem:
        """Build tree items from compare nodes."""
        item = FileTreeItem(node.result)
        
        for child_node in node.children:
            child_item = self._build_tree(child_node)
            item.add_child(child_item)
        
        return item
    
    def clear(self) -> None:
        """Clear the model."""
        self.beginResetModel()
        self._root = None
        self.endResetModel()
    
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if not self._root:
            return 0
        
        if not parent.isValid():
            count = self._root.child_count()
            return count
        
        item = parent.internalPointer()
        count = item.child_count()
        return count
    
    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.COLUMNS)
        
    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
    
    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not self._root:
            return None
        
        item: FileTreeItem = index.internalPointer()
        column = index.column()
        
        if role == Qt.ItemDataRole.DisplayRole:
            return self._get_display_data(item, column)
        
        elif role == Qt.ItemDataRole.DecorationRole:
            if column == 0:
                return self._get_icon(item)
        
        elif role == Qt.ItemDataRole.ForegroundRole:
            return self._get_foreground(item)
        
        elif role == Qt.ItemDataRole.BackgroundRole:
            return self._get_background(item)
        
        elif role == Qt.ItemDataRole.UserRole + 1: # Custom role for FileStatus
            return item.status
        
        elif role == Qt.ItemDataRole.FontRole:
            if item.status != FileStatus.IDENTICAL:
                font = QFont()
                font.setBold(True)
                return font
        
        elif role == Qt.ItemDataRole.ToolTipRole:
            return self._get_tooltip(item)
        
        return None
    
    def _get_display_data(self, item: FileTreeItem, column: int) -> str:
        if column == 0:
            return item.name
        elif column == 1:
            return self._status_text(item.status)
        elif column == 2:
            # % Match
            if item.is_directory:
                return ''
            if item.status == FileStatus.IDENTICAL:
                return '100%'
            elif item.status == FileStatus.MODIFIED:
                return f"{item.data.similarity * 100:.1f}%"
            elif item.status in (FileStatus.LEFT_ONLY, FileStatus.RIGHT_ONLY):
                return '0%'
            return ''
        elif column == 3:
            if item.data.left_metadata:
                return self._format_size(item.data.left_metadata.size)
            return ''
        elif column == 4:
            if item.data.right_metadata:
                return self._format_size(item.data.right_metadata.size)
            return ''
        elif column == 5:
            if item.data.left_metadata and item.data.left_metadata.modified_time:
                return item.data.left_metadata.modified_time.strftime('%Y-%m-%d %H:%M')
            return ''
        elif column == 6:
            if item.data.right_metadata and item.data.right_metadata.modified_time:
                return item.data.right_metadata.modified_time.strftime('%Y-%m-%d %H:%M')
            return ''
        return ''
    
    def _status_text(self, status: FileStatus) -> str:
        texts = {
            FileStatus.IDENTICAL: 'Identical',
            FileStatus.MODIFIED: 'Modified',
            FileStatus.LEFT_ONLY: 'Left Only',
            FileStatus.RIGHT_ONLY: 'Right Only',
            FileStatus.TYPE_MISMATCH: 'Type Mismatch',
            FileStatus.ERROR: 'Error',
        }
        return texts.get(status, 'Unknown')
    
    def _format_size(self, size: int) -> str:
        if size < 1024:
            return f'{size} B'
        elif size < 1024 * 1024:
            return f'{size / 1024:.1f} KB'
        elif size < 1024 * 1024 * 1024:
            return f'{size / (1024 * 1024):.1f} MB'
        else:
            return f'{size / (1024 * 1024 * 1024):.2f} GB'
    
    def _get_icon(self, item: FileTreeItem) -> QIcon:
        if item.is_directory:
            return self._icons['folder']
        return self._icons['file']
    
    def _get_foreground(self, item: FileTreeItem) -> QBrush:
        colors = {
            FileStatus.IDENTICAL: QColor(100, 100, 100), # Grey
            FileStatus.MODIFIED: QColor("#CC6600"), # Dark Orange
            FileStatus.LEFT_ONLY: QColor("#0066CC"), # Dark Blue
            FileStatus.RIGHT_ONLY: QColor("#008000"), # Dark Green
            FileStatus.ERROR: QColor(200, 0, 0), # Red
        }
        color = colors.get(item.status, QColor(0, 0, 0))
        return QBrush(color)
    
    def _get_background(self, item: FileTreeItem) -> Optional[QBrush]:
        if item.status == FileStatus.MODIFIED:
            return QBrush(QColor(255, 255, 220))
        elif item.status == FileStatus.LEFT_ONLY:
            return QBrush(QColor(220, 235, 255))
        elif item.status == FileStatus.RIGHT_ONLY:
            return QBrush(QColor(220, 255, 220))
        elif item.status == FileStatus.ERROR:
            return QBrush(QColor(255, 220, 220))
        return None
    
    def _get_tooltip(self, item: FileTreeItem) -> str:
        lines = [f"Path: {item.path}"]
        lines.append(f"Status: {self._status_text(item.status)}")
        
        if item.data.error:
            lines.append(f"Error: {item.data.error}")
        
        if item.data.left_metadata:
            lines.append(f"Left: {self._format_size(item.data.left_metadata.size)}")
        if item.data.right_metadata:
            lines.append(f"Right: {self._format_size(item.data.right_metadata.size)}")
        
        return '\n'.join(lines)
    
    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self.COLUMNS):
                return self.COLUMNS[section]
        return None
    
    def index(
        self,
        row: int,
        column: int,
        parent: QModelIndex = QModelIndex()
    ) -> QModelIndex:
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        
        if not parent.isValid():
            parent_item = self._root
        else:
            parent_item = parent.internalPointer()
        
        child_item = parent_item.child(row)
        if child_item:
            return self.createIndex(row, column, child_item)
        return QModelIndex()
    
    def parent(self, index: QModelIndex) -> QModelIndex:
        if not index.isValid():
            return QModelIndex()
        
        child_item: FileTreeItem = index.internalPointer()
        parent_item = child_item.parent
        
        if parent_item is None or parent_item == self._root:
            return QModelIndex()
        
        return self.createIndex(parent_item.row(), 0, parent_item)
    
    def get_item(self, index: QModelIndex) -> Optional[FileTreeItem]:
        """Get the item at an index."""
        if index.isValid():
            return index.internalPointer()
        return None


class FileFilterProxyModel(QSortFilterProxyModel):
    """
    Proxy model for filtering the file tree.
    
    Supports filtering by:
    - File name pattern
    - Status
    - Show/hide identical files
    """
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self._show_identical = True
        self._status_filter: set[FileStatus] = set(FileStatus)
        self._name_filter = ""
        
        self.setRecursiveFilteringEnabled(True)
    
    def set_show_identical(self, show: bool) -> None:
        """Show or hide identical items."""
        self._show_identical = show
        self.invalidateFilter()
    
    def set_status_filter(self, statuses: set[FileStatus]) -> None:
        """Set which statuses to show."""
        self._status_filter = statuses
        self.invalidateFilter()
    
    def set_name_filter(self, pattern: str) -> None:
        """Set name filter pattern."""
        self._name_filter = pattern.lower()
        self.invalidateFilter()
    
    def filterAcceptsRow(
        self,
        source_row: int,
        source_parent: QModelIndex
    ) -> bool:
        index = self.sourceModel().index(source_row, 0, source_parent)
        item = self.sourceModel().get_item(index)
        
        if not item:
            return True
        
        # Status filter
        if item.status not in self._status_filter:
            return False
        
        # Identical filter
        if not self._show_identical and item.status == FileStatus.IDENTICAL:
            # Still show if children have differences
            if not item.has_differences():
                return False
        
        # Name filter
        if self._name_filter:
            if self._name_filter not in item.name.lower():
                # Check if any children match
                if not self._children_match_name(item):
                    return False
        
        return True
    
    def _children_match_name(self, item: FileTreeItem) -> bool:
        """Check if any children match the name filter."""
        for child in item.children:
            if self._name_filter in child.name.lower():
                return True
            if self._children_match_name(child):
                return True
        return False


class FileTreeWidget(QWidget):
    """
    Complete file tree widget with filtering and actions.
    """
    
    item_activated = pyqtSignal(object)  # FileCompareResult
    item_selected = pyqtSignal(object)  # FileCompareResult
    context_menu_requested = pyqtSignal(object, object)  # FileCompareResult, QPoint
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self) -> None:
        """Setup the widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Filter bar
        filter_layout = QHBoxLayout()
        
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter by name...")
        self.filter_edit.setClearButtonEnabled(True)
        filter_layout.addWidget(self.filter_edit)
        
        self.status_combo = QComboBox()
        self.status_combo.addItem("All", None)
        self.status_combo.addItem("Different", 'different')
        self.status_combo.addItem("Modified", FileStatus.MODIFIED)
        self.status_combo.addItem("Left Only", FileStatus.LEFT_ONLY)
        self.status_combo.addItem("Right Only", FileStatus.RIGHT_ONLY)
        filter_layout.addWidget(self.status_combo)
        
        self.hide_identical_cb = QCheckBox("Hide Identical")
        filter_layout.addWidget(self.hide_identical_cb)
        
        layout.addLayout(filter_layout)
        
        # Tree view
        self.tree_view = QTreeView()
        self.tree_view.setAlternatingRowColors(True)
        self.tree_view.setUniformRowHeights(True)
        self.tree_view.setAnimated(True)
        self.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_view.setSortingEnabled(True)
        
        # Model
        self.model = FileTreeModel()
        self.proxy_model = FileFilterProxyModel()
        self.proxy_model.setSourceModel(self.model)
        self.tree_view.setModel(self.proxy_model)
        
        # Header
        header = self.tree_view.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, len(FileTreeModel.COLUMNS)):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        
        layout.addWidget(self.tree_view)
    
    def _connect_signals(self) -> None:
        """Connect signals."""
        self.filter_edit.textChanged.connect(self._on_filter_changed)
        self.status_combo.currentIndexChanged.connect(self._on_status_filter_changed)
        self.hide_identical_cb.toggled.connect(self._on_hide_identical_changed)
        
        self.tree_view.activated.connect(self._on_item_activated)
        self.tree_view.clicked.connect(self._on_item_clicked)
        self.tree_view.customContextMenuRequested.connect(self._on_context_menu)
    
    def set_result(self, result: FolderCompareResult) -> None:
        """Set the comparison result to display."""
        self.model.set_result(result)
        self.tree_view.expandToDepth(1)
    
    def clear(self) -> None:
        """Clear the tree."""
        self.model.clear()
    
    def expand_all(self) -> None:
        """Expand all nodes."""
        self.tree_view.expandAll()
    
    def collapse_all(self) -> None:
        """Collapse all nodes."""
        self.tree_view.collapseAll()
    
    def _on_filter_changed(self, text: str) -> None:
        """Handle filter text change."""
        self.proxy_model.set_name_filter(text)
    
    def _on_status_filter_changed(self, index: int) -> None:
        """Handle status filter change."""
        data = self.status_combo.currentData()
        
        if data is None:
            # All statuses
            self.proxy_model.set_status_filter(set(FileStatus))
        elif data == 'different':
            # All different statuses
            self.proxy_model.set_status_filter({
                FileStatus.MODIFIED,
                FileStatus.LEFT_ONLY,
                FileStatus.RIGHT_ONLY,
                FileStatus.TYPE_MISMATCH,
                FileStatus.ERROR,
            })
        else:
            # Single status
            self.proxy_model.set_status_filter({data, FileStatus.IDENTICAL})
    
    def _on_hide_identical_changed(self, checked: bool) -> None:
        """Handle hide identical change."""
        self.proxy_model.set_show_identical(not checked)
    
    def _on_item_activated(self, index: QModelIndex) -> None:
        """Handle item double-click."""
        source_index = self.proxy_model.mapToSource(index)
        item = self.model.get_item(source_index)
        if item:
            self.item_activated.emit(item.data)
    
    def _on_item_clicked(self, index: QModelIndex) -> None:
        """Handle item single-click."""
        source_index = self.proxy_model.mapToSource(index)
        item = self.model.get_item(source_index)
        if item:
            self.item_selected.emit(item.data)
    
    def _on_context_menu(self, pos) -> None:
        """Handle context menu request."""
        index = self.tree_view.indexAt(pos)
        if index.isValid():
            source_index = self.proxy_model.mapToSource(index)
            item = self.model.get_item(source_index)
            if item:
                global_pos = self.tree_view.viewport().mapToGlobal(pos)
                self.context_menu_requested.emit(item.data, global_pos)