"""
Folder comparison view.

Provides tree-based display of folder comparison results.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Any
import logging

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QModelIndex, QPoint
from PyQt6.QtGui import QIcon, QColor, QAction
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTreeView, QHeaderView, QLabel, QFrame,
    QMenu, QToolBar, QComboBox, QLineEdit,
    QPushButton, QMessageBox, QApplication, QStyle, # Import QApplication, QStyle
)

from app.core.models import (
    FolderCompareResult, FolderCompareNode, FileStatus, FileType
)
from app.ui.widgets.file_tree_widget import (
    FileTreeModel as FolderCompareModel,
    FileFilterProxyModel as FolderCompareProxyModel
)
from app.services.settings import ColorSettings # Import ColorSettings

from PyQt6.QtWidgets import QStyledItemDelegate
from PyQt6.QtGui import QColor, QBrush, QPen, QFont, QPainter # Import QPainter, QPen, QFont
from PyQt6.QtCore import QRect # Import QRect

class FolderCompareDelegate(QStyledItemDelegate):
    def __init__(self, colors: ColorSettings, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._colors = colors

    def paint(self, painter: QPainter, option: 'QStyleOptionViewItem', index: QModelIndex) -> None:
        status = index.data(Qt.ItemDataRole.UserRole + 1) # Get the FileStatus
        
        # Draw background based on status
        if status == FileStatus.IDENTICAL:
            painter.fillRect(option.rect, QColor(self._colors.folder_identical_color))
        elif status == FileStatus.MODIFIED:
            painter.fillRect(option.rect, QColor(self._colors.folder_modified_color))
        elif status == FileStatus.LEFT_ONLY:
            painter.fillRect(option.rect, QColor(self._colors.folder_left_only_color))
        elif status == FileStatus.RIGHT_ONLY:
            painter.fillRect(option.rect, QColor(self._colors.folder_right_only_color))
        elif status == FileStatus.CONFLICT: # Assuming CONFLICT might be a status
            painter.fillRect(option.rect, QColor(self._colors.folder_conflict_color))
        
        # Call the base class paint to draw text, icons, etc.
        super().paint(painter, option, index)

from app.ui.widgets.file_preview import FilePreviewPanel
from app.services.settings import SettingsManager, ColorSettings # Import SettingsManager, ColorSettings


class FolderCompareView(QWidget):
    """
    View for comparing two folders.
    
    Features:
    - Tree view of differences
    - Filter by status (modified, new, etc.)
    - File preview panel
    - Context menu for actions
    """
    
    # Signals
    file_selected = pyqtSignal(str)  # relative path
    comparison_requested = pyqtSignal(str, str)  # left_path, right_path
    file_comparison_requested = pyqtSignal(str, str) # left_path, right_path
    preview_comparison_requested = pyqtSignal(str, str, FilePreviewPanel) # left_path, right_path, preview_panel

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self._settings_manager = SettingsManager()
        self._colors = self._settings_manager.settings.colors
        
        self._result: Optional[FolderCompareResult] = None
        self._model: Optional[FolderCompareModel] = None
        
        self._setup_ui()
        self._setup_connections()

    def start_comparison(self, left_path: str, right_path: str) -> None:
        """
        Starts the folder comparison process.
        """
        self._left_path = Path(left_path)
        self._right_path = Path(right_path)
        
        # Call the actual comparison logic here
        self.comparison_requested.emit(str(self._left_path), str(self._right_path))
    
    def _setup_ui(self) -> None:
        """Set up the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Toolbar
        toolbar = self._create_toolbar()
        layout.addWidget(toolbar)
        
        # Main content
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Tree view panel
        tree_panel = self._create_tree_panel()
        splitter.addWidget(tree_panel)
        
        # Preview panel
        self._preview_panel = FilePreviewPanel()
        splitter.addWidget(self._preview_panel)
        
        # Set initial sizes (equal distribution)
        splitter.setStretchFactor(0, 1) # Tree panel gets most vertical space
        splitter.setStretchFactor(1, 0) # Preview panel gets almost no vertical space
        # splitter.setSizes([700, 300]) # Removed hardcoded sizes
        
        layout.addWidget(splitter)
        
        # Status bar
        self._status_bar = self._create_status_bar()
        layout.addWidget(self._status_bar)
    
    def _create_toolbar(self) -> QToolBar:
        """Create the toolbar."""
        toolbar = QToolBar()
        toolbar.setMovable(False)
        
        # Filter dropdown
        self._filter_combo = QComboBox()
        self._filter_combo.addItems([
            "Show All",
            "Different Only",
            "Left Only",
            "Right Only",
            "Identical Only",
        ])
        self._filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        toolbar.addWidget(QLabel("Filter: "))
        toolbar.addWidget(self._filter_combo)
        
        toolbar.addSeparator()
        
        # Search box
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search files...")
        self._search_box.setClearButtonEnabled(True)
        self._search_box.textChanged.connect(self._on_search_changed)
        self._search_box.setMaximumWidth(200)
        toolbar.addWidget(self._search_box)
        
        toolbar.addSeparator()
        
        # Action buttons
        self._action_expand_all = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown), "Expand All", self)
        self._action_expand_all.triggered.connect(self._on_expand_all)
        toolbar.addAction(self._action_expand_all)
        
        self._action_collapse_all = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp), "Collapse All", self)
        self._action_collapse_all.triggered.connect(self._on_collapse_all)
        toolbar.addAction(self._action_collapse_all)
        
        toolbar.addSeparator()
        
        self._action_sync = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload), "Synchronize...", self) # Using SP_BrowserReload as a generic sync icon
        self._action_sync.triggered.connect(self._on_sync)
        toolbar.addAction(self._action_sync)
        
        return toolbar
    
    def _create_tree_panel(self) -> QWidget:
        """Create the tree view panel."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Headers
        header_layout = QHBoxLayout()
        
        left_header = QLabel()
        # left_header.setStyleSheet("font-weight: bold; padding: 4px;") # Removed hardcoded style
        left_header.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold)) # Set font directly
        left_header.setContentsMargins(4, 4, 4, 4) # Use contentsMargins for padding
        self._left_header = left_header
        header_layout.addWidget(left_header, 1)
        
        right_header = QLabel()
        # right_header.setStyleSheet("font-weight: bold; padding: 4px;") # Removed hardcoded style
        right_header.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold)) # Set font directly
        right_header.setContentsMargins(4, 4, 4, 4) # Use contentsMargins for padding
        right_header.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._right_header = right_header
        header_layout.addWidget(right_header, 1)
        
        layout.addLayout(header_layout)
        
        # Tree view
        self._tree_view = QTreeView()
        self._tree_view.setAlternatingRowColors(True)
        self._tree_view.setSelectionMode(QTreeView.SelectionMode.ExtendedSelection)
        self._tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree_view.customContextMenuRequested.connect(self._on_context_menu)
        self._tree_view.doubleClicked.connect(self._on_item_double_clicked)
        
        # Custom delegate for styling
        self._delegate = FolderCompareDelegate(self._colors)
        self._tree_view.setItemDelegate(self._delegate)
        
        layout.addWidget(self._tree_view, 1)
        
        return panel
    
    def _create_status_bar(self) -> QFrame:
        """Create the status bar."""
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(8, 4, 8, 4)
        
        self._status_label = QLabel()
        layout.addWidget(self._status_label)
        
        layout.addStretch()
        
        # Statistics
        self._stats_identical = QLabel()
        layout.addWidget(self._stats_identical)
        
        self._stats_modified = QLabel()
        layout.addWidget(self._stats_modified)
        
        self._stats_left_only = QLabel()
        layout.addWidget(self._stats_left_only)
        
        self._stats_right_only = QLabel()
        layout.addWidget(self._stats_right_only)
        
        return frame
    
    def _setup_connections(self) -> None:
        """Set up signal connections."""
        pass
    
    def set_compare_result(self, result: FolderCompareResult) -> None:
        """
        Set the comparison result to display.
        
        Args:
            result: Folder comparison result
        """
        self._result = result
        
        # Update headers
        self._left_header.setText(f"Left: {result.left_path}")
        self._right_header.setText(f"Right: {result.right_path}")
        
        # Create model
        self._model = FolderCompareModel(self)
        self._model.set_result(result)
        
        self._proxy_model = FolderCompareProxyModel(self)
        self._proxy_model.setSourceModel(self._model)
        self._tree_view.setModel(self._proxy_model)
        
        # Configure columns
        header = self._tree_view.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, len(FolderCompareModel.COLUMNS)):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        
        # Expand all levels
        self._tree_view.expandAll()
        
        # Update statistics
        self._update_statistics(result)
        
        # Selection handling
        self._tree_view.selectionModel().selectionChanged.connect(
            self._on_selection_changed
        )
    
    def _update_statistics(self, result: FolderCompareResult) -> None:
        """Update statistics display."""
        self._stats_identical.setText(f"✓ {result.identical_count}")
        self._stats_modified.setText(f"≠ {result.modified_count}")
        self._stats_left_only.setText(f"← {result.left_only_count}")
        self._stats_right_only.setText(f"→ {result.right_only_count}")
        
        self._status_label.setText(
            f"Total: {result.total_files} files, {result.total_directories} folders"
        )
    
    # === Actions ===
    
    @pyqtSlot(int)
    def _on_filter_changed(self, index: int) -> None:
        """Handle filter change."""
        if self._model:
            filter_map = {
                0: set(FileStatus),  # Show all
                1: {FileStatus.MODIFIED, FileStatus.LEFT_ONLY, FileStatus.RIGHT_ONLY, FileStatus.TYPE_MISMATCH, FileStatus.ERROR},
                2: {FileStatus.LEFT_ONLY},
                3: {FileStatus.RIGHT_ONLY},
                4: {FileStatus.IDENTICAL},
            }
            self._proxy_model.set_status_filter(filter_map.get(index))
    
    @pyqtSlot(str)
    def _on_search_changed(self, text: str) -> None:
        """Handle search text change."""
        if self._proxy_model:
            self._proxy_model.set_name_filter(text)
    
    @pyqtSlot()
    def _on_expand_all(self) -> None:
        """Expand all nodes."""
        self._tree_view.expandAll()
    
    @pyqtSlot()
    def _on_collapse_all(self) -> None:
        """Collapse all nodes."""
        self._tree_view.collapseAll()
    
    @pyqtSlot()
    def _on_sync(self) -> None:
        """Open sync dialog."""
        if self._result:
            from app.ui.widgets.dialogs import SyncDialog
            dialog = SyncDialog(self._result, self)
            if dialog.exec():
                self.refresh()
    
    @pyqtSlot()
    def _on_selection_changed(self) -> None:
        """Handle selection change."""
        indexes = self._tree_view.selectionModel().selectedIndexes()
        if indexes:
            # Map proxy index to source index
            source_index = self._proxy_model.mapToSource(indexes[0])
            item = self._model.get_item(source_index)
            
            if item and not item.is_directory:
                self._update_preview(item)
                self.file_selected.emit(str(item.data.relative_path))
    
    def _update_preview(self, item: Any) -> None:
        """Update the preview panel."""
        result = item.data
        left_path = None
        right_path = None
        
        if result.left_metadata:
            left_path = Path(self._result.left_path) / result.relative_path
        if result.right_metadata:
            right_path = Path(self._result.right_path) / result.relative_path
        
        self.preview_comparison_requested.emit(str(left_path or ""), str(right_path or ""), self._preview_panel)
    
    @pyqtSlot(QModelIndex)
    def _on_item_double_clicked(self, index: QModelIndex) -> None:
        """Handle item double-click."""
        # Map proxy index to source index
        source_index = self._proxy_model.mapToSource(index)
        item = self._model.get_item(source_index)
        
        if item:
            if item.is_directory:
                # Toggle expand (use proxy index for view)
                if self._tree_view.isExpanded(index):
                    self._tree_view.collapse(index)
                else:
                    self._tree_view.expand(index)
            else:
                # Open comparison for file
                self._compare_file(item)
    
    def _compare_file(self, item: Any) -> None:
        """Open file comparison for an item."""
        result = item.data
        
        left_path = Path(self._result.left_path) / result.relative_path
        right_path = Path(self._result.right_path) / result.relative_path
        
        if left_path.exists() and right_path.exists():
            self.file_comparison_requested.emit(str(left_path), str(right_path))
        elif left_path.exists():
            # Show left only
            pass
        elif right_path.exists():
            # Show right only
            pass
    
    @pyqtSlot(QPoint)
    def _on_context_menu(self, position: QPoint) -> None:
        """Show context menu."""
        # Check selection for multi-file compare
        selection = self._tree_view.selectionModel().selectedRows()
        
        if len(selection) == 2:
            idx1 = self._proxy_model.mapToSource(selection[0])
            idx2 = self._proxy_model.mapToSource(selection[1])
            
            item1 = self._model.get_item(idx1)
            item2 = self._model.get_item(idx2)
            
            if item1 and item2 and not item1.is_directory and not item2.is_directory:
                menu = QMenu(self)
                menu.addAction("Compare Selected Files").triggered.connect(
                    lambda: self._compare_two_items(item1, item2)
                )
                menu.exec(self._tree_view.viewport().mapToGlobal(position))
                return

        index = self._tree_view.indexAt(position)
        if not index.isValid():
            return
        
        source_index = self._proxy_model.mapToSource(index)
        item = self._model.get_item(source_index)
        if not item:
            return
            
        result = item.data
        menu = QMenu(self)
        
        # Compare action
        if not item.is_directory and result.exists_both:
            compare_action = menu.addAction("Compare")
            compare_action.triggered.connect(lambda: self._compare_file(item))
        
        menu.addSeparator()
        
        # Copy actions
        if result.exists_left and not result.exists_right:
            copy_action = menu.addAction("Copy to Right")
            copy_action.triggered.connect(lambda: self._copy_to_right(item))
        
        if result.exists_right and not result.exists_left:
            copy_action = menu.addAction("Copy to Left")
            copy_action.triggered.connect(lambda: self._copy_to_left(item))
        
        menu.addSeparator()
        
        # Open actions
        if result.exists_left:
            open_left = menu.addAction("Open Left")
            open_left.triggered.connect(lambda: self._open_file(item, 'left'))
        
        if result.exists_right:
            open_right = menu.addAction("Open Right")
            open_right.triggered.connect(lambda: self._open_file(item, 'right'))
        
        menu.addSeparator()
        
        # Show in explorer
        show_left = menu.addAction("Show Left in Explorer")
        show_left.triggered.connect(lambda: self._show_in_explorer(item, 'left'))
        
        show_right = menu.addAction("Show Right in Explorer")
        show_right.triggered.connect(lambda: self._show_in_explorer(item, 'right'))
        
        menu.exec(self._tree_view.viewport().mapToGlobal(position))

    def _get_best_path(self, item: Any) -> Path:
        """Get the existing path for an item, preferring left."""
        if item.data.exists_left:
             return Path(self._result.left_path) / item.data.relative_path
        return Path(self._result.right_path) / item.data.relative_path

    def _compare_two_items(self, item1: Any, item2: Any) -> None:
        """Compare two arbitrary items."""
        p1 = self._get_best_path(item1)
        p2 = self._get_best_path(item2)
        self.file_comparison_requested.emit(str(p1), str(p2))
    
    def _copy_to_right(self, item: Any) -> None:
        """Copy file from left to right."""
        import shutil
        
        src = Path(self._result.left_path) / item.data.relative_path
        dst = Path(self._result.right_path) / item.data.relative_path
        
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to copy: {e}")
    
    def _copy_to_left(self, item: Any) -> None:
        """Copy file from right to left."""
        import shutil
        
        src = Path(self._result.right_path) / item.data.relative_path
        dst = Path(self._result.left_path) / item.data.relative_path
        
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to copy: {e}")
    
    def _open_file(self, item: Any, side: str) -> None:
        """Open file with default application."""
        import subprocess
        import sys
        
        if side == 'left':
            path = Path(self._result.left_path) / item.data.relative_path
        else:
            path = Path(self._result.right_path) / item.data.relative_path
        
        if sys.platform == 'win32':
            subprocess.run(['start', '', str(path)], shell=True)
        elif sys.platform == 'darwin':
            subprocess.run(['open', str(path)])
        else:
            subprocess.run(['xdg-open', str(path)])
    
    def _show_in_explorer(self, item: Any, side: str) -> None:
        """Show file in file explorer."""
        import subprocess
        import sys
        
        if side == 'left':
            path = Path(self._result.left_path) / item.data.relative_path
        else:
            path = Path(self._result.right_path) / item.data.relative_path
        
        if sys.platform == 'win32':
            subprocess.run(['explorer', '/select,', str(path)])
        elif sys.platform == 'darwin':
            subprocess.run(['open', '-R', str(path)])
        else:
            subprocess.run(['xdg-open', str(path.parent)])
    
    def refresh(self) -> None:
        """Refresh the comparison."""
        # Re-compare folders
        if self._left_path and self._right_path:
            self.comparison_requested.emit(str(self._left_path), str(self._right_path))