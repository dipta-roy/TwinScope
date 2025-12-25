"""
Enhanced text editor widgets for diff display.

Provides specialized text editors with:
- Line highlighting for additions/deletions/modifications
- Intraline diff highlighting
- Synchronized scrolling
- Line number display
- Fold markers for unchanged regions
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Callable, List, Tuple, TYPE_CHECKING
if TYPE_CHECKING:
    from app.services.settings import Theme

from PyQt6.QtCore import (
    Qt, QRect, QSize, QPoint, pyqtSignal, QTimer, QMimeData
)
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QTextFormat, QTextCharFormat,
    QTextCursor, QPalette, QBrush, QPen, QFontMetrics,
    QTextDocument, QKeyEvent, QMouseEvent, QWheelEvent,
    QPaintEvent, QResizeEvent, QFocusEvent
)
from PyQt6.QtWidgets import (
    QWidget, QPlainTextEdit, QTextEdit, QVBoxLayout,
    QHBoxLayout, QSplitter, QScrollBar, QFrame,
    QApplication, QToolTip
)

from app.core.models import DiffLine, DiffLineType, IntralineDiff, LinePair


class DiffViewMode(Enum):
    """Display mode for diff view."""
    SIDE_BY_SIDE = auto()
    UNIFIED = auto()
    INLINE = auto()


@dataclass
class DiffColors:
    """Color scheme for diff highlighting."""
    added_bg: QColor = field(default_factory=lambda: QColor(230, 255, 236))  # #e6ffec
    added_fg: QColor = field(default_factory=lambda: QColor(36, 41, 46))
    removed_bg: QColor = field(default_factory=lambda: QColor(255, 235, 233))  # #ffebe9
    removed_fg: QColor = field(default_factory=lambda: QColor(36, 41, 46))
    modified_bg: QColor = field(default_factory=lambda: QColor(255, 248, 197))  # #fff8c5
    modified_fg: QColor = field(default_factory=lambda: QColor(36, 41, 46))
    unchanged_bg: QColor = field(default_factory=lambda: QColor(255, 255, 255))
    unchanged_fg: QColor = field(default_factory=lambda: QColor(36, 41, 46))
    
    # Intraline highlighting
    intraline_added: QColor = field(default_factory=lambda: QColor(150, 255, 150))
    intraline_removed: QColor = field(default_factory=lambda: QColor(255, 150, 150))
    intraline_changed: QColor = field(default_factory=lambda: QColor(255, 220, 100))
    
    # Line numbers
    line_number_bg: QColor = field(default_factory=lambda: QColor(245, 245, 245))
    line_number_fg: QColor = field(default_factory=lambda: QColor(128, 128, 128))
    current_line_bg: QColor = field(default_factory=lambda: QColor(255, 255, 220))
    
    # Selection
    selection_bg: QColor = field(default_factory=lambda: QColor(51, 153, 255))
    
    # Search
    search_match_bg: QColor = field(default_factory=lambda: QColor(255, 255, 0, 100)) # Yellow, translucent
    search_current_match_bg: QColor = field(default_factory=lambda: QColor(255, 150, 0, 150)) # Orange, translucent
    
    @classmethod
    def dark_theme(cls) -> 'DiffColors':
        """Get dark theme colors."""
        return cls(
            added_bg=QColor(30, 60, 30),
            added_fg=QColor(150, 255, 150),
            removed_bg=QColor(60, 30, 30),
            removed_fg=QColor(255, 150, 150),
            modified_bg=QColor(60, 60, 30),
            modified_fg=QColor(255, 255, 150),
            unchanged_bg=QColor(40, 40, 40),
            unchanged_fg=QColor(220, 220, 220),
            intraline_added=QColor(50, 100, 50),
            intraline_removed=QColor(100, 50, 50),
            intraline_changed=QColor(100, 100, 50),
            line_number_bg=QColor(50, 50, 50),
            line_number_fg=QColor(150, 150, 150),
            current_line_bg=QColor(60, 60, 50),
            selection_bg=QColor(51, 102, 153),
        )

    def reset_to_theme(self, theme: 'Theme') -> None:
        """Reset colors based on theme."""
        # Using a string comparison for robustness if types mismatch
        theme_str = str(theme).lower()
        is_dark = theme_str.endswith('dark') or theme_str.endswith('custom')
        
        if is_dark:
            dark = self.dark_theme()
            for field_name in self.__dataclass_fields__:
                setattr(self, field_name, getattr(dark, field_name))
        else:
            # Reset to light defaults
            default = DiffColors()
            for field_name in self.__dataclass_fields__:
                setattr(self, field_name, getattr(default, field_name))


class LineNumberArea(QWidget):
    """
    Widget for displaying line numbers alongside a text editor.
    
    Supports:
    - Regular line numbers
    - Diff line numbers (left/right)
    - Click to select line
    - Current line highlighting
    """
    
    clicked = pyqtSignal(int)  # Line number clicked
    
    def __init__(
        self,
        editor: 'DiffTextEdit',
        side: str = 'left'  # 'left', 'right', or 'both'
    ):
        super().__init__(editor)
        self.editor = editor
        self.side = side
        self.colors = DiffColors()
        self._width = 50
        self._line_numbers: dict[int, tuple[Optional[int], Optional[int]]] = {}
    
    def set_line_numbers(
        self,
        line_numbers: dict[int, tuple[Optional[int], Optional[int]]]
    ) -> None:
        """Set the line number mapping. Block index -> (left_num, right_num)"""
        self._line_numbers = line_numbers
        self.update()
    
    def sizeHint(self) -> QSize:
        return QSize(self._width, 0)
    
    def update_width(self) -> None:
        """Calculate and update width based on line count."""
        if self.side == 'both':
            max_num = max(
                max((ln[0] or 0, ln[1] or 0) for ln in self._line_numbers.values()),
                default=(1, 1)
            )
            digits = max(len(str(max_num[0])), len(str(max_num[1])), 3)
            self._width = 10 + self.fontMetrics().horizontalAdvance('9') * digits * 2 + 10
        else:
            digits = len(str(max(1, self.editor.blockCount())))
            self._width = 10 + self.fontMetrics().horizontalAdvance('9') * digits
        
        self.setFixedWidth(self._width)
    
    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint line numbers."""
        painter = QPainter(self)
        painter.fillRect(event.rect(), self.colors.line_number_bg)
        
        block = self.editor.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.editor.blockBoundingGeometry(block).translated(
            self.editor.contentOffset()).top())
        bottom = top + int(self.editor.blockBoundingRect(block).height())
        
        current_block = self.editor.textCursor().blockNumber()
        
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                # Get line number(s)
                if block_number in self._line_numbers:
                    left_num, right_num = self._line_numbers[block_number]
                else:
                    left_num = block_number + 1
                    right_num = block_number + 1
                
                # Highlight current line
                if block_number == current_block:
                    painter.fillRect(
                        0, top,
                        self._width,
                        self.fontMetrics().height(),
                        self.colors.current_line_bg
                    )
                
                # Draw line number(s)
                painter.setPen(self.colors.line_number_fg)
                
                if self.side == 'both':
                    # Draw left and right numbers
                    half_width = self._width // 2 - 5
                    
                    if left_num is not None:
                        painter.drawText(
                            0, top,
                            half_width, self.fontMetrics().height(),
                            Qt.AlignmentFlag.AlignRight,
                            str(left_num)
                        )
                    
                    if right_num is not None:
                        painter.drawText(
                            half_width + 10, top,
                            half_width, self.fontMetrics().height(),
                            Qt.AlignmentFlag.AlignRight,
                            str(right_num)
                        )
                else:
                    # Draw single number
                    num = left_num if self.side == 'left' else right_num
                    if num is not None:
                        painter.drawText(
                            0, top,
                            self._width - 5, self.fontMetrics().height(),
                            Qt.AlignmentFlag.AlignRight,
                            str(num)
                        )
            
            block = block.next()
            top = bottom
            bottom = top + int(self.editor.blockBoundingRect(block).height())
            block_number += 1
    
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle click to select line."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Find clicked line
            block = self.editor.firstVisibleBlock()
            top = int(self.editor.blockBoundingGeometry(block).translated(
                self.editor.contentOffset()).top())
            
            while block.isValid():
                bottom = top + int(self.editor.blockBoundingRect(block).height())
                if top <= event.position().y() < bottom:
                    self.clicked.emit(block.blockNumber())
                    break
                block = block.next()
                top = bottom


