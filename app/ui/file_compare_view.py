"""
File comparison view.

Provides side-by-side and unified diff display for text files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QTimer
from PyQt6.QtGui import QFont, QFontMetrics, QColor, QTextCursor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QScrollBar, QFrame, QPushButton, QMessageBox,
)

from app.core.models import DiffResult, DiffLine, DiffLineType, BinaryDiffResult, ImageDiffResult
from app.ui.widgets.diff_text_edit import DiffTextEdit, SideBySideDiffWidget as SyncedDiffView, UnifiedDiffWidget, DiffColors
from app.ui.widgets.image_compare import ImageCompareWidget
from app.ui.widgets.line_number_widget import LineNumberWidget
from app.ui.widgets.search_widget import (
    SearchWidget as FindBar, 
    SearchController, 
    SearchOptions, 
    SearchResult, 
    SearchMatch
)
import re
from app.ui.widgets.diff_overview import DiffOverviewBar
from app.ui.widgets.syntax_highlighter import create_highlighter_for_file
from app.ui.widgets.diff_legend import DiffLegend

@dataclass
class SimpleDiffLine:
    line_type: DiffLineType
    display_content: str
    left_line_num: Optional[int]
    right_line_num: Optional[int]
    intraline_diff: Optional[Any] = None

class FileCompareView(QWidget):
    """
    View for comparing two text files.
    
    Supports:
    - Side-by-side view
    - Unified diff view
    - Synchronized scrolling
    - Difference navigation
    - Intraline highlighting
    """
    
    # Signals
    position_changed = pyqtSignal(int, int)  # line, column
    modified_changed = pyqtSignal(bool)
    current_diff_changed = pyqtSignal(int)  # diff index
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self._diff_result: Optional[DiffResult] = None
        self._current_diff_index = -1
        self._diff_positions: list[int] = []  # Line numbers of diffs
        self._modified = False
        self._view_mode = 'side_by_side'
        self._current_active_line_number: int = 0 # Added to track current line
        self._displayed_line_to_pair_index_map: dict[int, int] = {} # Added to map displayed line to diff_result index
        
        self._diff_colors = DiffColors() # Central DiffColors instance
        
        # Initialize with current theme
        from app.services.settings import SettingsManager
        settings = SettingsManager().settings
        self._diff_colors.reset_to_theme(settings.ui.theme)
        
        self._search_controller = SearchController(self._diff_colors) # Pass DiffColors to SearchController
        
        self._setup_ui()
        self._setup_connections()
        
        # Register editors for search
        self._search_controller.register_widget("left", self._left_editor)
        self._search_controller.register_widget("right", self._right_editor)
    
    def _setup_ui(self) -> None:
        """Set up the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header with file paths
        self._header = self._create_header()
        layout.addWidget(self._header)
        
        # Main content area
        self._content = QWidget()
        content_layout = QHBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # Side-by-side view
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left panel
        self._left_panel = self._create_editor_panel('left')
        self._splitter.addWidget(self._left_panel)
        
        # Right panel
        self._right_panel = self._create_editor_panel('right')
        self._splitter.addWidget(self._right_panel)
        
        # Equal sizes
        self._splitter.setSizes([500, 500])
        
        content_layout.addWidget(self._splitter, 1)
        
        # Overview bar (shows diff map)
        self._overview_bar = DiffOverviewBar()
        self._overview_bar.position_clicked.connect(self._on_overview_clicked)
        self._overview_bar.show() # Initially visible
        content_layout.addWidget(self._overview_bar)
        
        layout.addWidget(self._content, 1)
        
        # Legend
        self._legend = DiffLegend(colors=self._diff_colors)
        self._legend.show() # Initially visible
        layout.addWidget(self._legend)
        
        # Find bar (hidden by default)
        self._find_bar = FindBar()
        self._find_bar.hide()
        self._find_bar.search_changed.connect(self._on_find)
        self._find_bar.find_next.connect(self._on_find_next)
        self._find_bar.find_prev.connect(self._on_find_prev)
        self._find_bar.close_requested.connect(self._find_bar.hide)
        layout.addWidget(self._find_bar)
        
        # Unified diff view (hidden by default)
        self._unified_view = DiffTextEdit()
        self._unified_view.setReadOnly(True)
        self._unified_view.hide()
        
        # Image compare view (hidden by default)
        self._image_compare_widget = ImageCompareWidget()
        self._image_compare_widget.hide()
        content_layout.addWidget(self._image_compare_widget, 1)
    
    def _create_header(self) -> QWidget:
        """Create the header with file paths."""
        header = QFrame()
        header.setObjectName("DiffHeader")
        header.setStyleSheet("""
            #DiffHeader {
                /* background-color: #f6f8fa; */
                /* border-bottom: 1px solid #e1e4e8; */
            }
            QLabel {
                font-family: 'Segoe UI', system-ui, sans-serif;
                font-size: 10pt;
                /* color: #24292e; */
                padding: 4px;
            }
        """)
        
        layout = QHBoxLayout(header)
        layout.setContentsMargins(12, 8, 12, 8)
        
        self._left_path_label = QLabel()
        self._left_path_label.setStyleSheet("font-weight: 600;")
        
        self._right_path_label = QLabel()
        self._right_path_label.setStyleSheet("font-weight: 600;")
        self._right_path_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        
        layout.addWidget(self._left_path_label, 1)
        
        self._legend_button = QPushButton("Legend")
        self._legend_button.setCheckable(True)
        self._legend_button.setChecked(True)
        self._legend_button.toggled.connect(self._toggle_legend)
        self._legend_button.hide() # Hide the button as per request
        layout.addWidget(self._legend_button)
        
        layout.addWidget(self._right_path_label, 1)
        
        return header

    def _toggle_legend(self, checked: bool):
        self._legend.setVisible(checked)
    
    def _create_editor_panel(self, side: str) -> QWidget:
        """Create an editor panel with line numbers."""
        panel = QWidget()
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Text editor
        editor = DiffTextEdit(colors=self._diff_colors)
        editor.setReadOnly(True)
        
        # Line number area (must be created after editor)
        line_numbers = LineNumberWidget(editor, parent=panel)
        layout.addWidget(line_numbers)
        layout.addWidget(editor)
        
        # Connect line numbers to editor
        # Handled inside LineNumberWidget constructor now
        # editor.blockCountChanged.connect(line_numbers.update_width)
        # editor.updateRequest.connect(line_numbers.update_area)
        
        # Store references
        if side == 'left':
            self._left_line_numbers = line_numbers
            self._left_editor = editor
        else:
            self._right_line_numbers = line_numbers
            self._right_editor = editor
        
        return panel
    
    def _setup_connections(self) -> None:
        """Set up signal connections."""
        # Synchronized scrolling
        self._left_editor.verticalScrollBar().valueChanged.connect(
            self._sync_scroll_from_left
        )
        self._left_editor.verticalScrollBar().valueChanged.connect(
            self._update_overview_viewport
        )
        self._right_editor.verticalScrollBar().valueChanged.connect(
            self._sync_scroll_from_right
        )
        self._right_editor.verticalScrollBar().valueChanged.connect(
            self._update_overview_viewport
        )
        
        # Cursor position
        self._left_editor.cursorPositionChanged.connect(self._on_cursor_changed)
        self._right_editor.cursorPositionChanged.connect(self._on_cursor_changed)
        
        # Text changes (to update search highlights if needed)
        self._left_editor.textChanged.connect(self._update_search_results)
        self._right_editor.textChanged.connect(self._update_search_results)
        
        # Keyboard shortcuts
        QShortcut(QKeySequence("Escape"), self).activated.connect(self._find_bar.hide)
        QShortcut(QKeySequence("F3"), self).activated.connect(self.find_next)
        QShortcut(QKeySequence("Shift+F3"), self).activated.connect(self.find_previous)
    
    def clear(self):
        """Clears the view."""
        self._diff_result = None
        self._current_diff_index = -1
        self._diff_positions.clear()
        self._left_editor.clear()
        self._right_editor.clear()
        self._left_path_label.setText("")
        self._right_path_label.setText("")
        self._overview_bar.set_diff_result(None)
        
        self._left_line_numbers.hide()
        self._right_line_numbers.hide()
        self._overview_bar.hide()
        self._legend.hide()
        self._legend.clear_similarity()

    def set_diff_result(self, result: DiffResult | BinaryDiffResult) -> None:
        """
        Set the diff result to display.
        
        Args:
            result: The diff result from comparison
        """
        self._diff_result = result
        
        # Update headers
        self._left_path_label.setText(str(result.left_path))
        self._right_path_label.setText(str(result.right_path))

        if isinstance(result, BinaryDiffResult):
            self._handle_binary_diff_result(result)
        elif isinstance(result, ImageDiffResult):
            self._handle_image_diff_result(result)
        elif isinstance(result, DiffResult):
            self._handle_text_diff_result(result)
        else:
            # Handle unknown result type, clear view
            self.clear()

        # Reset navigation
        self._current_diff_index = -1
        if self._diff_positions:
            self.goto_first_diff()

    def _handle_binary_diff_result(self, result: BinaryDiffResult) -> None:
        """Handle displaying a BinaryDiffResult."""
        self._image_compare_widget.hide()
        self._splitter.show()
        self._left_editor.clear()
        self._right_editor.clear()

        self._left_editor.setReadOnly(True)
        self._right_editor.setReadOnly(True)

        self._left_line_numbers.hide()
        self._right_line_numbers.hide()
        self._overview_bar.hide()
        self._legend.hide()
        self._legend.clear_similarity()

        message = f"Binary files are {'identical' if result.is_identical else 'different'}.\n"
        if not result.is_identical and result.first_diff_offset is not None:
            message += f"First difference at offset: 0x{result.first_diff_offset:X}"
        
        self._left_editor.setPlainText(message)
        self._right_editor.setPlainText(message)

    def _handle_image_diff_result(self, result: ImageDiffResult) -> None:
        """Handle displaying an ImageDiffResult."""
        self._splitter.hide()
        self._left_line_numbers.hide()
        self._right_line_numbers.hide()
        self._legend.show()
        self._legend.set_similarity(result.similarity)
        self._unified_view.hide()
        
        # Show image widget
        self._image_compare_widget.set_diff_result(result)
        self._image_compare_widget.show()
        
        # Show overview bar for images too (it now supports ImageDiffResult)
        self._overview_bar.set_diff_result(result)
        self._overview_bar.show()

    def _handle_text_diff_result(self, result: DiffResult) -> None:
        """Handle displaying a DiffResult (text)."""
        self._image_compare_widget.hide()
        self._splitter.show()
        # Ensure text editors are editable and visible
        self._left_editor.setReadOnly(False)
        self._right_editor.setReadOnly(False)
        self._left_line_numbers.show()
        self._right_line_numbers.show()
        self._overview_bar.show()
        self._legend.show() # Show legend by default
        self._legend.set_similarity(result.similarity_ratio)

        # Apply syntax highlighting
        try:
            self._left_highlighter = create_highlighter_for_file(
                self._diff_result.left_path, self._left_editor.document()
            )
            self._right_highlighter = create_highlighter_for_file(
                self._diff_result.right_path, self._right_editor.document()
            )
        except Exception:
            # Fallback if syntax highlighting fails
            pass
        
        # Build content
        self._populate_editors(result)
        
        # Update overview bar
        try:
            self._overview_bar.set_diff_result(result)
        except Exception:
            pass
        self._current_diff_index = -1
        if self._diff_positions:
            self.goto_first_diff()
            
        # Initial viewport update
        QTimer.singleShot(0, self._update_overview_viewport)
    
    def _populate_editors(self, result: DiffResult) -> None:
        """Populate editors with diff content."""
        self._diff_positions.clear()
        self._displayed_line_to_pair_index_map.clear() # Clear map on repopulate
        
        left_lines: list[SimpleDiffLine] = []
        right_lines: list[SimpleDiffLine] = []
        
        display_line_idx = 0 # This is the displayed line index
        
        for original_pair_idx, pair in enumerate(result.line_pairs):
            if pair.pair_type != DiffLineType.UNCHANGED:
                self._diff_positions.append(display_line_idx)
            
            self._displayed_line_to_pair_index_map[display_line_idx] = original_pair_idx
            
            if pair.left_line:
                left_lines.append(SimpleDiffLine(
                    line_type=pair.left_line.line_type,
                    display_content=pair.left_line.display_content,
                    left_line_num=getattr(pair.left_line, 'left_line_num', getattr(pair.left_line, 'line_number', None)),
                    right_line_num=getattr(pair.left_line, 'right_line_num', None),
                    intraline_diff=getattr(pair.left_line, 'intraline_diff', None)
                ))
            else:
                left_lines.append(SimpleDiffLine(DiffLineType.EMPTY, "", None, None))
            
            if pair.right_line:
                right_lines.append(SimpleDiffLine(
                    line_type=pair.right_line.line_type,
                    display_content=pair.right_line.display_content,
                    left_line_num=getattr(pair.right_line, 'left_line_num', None),
                    right_line_num=getattr(pair.right_line, 'right_line_num', getattr(pair.right_line, 'line_number', None)),
                    intraline_diff=getattr(pair.right_line, 'intraline_diff', None)
                ))
            else:
                right_lines.append(SimpleDiffLine(DiffLineType.EMPTY, "", None, None))
            
            display_line_idx += 1
        
        # Set content
        self._left_editor.set_diff_lines(left_lines)
        self._right_editor.set_diff_lines(right_lines)
        
        # Update line numbers
        self._left_line_numbers.set_line_numbers([l.left_line_num for l in left_lines])
        self._right_line_numbers.set_line_numbers([l.right_line_num for l in right_lines])
    
    def set_view_mode(self, mode: str) -> None:
        """
        Set the view mode.
        
        Args:
            mode: 'side_by_side' or 'unified'
        """
        self._view_mode = mode
        
        if mode == 'unified':
            self._splitter.hide()
            self._unified_view.show()
            self._populate_unified_view()
        else:
            self._unified_view.hide()
            self._splitter.show()
    
    def _populate_unified_view(self) -> None:
        """Populate the unified diff view."""
        if not self._diff_result:
            return
        
        lines = list(self._diff_result.get_unified_diff())
        self._unified_view.setPlainText('\n'.join(lines))
    
    def set_show_line_numbers(self, show: bool) -> None:
        """Show or hide line numbers."""
        self._left_line_numbers.setVisible(show)
        self._right_line_numbers.setVisible(show)
    
    def set_show_whitespace(self, show: bool) -> None:
        """Show or hide whitespace characters."""
        self._left_editor.set_show_whitespace(show)
        self._right_editor.set_show_whitespace(show)
    
    def set_word_wrap(self, wrap: bool) -> None:
        """Enable or disable word wrap."""
        from PyQt6.QtWidgets import QPlainTextEdit
        mode = (QPlainTextEdit.LineWrapMode.WidgetWidth if wrap 
                else QPlainTextEdit.LineWrapMode.NoWrap)
        self._left_editor.setLineWrapMode(mode)
        self._right_editor.setLineWrapMode(mode)
    
    # === Navigation ===
    
    def goto_next_diff(self) -> None:
        """Navigate to the next difference."""
        if not self._diff_positions:
            return
        
        self._current_diff_index += 1
        if self._current_diff_index >= len(self._diff_positions):
            self._current_diff_index = 0
        
        self._goto_diff(self._current_diff_index)
    
    def goto_prev_diff(self) -> None:
        """Navigate to the previous difference."""
        if not self._diff_positions:
            return
        
        self._current_diff_index -= 1
        if self._current_diff_index < 0:
            self._current_diff_index = len(self._diff_positions) - 1
        
        self._goto_diff(self._current_diff_index)
    
    def goto_first_diff(self) -> None:
        """Navigate to the first difference."""
        if self._diff_positions:
            self._current_diff_index = 0
            self._goto_diff(0)
    
    def goto_last_diff(self) -> None:
        """Navigate to the last difference."""
        if self._diff_positions:
            self._current_diff_index = len(self._diff_positions) - 1
            self._goto_diff(self._current_diff_index)
    
    def goto_line(self, line: int) -> None:
        """Go to a specific line number in both editors."""
        if not self._diff_result:
            return

        # Ensure line number is 0-indexed for internal use
        target_line = max(0, line - 1) 

        # Left editor
        left_doc_lines = self._left_editor.document().blockCount()
        if target_line < left_doc_lines:
            block = self._left_editor.document().findBlockByLineNumber(target_line)
            cursor = QTextCursor(block)
            self._left_editor.setTextCursor(cursor)
            self._left_editor.centerCursor()
        
        # Right editor
        right_doc_lines = self._right_editor.document().blockCount()
        if target_line < right_doc_lines:
            block = self._right_editor.document().findBlockByLineNumber(target_line)
            cursor = QTextCursor(block)
            self._right_editor.setTextCursor(cursor)
            self._right_editor.centerCursor()
        
        # Emit position changed for status bar update
        self.position_changed.emit(line, 1) # Assume column 1 when going to line
    
    def _goto_diff(self, index: int) -> None:
        """Go to a specific diff by index."""
        if 0 <= index < len(self._diff_positions):
            line = self._diff_positions[index]
            block = self._left_editor.document().findBlockByLineNumber(line)
            cursor = QTextCursor(block)
            self._left_editor.setTextCursor(cursor)
            self._left_editor.centerCursor()
            self.current_diff_changed.emit(index)
    
    # === Scrolling ===
    
    def _sync_scroll_from_left(self, value: int) -> None:
        """Sync right scroll to left."""
        self._right_editor.verticalScrollBar().setValue(value)
    
    def _sync_scroll_from_right(self, value: int) -> None:
        """Sync left scroll to right."""
        self._left_editor.verticalScrollBar().setValue(value)
        
    def _update_overview_viewport(self) -> None:
        """Update the overview bar's viewport indicator."""
        if self._overview_bar.isVisible():
            scrollbar = self._left_editor.verticalScrollBar()
            # value() is the top visible line index
            # pageStep() is the number of visible lines
            self._overview_bar.set_viewport(scrollbar.value(), scrollbar.pageStep())
    
    # === Find ===
    
    def show_find(self) -> None:
        """Show the find bar."""
        self._find_bar.show()
        self._find_bar.focus_search()
    
    def find_next(self) -> None:
        """Find next occurrence."""
        if self._find_bar.isVisible():
            self._on_find_next()
        else:
            self.show_find()
    
    def find_previous(self) -> None:
        """Find previous occurrence."""
        if self._find_bar.isVisible():
            self._on_find_prev()
        else:
            self.show_find()
    
    @pyqtSlot(str, object)
    def _on_find(self, text: str, options: SearchOptions) -> None:
        """Handle find request from search widget."""
        self._update_search_results()
        
        # Jumps to first match for incremental search
        if text and options.incremental:
            self._highlight_current_search_match()

    @pyqtSlot()
    def _on_find_next(self) -> None:
        """Handle find next."""
        match = self._search_controller.find_next(self._find_bar.get_options())
        if match:
            self._highlight_current_search_match()
            self._find_bar.set_search_result(self._search_controller.get_result())
    
    @pyqtSlot()
    def _on_find_prev(self) -> None:
        """Handle find previous."""
        match = self._search_controller.find_prev(self._find_bar.get_options())
        if match:
            self._highlight_current_search_match()
            self._find_bar.set_search_result(self._search_controller.get_result())
    
    # === Editing ===
    
    def copy_left_to_right(self) -> None:
        """Copy current diff from left to right."""
        if not self._diff_result or not self._current_active_line_number:
            return

        displayed_line_idx = self._current_active_line_number - 1
        
        if displayed_line_idx not in self._displayed_line_to_pair_index_map:
            return

        original_pair_idx = self._displayed_line_to_pair_index_map[displayed_line_idx]
        line_pair = self._diff_result.line_pairs[original_pair_idx]

        if line_pair.left_line and (not line_pair.right_line or line_pair.left_line.content != line_pair.right_line.content):
            # Create a new DiffLine for the right side, based on the left side
            line_pair.right_line = DiffLine(
                line_number=line_pair.left_line.line_number if line_pair.left_line.line_number is not None else -1,
                content=line_pair.left_line.content,
                line_type=DiffLineType.UNCHANGED,
                display_content=line_pair.left_line.content
            )
            line_pair.pair_type = DiffLineType.UNCHANGED
            line_pair.intraline_diff = None # Clear intraline diff after copy
            self._modified = True
            self.modified_changed.emit(True)
            self.set_diff_result(self._diff_result) # Refresh view
    
    def copy_right_to_left(self) -> None:
        """Copy current diff from right to left."""
        if not self._diff_result or not self._current_active_line_number:
            return

        displayed_line_idx = self._current_active_line_number - 1
        
        if displayed_line_idx not in self._displayed_line_to_pair_index_map:
            return

        original_pair_idx = self._displayed_line_to_pair_index_map[displayed_line_idx]
        line_pair = self._diff_result.line_pairs[original_pair_idx]

        if line_pair.right_line and (not line_pair.left_line or line_pair.right_line.content != line_pair.left_line.content):
            # Create a new DiffLine for the left side, based on the right side
            line_pair.left_line = DiffLine(
                line_number=line_pair.right_line.line_number if line_pair.right_line.line_number is not None else -1,
                content=line_pair.right_line.content,
                line_type=DiffLineType.UNCHANGED,
                display_content=line_pair.right_line.content
            )
            line_pair.pair_type = DiffLineType.UNCHANGED
            line_pair.intraline_diff = None # Clear intraline diff after copy
            self._modified = True
            self.modified_changed.emit(True)
            self.set_diff_result(self._diff_result) # Refresh view
    
    def use_left_all(self) -> None:
        """Use left version for all differences."""
        if not self._diff_result:
            return

        any_changed = False
        for pair in self._diff_result.line_pairs:
            if pair.pair_type != DiffLineType.UNCHANGED:
                if pair.left_line:
                    # Replace right with left content
                    pair.right_line = DiffLine(
                        line_number=pair.left_line.line_number,
                        content=pair.left_line.content,
                        line_type=DiffLineType.UNCHANGED,
                        display_content=pair.left_line.display_content
                    )
                else:
                     # Left is empty (deleted), so right should be empty/deleted too?
                     # Ideally we match the left state. If left is empty, right should be empty.
                     pair.right_line = None
                
                pair.pair_type = DiffLineType.UNCHANGED
                pair.intraline_diff = None
                any_changed = True
        
        if any_changed:
            self._modified = True
            self.modified_changed.emit(True)
            self.set_diff_result(self._diff_result)

    def use_right_all(self) -> None:
        """Use right version for all differences."""
        if not self._diff_result:
            return

        any_changed = False
        for pair in self._diff_result.line_pairs:
            if pair.pair_type != DiffLineType.UNCHANGED:
                if pair.right_line:
                    # Replace left with right content
                    pair.left_line = DiffLine(
                        line_number=pair.right_line.line_number,
                        content=pair.right_line.content,
                        line_type=DiffLineType.UNCHANGED,
                        display_content=pair.right_line.display_content
                    )
                else:
                     # Right is empty, make left empty
                     pair.left_line = None
                
                pair.pair_type = DiffLineType.UNCHANGED
                pair.intraline_diff = None
                any_changed = True
        
        if any_changed:
            self._modified = True
            self.modified_changed.emit(True)
            self.set_diff_result(self._diff_result)
    
    def copy_selection(self) -> None:
        """Copy selected text to clipboard."""
        focused = self.focusWidget()
        if hasattr(focused, 'copy'):
            focused.copy()
    
    # === State ===
    
    def is_modified(self) -> bool:
        """Check if content is modified."""
        return self._modified
    
    def save(self) -> None:
        """Save changes."""
        if not self._diff_result:
            return
            
        # We save the file that corresponds to the editors. 
        # Typically we save both if modified, or just the one modified.
        # Since we don't track which specific side was modified finely enough (just global _modified),
        # we can try to save both contents to their respective paths.
        
        try:
            # Save Left
            left_content = self._left_editor.toPlainText()
            with open(self._diff_result.left_path, 'w', encoding='utf-8') as f:
                f.write(left_content)
                
            # Save Right
            right_content = self._right_editor.toPlainText()
            with open(self._diff_result.right_path, 'w', encoding='utf-8') as f:
                f.write(right_content)
                
            self._modified = False
            self.modified_changed.emit(False)
            
        except OSError as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save file: {e}")
    
    def save_as(self) -> None:
        """Save as new file."""
        # Helper to prompt and save
        def save_editor_content(editor, default_path):
            path, _ = QFileDialog.getSaveFileName(self, "Save File", str(default_path))
            if path:
                try:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(editor.toPlainText())
                except OSError as e:
                    QMessageBox.critical(self, "Save Error", f"Failed to save file: {e}")

        # If both modified, maybe ask which one? Or just defaulting to Right as it's often the 'new' one
        # For simplicity, let's offer to save the file corresponding to the focused editor, 
        # or default to Right if neither.
        if self._left_editor.hasFocus():
             save_editor_content(self._left_editor, self._diff_result.left_path if self._diff_result else "")
        else:
             save_editor_content(self._right_editor, self._diff_result.right_path if self._diff_result else "")

    def refresh(self) -> None:
        """Refresh the comparison."""
        if self._diff_result and self.window():
            # Trigger re-comparison in place
            # This relies on MainWindow's implementation of _start_file_comparison_worker
            if hasattr(self.window(), '_start_file_comparison_worker'):
                 self.window()._start_file_comparison_worker(
                     str(self._diff_result.left_path), 
                     str(self._diff_result.right_path), 
                     target_view=self
                 )
            
    def generate_report(self) -> None:
        """Generate a comparison report."""
        QMessageBox.information(self, "Report Generation", "Report generation is not yet implemented for file comparisons.")
        
    # === Aliases for compatibility ===
    @pyqtSlot()
    def _go_to_next_diff(self): return self.goto_next_diff()
    
    @pyqtSlot()
    def _go_to_prev_diff(self): return self.goto_prev_diff()
    
    # === Slots ===
    
    @pyqtSlot()
    def _update_search_results(self) -> None:
        """Re-run search when text or options change."""
        text = self._find_bar.get_search_text()
        options = self._find_bar.get_options()
        
        if not self._find_bar.isVisible():
            return
            
        if not text:
            self._search_controller.clear_highlights()
            self._find_bar.set_search_result(self._search_controller.get_result())
            return

        try:
            result = self._search_controller.search(text, options)
            self._find_bar.set_search_result(result)
        except re.error as e:
            self._find_bar.set_error(f"Invalid regex: {e}")
        except Exception as e:
            self._find_bar.set_error(f"Search error: {e}")

    def _highlight_current_search_match(self) -> None:
        """Update current highlight and scroll to match."""
        result = self._search_controller.get_result()
        match = result.current_match
        if match:
            # We use the internal _goto_match of controller which handles
            # focus, scrolling and current highlight state for highlighters.
            self._search_controller._goto_match(match)
    
    @pyqtSlot()
    def _on_cursor_changed(self) -> None:
        """Handle cursor position change."""
        editor = self.sender()
        if editor:
            cursor = editor.textCursor()
            line = cursor.blockNumber() + 1
            column = cursor.columnNumber() + 1
            self.position_changed.emit(line, column)
            self._current_active_line_number = line # Store the current line number
    
    @pyqtSlot(float)
    def _on_overview_clicked(self, position: float) -> None:
        """Handle overview bar click."""
        # Scroll to the clicked position
        scrollbar = self._left_editor.verticalScrollBar()
        max_scroll = scrollbar.maximum()
        scrollbar.setValue(int(position * max_scroll))

    def refresh_style(self) -> None:
        """Refresh the view's style based on current theme."""
        from app.services.settings import SettingsManager
        settings = SettingsManager().settings
        theme = settings.ui.theme
        
        # Update diff colors
        self._diff_colors.reset_to_theme(theme)
        
        # Notify editors
        self._left_editor.set_colors(self._diff_colors)
        self._right_editor.set_colors(self._diff_colors)
        self._unified_view.set_colors(self._diff_colors)
        
        # Force redraw of overlays
        if hasattr(self, '_overview_bar'):
            self._overview_bar.update()
        if hasattr(self, '_legend'):
            self._legend.update_colors(self._diff_colors)
