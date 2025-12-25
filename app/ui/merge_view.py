"""
Three-way merge view for conflict resolution.

Provides a comprehensive UI for:
- Viewing base, left, and right versions
- Navigating conflicts
- Resolving conflicts interactively
- Editing merged result
- Saving resolved merge
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Optional, Callable

from PyQt6.QtCore import (
    Qt, QTimer, pyqtSignal, pyqtSlot, QSize, QRect, QPoint
)
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QTextFormat, QTextCharFormat,
    QSyntaxHighlighter, QTextDocument, QTextCursor, QPalette,
    QAction, QKeySequence, QBrush, QPen, QFontMetrics, QIcon
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QPlainTextEdit, QTextEdit, QLabel, QPushButton,
    QToolBar, QComboBox, QMessageBox, QFileDialog,
    QFrame, QScrollBar, QApplication, QToolButton,
    QMenu, QButtonGroup, QRadioButton, QGroupBox,
    QStatusBar, QProgressBar, QSizePolicy, QStackedWidget,
    QDialog, QDialogButtonBox, QCheckBox, QSpinBox,
    QGridLayout
)

from app.core.models import (
    MergeResult, MergeConflict, MergeRegion, MergeRegionType,
    ConflictResolution, ThreeWayLine, ThreeWayLineOrigin
)
from app.core.merge.three_way import ThreeWayMergeEngine, MergeStrategy
from app.core.merge.conflict_resolver import ConflictAnalyzer, AutoMerger
from app.services.file_io import FileIOService, LineEnding


class ConflictState(Enum):
    """State of a conflict in the UI."""
    UNRESOLVED = auto()
    RESOLVED_LEFT = auto()
    RESOLVED_RIGHT = auto()
    RESOLVED_BASE = auto()
    RESOLVED_BOTH = auto()
    RESOLVED_CUSTOM = auto()


@dataclass
class ConflictUIState:
    """UI state for a conflict."""
    conflict: MergeConflict
    state: ConflictState
    custom_text: Optional[str] = None
    widget: Optional[QWidget] = None


class MergeViewColors:
    """Color scheme for merge view."""
    # These will be updated by the load() method
    CONFLICT_BACKGROUND = QColor(255, 230, 230)
    CONFLICT_BORDER = QColor(255, 100, 100)
    RESOLVED_BACKGROUND = QColor(230, 255, 230)
    RESOLVED_BORDER = QColor(100, 200, 100)
    BASE_COLOR = QColor(200, 200, 255, 50)
    LEFT_COLOR = QColor(200, 255, 200, 50)
    RIGHT_COLOR = QColor(255, 200, 200, 50)
    ADDED_LINE = QColor(220, 255, 220)
    REMOVED_LINE = QColor(255, 220, 220)
    CHANGED_LINE = QColor(255, 255, 200)
    CURRENT_CONFLICT = QColor(255, 255, 150, 100)
    CONFLICT_TEXT = QColor(180, 0, 0)
    RESOLVED_TEXT = QColor(0, 128, 0)

    @classmethod
    def load(cls, theme: 'Theme'):
        """Load colors based on theme."""
        # Check if theme name contains 'dark' (handles both app.services.settings.Theme and main.Theme)
        theme_str = str(theme).lower()
        is_dark = theme_str.endswith('dark') or theme_str.endswith('custom')
        
        if is_dark:
            cls.CONFLICT_BACKGROUND = QColor(60, 30, 30)
            cls.CONFLICT_BORDER = QColor(150, 50, 50)
            cls.RESOLVED_BACKGROUND = QColor(30, 60, 30)
            cls.RESOLVED_BORDER = QColor(50, 150, 50)
            cls.BASE_COLOR = QColor(50, 50, 100, 100)
            cls.LEFT_COLOR = QColor(50, 100, 50, 100)
            cls.RIGHT_COLOR = QColor(100, 50, 50, 100)
            cls.ADDED_LINE = QColor(30, 60, 30)
            cls.REMOVED_LINE = QColor(60, 30, 30)
            cls.CHANGED_LINE = QColor(60, 60, 30)
            cls.CURRENT_CONFLICT = QColor(80, 80, 40, 150)
            cls.CONFLICT_TEXT = QColor(255, 100, 100)
            cls.RESOLVED_TEXT = QColor(100, 255, 100)
        else:
            cls.CONFLICT_BACKGROUND = QColor(255, 230, 230)
            cls.CONFLICT_BORDER = QColor(255, 100, 100)
            cls.RESOLVED_BACKGROUND = QColor(230, 255, 230)
            cls.RESOLVED_BORDER = QColor(100, 200, 100)
            cls.BASE_COLOR = QColor(200, 200, 255, 50)
            cls.LEFT_COLOR = QColor(200, 255, 200, 50)
            cls.RIGHT_COLOR = QColor(255, 200, 200, 50)
            cls.ADDED_LINE = QColor(220, 255, 220)
            cls.REMOVED_LINE = QColor(255, 220, 220)
            cls.CHANGED_LINE = QColor(255, 255, 200)
            cls.CURRENT_CONFLICT = QColor(255, 255, 150, 100)
            cls.CONFLICT_TEXT = QColor(180, 0, 0)
            cls.RESOLVED_TEXT = QColor(0, 128, 0)


class LineNumberArea(QWidget):
    """Line number display for text editors."""
    
    def __init__(self, editor: 'MergeTextEdit'):
        super().__init__(editor)
        self.editor = editor
        self._width = 50
    
    def sizeHint(self) -> QSize:
        return QSize(self._width, 0)
    
    def paintEvent(self, event) -> None:
        self.editor.line_number_area_paint_event(event)
    
    def update_width(self, width: int) -> None:
        self._width = width
        self.setFixedWidth(width)


class MergeTextEdit(QPlainTextEdit):
    """
    Enhanced text editor for merge view.
    
    Features:
    - Line numbers
    - Conflict highlighting
    - Region markers
    - Synchronized scrolling support
    """
    
    # Signal when scroll position changes
    scroll_changed = pyqtSignal(int, int)  # (horizontal, vertical)
    
    # Signal when cursor moves to a conflict
    conflict_focused = pyqtSignal(int)  # conflict_id
    
    # Signal when a conflict resolution is requested via double-click or context menu
    apply_requested = pyqtSignal(int)  # conflict_id
    
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        show_line_numbers: bool = True,
        editable: bool = False,
        side: str = 'merged'
    ):
        super().__init__(parent)
        
        self._side = side
        
        self._show_line_numbers = show_line_numbers
        self._conflict_regions: list[tuple[int, int, int, ConflictState]] = []  # (start, end, id, state)
        self._current_conflict: Optional[int] = None
        self._region_backgrounds: list[tuple[int, int, QColor]] = []
        
        # Setup
        self.setReadOnly(not editable)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        
        # Font
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        
        # Line numbers
        if show_line_numbers:
            self.line_number_area = LineNumberArea(self)
            self.blockCountChanged.connect(self._update_line_number_width)
            self.updateRequest.connect(self._update_line_number_area)
            self._update_line_number_width()
        else:
            self.line_number_area = None
        
        # Scrolling
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.horizontalScrollBar().valueChanged.connect(self._on_scroll)
        
        # Cursor
        self.cursorPositionChanged.connect(self._on_cursor_changed)
    
    def set_conflict_regions(
        self,
        regions: list[tuple[int, int, int, ConflictState]]
    ) -> None:
        """Set conflict regions for highlighting."""
        self._conflict_regions = regions
        self.viewport().update()
    
    def set_region_backgrounds(
        self,
        regions: list[tuple[int, int, QColor]]
    ) -> None:
        """Set background colors for line regions."""
        self._region_backgrounds = regions
        self.viewport().update()
    
    def set_current_conflict(self, conflict_id: Optional[int]) -> None:
        """Highlight the current conflict."""
        self._current_conflict = conflict_id
        self.viewport().update()
    
    def goto_line(self, line: int) -> None:
        """Move cursor to specific line."""
        block = self.document().findBlockByLineNumber(line - 1)
        if block.isValid():
            cursor = QTextCursor(block)
            self.setTextCursor(cursor)
            self.centerCursor()
    
    def goto_conflict(self, conflict_id: int) -> None:
        """Navigate to a specific conflict."""
        for start, end, cid, state in self._conflict_regions:
            if cid == conflict_id:
                self.goto_line(start + 1)
                self.set_current_conflict(conflict_id)
                return
    
    def get_selected_text(self) -> str:
        """Get currently selected text."""
        return self.textCursor().selectedText().replace('\u2029', '\n')
    
    def get_all_text(self) -> str:
        """Get all text content."""
        return self.toPlainText()
    
    def set_synchronized_scroll(
        self,
        h_value: int,
        v_value: int
    ) -> None:
        """Set scroll position (for sync with other editors)."""
        self.horizontalScrollBar().setValue(h_value)
        self.verticalScrollBar().setValue(v_value)
    
    def _update_line_number_width(self) -> None:
        """Update line number area width."""
        if not self.line_number_area:
            return
        
        digits = len(str(max(1, self.blockCount())))
        width = 10 + self.fontMetrics().horizontalAdvance('9') * digits
        
        self.line_number_area.update_width(width)
        self.setViewportMargins(width, 0, 0, 0)
    
    def _update_line_number_area(self, rect: QRect, dy: int) -> None:
        """Update line number area on scroll."""
        if not self.line_number_area:
            return
        
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(
                0, rect.y(),
                self.line_number_area.width(), rect.height()
            )
    
    def line_number_area_paint_event(self, event) -> None:
        """Paint line numbers."""
        if not self.line_number_area:
            return
        
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor(245, 245, 245))
        
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                
                # Check if line is in a conflict
                in_conflict = False
                conflict_state = None
                for start, end, cid, state in self._conflict_regions:
                    if start <= block_number < end:
                        in_conflict = True
                        conflict_state = state
                        break
                
                if in_conflict:
                    if conflict_state == ConflictState.UNRESOLVED:
                        painter.setPen(MergeViewColors.CONFLICT_TEXT)
                    else:
                        painter.setPen(MergeViewColors.RESOLVED_TEXT)
                else:
                    painter.setPen(QColor(128, 128, 128))
                
                painter.drawText(
                    0, top,
                    self.line_number_area.width() - 5,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    number
                )
            
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1
    
    def paintEvent(self, event) -> None:
        """Custom paint for region highlighting."""
        # Paint backgrounds for regions
        painter = QPainter(self.viewport())
        
        for start_line, end_line, color in self._region_backgrounds:
            self._paint_line_range(painter, start_line, end_line, color)
        
        # Paint conflict regions
        for start, end, cid, state in self._conflict_regions:
            if state == ConflictState.UNRESOLVED:
                color = MergeViewColors.CONFLICT_BACKGROUND
            else:
                color = MergeViewColors.RESOLVED_BACKGROUND
            
            # Highlight current conflict
            if cid == self._current_conflict:
                color = MergeViewColors.CURRENT_CONFLICT
            
            self._paint_line_range(painter, start, end, color)
        
        painter.end()
        
        # Standard paint
        super().paintEvent(event)
    
    def _paint_line_range(
        self,
        painter: QPainter,
        start_line: int,
        end_line: int,
        color: QColor
    ) -> None:
        """Paint background for a range of lines."""
        block = self.document().findBlockByLineNumber(start_line)
        if not block.isValid():
            return
        
        end_block = self.document().findBlockByLineNumber(end_line - 1)
        if not end_block.isValid():
            end_block = self.document().lastBlock()
        
        # Get geometry
        start_rect = self.blockBoundingGeometry(block).translated(self.contentOffset())
        end_rect = self.blockBoundingGeometry(end_block).translated(self.contentOffset())
        
        rect = QRect(
            0,
            int(start_rect.top()),
            self.viewport().width(),
            int(end_rect.bottom() - start_rect.top())
        )
        
        painter.fillRect(rect, color)
    
    def _on_scroll(self) -> None:
        """Handle scroll changes."""
        self.scroll_changed.emit(
            self.horizontalScrollBar().value(),
            self.verticalScrollBar().value()
        )
    
    def _on_cursor_changed(self) -> None:
        """Handle cursor position changes."""
        line = self.textCursor().blockNumber()
        
        for start, end, cid, state in self._conflict_regions:
            if start <= line < end:
                self.conflict_focused.emit(cid)
                return
    
    def mouseDoubleClickEvent(self, event) -> None:
        """Handle double-click to apply conflict resolution."""
        if self.isReadOnly() and self._side != 'merged':
            line = self.cursorForPosition(event.pos()).blockNumber()
            for start, end, cid, state in self._conflict_regions:
                if start <= line < end:
                    self.apply_requested.emit(cid)
                    return
        super().mouseDoubleClickEvent(event)
    
    def contextMenuEvent(self, event) -> None:
        """Add custom actions to context menu."""
        menu = self.createStandardContextMenu()
        
        if self.isReadOnly() and self._side != 'merged':
            line = self.cursorForPosition(event.pos()).blockNumber()
            conflict_id = None
            for start, end, cid, state in self._conflict_regions:
                if start <= line < end:
                    conflict_id = cid
                    break
            
            if conflict_id is not None:
                menu.addSeparator()
                side_name = self._side.capitalize()
                apply_action = menu.addAction(f"Apply {side_name} to Merged Result")
                apply_action.triggered.connect(lambda: self.apply_requested.emit(conflict_id))
        
        menu.exec(event.globalPos())

    def resizeEvent(self, event) -> None:
        """Handle resize."""
        super().resizeEvent(event)
        
        if self.line_number_area:
            cr = self.contentsRect()
            self.line_number_area.setGeometry(
                QRect(cr.left(), cr.top(), self.line_number_area.width(), cr.height())
            )


class ConflictWidget(QFrame):
    """
    Widget for displaying and resolving a single conflict.
    
    Shows conflict details and resolution options.
    """
    
    # Signal when resolution is chosen
    resolution_chosen = pyqtSignal(int, object, str)  # (conflict_id, resolution, custom_text)
    
    # Signal to navigate to conflict
    navigate_requested = pyqtSignal(int)  # conflict_id
    
    def __init__(
        self,
        conflict: MergeConflict,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.conflict = conflict
        self._is_expanded = True
        
        self._setup_ui()
        self._update_state()
    
    def _setup_ui(self) -> None:
        """Setup the widget UI."""
        self.setFrameShape(QFrame.Shape.Box)
        self.setFrameShadow(QFrame.Shadow.Raised)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Header
        header_layout = QHBoxLayout()
        
        self.status_label = QLabel()
        self.status_label.setStyleSheet("font-weight: bold;")
        header_layout.addWidget(self.status_label)
        
        header_layout.addStretch()
        
        # Navigate button
        self.goto_btn = QToolButton()
        self.goto_btn.setText("Go to")
        self.goto_btn.setToolTip("Navigate to this conflict")
        self.goto_btn.clicked.connect(lambda: self.navigate_requested.emit(self.conflict.conflict_id))
        header_layout.addWidget(self.goto_btn)
        
        # Expand/collapse button
        self.expand_btn = QToolButton()
        self.expand_btn.setText("▼")
        self.expand_btn.clicked.connect(self._toggle_expand)
        header_layout.addWidget(self.expand_btn)
        
        layout.addLayout(header_layout)
        
        # Content area (collapsible)
        self.content_widget = QWidget()
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        
        # Preview area
        preview_layout = QHBoxLayout()
        
        # Left preview
        left_group = QGroupBox("Left (Ours)")
        left_layout = QVBoxLayout(left_group)
        self.left_preview = QPlainTextEdit()
        self.left_preview.setReadOnly(True)
        self.left_preview.setMaximumHeight(100)
        self.left_preview.setPlainText(''.join(self.conflict.left_lines))
        self.left_preview.setStyleSheet("background-color: #e6ffe6;")
        left_layout.addWidget(self.left_preview)
        preview_layout.addWidget(left_group)
        
        # Right preview
        right_group = QGroupBox("Right (Theirs)")
        right_layout = QVBoxLayout(right_group)
        self.right_preview = QPlainTextEdit()
        self.right_preview.setReadOnly(True)
        self.right_preview.setMaximumHeight(100)
        self.right_preview.setPlainText(''.join(self.conflict.right_lines))
        self.right_preview.setStyleSheet("background-color: #ffe6e6;")
        right_layout.addWidget(self.right_preview)
        preview_layout.addWidget(right_group)
        
        content_layout.addLayout(preview_layout)
        
        # Resolution buttons
        button_layout = QHBoxLayout()
        
        self.use_left_btn = QPushButton("Use Left")
        self.use_left_btn.setToolTip("Accept left/ours version")
        self.use_left_btn.clicked.connect(
            lambda: self._choose_resolution(ConflictResolution.USE_LEFT)
        )
        button_layout.addWidget(self.use_left_btn)
        
        self.use_right_btn = QPushButton("Use Right")
        self.use_right_btn.setToolTip("Accept right/theirs version")
        self.use_right_btn.clicked.connect(
            lambda: self._choose_resolution(ConflictResolution.USE_RIGHT)
        )
        button_layout.addWidget(self.use_right_btn)
        
        self.use_both_btn = QPushButton("Use Both")
        self.use_both_btn.setToolTip("Include both versions")
        menu = QMenu(self)
        menu.addAction("Left then Right", 
                      lambda: self._choose_resolution(ConflictResolution.USE_BOTH_LEFT_FIRST))
        menu.addAction("Right then Left",
                      lambda: self._choose_resolution(ConflictResolution.USE_BOTH_RIGHT_FIRST))
        self.use_both_btn.setMenu(menu)
        button_layout.addWidget(self.use_both_btn)
        
        self.use_base_btn = QPushButton("Use Base")
        self.use_base_btn.setToolTip("Use original/base version")
        self.use_base_btn.clicked.connect(
            lambda: self._choose_resolution(ConflictResolution.USE_BASE)
        )
        self.use_base_btn.setEnabled(len(self.conflict.base_lines) > 0)
        button_layout.addWidget(self.use_base_btn)
        
        self.custom_btn = QPushButton("Custom...")
        self.custom_btn.setToolTip("Edit a custom resolution")
        self.custom_btn.clicked.connect(self._show_custom_dialog)
        button_layout.addWidget(self.custom_btn)
        
        content_layout.addLayout(button_layout)
        
        layout.addWidget(self.content_widget)
        
        # Suggestion label
        self.suggestion_label = QLabel()
        self.suggestion_label.setWordWrap(True)
        self.suggestion_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(self.suggestion_label)
        
        # Show suggestions
        self._show_suggestions()
    
    def _update_state(self) -> None:
        """Update widget state based on conflict resolution."""
        if self.conflict.is_resolved:
            self.status_label.setText(f"✓ Conflict {self.conflict.conflict_id + 1} (Resolved)")
            self.status_label.setStyleSheet("font-weight: bold; color: green;")
            self.setStyleSheet("QFrame { background-color: #f0fff0; }")
        else:
            self.status_label.setText(f"⚠ Conflict {self.conflict.conflict_id + 1} (Unresolved)")
            self.status_label.setStyleSheet("font-weight: bold; color: #cc0000;")
            self.setStyleSheet("QFrame { background-color: #fff0f0; }")
    
    def _toggle_expand(self) -> None:
        """Toggle content visibility."""
        self._is_expanded = not self._is_expanded
        self.content_widget.setVisible(self._is_expanded)
        self.expand_btn.setText("▼" if self._is_expanded else "▶")
    
    def _choose_resolution(self, resolution: ConflictResolution) -> None:
        """Handle resolution choice."""
        self.conflict.resolution = resolution
        
        # Get resolved lines
        preview = self.conflict.get_preview(resolution)
        self.conflict.resolved_lines = preview
        
        self._update_state()
        self.resolution_chosen.emit(
            self.conflict.conflict_id,
            resolution,
            ''.join(preview)
        )
    
    def _show_custom_dialog(self) -> None:
        """Show dialog for custom resolution."""
        dialog = CustomResolutionDialog(self.conflict, self)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            custom_text = dialog.get_text()
            self.conflict.resolution = ConflictResolution.CUSTOM
            self.conflict.resolved_lines = custom_text.splitlines(keepends=True)
            
            self._update_state()
            self.resolution_chosen.emit(
                self.conflict.conflict_id,
                ConflictResolution.CUSTOM,
                custom_text
            )
    
    def _show_suggestions(self) -> None:
        """Show resolution suggestions."""
        suggestions = ConflictAnalyzer.analyze(self.conflict)
        
        if suggestions:
            best = suggestions[0]
            self.suggestion_label.setText(
                f"💡 Suggestion: {best.reason} (confidence: {best.confidence:.0%})"
            )
        else:
            self.suggestion_label.hide()
    
    def update_conflict(self, conflict: MergeConflict) -> None:
        """Update with new conflict data."""
        self.conflict = conflict
        self.left_preview.setPlainText(''.join(conflict.left_lines))
        self.right_preview.setPlainText(''.join(conflict.right_lines))
        self._update_state()
        self._show_suggestions()


class CustomResolutionDialog(QDialog):
    """Dialog for editing custom conflict resolution."""
    
    def __init__(
        self,
        conflict: MergeConflict,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.conflict = conflict
        
        self.setWindowTitle("Custom Resolution")
        self.setMinimumSize(700, 500)
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup dialog UI."""
        layout = QVBoxLayout(self)
        
        # Instructions
        instructions = QLabel(
            "Edit the text below to create a custom resolution for this conflict.\n"
            "You can use the buttons to insert content from different versions."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        
        # Source buttons
        button_layout = QHBoxLayout()
        
        insert_left_btn = QPushButton("Insert Left")
        insert_left_btn.clicked.connect(self._insert_left)
        button_layout.addWidget(insert_left_btn)
        
        insert_right_btn = QPushButton("Insert Right")
        insert_right_btn.clicked.connect(self._insert_right)
        button_layout.addWidget(insert_right_btn)
        
        insert_base_btn = QPushButton("Insert Base")
        insert_base_btn.clicked.connect(self._insert_base)
        insert_base_btn.setEnabled(len(self.conflict.base_lines) > 0)
        button_layout.addWidget(insert_base_btn)
        
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(lambda: self.editor.clear())
        button_layout.addWidget(clear_btn)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # Editor
        self.editor = QPlainTextEdit()
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.editor.setFont(font)
        
        # Initialize with left content
        initial_text = ''.join(self.conflict.left_lines)
        self.editor.setPlainText(initial_text)
        layout.addWidget(self.editor)
        
        # Preview
        preview_group = QGroupBox("Preview")
        preview_layout = QHBoxLayout(preview_group)
        
        # Left comparison
        left_label = QLabel("Left:")
        preview_layout.addWidget(left_label)
        self.left_preview = QPlainTextEdit()
        self.left_preview.setReadOnly(True)
        self.left_preview.setPlainText(''.join(self.conflict.left_lines))
        self.left_preview.setMaximumHeight(80)
        preview_layout.addWidget(self.left_preview)
        
        # Right comparison
        right_label = QLabel("Right:")
        preview_layout.addWidget(right_label)
        self.right_preview = QPlainTextEdit()
        self.right_preview.setReadOnly(True)
        self.right_preview.setPlainText(''.join(self.conflict.right_lines))
        self.right_preview.setMaximumHeight(80)
        preview_layout.addWidget(self.right_preview)
        
        layout.addWidget(preview_group)
        
        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def _insert_left(self) -> None:
        """Insert left content at cursor."""
        self.editor.insertPlainText(''.join(self.conflict.left_lines))
    
    def _insert_right(self) -> None:
        """Insert right content at cursor."""
        self.editor.insertPlainText(''.join(self.conflict.right_lines))
    
    def _insert_base(self) -> None:
        """Insert base content at cursor."""
        self.editor.insertPlainText(''.join(self.conflict.base_lines))
    
    def get_text(self) -> str:
        """Get the edited text."""
        return self.editor.toPlainText()


class ConflictListWidget(QWidget):
    """Widget listing all conflicts with their status."""
    
    # Signal when a conflict is selected
    conflict_selected = pyqtSignal(int)
    
    # Signal when resolution changes
    resolution_changed = pyqtSignal(int, object, str)
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self._conflict_widgets: dict[int, ConflictWidget] = {}
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup the widget."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header
        header_layout = QHBoxLayout()
        
        self.title_label = QLabel("Conflicts")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_layout.addWidget(self.title_label)
        
        header_layout.addStretch()
        
        self.status_label = QLabel()
        header_layout.addWidget(self.status_label)
        
        layout.addLayout(header_layout)
        
        # Scroll area for conflicts
        from PyQt6.QtWidgets import QScrollArea
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.conflict_container = QWidget()
        self.conflict_layout = QVBoxLayout(self.conflict_container)
        self.conflict_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.conflict_layout.setSpacing(10)
        
        scroll.setWidget(self.conflict_container)
        layout.addWidget(scroll)
        
        # Action buttons
        action_layout = QHBoxLayout()
        
        self.resolve_all_left_btn = QPushButton("All → Left")
        self.resolve_all_left_btn.setToolTip("Resolve all conflicts using left version")
        self.resolve_all_left_btn.clicked.connect(
            lambda: self._resolve_all(ConflictResolution.USE_LEFT)
        )
        action_layout.addWidget(self.resolve_all_left_btn)
        
        self.resolve_all_right_btn = QPushButton("All → Right")
        self.resolve_all_right_btn.setToolTip("Resolve all conflicts using right version")
        self.resolve_all_right_btn.clicked.connect(
            lambda: self._resolve_all(ConflictResolution.USE_RIGHT)
        )
        action_layout.addWidget(self.resolve_all_right_btn)
        
        action_layout.addStretch()
        
        layout.addLayout(action_layout)
    
    def set_conflicts(self, conflicts: list[MergeConflict]) -> None:
        """Set the conflicts to display."""
        # Clear existing
        for widget in self._conflict_widgets.values():
            widget.deleteLater()
        self._conflict_widgets.clear()
        
        # Clear layout
        while self.conflict_layout.count():
            item = self.conflict_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Add new conflict widgets
        for conflict in conflicts:
            widget = ConflictWidget(conflict)
            widget.navigate_requested.connect(self.conflict_selected.emit)
            widget.resolution_chosen.connect(self._on_resolution_changed)
            
            self._conflict_widgets[conflict.conflict_id] = widget
            self.conflict_layout.addWidget(widget)
        
        # Add stretch at end
        self.conflict_layout.addStretch()
        
        self._update_status()
    
    def update_conflict(self, conflict_id: int, conflict: MergeConflict) -> None:
        """Update a specific conflict."""
        if conflict_id in self._conflict_widgets:
            self._conflict_widgets[conflict_id].update_conflict(conflict)
            self._update_status()
    
    def highlight_conflict(self, conflict_id: int) -> None:
        """Highlight a specific conflict."""
        for cid, widget in self._conflict_widgets.items():
            if cid == conflict_id:
                widget.setStyleSheet("QFrame { border: 2px solid #0066cc; }")
            else:
                widget._update_state()  # Reset style
    
    def _on_resolution_changed(
        self,
        conflict_id: int,
        resolution: ConflictResolution,
        text: str
    ) -> None:
        """Handle resolution change from a conflict widget."""
        self._update_status()
        self.resolution_changed.emit(conflict_id, resolution, text)
    
    def _resolve_all(self, resolution: ConflictResolution) -> None:
        """Resolve all conflicts with the same resolution."""
        for conflict_id, widget in self._conflict_widgets.items():
            if not widget.conflict.is_resolved:
                widget._choose_resolution(resolution)
    
    def _update_status(self) -> None:
        """Update status label."""
        total = len(self._conflict_widgets)
        resolved = sum(
            1 for w in self._conflict_widgets.values()
            if w.conflict.is_resolved
        )
        
        self.status_label.setText(f"{resolved}/{total} resolved")
        
        if resolved == total:
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
        elif resolved > 0:
            self.status_label.setStyleSheet("color: orange;")
        else:
            self.status_label.setStyleSheet("color: red;")


class MergeView(QWidget):
    """
    Complete three-way merge view.
    
    Provides:
    - Four panels: Base, Left, Right, Merged
    - Conflict navigation
    - Interactive resolution
    - Save functionality
    """
    
    # Signal when merge is complete
    merge_complete = pyqtSignal(object)  # MergeResult
    
    # Signal when save is requested
    save_requested = pyqtSignal(str)  # output_path
    
    # Signal when view is closed
    closed = pyqtSignal()
    
    # Signal when modification state changes
    modified_changed = pyqtSignal(bool)
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self._merge_result: Optional[MergeResult] = None
        self._base_path: Optional[Path] = None
        self._left_path: Optional[Path] = None
        self._right_path: Optional[Path] = None
        self._output_path: Optional[Path] = None
        self._is_modified = False
        self._current_conflict_index = 0
        self._sync_scroll = True
        
        self._setup_ui()
        self._setup_actions()
    
    def _setup_ui(self) -> None:
        """Setup the main UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Toolbar
        self.toolbar = self._create_toolbar()
        layout.addWidget(self.toolbar)
        
        # Main content
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left panel: Source views
        source_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Base view (optional)
        self.base_container = QWidget()
        base_layout = QVBoxLayout(self.base_container)
        base_layout.setContentsMargins(4, 4, 4, 4)
        
        base_header = QLabel("Base (Original)")
        base_header.setStyleSheet("font-weight: bold; background-color: #e0e0ff; padding: 4px;")
        base_layout.addWidget(base_header)
        
        self.base_header = base_header
        self.base_editor = MergeTextEdit(editable=False, side='base')
        base_layout.addWidget(self.base_editor)
        source_splitter.addWidget(self.base_container)
        
        # Left/Right split
        lr_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left view
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(4, 4, 4, 4)
        
        left_header = QLabel("Left (Ours)")
        left_header.setStyleSheet("font-weight: bold; background-color: #e0ffe0; padding: 4px;")
        left_layout.addWidget(left_header)
        
        self.left_header = left_header
        self.left_editor = MergeTextEdit(editable=False, side='left')
        left_layout.addWidget(self.left_editor)
        lr_splitter.addWidget(left_container)
        
        # Right view
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(4, 4, 4, 4)
        
        right_header = QLabel("Right (Theirs)")
        right_header.setStyleSheet("font-weight: bold; background-color: #ffe0e0; padding: 4px;")
        right_layout.addWidget(right_header)
        
        self.right_header = right_header
        self.right_editor = MergeTextEdit(editable=False, side='right')
        right_layout.addWidget(self.right_editor)
        lr_splitter.addWidget(right_container)
        
        source_splitter.addWidget(lr_splitter)
        source_splitter.setSizes([200, 400])
        
        main_splitter.addWidget(source_splitter)
        
        # Right panel: Merged view and conflicts
        right_panel = QSplitter(Qt.Orientation.Vertical)
        
        # Merged view
        merged_container = QWidget()
        merged_layout = QVBoxLayout(merged_container)
        merged_layout.setContentsMargins(4, 4, 4, 4)
        
        merged_header = QLabel("Merged Result")
        merged_header.setStyleSheet("font-weight: bold; background-color: #ffffd0; padding: 4px;")
        merged_layout.addWidget(merged_header)
        self.merged_header = merged_header
        
        # Make merged editor read-only to prevent manual edits from being lost
        # when other conflicts are resolved. Custom resolutions should be done
        # via the conflict resolution dialog.
        self.merged_editor = MergeTextEdit(editable=False)
        self.merged_editor.textChanged.connect(self._on_merged_text_changed)
        merged_layout.addWidget(self.merged_editor)
        right_panel.addWidget(merged_container)
        
        # Conflict list
        self.conflict_list = ConflictListWidget()
        self.conflict_list.conflict_selected.connect(self._goto_conflict)
        self.conflict_list.resolution_changed.connect(self._on_conflict_resolved)
        right_panel.addWidget(self.conflict_list)
        
        right_panel.setSizes([400, 200])
        
        main_splitter.addWidget(right_panel)
        main_splitter.setSizes([500, 500])
        
        layout.addWidget(main_splitter)
        
        # Status bar
        self.status_bar = QStatusBar()
        layout.addWidget(self.status_bar)
        
        # Connect synchronized scrolling
        self._setup_scroll_sync()
    
    def _create_toolbar(self) -> QToolBar:
        """Create the toolbar."""
        toolbar = QToolBar()
        toolbar.setMovable(False)
        
        # Navigation
        self.prev_conflict_action = toolbar.addAction("◀ Previous")
        self.prev_conflict_action.setShortcut(QKeySequence("Alt+Up"))
        self.prev_conflict_action.triggered.connect(self._prev_conflict)
        
        self.next_conflict_action = toolbar.addAction("Next ▶")
        self.next_conflict_action.setShortcut(QKeySequence("Alt+Down"))
        self.next_conflict_action.triggered.connect(self._next_conflict)
        
        toolbar.addSeparator()
        
        # Conflict counter
        self.conflict_label = QLabel(" Conflict: 0/0 ")
        toolbar.addWidget(self.conflict_label)
        
        toolbar.addSeparator()
        
        # Quick resolution
        self.use_left_action = toolbar.addAction("Use Left")
        self.use_left_action.setShortcut(QKeySequence("Alt+L"))
        self.use_left_action.triggered.connect(
            lambda: self._resolve_current(ConflictResolution.USE_LEFT)
        )
        
        self.use_right_action = toolbar.addAction("Use Right")
        self.use_right_action.setShortcut(QKeySequence("Alt+R"))
        self.use_right_action.triggered.connect(
            lambda: self._resolve_current(ConflictResolution.USE_RIGHT)
        )
        
        toolbar.addSeparator()
        
        # View options
        self.sync_scroll_action = toolbar.addAction("Sync Scroll")
        self.sync_scroll_action.setCheckable(True)
        self.sync_scroll_action.setChecked(True)
        self.sync_scroll_action.triggered.connect(self._toggle_sync_scroll)
        
        self.show_base_action = toolbar.addAction("Show Base")
        self.show_base_action.setCheckable(True)
        self.show_base_action.setChecked(True)
        self.show_base_action.triggered.connect(self._toggle_base_view)
        
        toolbar.addSeparator()
        
        # Save
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        
        self.save_action = toolbar.addAction("💾 Save")
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self._save_merge)
        
        self.save_as_action = toolbar.addAction("Save As...")
        self.save_as_action.triggered.connect(self._save_merge_as)
        
        # Connect editor apply signals
        self.base_editor.apply_requested.connect(lambda cid: self._apply_chunk(cid, 'base'))
        self.left_editor.apply_requested.connect(lambda cid: self._apply_chunk(cid, 'left'))
        self.right_editor.apply_requested.connect(lambda cid: self._apply_chunk(cid, 'right'))
        
        return toolbar
    
    def _setup_actions(self) -> None:
        """Setup keyboard shortcuts and actions."""
        # Additional shortcuts
        pass
    
    def _setup_scroll_sync(self) -> None:
        """Setup synchronized scrolling between editors."""
        editors = [self.base_editor, self.left_editor, self.right_editor, self.merged_editor]
        
        for editor in editors:
            editor.scroll_changed.connect(
                lambda h, v, e=editor: self._sync_editor_scroll(e, h, v)
            )
    
    def _sync_editor_scroll(
        self,
        source: MergeTextEdit,
        h_value: int,
        v_value: int
    ) -> None:
        """Synchronize scroll position from source to other editors."""
        if not self._sync_scroll:
            return
        
        editors = [self.base_editor, self.left_editor, self.right_editor, self.merged_editor]
        
        for editor in editors:
            if editor != source:
                editor.blockSignals(True)
                editor.set_synchronized_scroll(h_value, v_value)
                editor.blockSignals(False)
    
    def load_files(
        self,
        base_path: str | Path,
        left_path: str | Path,
        right_path: str | Path,
        output_path: Optional[str | Path] = None
    ) -> None:
        """
        Load files and perform merge.
        
        Args:
            base_path: Path to base/ancestor file
            left_path: Path to left/ours file
            right_path: Path to right/theirs file
            output_path: Path for saving merged result
        """
        self._base_path = Path(base_path)
        self._left_path = Path(left_path)
        self._right_path = Path(right_path)
        self._output_path = Path(output_path) if output_path else None
        
        # Read files
        io_service = FileIOService()
        
        base_result = io_service.read_file(self._base_path)
        left_result = io_service.read_file(self._left_path)
        right_result = io_service.read_file(self._right_path)
        
        if not all([base_result.success, left_result.success, right_result.success]):
            errors = []
            if not base_result.success:
                errors.append(f"Base: {base_result.error}")
            if not left_result.success:
                errors.append(f"Left: {left_result.error}")
            if not right_result.success:
                errors.append(f"Right: {right_result.error}")
            
            QMessageBox.critical(
                self,
                "Error Loading Files",
                "\n".join(errors)
            )
            return
        
        # Perform merge
        engine = ThreeWayMergeEngine(MergeStrategy.MANUAL)
        self._merge_result = engine.merge(
            base_result.content.lines,
            left_result.content.lines,
            right_result.content.lines,
            left_label=str(self._left_path),
            right_label=str(self._right_path),
            base_label=str(self._base_path)
        )
        
        # Update UI
        self._update_editors()
        self._update_conflict_list()
        self._update_status()
        
        # Navigate to first conflict
        if self._merge_result.conflicts:
            self._current_conflict_index = 0
            self._goto_conflict(0)
    
    def load_merge_result(
        self,
        merge_result: MergeResult,
        base_content: str = "",
        left_content: str = "",
        right_content: str = ""
    ) -> None:
        """
        Load a pre-computed merge result.
        
        Args:
            merge_result: The merge result to display
            base_content: Original base content
            left_content: Original left content
            right_content: Original right content
        """
        self._merge_result = merge_result
        
        # Set editor contents
        self.base_editor.setPlainText(base_content)
        self.left_editor.setPlainText(left_content)
        self.right_editor.setPlainText(right_content)
        self.merged_editor.setPlainText(merge_result.merged_text)
        
        # Update conflict list
        self._update_conflict_list()
        self._update_status()
        
        # Highlight regions
        self._highlight_merge_regions()
        
        # Navigate to first conflict
        if merge_result.conflicts:
            self._current_conflict_index = 0
            self._goto_conflict(0)
    
    def _update_editors(self) -> None:
        """Update editor contents from file paths."""
        if not self._merge_result:
            return
        
        io_service = FileIOService()
        
        # Load and display contents
        if self._base_path:
            result = io_service.read_file(self._base_path)
            if result.success:
                self.base_editor.setPlainText(result.content.content)
        
        if self._left_path:
            result = io_service.read_file(self._left_path)
            if result.success:
                self.left_editor.setPlainText(result.content.content)
        
        if self._right_path:
            result = io_service.read_file(self._right_path)
            if result.success:
                self.right_editor.setPlainText(result.content.content)
        
        # Set merged content
        self.merged_editor.setPlainText(self._merge_result.merged_text)
        
        # Highlight regions
        self._highlight_merge_regions()
    
    def _highlight_merge_regions(self) -> None:
        """Highlight merge regions in all editors."""
        if not self._merge_result:
            return
        
        # Build conflict regions for merged editor
        conflict_regions = []
        line = 0
        
        for region in self._merge_result.regions:
            region_lines = len(region.lines)
            
            if region.region_type == MergeRegionType.CONFLICT:
                # Find conflict ID
                for conflict in self._merge_result.conflicts:
                    if conflict.base_start == region.base_start:
                        state = (ConflictState.UNRESOLVED 
                                if not conflict.is_resolved 
                                else ConflictState.RESOLVED_CUSTOM)
                        conflict_regions.append((line, line + region_lines, conflict.conflict_id, state))
                        break
            
            line += region_lines
        
        self.merged_editor.set_conflict_regions(conflict_regions)
        
        # Highlight source editors
        self._highlight_source_regions()
    
    def _highlight_source_regions(self) -> None:
        """Highlight corresponding regions in source editors."""
        if not self._merge_result:
            return
        
        # Build region backgrounds for each editor
        left_regions = []
        right_regions = []
        
        for conflict in self._merge_result.conflicts:
            state = ConflictState.UNRESOLVED if not conflict.is_resolved else ConflictState.RESOLVED_CUSTOM
            
            # Left editor
            if conflict.left_lines:
                left_regions.append((
                    conflict.left_start,
                    conflict.left_end,
                    conflict.conflict_id,
                    state
                ))
            
            # Right editor
            if conflict.right_lines:
                right_regions.append((
                    conflict.right_start,
                    conflict.right_end,
                    conflict.conflict_id,
                    state
                ))
        
        self.left_editor.set_conflict_regions(left_regions)
        self.right_editor.set_conflict_regions(right_regions)
    
    def _update_conflict_list(self) -> None:
        """Update the conflict list widget."""
        if not self._merge_result:
            return
        
        self.conflict_list.set_conflicts(self._merge_result.conflicts)
    
    def _update_status(self) -> None:
        """Update status bar."""
        if not self._merge_result:
            self.status_bar.showMessage("No merge loaded")
            return
        
        total = len(self._merge_result.conflicts)
        resolved = sum(1 for c in self._merge_result.conflicts if c.is_resolved)
        
        status = f"Conflicts: {resolved}/{total} resolved"
        
        if self._is_modified:
            status += " | Modified"
        
        if self._output_path:
            status += f" | Output: {self._output_path.name}"
        
        self.status_bar.showMessage(status)
        
        # Update conflict label
        if total > 0:
            self.conflict_label.setText(
                f" Conflict: {self._current_conflict_index + 1}/{total} "
            )
        else:
            self.conflict_label.setText(" No conflicts ")
    
    def _goto_conflict(self, conflict_id: int) -> None:
        """Navigate to a specific conflict."""
        if not self._merge_result:
            return
        
        for i, conflict in enumerate(self._merge_result.conflicts):
            if conflict.conflict_id == conflict_id:
                self._current_conflict_index = i
                break
        
        # Navigate in all editors
        self.merged_editor.goto_conflict(conflict_id)
        
        # Highlight in source editors
        conflict = self._merge_result.conflicts[self._current_conflict_index]
        self.left_editor.goto_line(conflict.left_start + 1)
        self.right_editor.goto_line(conflict.right_start + 1)
        self.base_editor.goto_line(conflict.base_start + 1)
        
        # Highlight in conflict list
        self.conflict_list.highlight_conflict(conflict_id)
        
        self._update_status()
    
    def _prev_conflict(self) -> None:
        """Navigate to previous conflict."""
        if not self._merge_result or not self._merge_result.conflicts:
            return
        
        self._current_conflict_index = max(0, self._current_conflict_index - 1)
        conflict = self._merge_result.conflicts[self._current_conflict_index]
        self._goto_conflict(conflict.conflict_id)
    
    def _next_conflict(self) -> None:
        """Navigate to next conflict."""
        if not self._merge_result or not self._merge_result.conflicts:
            return
        
        max_index = len(self._merge_result.conflicts) - 1
        self._current_conflict_index = min(max_index, self._current_conflict_index + 1)
        conflict = self._merge_result.conflicts[self._current_conflict_index]
        self._goto_conflict(conflict.conflict_id)
    
    def _resolve_current(self, resolution: ConflictResolution) -> None:
        """Resolve the current conflict."""
        if not self._merge_result or not self._merge_result.conflicts:
            return
        
        conflict = self._merge_result.conflicts[self._current_conflict_index]
        self._resolve_conflict(conflict.conflict_id, resolution)
    
    def _resolve_conflict(
        self,
        conflict_id: int,
        resolution: ConflictResolution,
        custom_text: str = ""
    ) -> None:
        """Resolve a specific conflict."""
        if not self._merge_result:
            return
        
        engine = ThreeWayMergeEngine()
        
        custom_lines = custom_text.splitlines(keepends=True) if custom_text else None
        
        self._merge_result = engine.apply_resolution(
            self._merge_result,
            conflict_id,
            resolution,
            custom_lines
        )
        
        # Update UI
        self.merged_editor.setPlainText(self._merge_result.merged_text)
        self._highlight_merge_regions()
        self._update_conflict_list()
        self._update_status()
        
        self._is_modified = True
        
        # Move to next unresolved conflict
        self._goto_next_unresolved()
    
    @pyqtSlot(int, str)
    def _apply_chunk(self, conflict_id: int, side: str) -> None:
        """
        Apply a selected change (chunk) from one of the sides to a conflict.
        
        Args:
            conflict_id: ID of the conflict to resolve
            side: 'left', 'right', 'base', 'both_left', or 'both_right'
        """
        if not self._merge_result:
            return
            
        resolution_map = {
            'left': ConflictResolution.USE_LEFT,
            'right': ConflictResolution.USE_RIGHT,
            'base': ConflictResolution.USE_BASE,
            'both_left': ConflictResolution.USE_BOTH_LEFT_FIRST,
            'both_right': ConflictResolution.USE_BOTH_RIGHT_FIRST
        }
        
        side_lower = side.lower().replace('-', '_')
        if side_lower in resolution_map:
            self._resolve_conflict(conflict_id, resolution_map[side_lower])
        else:
            self.status_bar.showMessage(f"Unknown side: {side}", 3000)
    
    def _on_conflict_resolved(
        self,
        conflict_id: int,
        resolution: ConflictResolution,
        text: str
    ) -> None:
        """Handle conflict resolution from conflict list."""
        self._resolve_conflict(conflict_id, resolution, text)
    
    def _goto_next_unresolved(self) -> None:
        """Navigate to the next unresolved conflict."""
        if not self._merge_result:
            return
        
        # Find next unresolved
        start_index = self._current_conflict_index
        
        for i in range(len(self._merge_result.conflicts)):
            index = (start_index + i + 1) % len(self._merge_result.conflicts)
            conflict = self._merge_result.conflicts[index]
            
            if not conflict.is_resolved:
                self._goto_conflict(conflict.conflict_id)
                return
        
        # All resolved
        self._check_all_resolved()
    
    def _check_all_resolved(self) -> None:
        """Check if all conflicts are resolved and prompt for save."""
        if not self._merge_result or not self._merge_result.is_fully_resolved():
            return
        
        reply = QMessageBox.question(
            self,
            "All Conflicts Resolved",
            "All conflicts have been resolved. Would you like to save the merged result?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self._save_merge()
    
    def _on_merged_text_changed(self) -> None:
        """Handle changes to merged text."""
        if not self._is_modified:
            self._is_modified = True
            self.modified_changed.emit(True)
        self._update_status()
    
    def _toggle_sync_scroll(self, checked: bool) -> None:
        """Toggle synchronized scrolling."""
        self._sync_scroll = checked
    
    def _toggle_base_view(self, checked: bool) -> None:
        """Toggle base view visibility."""
        self.base_container.setVisible(checked)
    
    def _save_merge(self) -> None:
        """Save the merged result."""
        if not self._output_path:
            self._save_merge_as()
            return
        
        self._do_save(self._output_path)
    
    def _save_merge_as(self) -> None:
        """Save merged result to a new file."""
        # Suggest default path
        if self._left_path:
            default_path = str(self._left_path.parent / f"{self._left_path.stem}_merged{self._left_path.suffix}")
        else:
            default_path = ""
        
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Merged File",
            default_path,
            "All Files (*.*)"
        )
        
        if path:
            self._output_path = Path(path)
            self._do_save(self._output_path)
    
    def _do_save(self, path: Path) -> None:
        """Actually save to the specified path."""
        try:
            # Get content from editor (in case of manual edits)
            content = self.merged_editor.get_all_text()
            
            io_service = FileIOService()
            result = io_service.write_file(
                path,
                content,
                create_backup=True
            )
            
            if result.success:
                self._is_modified = False
                self._update_status()
                
                self.status_bar.showMessage(f"Saved to {path}", 3000)
                self.save_requested.emit(str(path))
                
                QMessageBox.information(
                    self,
                    "Saved",
                    f"Merged file saved to:\n{path}"
                )
            else:
                QMessageBox.critical(
                    self,
                    "Save Failed",
                    f"Failed to save file:\n{result.error}"
                )
                
        except Exception as e:
            QMessageBox.critical(
                self,
                "Save Error",
                f"Error saving file:\n{e}"
            )
    
    def get_merge_result(self) -> Optional[MergeResult]:
        """Get the current merge result."""
        return self._merge_result
    
    def is_modified(self) -> bool:
        """Check if there are unsaved changes."""
        return self._is_modified
    
    def has_unresolved_conflicts(self) -> bool:
        """Check if there are unresolved conflicts."""
        if not self._merge_result:
            return False
        return not self._merge_result.is_fully_resolved()

    def refresh_style(self) -> None:
        """Refresh the view's style based on current theme."""
        from app.services.settings import SettingsManager
        settings = SettingsManager().settings
        theme = settings.ui.theme
        
        MergeViewColors.load(theme)
        
        # Update headers
        theme_str = str(theme).lower()
        is_dark = theme_str.endswith('dark') or theme_str.endswith('custom')
        if is_dark:
            self.base_header.setStyleSheet("font-weight: bold; background-color: #303060; color: #e0e0ff; padding: 4px;")
            self.left_header.setStyleSheet("font-weight: bold; background-color: #205020; color: #e0ffe0; padding: 4px;")
            self.right_header.setStyleSheet("font-weight: bold; background-color: #502020; color: #ffe0e0; padding: 4px;")
            self.merged_header.setStyleSheet("font-weight: bold; background-color: #505020; color: #ffffd0; padding: 4px;")
        else:
            self.base_header.setStyleSheet("font-weight: bold; background-color: #e0e0ff; color: black; padding: 4px;")
            self.left_header.setStyleSheet("font-weight: bold; background-color: #e0ffe0; color: black; padding: 4px;")
            self.right_header.setStyleSheet("font-weight: bold; background-color: #ffe0e0; color: black; padding: 4px;")
            self.merged_header.setStyleSheet("font-weight: bold; background-color: #ffffd0; color: black; padding: 4px;")
            
        # Repaint all editors
        self.base_editor.viewport().update()
        self.left_editor.viewport().update()
        self.right_editor.viewport().update()
        self.merged_editor.viewport().update()
    
    def closeEvent(self, event) -> None:
        """Handle close event."""
        if self._is_modified:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "There are unsaved changes. Do you want to save before closing?",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel
            )
            
            if reply == QMessageBox.StandardButton.Save:
                self._save_merge()
                if self._is_modified:  # Save was cancelled
                    event.ignore()
                    return
            elif reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
        
        self.closed.emit()
        event.accept()


