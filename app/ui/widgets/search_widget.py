"""
Search widget for finding and replacing text in comparison views.

Provides:
- Find functionality with various options
- Find and replace
- Search history
- Match highlighting
- Navigation between matches
- Regular expression support
- Search in specific panels
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Callable, List, Tuple

from PyQt6.QtCore import (
    Qt, pyqtSignal, pyqtSlot, QTimer, QSize, QRegularExpression,
    QSettings, QPoint
)
from PyQt6.QtGui import (
    QFont, QColor, QTextDocument, QTextCursor, QTextCharFormat,
    QKeySequence, QAction, QShortcut, QPainter, QPalette,
    QSyntaxHighlighter, QIcon, QKeyEvent
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QLabel, QCheckBox, QComboBox, QToolButton, QFrame,
    QPlainTextEdit, QTextEdit, QMenu, QCompleter,
    QSizePolicy, QApplication, QStyle, QMessageBox,
    QButtonGroup, QRadioButton, QGroupBox, QGridLayout,
    QSpinBox
)

from app.ui.widgets.diff_text_edit import DiffColors # Import DiffColors


class SearchDirection(Enum):
    """Direction for search."""
    FORWARD = auto()
    BACKWARD = auto()


class SearchScope(Enum):
    """Scope for search operation."""
    ALL = auto()           # Search in all panels
    LEFT = auto()          # Search in left panel only
    RIGHT = auto()         # Search in right panel only
    MERGED = auto()        # Search in merged panel only
    SELECTION = auto()     # Search in current selection
    CURRENT = auto()       # Search in currently focused panel


class SearchMode(Enum):
    """Search mode."""
    NORMAL = auto()        # Normal text search
    REGEX = auto()         # Regular expression
    WILDCARD = auto()      # Wildcard pattern (*, ?)


@dataclass
class SearchOptions:
    """Options for search operation."""
    case_sensitive: bool = False
    whole_word: bool = False
    regex: bool = False
    wrap_around: bool = True
    incremental: bool = True
    highlight_all: bool = True
    search_scope: SearchScope = SearchScope.ALL
    
    def to_find_flags(self) -> QTextDocument.FindFlag:
        """Convert to Qt find flags."""
        flags = QTextDocument.FindFlag(0)
        
        if self.case_sensitive:
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if self.whole_word:
            flags |= QTextDocument.FindFlag.FindWholeWords
        
        return flags


@dataclass
class SearchMatch:
    """Represents a search match."""
    start: int              # Start position in document
    end: int                # End position
    line: int               # Line number (1-indexed)
    column: int             # Column number (1-indexed)
    text: str               # Matched text
    panel: str = ""         # Which panel ('left', 'right', 'merged')
    
    @property
    def length(self) -> int:
        return self.end - self.start


@dataclass
class SearchResult:
    """Result of a search operation."""
    matches: List[SearchMatch] = field(default_factory=list)
    current_index: int = -1
    search_term: str = ""
    
    @property
    def count(self) -> int:
        return len(self.matches)
    
    @property
    def has_matches(self) -> bool:
        return len(self.matches) > 0
    
    @property
    def current_match(self) -> Optional[SearchMatch]:
        if 0 <= self.current_index < len(self.matches):
            return self.matches[self.current_index]
        return None
    
    def next_index(self, wrap: bool = True) -> int:
        """Get next match index."""
        if not self.matches:
            return -1
        
        next_idx = self.current_index + 1
        if next_idx >= len(self.matches):
            return 0 if wrap else len(self.matches) - 1
        return next_idx
    
    def prev_index(self, wrap: bool = True) -> int:
        """Get previous match index."""
        if not self.matches:
            return -1
        
        prev_idx = self.current_index - 1
        if prev_idx < 0:
            return len(self.matches) - 1 if wrap else 0
        return prev_idx


class SearchHistory:
    """Manages search history."""
    
    MAX_HISTORY = 20
    
    def __init__(self, settings_key: str = "search_history"):
        self._history: List[str] = []
        self._settings_key = settings_key
        self._load()
    
    def add(self, term: str) -> None:
        """Add a term to history."""
        if not term:
            return
        
        # Remove if already exists
        if term in self._history:
            self._history.remove(term)
        
        # Add to front
        self._history.insert(0, term)
        
        # Trim to max
        self._history = self._history[:self.MAX_HISTORY]
        
        self._save()
    
    def get_all(self) -> List[str]:
        """Get all history items."""
        return self._history.copy()
    
    def clear(self) -> None:
        """Clear history."""
        self._history.clear()
        self._save()
    
    def _load(self) -> None:
        """Load history from settings."""
        settings = QSettings()
        self._history = settings.value(self._settings_key, [], type=list)
    
    def _save(self) -> None:
        """Save history to settings."""
        settings = QSettings()
        settings.setValue(self._settings_key, self._history)


class SearchLineEdit(QLineEdit):
    """
    Enhanced line edit for search input.
    
    Features:
    - Search history dropdown
    - Clear button
    - Visual feedback for matches
    - Keyboard shortcuts
    """
    
    # Signal when search should be triggered
    search_requested = pyqtSignal(str)
    
    # Signal for navigation
    next_requested = pyqtSignal()
    prev_requested = pyqtSignal()
    
    # Signal when escape is pressed
    escape_pressed = pyqtSignal()
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self._history = SearchHistory()
        self._match_count = 0
        self._current_match = 0
        self._has_error = False
        
        self._setup_ui()
        self._setup_completer()
    
    def _setup_ui(self) -> None:
        """Setup the widget."""
        self.setPlaceholderText("Search...")
        self.setClearButtonEnabled(True)
        self.setMinimumWidth(200)
        
        # Style
        self._update_style()
        
        # Connect signals
        self.textChanged.connect(self._on_text_changed)
        self.returnPressed.connect(self._on_return_pressed)
    
    def _setup_completer(self) -> None:
        """Setup history completer."""
        from PyQt6.QtCore import QStringListModel
        
        self._completer = QCompleter(self)
        self._completer_model = QStringListModel()
        self._completer.setModel(self._completer_model)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setCompleter(self._completer)
        
        self._update_completer()
    
    def _update_completer(self) -> None:
        """Update completer with history."""
        self._completer_model.setStringList(self._history.get_all())
    
    def _update_style(self) -> None:
        """Update style based on state."""
        if self._has_error:
            self.setStyleSheet("""
                QLineEdit {
                    background-color: #ffe0e0;
                    border: 1px solid #ff6666;
                }
            """)
        elif self._match_count > 0:
            self.setStyleSheet("""
                QLineEdit {
                    background-color: #e0ffe0;
                    border: 1px solid #66cc66;
                }
            """)
        elif self.text() and self._match_count == 0:
            self.setStyleSheet("""
                QLineEdit {
                    background-color: #fff0e0;
                    border: 1px solid #ffaa66;
                }
            """)
        else:
            self.setStyleSheet("")
    
    def set_match_info(self, current: int, total: int) -> None:
        """Set match information for display."""
        self._current_match = current
        self._match_count = total
        self._has_error = False
        self._update_style()
    
    def set_error(self, has_error: bool) -> None:
        """Set error state (e.g., invalid regex)."""
        self._has_error = has_error
        self._update_style()
    
    def add_to_history(self) -> None:
        """Add current text to history."""
        text = self.text()
        if text:
            self._history.add(text)
            self._update_completer()
    
    def clear_history(self) -> None:
        """Clear search history."""
        self._history.clear()
        self._update_completer()
    
    def _on_text_changed(self, text: str) -> None:
        """Handle text changes."""
        self._has_error = False
        self._update_style()
        self.search_requested.emit(text)
    
    def _on_return_pressed(self) -> None:
        """Handle return key."""
        self.add_to_history()
        self.next_requested.emit()
    
    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle key events."""
        if event.key() == Qt.Key.Key_Escape:
            self.escape_pressed.emit()
            return
        
        if event.key() == Qt.Key.Key_F3:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.prev_requested.emit()
            else:
                self.next_requested.emit()
            return
        
        if event.key() == Qt.Key.Key_Return:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.add_to_history()
                self.prev_requested.emit()
                return
        
        super().keyPressEvent(event)