class DiffTextEdit(QPlainTextEdit):
    """
    Enhanced text editor for displaying diff content.
    
    Features:
    - Line highlighting based on diff type
    - Intraline diff highlighting
    - Synchronized scrolling with other editors
    - Line number display
    - Folding support
    - Search highlighting
    """
    
    # Signals
    scroll_changed = pyqtSignal(int, int)  # (h_value, v_value)
    line_clicked = pyqtSignal(int)  # line number
    selection_changed_custom = pyqtSignal(int, int)  # (start, end)
    
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        readonly: bool = True,
        show_line_numbers: bool = True,
        side: str = 'left',
        colors: Optional[DiffColors] = None # Accept DiffColors
    ):
        super().__init__(parent)
        
        self.colors = colors or DiffColors() # Use passed colors or default
        self._readonly = readonly
        self._show_line_numbers = show_line_numbers
        self._side = side
        
        # Line data
        self._line_types: dict[int, DiffLineType] = {}
        self._line_backgrounds: dict[int, QColor] = {}
        self._intraline_diffs: dict[int, list[IntralineDiff]] = {}
        self._line_numbers: dict[int, tuple[Optional[int], Optional[int]]] = {}
        
        # State
        self._current_search: Optional[str] = None
        self._search_matches: list[tuple[int, int]] = []
        self._current_match_index = -1
        self._sync_scroll = True
        
        # Setup
        self._setup_editor()
        self._setup_line_numbers()
        self._connect_signals()
    
    def _setup_editor(self) -> None:
        """Configure editor settings."""
        self.setReadOnly(self._readonly)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(
            self.fontMetrics().horizontalAdvance(' ') * 4
        )
        
        # Font
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        
        # Cursor
        if self._readonly:
            self.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse |
                Qt.TextInteractionFlag.TextSelectableByKeyboard
            )
    
    def _setup_line_numbers(self) -> None:
        """Setup line number widget."""
        if self._show_line_numbers:
            self.line_number_area = LineNumberArea(self, self._side)
            self.line_number_area.clicked.connect(self._on_line_clicked)
            self._update_line_number_width()
        else:
            self.line_number_area = None
    
    def _connect_signals(self) -> None:
        """Connect internal signals."""
        self.blockCountChanged.connect(self._update_line_number_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.horizontalScrollBar().valueChanged.connect(self._on_scroll)
        self.cursorPositionChanged.connect(self._highlight_current_line)
    
    def set_colors(self, colors: DiffColors) -> None:
        """Set color scheme."""
        self.colors = colors
        if self.line_number_area:
            self.line_number_area.colors = colors
        self.viewport().update()
    
    def set_diff_lines(self, lines: list[DiffLine]) -> None:
        """
        Set content from diff lines.
        
        Args:
            lines: List of DiffLine objects
        """
        self._line_types.clear()
        self._line_backgrounds.clear()
        self._intraline_diffs.clear()
        self._line_numbers.clear()
        
        content_lines = []
        
        for i, line in enumerate(lines):
            self._line_types[i] = line.line_type
            self._line_backgrounds[i] = self._get_line_background(line.line_type)
            
            if line.intraline_diff:
                self._intraline_diffs[i] = line.intraline_diff
            
            self._line_numbers[i] = (line.left_line_num, line.right_line_num)
            content_lines.append(line.display_content)
        
        self.setPlainText('\n'.join(content_lines))
        
        if self.line_number_area:
            self.line_number_area.set_line_numbers(self._line_numbers)
            self._update_line_number_width()
        
        self._apply_highlighting()
    
    def set_line_pairs(
        self,
        pairs: list[LinePair],
        side: str = 'left'
    ) -> None:
        """
        Set content from line pairs.
        
        Args:
            pairs: List of LinePair objects
            side: Which side to display ('left' or 'right')
        """
        self._line_types.clear()
        self._line_backgrounds.clear()
        self._intraline_diffs.clear()
        self._line_numbers.clear()
        
        content_lines = []
        
        for i, pair in enumerate(pairs):
            line = pair.left_line if side == 'left' else pair.right_line
            
            if line:
                self._line_types[i] = line.line_type
                self._line_backgrounds[i] = self._get_line_background(line.line_type)
                
                if line.intraline_diff:
                    self._intraline_diffs[i] = line.intraline_diff
                
                self._line_numbers[i] = (line.left_line_num, line.right_line_num)
                content_lines.append(line.display_content)
            else:
                # Empty line for alignment
                self._line_types[i] = DiffLineType.EMPTY
                self._line_backgrounds[i] = QColor(240, 240, 240)
                self._line_numbers[i] = (None, None)
                content_lines.append('')
        
        self.setPlainText('\n'.join(content_lines))
        
        if self.line_number_area:
            self.line_number_area.set_line_numbers(self._line_numbers)
            self._update_line_number_width()
        
        self._apply_highlighting()
    
    def set_plain_content(
        self,
        content: str,
        line_type: DiffLineType = DiffLineType.UNCHANGED
    ) -> None:
        """Set plain text content with uniform styling."""
        lines = content.split('\n')
        
        self._line_types.clear()
        self._line_backgrounds.clear()
        self._line_numbers.clear()
        
        for i in range(len(lines)):
            self._line_types[i] = line_type
            self._line_backgrounds[i] = self._get_line_background(line_type)
            self._line_numbers[i] = (i + 1, i + 1)
        
        self.setPlainText(content)
        
        if self.line_number_area:
            self.line_number_area.set_line_numbers(self._line_numbers)
            self._update_line_number_width()
    
    def _get_line_background(self, line_type: DiffLineType) -> QColor:
        """Get background color for line type."""
        colors_map = {
            DiffLineType.UNCHANGED: self.colors.unchanged_bg,
            DiffLineType.ADDED: self.colors.added_bg,
            DiffLineType.REMOVED: self.colors.removed_bg,
            DiffLineType.MODIFIED: self.colors.modified_bg,
            DiffLineType.CONTEXT: self.colors.unchanged_bg,
            DiffLineType.EMPTY: QColor(245, 245, 245),
        }
        return colors_map.get(line_type, self.colors.unchanged_bg)
    
    def _apply_highlighting(self) -> None:
        """Apply syntax and diff highlighting."""
        # Clear existing formatting
        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.setCharFormat(QTextCharFormat())
        
        # Apply intraline highlighting
        for block_num, diffs in self._intraline_diffs.items():
            block = self.document().findBlockByNumber(block_num)
            if not block.isValid():
                continue
            
            for diff in diffs:
                cursor = QTextCursor(block)
                cursor.movePosition(
                    QTextCursor.MoveOperation.Right,
                    QTextCursor.MoveMode.MoveAnchor,
                    diff.start
                )
                cursor.movePosition(
                    QTextCursor.MoveOperation.Right,
                    QTextCursor.MoveMode.KeepAnchor,
                    diff.end - diff.start
                )
                
                fmt = QTextCharFormat()
                if diff.diff_type == 'inserted':
                    fmt.setBackground(self.colors.intraline_added)
                elif diff.diff_type == 'deleted':
                    fmt.setBackground(self.colors.intraline_removed)
                else:
                    fmt.setBackground(self.colors.intraline_changed)
                
                cursor.mergeCharFormat(fmt)
    
    def _highlight_current_line(self) -> None:
        """Highlight the current line."""
        selections = []
        
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            selection.format.setBackground(self.colors.current_line_bg)
            selection.format.setProperty(
                QTextFormat.Property.FullWidthSelection, True
            )
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            selections.append(selection)
        
        self.setExtraSelections(selections)
    
    def _update_line_number_width(self) -> None:
        """Update line number area width."""
        if self.line_number_area:
            self.line_number_area.update_width()
            self.setViewportMargins(
                self.line_number_area.width(), 0, 0, 0
            )
    
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
    
    def _on_scroll(self) -> None:
        """Handle scroll changes."""
        if self._sync_scroll:
            self.scroll_changed.emit(
                self.horizontalScrollBar().value(),
                self.verticalScrollBar().value()
            )
    
    def _on_line_clicked(self, line: int) -> None:
        """Handle line number click."""
        self.line_clicked.emit(line)
        
        # Select the line
        block = self.document().findBlockByNumber(line)
        if block.isValid():
            cursor = QTextCursor(block)
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            self.setTextCursor(cursor)
    
    def set_sync_scroll(self, enabled: bool) -> None:
        """Enable/disable scroll synchronization."""
        self._sync_scroll = enabled
    
    def sync_scroll_to(self, h_value: int, v_value: int) -> None:
        """Synchronize scroll position."""
        self.blockSignals(True)
        self.horizontalScrollBar().setValue(h_value)
        self.verticalScrollBar().setValue(v_value)
        self.blockSignals(False)
    
    def goto_line(self, line: int) -> None:
        """Navigate to a specific line."""
        block = self.document().findBlockByNumber(line)
        if block.isValid():
            cursor = QTextCursor(block)
            self.setTextCursor(cursor)
            self.centerCursor()
    
    def find_text(
        self,
        text: str,
        case_sensitive: bool = False,
        whole_word: bool = False,
        regex: bool = False
    ) -> int:
        """
        Find text in document.
        
        Returns number of matches found.
        """
        self._current_search = text
        self._search_matches.clear()
        self._current_match_index = -1
        
        if not text:
            self._clear_search_highlighting()
            return 0
        
        # Build search flags
        flags = QTextDocument.FindFlag(0)
        if case_sensitive:
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if whole_word:
            flags |= QTextDocument.FindFlag.FindWholeWords
        
        # Find all matches
        cursor = QTextCursor(self.document())
        
        while True:
            if regex:
                from PyQt6.QtCore import QRegularExpression
                rx = QRegularExpression(text)
                cursor = self.document().find(rx, cursor, flags)
            else:
                cursor = self.document().find(text, cursor, flags)
            
            if cursor.isNull():
                break
            
            self._search_matches.append(
                (cursor.selectionStart(), cursor.selectionEnd())
            )
        
        self._highlight_search_matches()
        
        if self._search_matches:
            self._current_match_index = 0
            self._goto_match(0)
        
        return len(self._search_matches)
    
    def find_next(self) -> bool:
        """Go to next search match."""
        if not self._search_matches:
            return False
        
        self._current_match_index = (
            (self._current_match_index + 1) % len(self._search_matches)
        )
        self._goto_match(self._current_match_index)
        return True
    
    def find_previous(self) -> bool:
        """Go to previous search match."""
        if not self._search_matches:
            return False
        
        self._current_match_index = (
            (self._current_match_index - 1) % len(self._search_matches)
        )
        self._goto_match(self._current_match_index)
        return True
    
    def _goto_match(self, index: int) -> None:
        """Navigate to a specific match."""
        if 0 <= index < len(self._search_matches):
            start, end = self._search_matches[index]
            cursor = self.textCursor()
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            self.setTextCursor(cursor)
            self.centerCursor()
    
    def _highlight_search_matches(self) -> None:
        """Highlight all search matches."""
        selections = list(self.extraSelections())
        
        # Remove previous search selections
        selections = [
            s for s in selections
            if s.format.background().color() != QColor(255, 255, 0)
        ]
        
        # Add new search selections
        for i, (start, end) in enumerate(self._search_matches):
            selection = QTextEdit.ExtraSelection()
            
            cursor = self.textCursor()
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            selection.cursor = cursor
            
            if i == self._current_match_index:
                selection.format.setBackground(QColor(255, 165, 0))  # Orange for current
            else:
                selection.format.setBackground(QColor(255, 255, 0))  # Yellow for others
            
            selections.append(selection)
        
        self.setExtraSelections(selections)
    
    def _clear_search_highlighting(self) -> None:
        """Clear search highlighting."""
        selections = [
            s for s in self.extraSelections()
            if s.format.background().color() not in (QColor(255, 255, 0), QColor(255, 165, 0))
        ]
        self.setExtraSelections(selections)
    
    def clear_search(self) -> None:
        """Clear current search."""
        self._current_search = None
        self._search_matches.clear()
        self._current_match_index = -1
        self._clear_search_highlighting()
    
    def set_show_whitespace(self, show: bool) -> None:
        """Show or hide whitespace characters."""
        option = self.document().defaultTextOption()
        if show:
            option.setFlags(option.flags() | QTextOption.Flag.ShowTabsAndSpaces)
            # option.setFlags(option.flags() | QTextOption.Flag.ShowLineAndParagraphSeparators)
        else:
            option.setFlags(option.flags() & ~QTextOption.Flag.ShowTabsAndSpaces)
            # option.setFlags(option.flags() & ~QTextOption.Flag.ShowLineAndParagraphSeparators)
        self.document().setDefaultTextOption(option)
    
    def paintEvent(self, event: QPaintEvent) -> None:
        """Custom paint for line backgrounds."""
        # Paint line backgrounds
        painter = QPainter(self.viewport())
        
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(
            self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                if block_number in self._line_backgrounds:
                    color = self._line_backgrounds[block_number]
                    painter.fillRect(
                        0, top,
                        self.viewport().width(),
                        int(self.blockBoundingRect(block).height()),
                        color
                    )
            
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1
        
        painter.end()
        
        # Standard paint
        super().paintEvent(event)
    
    def resizeEvent(self, event: QResizeEvent) -> None:
        """Handle resize."""
        super().resizeEvent(event)
        
        if self.line_number_area:
            cr = self.contentsRect()
            self.line_number_area.setGeometry(
                QRect(
                    cr.left(), cr.top(),
                    self.line_number_area.width(), cr.height()
                )
            )


class SideBySideDiffWidget(QWidget):
    """
    Side-by-side diff display widget.
    
    Shows left and right files in synchronized panels.
    """
    
    # Signals
    line_selected = pyqtSignal(int, str)  # (line_num, side)
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self._sync_scroll = True
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self) -> None:
        """Setup the widget layout."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Splitter for resizable panels
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left panel
        left_container = QFrame()
        left_container.setFrameShape(QFrame.Shape.StyledPanel)
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        self.left_editor = DiffTextEdit(side='left')
        left_layout.addWidget(self.left_editor)
        self.splitter.addWidget(left_container)
        
        # Right panel
        right_container = QFrame()
        right_container.setFrameShape(QFrame.Shape.StyledPanel)
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        self.right_editor = DiffTextEdit(side='right')
        right_layout.addWidget(self.right_editor)
        self.splitter.addWidget(right_container)
        
        # Equal sizes
        self.splitter.setSizes([1, 1])
        
        layout.addWidget(self.splitter)
    
    def _connect_signals(self) -> None:
        """Connect editor signals for synchronization."""
        # Synchronized scrolling
        self.left_editor.scroll_changed.connect(
            lambda h, v: self._sync_scroll_from('left', h, v)
        )
        self.right_editor.scroll_changed.connect(
            lambda h, v: self._sync_scroll_from('right', h, v)
        )
        
        # Line selection
        self.left_editor.line_clicked.connect(
            lambda l: self.line_selected.emit(l, 'left')
        )
        self.right_editor.line_clicked.connect(
            lambda l: self.line_selected.emit(l, 'right')
        )
    
    def _sync_scroll_from(self, source: str, h: int, v: int) -> None:
        """Synchronize scroll from source to other editor."""
        if not self._sync_scroll:
            return
        
        if source == 'left':
            self.right_editor.sync_scroll_to(h, v)
        else:
            self.left_editor.sync_scroll_to(h, v)
    
    def set_sync_scroll(self, enabled: bool) -> None:
        """Enable/disable synchronized scrolling."""
        self._sync_scroll = enabled
        self.left_editor.set_sync_scroll(enabled)
        self.right_editor.set_sync_scroll(enabled)
    
    def set_line_pairs(self, pairs: list[LinePair]) -> None:
        """Set content from line pairs."""
        self.left_editor.set_line_pairs(pairs, 'left')
        self.right_editor.set_line_pairs(pairs, 'right')
    
    def set_content(
        self,
        left_lines: list[DiffLine],
        right_lines: list[DiffLine]
    ) -> None:
        """Set content from separate line lists."""
        self.left_editor.set_diff_lines(left_lines)
        self.right_editor.set_diff_lines(right_lines)
    
    def set_plain_content(
        self,
        left_content: str,
        right_content: str
    ) -> None:
        """Set plain text content."""
        self.left_editor.set_plain_content(left_content)
        self.right_editor.set_plain_content(right_content)
    
    def set_colors(self, colors: DiffColors) -> None:
        """Set color scheme for both editors."""
        self.left_editor.set_colors(colors)
        self.right_editor.set_colors(colors)
    
    def goto_line(self, line: int) -> None:
        """Navigate both editors to line."""
        self.left_editor.goto_line(line)
        self.right_editor.goto_line(line)
    
    def find_text(self, text: str, **kwargs) -> tuple[int, int]:
        """Find text in both editors."""
        left_count = self.left_editor.find_text(text, **kwargs)
        right_count = self.right_editor.find_text(text, **kwargs)
        return left_count, right_count
    
    def clear_search(self) -> None:
        """Clear search in both editors."""
        self.left_editor.clear_search()
        self.right_editor.clear_search()


class UnifiedDiffWidget(DiffTextEdit):
    """
    Unified diff display widget.
    
    Shows diff in unified format with +/- prefixes.
    """
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent, readonly=True, show_line_numbers=True, side='both')
        
        self._hunk_positions: list[int] = []  # Line numbers of hunk headers
    
    def set_unified_diff(self, diff_lines: list[str]) -> None:
        """Set content from unified diff output."""
        self._line_types.clear()
        self._line_backgrounds.clear()
        self._line_numbers.clear()
        self._hunk_positions.clear()
        
        left_num = 0
        right_num = 0
        
        for i, line in enumerate(diff_lines):
            if line.startswith('@@'):
                # Hunk header
                self._line_types[i] = DiffLineType.CONTEXT
                self._line_backgrounds[i] = QColor(200, 200, 255)
                self._line_numbers[i] = (None, None)
                self._hunk_positions.append(i)
                
                # Parse line numbers from header
                import re
                match = re.match(r'@@ -(\d+)', line)
                if match:
                    left_num = int(match.group(1))
                match = re.search(r'\+(\d+)', line)
                if match:
                    right_num = int(match.group(1))
                    
            elif line.startswith('+') and not line.startswith('+++'):
                self._line_types[i] = DiffLineType.ADDED
                self._line_backgrounds[i] = self.colors.added_bg
                self._line_numbers[i] = (None, right_num)
                right_num += 1
                
            elif line.startswith('-') and not line.startswith('---'):
                self._line_types[i] = DiffLineType.REMOVED
                self._line_backgrounds[i] = self.colors.removed_bg
                self._line_numbers[i] = (left_num, None)
                left_num += 1
                
            elif line.startswith('---') or line.startswith('+++'):
                self._line_types[i] = DiffLineType.CONTEXT
                self._line_backgrounds[i] = QColor(230, 230, 230)
                self._line_numbers[i] = (None, None)
                
            else:
                self._line_types[i] = DiffLineType.UNCHANGED
                self._line_backgrounds[i] = self.colors.unchanged_bg
                self._line_numbers[i] = (left_num, right_num)
                left_num += 1
                right_num += 1
        
        self.setPlainText('\n'.join(diff_lines))
        
        if self.line_number_area:
            self.line_number_area.set_line_numbers(self._line_numbers)
            self._update_line_number_width()
    
    def next_hunk(self) -> bool:
        """Navigate to next hunk."""
        current_line = self.textCursor().blockNumber()
        
        for pos in self._hunk_positions:
            if pos > current_line:
                self.goto_line(pos)
                return True
        
        return False
    
    def previous_hunk(self) -> bool:
        """Navigate to previous hunk."""
        current_line = self.textCursor().blockNumber()
        
        for pos in reversed(self._hunk_positions):
            if pos < current_line:
                self.goto_line(pos)
                return True
        
        return False


class DualLineNumberArea(QWidget):
    """
    Line number area showing both left and right line numbers.
    
    Used for unified diff view.
    """
    
    def __init__(self, editor: DiffTextEdit):
        super().__init__(editor)
        self.editor = editor
        self.colors = DiffColors()
        self._line_numbers: dict[int, tuple[Optional[int], Optional[int]]] = {}
    
    def set_line_numbers(
        self,
        line_numbers: dict[int, tuple[Optional[int], Optional[int]]]
    ) -> None:
        """Set line number mapping."""
        self._line_numbers = line_numbers
        self.update()
    
    def sizeHint(self) -> QSize:
        return QSize(self._calculate_width(), 0)
    
    def _calculate_width(self) -> int:
        """Calculate required width."""
        max_left = max((ln[0] or 0 for ln in self._line_numbers.values()), default=0)
        max_right = max((ln[1] or 0 for ln in self._line_numbers.values()), default=0)
        
        digits_left = len(str(max(max_left, 1)))
        digits_right = len(str(max(max_right, 1)))
        
        char_width = self.fontMetrics().horizontalAdvance('9')
        return 20 + char_width * (digits_left + digits_right + 2)
    
    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint dual line numbers."""
        painter = QPainter(self)
        painter.fillRect(event.rect(), self.colors.line_number_bg)
        
        block = self.editor.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.editor.blockBoundingGeometry(block).translated(
            self.editor.contentOffset()).top())
        bottom = top + int(self.editor.blockBoundingRect(block).height())
        
        width = self.width()
        half = width // 2
        
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                if block_number in self._line_numbers:
                    left_num, right_num = self._line_numbers[block_number]
                else:
                    left_num, right_num = None, None
                
                painter.setPen(self.colors.line_number_fg)
                
                # Left number
                if left_num is not None:
                    painter.drawText(
                        0, top, half - 5,
                        self.fontMetrics().height(),
                        Qt.AlignmentFlag.AlignRight,
                        str(left_num)
                    )
                
                # Right number
                if right_num is not None:
                    painter.drawText(
                        half + 5, top, half - 5,
                        self.fontMetrics().height(),
                        Qt.AlignmentFlag.AlignRight,
                        str(right_num)
                    )
            
            block = block.next()
            top = bottom
            bottom = top + int(self.editor.blockBoundingRect(block).height())
            block_number += 1