class MergeOptionsDialog(QDialog):
    """Dialog for configuring merge options."""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.setWindowTitle("Merge Options")
        self.setMinimumWidth(400)
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup dialog UI."""
        layout = QVBoxLayout(self)
        
        # Strategy
        strategy_group = QGroupBox("Merge Strategy")
        strategy_layout = QVBoxLayout(strategy_group)
        
        self.strategy_manual = QRadioButton("Manual - Require manual resolution for all conflicts")
        self.strategy_manual.setChecked(True)
        strategy_layout.addWidget(self.strategy_manual)
        
        self.strategy_left = QRadioButton("Favor Left - Automatically use left for conflicts")
        strategy_layout.addWidget(self.strategy_left)
        
        self.strategy_right = QRadioButton("Favor Right - Automatically use right for conflicts")
        strategy_layout.addWidget(self.strategy_right)
        
        layout.addWidget(strategy_group)
        
        # Auto-resolution options
        auto_group = QGroupBox("Auto-Resolution")
        auto_layout = QVBoxLayout(auto_group)
        
        self.auto_whitespace = QCheckBox("Auto-resolve whitespace-only differences")
        self.auto_whitespace.setChecked(True)
        auto_layout.addWidget(self.auto_whitespace)
        
        self.auto_identical = QCheckBox("Auto-resolve identical changes")
        self.auto_identical.setChecked(True)
        auto_layout.addWidget(self.auto_identical)
        
        layout.addWidget(auto_group)
        
        # Conflict markers
        markers_group = QGroupBox("Conflict Markers")
        markers_layout = QGridLayout(markers_group)
        
        markers_layout.addWidget(QLabel("Style:"), 0, 0)
        self.marker_style = QComboBox()
        self.marker_style.addItems(["Git", "SVN", "Simple"])
        markers_layout.addWidget(self.marker_style, 0, 1)
        
        self.show_base_markers = QCheckBox("Include base in conflict markers")
        self.show_base_markers.setChecked(True)
        markers_layout.addWidget(self.show_base_markers, 1, 0, 1, 2)
        
        layout.addWidget(markers_group)
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def get_strategy(self) -> MergeStrategy:
        """Get selected merge strategy."""
        if self.strategy_left.isChecked():
            return MergeStrategy.FAVOR_LEFT
        elif self.strategy_right.isChecked():
            return MergeStrategy.FAVOR_RIGHT
        else:
            return MergeStrategy.MANUAL
    
    def get_options(self) -> dict:
        """Get all options as a dictionary."""
        return {
            'strategy': self.get_strategy(),
            'auto_whitespace': self.auto_whitespace.isChecked(),
            'auto_identical': self.auto_identical.isChecked(),
            'marker_style': self.marker_style.currentText().lower(),
            'show_base_markers': self.show_base_markers.isChecked(),
        }


class MergeWindow(QWidget):
    """
    Standalone merge window.
    
    Can be used as a dialog or independent window.
    """
    
    def __init__(
        self,
        base_path: Optional[str | Path] = None,
        left_path: Optional[str | Path] = None,
        right_path: Optional[str | Path] = None,
        output_path: Optional[str | Path] = None,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        
        self.setWindowTitle("Three-Way Merge")
        self.setMinimumSize(1200, 800)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Menu bar
        self.menu_bar = self._create_menu_bar()
        layout.addWidget(self.menu_bar)
        
        # Merge view
        self.merge_view = MergeView()
        self.merge_view.closed.connect(self.close)
        layout.addWidget(self.merge_view)
        
        # Load files if provided
        if all([base_path, left_path, right_path]):
            self.merge_view.load_files(base_path, left_path, right_path, output_path)
    
    def _create_menu_bar(self) -> QWidget:
        """Create menu bar."""
        from PyQt6.QtWidgets import QMenuBar
        
        menu_bar = QMenuBar()
        
        # File menu
        file_menu = menu_bar.addMenu("File")
        
        open_action = file_menu.addAction("Open Files...")
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._open_files)
        
        file_menu.addSeparator()
        
        save_action = file_menu.addAction("Save")
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.merge_view._save_merge)
        
        save_as_action = file_menu.addAction("Save As...")
        save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_as_action.triggered.connect(self.merge_view._save_merge_as)
        
        file_menu.addSeparator()
        
        close_action = file_menu.addAction("Close")
        close_action.setShortcut(QKeySequence.StandardKey.Close)
        close_action.triggered.connect(self.close)
        
        # Edit menu
        edit_menu = menu_bar.addMenu("Edit")
        
        undo_action = edit_menu.addAction("Undo")
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        undo_action.triggered.connect(self.merge_view.merged_editor.undo)
        
        redo_action = edit_menu.addAction("Redo")
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        redo_action.triggered.connect(self.merge_view.merged_editor.redo)
        
        # Navigate menu
        nav_menu = menu_bar.addMenu("Navigate")
        
        prev_action = nav_menu.addAction("Previous Conflict")
        prev_action.setShortcut(QKeySequence("Alt+Up"))
        prev_action.triggered.connect(self.merge_view._prev_conflict)
        
        next_action = nav_menu.addAction("Next Conflict")
        next_action.setShortcut(QKeySequence("Alt+Down"))
        next_action.triggered.connect(self.merge_view._next_conflict)
        
        # Resolve menu
        resolve_menu = menu_bar.addMenu("Resolve")
        
        use_left_action = resolve_menu.addAction("Use Left")
        use_left_action.setShortcut(QKeySequence("Alt+L"))
        use_left_action.triggered.connect(
            lambda: self.merge_view._resolve_current(ConflictResolution.USE_LEFT)
        )
        
        use_right_action = resolve_menu.addAction("Use Right")
        use_right_action.setShortcut(QKeySequence("Alt+R"))
        use_right_action.triggered.connect(
            lambda: self.merge_view._resolve_current(ConflictResolution.USE_RIGHT)
        )
        
        use_base_action = resolve_menu.addAction("Use Base")
        use_base_action.setShortcut(QKeySequence("Alt+B"))
        use_base_action.triggered.connect(
            lambda: self.merge_view._resolve_current(ConflictResolution.USE_BASE)
        )
        
        resolve_menu.addSeparator()
        
        all_left_action = resolve_menu.addAction("Resolve All → Left")
        all_left_action.triggered.connect(
            lambda: self.merge_view.conflict_list._resolve_all(ConflictResolution.USE_LEFT)
        )
        
        all_right_action = resolve_menu.addAction("Resolve All → Right")
        all_right_action.triggered.connect(
            lambda: self.merge_view.conflict_list._resolve_all(ConflictResolution.USE_RIGHT)
        )
        
        # Options menu
        options_menu = menu_bar.addMenu("Options")
        
        options_action = options_menu.addAction("Merge Options...")
        options_action.triggered.connect(self._show_options)
        
        return menu_bar
    
    def _open_files(self) -> None:
        """Open file selection dialog."""
        dialog = MergeFileDialog(self)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            paths = dialog.get_paths()
            self.merge_view.load_files(
                paths['base'],
                paths['left'],
                paths['right'],
                paths.get('output')
            )
    
    def _show_options(self) -> None:
        """Show merge options dialog."""
        dialog = MergeOptionsDialog(self)
        dialog.exec()


class MergeFileDialog(QDialog):
    """Dialog for selecting files to merge."""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.setWindowTitle("Select Files to Merge")
        self.setMinimumWidth(500)
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup dialog UI."""
        layout = QVBoxLayout(self)
        
        # File selections
        grid = QGridLayout()
        
        # Base file
        grid.addWidget(QLabel("Base (Original):"), 0, 0)
        self.base_edit = QLineEdit()
        grid.addWidget(self.base_edit, 0, 1)
        base_browse = QPushButton("Browse...")
        base_browse.clicked.connect(lambda: self._browse('base'))
        grid.addWidget(base_browse, 0, 2)
        
        # Left file
        grid.addWidget(QLabel("Left (Ours):"), 1, 0)
        self.left_edit = QLineEdit()
        grid.addWidget(self.left_edit, 1, 1)
        left_browse = QPushButton("Browse...")
        left_browse.clicked.connect(lambda: self._browse('left'))
        grid.addWidget(left_browse, 1, 2)
        
        # Right file
        grid.addWidget(QLabel("Right (Theirs):"), 2, 0)
        self.right_edit = QLineEdit()
        grid.addWidget(self.right_edit, 2, 1)
        right_browse = QPushButton("Browse...")
        right_browse.clicked.connect(lambda: self._browse('right'))
        grid.addWidget(right_browse, 2, 2)
        
        # Output file
        grid.addWidget(QLabel("Output (Optional):"), 3, 0)
        self.output_edit = QLineEdit()
        grid.addWidget(self.output_edit, 3, 1)
        output_browse = QPushButton("Browse...")
        output_browse.clicked.connect(lambda: self._browse('output', save=True))
        grid.addWidget(output_browse, 3, 2)
        
        layout.addLayout(grid)
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._validate_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def _browse(self, field: str, save: bool = False) -> None:
        """Open file browser for a field."""
        if save:
            path, _ = QFileDialog.getSaveFileName(self, f"Select {field.title()} File")
        else:
            path, _ = QFileDialog.getOpenFileName(self, f"Select {field.title()} File")
        
        if path:
            edit = getattr(self, f'{field}_edit')
            edit.setText(path)
    
    def _validate_and_accept(self) -> None:
        """Validate inputs and accept dialog."""
        base = self.base_edit.text()
        left = self.left_edit.text()
        right = self.right_edit.text()
        
        errors = []
        
        if not base or not Path(base).exists():
            errors.append("Base file is required and must exist")
        if not left or not Path(left).exists():
            errors.append("Left file is required and must exist")
        if not right or not Path(right).exists():
            errors.append("Right file is required and must exist")
        
        if errors:
            QMessageBox.warning(
                self,
                "Invalid Input",
                "\n".join(errors)
            )
            return
        
        self.accept()
    
    def get_paths(self) -> dict:
        """Get the selected paths."""
        return {
            'base': self.base_edit.text(),
            'left': self.left_edit.text(),
            'right': self.right_edit.text(),
            'output': self.output_edit.text() or None,
        }


# For convenience, create QLineEdit import
from PyQt6.QtWidgets import QLineEdit