class SearchWidget(QFrame):
    """
    Compact search bar widget.
    
    Features:
    - Find text input
    - Next/Previous buttons
    - Match counter
    - Options toggles
    - Close button
    """
    
    # Signal when search term changes
    search_changed = pyqtSignal(str, object)  # (term, SearchOptions)
    
    # Signal for navigation
    find_next = pyqtSignal()
    find_prev = pyqtSignal()
    
    # Signal when widget should be hidden
    close_requested = pyqtSignal()
    
    # Signal when all matches should be highlighted
    highlight_all_requested = pyqtSignal(str, object)  # (term, SearchOptions)
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self._options = SearchOptions()
        self._result = SearchResult()
        
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self) -> None:
        """Setup the widget UI."""
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setAutoFillBackground(True)
        
        # Set background
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(250, 250, 250))
        self.setPalette(palette)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)
        
        # Search icon/label
        search_label = QLabel("🔍")
        layout.addWidget(search_label)
        
        # Search input
        self.search_input = SearchLineEdit()
        self.search_input.setMinimumWidth(250)
        layout.addWidget(self.search_input)
        
        # Match counter
        self.match_label = QLabel()
        self.match_label.setMinimumWidth(80)
        self.match_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.match_label)
        
        # Navigation buttons
        self.prev_btn = QToolButton()
        self.prev_btn.setText("▲")
        self.prev_btn.setToolTip("Previous match (Shift+F3)")
        self.prev_btn.setAutoRaise(True)
        layout.addWidget(self.prev_btn)
        
        self.next_btn = QToolButton()
        self.next_btn.setText("▼")
        self.next_btn.setToolTip("Next match (F3)")
        self.next_btn.setAutoRaise(True)
        layout.addWidget(self.next_btn)
        
        layout.addSpacing(10)
        
        # Options
        self.case_btn = QToolButton()
        self.case_btn.setText("Aa")
        self.case_btn.setToolTip("Match case")
        self.case_btn.setCheckable(True)
        self.case_btn.setAutoRaise(True)
        layout.addWidget(self.case_btn)
        
        self.word_btn = QToolButton()
        self.word_btn.setText("W")
        self.word_btn.setToolTip("Whole word")
        self.word_btn.setCheckable(True)
        self.word_btn.setAutoRaise(True)
        layout.addWidget(self.word_btn)
        
        self.regex_btn = QToolButton()
        self.regex_btn.setText(".*")
        self.regex_btn.setToolTip("Regular expression")
        self.regex_btn.setCheckable(True)
        self.regex_btn.setAutoRaise(True)
        layout.addWidget(self.regex_btn)
        
        layout.addStretch()
        
        # Close button
        self.close_btn = QToolButton()
        self.close_btn.setText("✕")
        self.close_btn.setToolTip("Close (Escape)")
        self.close_btn.setAutoRaise(True)
        layout.addWidget(self.close_btn)
        
        self._update_match_label()
    
    def _connect_signals(self) -> None:
        """Connect widget signals."""
        # Search input
        self.search_input.search_requested.connect(self._on_search_changed)
        self.search_input.next_requested.connect(self.find_next.emit)
        self.search_input.prev_requested.connect(self.find_prev.emit)
        self.search_input.escape_pressed.connect(self.close_requested.emit)
        
        # Navigation
        self.next_btn.clicked.connect(self.find_next.emit)
        self.prev_btn.clicked.connect(self.find_prev.emit)
        
        # Options
        self.case_btn.toggled.connect(self._on_option_changed)
        self.word_btn.toggled.connect(self._on_option_changed)
        self.regex_btn.toggled.connect(self._on_option_changed)
        
        # Close
        self.close_btn.clicked.connect(self.close_requested.emit)
    
    def _on_search_changed(self, text: str) -> None:
        """Handle search text change."""
        self._update_options()
        self.search_changed.emit(text, self._options)
    
    def _on_option_changed(self) -> None:
        """Handle option toggle."""
        self._update_options()
        
        text = self.search_input.text()
        if text:
            self.search_changed.emit(text, self._options)
    
    def _update_options(self) -> None:
        """Update options from UI state."""
        self._options.case_sensitive = self.case_btn.isChecked()
        self._options.whole_word = self.word_btn.isChecked()
        self._options.regex = self.regex_btn.isChecked()
    
    def _update_match_label(self) -> None:
        """Update the match counter label."""
        if not self.search_input.text():
            self.match_label.setText("")
            self.match_label.setStyleSheet("")
        elif self._result.count == 0:
            self.match_label.setText("No matches")
            self.match_label.setStyleSheet("color: #cc6600;")
        else:
            current = self._result.current_index + 1 if self._result.current_index >= 0 else 0
            self.match_label.setText(f"{current} of {self._result.count}")
            self.match_label.setStyleSheet("color: #006600;")
        
        # Update input styling
        self.search_input.set_match_info(
            self._result.current_index + 1 if self._result.current_index >= 0 else 0,
            self._result.count
        )
    
    def set_search_result(self, result: SearchResult) -> None:
        """Set the search result for display."""
        self._result = result
        self._update_match_label()
    
    def set_error(self, message: str) -> None:
        """Display an error (e.g., invalid regex)."""
        self.match_label.setText(message)
        self.match_label.setStyleSheet("color: #cc0000;")
        self.search_input.set_error(True)
    
    def get_search_text(self) -> str:
        """Get current search text."""
        return self.search_input.text()
    
    def get_options(self) -> SearchOptions:
        """Get current search options."""
        return self._options
    
    def set_search_text(self, text: str) -> None:
        """Set the search text."""
        self.search_input.setText(text)
    
    def focus_search(self) -> None:
        """Focus the search input and select all."""
        self.search_input.setFocus()
        self.search_input.selectAll()
    
    def showEvent(self, event) -> None:
        """Handle show event."""
        super().showEvent(event)
        self.focus_search()
    
    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle key events."""
        if event.key() == Qt.Key.Key_Escape:
            self.close_requested.emit()
            return
        
        super().keyPressEvent(event)


class FindReplaceWidget(QFrame):
    """
    Full find and replace widget.
    
    Features:
    - Find functionality
    - Replace functionality
    - Replace all
    - Search scope options
    - Advanced options
    """
    
    # Signals
    search_changed = pyqtSignal(str, object)  # (term, SearchOptions)
    find_next = pyqtSignal()
    find_prev = pyqtSignal()
    replace_requested = pyqtSignal(str)  # replacement text
    replace_all_requested = pyqtSignal(str, str, object)  # (find, replace, options)
    close_requested = pyqtSignal()
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self._options = SearchOptions()
        self._result = SearchResult()
        self._expanded = False
        
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self) -> None:
        """Setup the widget UI."""
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setAutoFillBackground(True)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)
        
        # Find row
        find_layout = QHBoxLayout()
        
        find_label = QLabel("Find:")
        find_label.setMinimumWidth(60)
        find_layout.addWidget(find_label)
        
        self.find_input = SearchLineEdit()
        self.find_input.setMinimumWidth(300)
        find_layout.addWidget(self.find_input)
        
        # Navigation
        self.prev_btn = QPushButton("◀")
        self.prev_btn.setFixedWidth(30)
        self.prev_btn.setToolTip("Previous (Shift+F3)")
        find_layout.addWidget(self.prev_btn)
        
        self.next_btn = QPushButton("▶")
        self.next_btn.setFixedWidth(30)
        self.next_btn.setToolTip("Next (F3)")
        find_layout.addWidget(self.next_btn)
        
        self.match_label = QLabel()
        self.match_label.setMinimumWidth(80)
        find_layout.addWidget(self.match_label)
        
        find_layout.addStretch()
        
        # Close button
        self.close_btn = QToolButton()
        self.close_btn.setText("✕")
        self.close_btn.setAutoRaise(True)
        find_layout.addWidget(self.close_btn)
        
        main_layout.addLayout(find_layout)
        
        # Replace row
        self.replace_widget = QWidget()
        replace_layout = QHBoxLayout(self.replace_widget)
        replace_layout.setContentsMargins(0, 0, 0, 0)
        
        replace_label = QLabel("Replace:")
        replace_label.setMinimumWidth(60)
        replace_layout.addWidget(replace_label)
        
        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("Replace with...")
        replace_layout.addWidget(self.replace_input)
        
        self.replace_btn = QPushButton("Replace")
        self.replace_btn.setToolTip("Replace current match")
        replace_layout.addWidget(self.replace_btn)
        
        self.replace_all_btn = QPushButton("Replace All")
        self.replace_all_btn.setToolTip("Replace all matches")
        replace_layout.addWidget(self.replace_all_btn)
        
        replace_layout.addStretch()
        
        main_layout.addWidget(self.replace_widget)
        
        # Options row
        options_layout = QHBoxLayout()
        
        self.case_check = QCheckBox("Match case")
        options_layout.addWidget(self.case_check)
        
        self.word_check = QCheckBox("Whole word")
        options_layout.addWidget(self.word_check)
        
        self.regex_check = QCheckBox("Regex")
        options_layout.addWidget(self.regex_check)
        
        self.wrap_check = QCheckBox("Wrap around")
        self.wrap_check.setChecked(True)
        options_layout.addWidget(self.wrap_check)
        
        options_layout.addStretch()
        
        # Scope
        options_layout.addWidget(QLabel("In:"))
        self.scope_combo = QComboBox()
        self.scope_combo.addItems(["All", "Left only", "Right only", "Selection"])
        options_layout.addWidget(self.scope_combo)
        
        main_layout.addLayout(options_layout)
        
        # Toggle button for expand/collapse
        self.toggle_btn = QPushButton("▼ More options")
        self.toggle_btn.setFlat(True)
        self.toggle_btn.setStyleSheet("text-align: left;")
        main_layout.addWidget(self.toggle_btn)
        
        # Advanced options (hidden by default)
        self.advanced_widget = QWidget()
        self.advanced_widget.setVisible(False)
        advanced_layout = QVBoxLayout(self.advanced_widget)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        
        self.highlight_check = QCheckBox("Highlight all matches")
        self.highlight_check.setChecked(True)
        advanced_layout.addWidget(self.highlight_check)
        
        self.incremental_check = QCheckBox("Search as you type")
        self.incremental_check.setChecked(True)
        advanced_layout.addWidget(self.incremental_check)
        
        self.preserve_case_check = QCheckBox("Preserve case when replacing")
        advanced_layout.addWidget(self.preserve_case_check)
        
        main_layout.addWidget(self.advanced_widget)
        
        self._update_match_label()
    
    def _connect_signals(self) -> None:
        """Connect signals."""
        # Find
        self.find_input.search_requested.connect(self._on_search_changed)
        self.find_input.next_requested.connect(self.find_next.emit)
        self.find_input.prev_requested.connect(self.find_prev.emit)
        self.find_input.escape_pressed.connect(self.close_requested.emit)
        
        # Navigation
        self.next_btn.clicked.connect(self.find_next.emit)
        self.prev_btn.clicked.connect(self.find_prev.emit)
        
        # Replace
        self.replace_btn.clicked.connect(self._on_replace)
        self.replace_all_btn.clicked.connect(self._on_replace_all)
        
        # Options
        self.case_check.toggled.connect(self._on_option_changed)
        self.word_check.toggled.connect(self._on_option_changed)
        self.regex_check.toggled.connect(self._on_option_changed)
        self.wrap_check.toggled.connect(self._on_option_changed)
        self.scope_combo.currentIndexChanged.connect(self._on_option_changed)
        
        # Toggle
        self.toggle_btn.clicked.connect(self._toggle_advanced)
        
        # Close
        self.close_btn.clicked.connect(self.close_requested.emit)
    
    def _on_search_changed(self, text: str) -> None:
        """Handle search text change."""
        if self.incremental_check.isChecked() or not text:
            self._update_options()
            self.search_changed.emit(text, self._options)
    
    def _on_option_changed(self) -> None:
        """Handle option change."""
        self._update_options()
        
        text = self.find_input.text()
        if text:
            self.search_changed.emit(text, self._options)
    
    def _on_replace(self) -> None:
        """Handle replace button."""
        self.find_input.add_to_history()
        self.replace_requested.emit(self.replace_input.text())
    
    def _on_replace_all(self) -> None:
        """Handle replace all button."""
        find_text = self.find_input.text()
        replace_text = self.replace_input.text()
        
        if not find_text:
            return
        
        self.find_input.add_to_history()
        self._update_options()
        
        self.replace_all_requested.emit(find_text, replace_text, self._options)
    
    def _toggle_advanced(self) -> None:
        """Toggle advanced options visibility."""
        self._expanded = not self._expanded
        self.advanced_widget.setVisible(self._expanded)
        self.toggle_btn.setText("▲ Fewer options" if self._expanded else "▼ More options")
    
    def _update_options(self) -> None:
        """Update options from UI."""
        self._options.case_sensitive = self.case_check.isChecked()
        self._options.whole_word = self.word_check.isChecked()
        self._options.regex = self.regex_check.isChecked()
        self._options.wrap_around = self.wrap_check.isChecked()
        self._options.highlight_all = self.highlight_check.isChecked()
        self._options.incremental = self.incremental_check.isChecked()
        
        # Scope
        scope_map = {
            0: SearchScope.ALL,
            1: SearchScope.LEFT,
            2: SearchScope.RIGHT,
            3: SearchScope.SELECTION,
        }
        self._options.search_scope = scope_map.get(
            self.scope_combo.currentIndex(),
            SearchScope.ALL
        )
    
    def _update_match_label(self) -> None:
        """Update match counter."""
        if not self.find_input.text():
            self.match_label.setText("")
        elif self._result.count == 0:
            self.match_label.setText("No matches")
            self.match_label.setStyleSheet("color: #cc6600;")
        else:
            current = self._result.current_index + 1 if self._result.current_index >= 0 else 0
            self.match_label.setText(f"{current}/{self._result.count}")
            self.match_label.setStyleSheet("color: #006600;")
        
        self.find_input.set_match_info(
            self._result.current_index + 1 if self._result.current_index >= 0 else 0,
            self._result.count
        )
    
    def set_search_result(self, result: SearchResult) -> None:
        """Set search result."""
        self._result = result
        self._update_match_label()
    
    def set_error(self, message: str) -> None:
        """Display error."""
        self.match_label.setText(message)
        self.match_label.setStyleSheet("color: #cc0000;")
        self.find_input.set_error(True)
    
    def get_find_text(self) -> str:
        """Get find text."""
        return self.find_input.text()
    
    def get_replace_text(self) -> str:
        """Get replace text."""
        return self.replace_input.text()
    
    def get_options(self) -> SearchOptions:
        """Get search options."""
        return self._options
    
    def set_find_text(self, text: str) -> None:
        """Set find text."""
        self.find_input.setText(text)
    
    def focus_find(self) -> None:
        """Focus find input."""
        self.find_input.setFocus()
        self.find_input.selectAll()
    
    def focus_replace(self) -> None:
        """Focus replace input."""
        self.replace_input.setFocus()
        self.replace_input.selectAll()
    
    def set_replace_visible(self, visible: bool) -> None:
        """Show/hide replace functionality."""
        self.replace_widget.setVisible(visible)
    
    def showEvent(self, event) -> None:
        """Handle show."""
        super().showEvent(event)
        self.focus_find()


class SearchEngine:
    """
    Search engine for text documents.
    
    Provides search functionality with various options.
    """
    
    def __init__(self):
        self._last_result = SearchResult()
    
    def search(
        self,
        document: QTextDocument,
        term: str,
        options: SearchOptions,
        start_pos: int = 0
    ) -> SearchResult:
        """
        Search a document for a term.
        
        Args:
            document: Document to search
            term: Search term
            options: Search options
            start_pos: Position to start from
            
        Returns:
            SearchResult with all matches
        """
        if not term:
            return SearchResult()
        
        matches: List[SearchMatch] = []
        
        if options.regex:
            matches = self._search_regex(document, term, options)
        else:
            matches = self._search_text(document, term, options)
        
        # Find current index based on start position
        current_index = 0
        for i, match in enumerate(matches):
            if match.start >= start_pos:
                current_index = i
                break
        
        result = SearchResult(
            matches=matches,
            current_index=current_index if matches else -1,
            search_term=term
        )
        
        self._last_result = result
        return result
    
    def _search_text(
        self,
        document: QTextDocument,
        term: str,
        options: SearchOptions
    ) -> List[SearchMatch]:
        """Search using plain text."""
        matches = []
        
        flags = options.to_find_flags()
        cursor = QTextCursor(document)
        
        while True:
            cursor = document.find(term, cursor, flags)
            
            if cursor.isNull():
                break
            
            # Get match info
            start = cursor.selectionStart()
            end = cursor.selectionEnd()
            
            # Get line and column
            block = document.findBlock(start)
            line = block.blockNumber() + 1
            column = start - block.position() + 1
            
            matches.append(SearchMatch(
                start=start,
                end=end,
                line=line,
                column=column,
                text=cursor.selectedText()
            ))
        
        return matches
    
    def _search_regex(
        self,
        document: QTextDocument,
        pattern: str,
        options: SearchOptions
    ) -> List[SearchMatch]:
        """Search using regular expression."""
        matches = []
        
        # Build regex
        flags = 0
        if not options.case_sensitive:
            flags |= re.IGNORECASE
        
        try:
            regex = re.compile(pattern, flags)
        except re.error:
            return []
        
        text = document.toPlainText()
        
        for match in regex.finditer(text):
            start = match.start()
            end = match.end()
            
            # Get line and column
            block = document.findBlock(start)
            line = block.blockNumber() + 1
            column = start - block.position() + 1
            
            matches.append(SearchMatch(
                start=start,
                end=end,
                line=line,
                column=column,
                text=match.group()
            ))
        
        return matches
    
    def find_next(
        self,
        document: QTextDocument,
        current_pos: int,
        options: SearchOptions
    ) -> Optional[SearchMatch]:
        """Find next match from current position."""
        if not self._last_result.has_matches:
            return None
        
        # Find next match after current position
        for match in self._last_result.matches:
            if match.start > current_pos:
                return match
        
        # Wrap around
        if options.wrap_around and self._last_result.matches:
            return self._last_result.matches[0]
        
        return None
    
    def find_prev(
        self,
        document: QTextDocument,
        current_pos: int,
        options: SearchOptions
    ) -> Optional[SearchMatch]:
        """Find previous match from current position."""
        if not self._last_result.has_matches:
            return None
        
        # Find previous match before current position
        for match in reversed(self._last_result.matches):
            if match.end < current_pos:
                return match
        
        # Wrap around
        if options.wrap_around and self._last_result.matches:
            return self._last_result.matches[-1]
        
        return None
    
    def replace(
        self,
        document: QTextDocument,
        match: SearchMatch,
        replacement: str,
        options: SearchOptions
    ) -> bool:
        """
        Replace a match with replacement text.
        
        Returns True if replacement was made.
        """
        cursor = QTextCursor(document)
        cursor.setPosition(match.start)
        cursor.setPosition(match.end, QTextCursor.MoveMode.KeepAnchor)
        
        # Handle regex replacement
        if options.regex:
            try:
                regex = re.compile(self._last_result.search_term)
                actual_replacement = regex.sub(replacement, match.text)
                cursor.insertText(actual_replacement)
            except re.error:
                cursor.insertText(replacement)
        else:
            cursor.insertText(replacement)
        
        return True
    
    def replace_all(
        self,
        document: QTextDocument,
        find_term: str,
        replacement: str,
        options: SearchOptions
    ) -> int:
        """
        Replace all matches.
        
        Returns number of replacements made.
        """
        # Search first
        result = self.search(document, find_term, options)
        
        if not result.has_matches:
            return 0
        
        # Replace in reverse order to maintain positions
        cursor = QTextCursor(document)
        cursor.beginEditBlock()
        
        count = 0
        for match in reversed(result.matches):
            cursor.setPosition(match.start)
            cursor.setPosition(match.end, QTextCursor.MoveMode.KeepAnchor)
            
            if options.regex:
                try:
                    regex = re.compile(find_term)
                    actual_replacement = regex.sub(replacement, match.text)
                    cursor.insertText(actual_replacement)
                except re.error:
                    cursor.insertText(replacement)
            else:
                cursor.insertText(replacement)
            
            count += 1
        
        cursor.endEditBlock()
        
        return count


class MatchHighlighter(QSyntaxHighlighter):
    """
    Syntax highlighter for search matches.
    
    Highlights all occurrences of search term.
    """
    
    def __init__(self, parent: QTextDocument, colors: DiffColors):
        super().__init__(parent)
        
        self._search_term = ""
        self._options = SearchOptions()
        self._current_match: Optional[SearchMatch] = None
        self._colors = colors # Store DiffColors
        
        # Highlight formats
        self._match_format = QTextCharFormat()
        self._match_format.setBackground(self._colors.search_match_bg)
        self._match_format.setForeground(QColor(0, 0, 0)) # Still hardcoded for foreground, can be added to DiffColors if needed
        
        self._current_format = QTextCharFormat()
        self._current_format.setBackground(self._colors.search_current_match_bg)
        self._current_format.setForeground(QColor(0, 0, 0)) # Still hardcoded for foreground
    
    def set_search_term(self, term: str, options: SearchOptions) -> None:
        """Set the term to highlight."""
        self._search_term = term
        self._options = options
        self.rehighlight()
    
    def set_current_match(self, match: Optional[SearchMatch]) -> None:
        """Set the current match for special highlighting."""
        self._current_match = match
        self.rehighlight()
    
    def clear_highlights(self) -> None:
        """Clear all highlights."""
        self._search_term = ""
        self._current_match = None
        self.rehighlight()
    
    def highlightBlock(self, text: str) -> None:
        """Highlight matches in a block of text."""
        if not self._search_term:
            return
        
        if self._options.regex:
            self._highlight_regex(text)
        else:
            self._highlight_text(text)
    
    def _highlight_text(self, text: str) -> None:
        """Highlight plain text matches."""
        term = self._search_term
        
        if not self._options.case_sensitive:
            text_lower = text.lower()
            term_lower = term.lower()
        else:
            text_lower = text
            term_lower = term
        
        start = 0
        while True:
            index = text_lower.find(term_lower, start)
            if index == -1:
                break
            
            # Check whole word
            if self._options.whole_word:
                if not self._is_whole_word(text, index, len(term)):
                    start = index + 1
                    continue
            
            # Determine format
            block_start = self.currentBlock().position()
            abs_start = block_start + index
            
            if (self._current_match and 
                self._current_match.start == abs_start):
                format = self._current_format
            else:
                format = self._match_format
            
            self.setFormat(index, len(term), format)
            start = index + len(term)
    
    def _highlight_regex(self, text: str) -> None:
        """Highlight regex matches."""
        flags = 0
        if not self._options.case_sensitive:
            flags |= re.IGNORECASE
        
        try:
            regex = re.compile(self._search_term, flags)
        except re.error:
            return
        
        block_start = self.currentBlock().position()
        
        for match in regex.finditer(text):
            abs_start = block_start + match.start()
            
            if (self._current_match and 
                self._current_match.start == abs_start):
                format = self._current_format
            else:
                format = self._match_format
            
            self.setFormat(match.start(), match.end() - match.start(), format)
    
    def _is_whole_word(self, text: str, index: int, length: int) -> bool:
        """Check if match is a whole word."""
        # Check character before
        if index > 0:
            char_before = text[index - 1]
            if char_before.isalnum() or char_before == '_':
                return False
        
        # Check character after
        end = index + length
        if end < len(text):
            char_after = text[end]
            if char_after.isalnum() or char_after == '_':
                return False
        
        return True


from PyQt6.QtCore import (
    Qt, pyqtSignal, pyqtSlot, QTimer, QSize, QRegularExpression,
    QSettings, QPoint, QObject, QThreadPool, QRunnable
)

# ... (Previous imports)

class SearchWorkerSignals(QObject):
    """Signals for SearchWorker."""
    finished = pyqtSignal(object)  # Returns list of (start, end, text) tuples
    error = pyqtSignal(str)

class SearchWorker(QRunnable):
    """
    Worker for running regex searches in background.
    """
    def __init__(self, text: str, pattern: str, options: SearchOptions):
        super().__init__()
        self.text = text
        self.pattern = pattern
        self.options = options
        self.signals = SearchWorkerSignals()
    
    def run(self):
        try:
            matches = []
            flags = 0
            if not self.options.case_sensitive:
                flags |= re.IGNORECASE
            
            # Simple timeout mechanism using a loop if possible, 
            # but standard re.finditer blocks. 
            # We rely on the fact that we are in a separate thread so UI doesn't freeze.
            # A true "timeout" to kill the thread is hard in Python without processes.
            # However, unblocking the UI is the primary goal of ReDoS protection in desktop apps.
            
            regex = re.compile(self.pattern, flags)
            
            # Limit number of matches to prevent OOM on massive match counts
            MAX_MATCHES = 10000 
            count = 0
            
            for match in regex.finditer(self.text):
                matches.append((match.start(), match.end(), match.group()))
                count += 1
                if count >= MAX_MATCHES:
                    break
            
            self.signals.finished.emit(matches)
            
        except re.error as e:
            self.signals.error.emit(str(e))
        except Exception as e:
            self.signals.error.emit(str(e))

class SearchController(QObject): # Inherit QObject for signals
    """
    Controller for managing search across multiple text widgets.
    
    Coordinates search between different panels.
    """
    search_finished = pyqtSignal(SearchResult) # New signal
    search_error = pyqtSignal(str) # New signal

    def __init__(self, colors: DiffColors):
        super().__init__()
        self._engine = SearchEngine()
        self._widgets: dict[str, QPlainTextEdit] = {}
        self._highlighters: dict[str, MatchHighlighter] = {}
        self._current_result = SearchResult()
        self._current_widget: Optional[str] = None
        self._colors = colors 
        self._thread_pool = QThreadPool()
    
    def register_widget(self, name: str, widget: QPlainTextEdit) -> None:
        """Register a text widget for searching."""
        self._widgets[name] = widget
        self._highlighters[name] = MatchHighlighter(widget.document(), self._colors)
    
    def unregister_widget(self, name: str) -> None:
        """Unregister a text widget."""
        if name in self._widgets:
            del self._widgets[name]
        if name in self._highlighters:
            self._highlighters[name].setDocument(None)
            del self._highlighters[name]
    
    def search(
        self,
        term: str,
        options: SearchOptions,
        widget_name: Optional[str] = None
    ) -> None: # Changed return to None (async)
        """
        Perform search across registered widgets.
        """
        if not term:
            self.clear_highlights()
            self.search_finished.emit(SearchResult())
            return

        # If it's a simple text search, run synchronously (fast enough)
        if not options.regex:
            result = self._search_sync(term, options, widget_name)
            self.search_finished.emit(result)
            return
            
        # For regex, use worker
        # We need to collect text from all widgets
        widgets_to_search = (
            {widget_name: self._widgets[widget_name]}
            if widget_name and widget_name in self._widgets
            else self._widgets
        )
        
        # Dispatch a worker for EACH widget? Or one big text?
        # Simplest is one worker per widget, then combine. 
        # But handling multiple async returns is complex.
        # Let's do a simplified approach: Search is usually fast. 
        # ReDoS hangs. We just need to NOT hang the UI.
        
        # We will dispatch sequentially or just handle the first one for now 
        # to keep it simple, OR we run one worker that handles the loop over widgets (using text copies).
        
        combined_text_data = [] # list of (name, text)
        for name, widget in widgets_to_search.items():
            combined_text_data.append((name, widget.toPlainText()))
            
        worker = CombinedSearchWorker(combined_text_data, term, options)
        worker.signals.finished.connect(self._on_search_worker_finished)
        worker.signals.error.connect(self._on_search_worker_error)
        self._thread_pool.start(worker)

    def _search_sync(self, term, options, widget_name) -> SearchResult:
        """Original synchronous search logic (refactored)."""
        all_matches: List[SearchMatch] = []
        
        widgets_to_search = (
            {widget_name: self._widgets[widget_name]}
            if widget_name and widget_name in self._widgets
            else self._widgets
        )
        
        for name, widget in widgets_to_search.items():
            document = widget.document()
            result = self._engine.search(document, term, options)
            for match in result.matches:
                match.panel = name
            all_matches.extend(result.matches)
            
            if name in self._highlighters:
                self._highlighters[name].set_search_term(term, options)
        
        self._current_result = SearchResult(
            matches=all_matches,
            current_index=0 if all_matches else -1,
            search_term=term
        )
        return self._current_result

    def _on_search_worker_finished(self, results):
        """Handle async search results: list of (name, matches_tuples)"""
        all_matches = []
        term = ""
        options = None

        for name, match_tuples, term_in, options_in in results:
            term = term_in
            options = options_in
            
            if name not in self._widgets: continue
            
            widget = self._widgets[name]
            document = widget.document()
            
            # Reconstruct SearchMatch objects mapped to document
            for start, end, text in match_tuples:
                 # Calculate line/col from document (must happen on main thread)
                block = document.findBlock(start)
                line = block.blockNumber() + 1
                column = start - block.position() + 1
                
                match = SearchMatch(
                    start=start,
                    end=end,
                    line=line,
                    column=column,
                    text=text,
                    panel=name
                )
                all_matches.append(match)
            
            # Update highlighter
            if name in self._highlighters:
                self._highlighters[name].set_search_term(term, options)

        self._current_result = SearchResult(
            matches=all_matches,
            current_index=0 if all_matches else -1,
            search_term=term
        )
        self.search_finished.emit(self._current_result)

    def _on_search_worker_error(self, error):
        self.search_error.emit(error)

    # ... (rest of methods: find_next, find_prev, etc. remain same)

class CombinedSearchWorker(QRunnable):
    """Worker to search multiple texts."""
    def __init__(self, text_data: list, pattern: str, options: SearchOptions):
        super().__init__()
        self.text_data = text_data # [(name, text), ...]
        self.pattern = pattern
        self.options = options
        self.signals = SearchWorkerSignals()

    def run(self):
        try:
            results = [] # [(name, match_tuples, term, options), ...]
            flags = 0
            if not self.options.case_sensitive:
                flags |= re.IGNORECASE
            
            regex = re.compile(self.pattern, flags)
            MAX_MATCHES = 10000
            
            for name, text in self.text_data:
                matches = []
                count = 0
                for match in regex.finditer(text):
                    matches.append((match.start(), match.end(), match.group()))
                    count += 1
                    if count >= MAX_MATCHES: break
                
                results.append((name, matches, self.pattern, self.options))
            
            self.signals.finished.emit(results)
        except Exception as e:
            self.signals.error.emit(str(e))

class SearchController_Old: # Kept for reference or removed? REMOVING.
    pass

# ... (Previous imports)

    
    def find_next(self, options: SearchOptions) -> Optional[SearchMatch]:
        """Find next match."""
        if not self._current_result.has_matches:
            return None
        
        next_idx = self._current_result.next_index(options.wrap_around)
        self._current_result.current_index = next_idx
        
        match = self._current_result.current_match
        if match:
            self._goto_match(match)
        
        return match
    
    def find_prev(self, options: SearchOptions) -> Optional[SearchMatch]:
        """Find previous match."""
        if not self._current_result.has_matches:
            return None
        
        prev_idx = self._current_result.prev_index(options.wrap_around)
        self._current_result.current_index = prev_idx
        
        match = self._current_result.current_match
        if match:
            self._goto_match(match)
        
        return match
    
    def _goto_match(self, match: SearchMatch) -> None:
        """Navigate to a match."""
        if match.panel in self._widgets:
            widget = self._widgets[match.panel]
            cursor = widget.textCursor()
            cursor.setPosition(match.start)
            cursor.setPosition(match.end, QTextCursor.MoveMode.KeepAnchor)
            widget.setTextCursor(cursor)
            widget.centerCursor()
            widget.setFocus()
            
            # Update current match highlight
            if match.panel in self._highlighters:
                self._highlighters[match.panel].set_current_match(match)
    
    def replace_current(self, replacement: str, options: SearchOptions) -> bool:
        """Replace current match."""
        match = self._current_result.current_match
        if not match or match.panel not in self._widgets:
            return False
        
        widget = self._widgets[match.panel]
        result = self._engine.replace(widget.document(), match, replacement, options)
        
        if result:
            # Re-search to update matches
            self.search(self._current_result.search_term, options)
        
        return result
    
    def replace_all(
        self,
        find_term: str,
        replacement: str,
        options: SearchOptions,
        widget_name: Optional[str] = None
    ) -> int:
        """Replace all matches."""
        total = 0
        
        widgets_to_search = (
            {widget_name: self._widgets[widget_name]}
            if widget_name and widget_name in self._widgets
            else self._widgets
        )
        
        for name, widget in widgets_to_search.items():
            count = self._engine.replace_all(
                widget.document(),
                find_term,
                replacement,
                options
            )
            total += count
        
        # Clear highlights
        self.clear_highlights()
        
        return total
    
    def clear_highlights(self) -> None:
        """Clear all search highlights."""
        for highlighter in self._highlighters.values():
            highlighter.clear_highlights()
        
        self._current_result = SearchResult()
    
    def get_result(self) -> SearchResult:
        """Get current search result."""
        return self._current_result