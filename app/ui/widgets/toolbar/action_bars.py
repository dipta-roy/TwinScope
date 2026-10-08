"""
Action bars, quick buttons, and ToolbarFactory for toolbar widgets.
"""

from __future__ import annotations

from typing import Dict, Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStyle,
    QToolBar,
    QToolButton,
    QWidget,
)

from app.ui.widgets.toolbar.indicators import (
    StatusIndicator,
)
from app.ui.widgets.toolbar.navigation import (
    NavigationButtons,
    ViewModeSelector,
)
from app.ui.widgets.toolbar.path_selector import PathSelectorButton
from app.ui.widgets.toolbar.selectors import (
    ToolbarSearchBox,
    ToolbarSeparator,
)


class CompareOptionsToolbar(QWidget):
    """
    Toolbar with comparison option toggles.
    
    Ignore whitespace, ignore case, ignore line endings, etc.
    """

    # Signal when options change
    options_changed = pyqtSignal(dict)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._options = {
            'ignore_whitespace': False,
            'ignore_case': False,
            'ignore_line_endings': True,
            'show_line_numbers': True,
        }

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup the widget."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._buttons: Dict[str, QToolButton] = {}

        options_info = [
            ('ignore_whitespace', '␣', 'Ignore whitespace differences'),
            ('ignore_case', 'Aa', 'Ignore case differences'),
            ('ignore_line_endings', '↵', 'Ignore line ending differences (CRLF/LF)'),
            ('show_line_numbers', '#', 'Show/hide line numbers'),
        ]

        for key, text, tooltip in options_info:
            btn = QToolButton()
            btn.setText(text)
            btn.setToolTip(tooltip)
            btn.setCheckable(True)
            btn.setChecked(self._options.get(key, False))
            btn.setAutoRaise(True)

            btn.toggled.connect(lambda checked, k=key: self._on_option_toggled(k, checked))

            self._buttons[key] = btn
            layout.addWidget(btn)

    def _on_option_toggled(self, key: str, checked: bool) -> None:
        """Handle option toggle."""
        self._options[key] = checked
        self.options_changed.emit(self._options.copy())

    def get_options(self) -> Dict[str, bool]:
        """Get current options."""
        return self._options.copy()

    def set_option(self, key: str, value: bool) -> None:
        """Set a single option."""
        if key in self._buttons:
            self._buttons[key].setChecked(value)
            self._options[key] = value

    def set_options(self, options: Dict[str, bool]) -> None:
        """Set multiple options."""
        for key, value in options.items():
            self.set_option(key, value)


class CompareButton(QPushButton):
    """
    Prominent compare button for toolbar.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.setText("Compare")
        style = self.style()
        if style is not None:
            self.setIcon(style.standardIcon(
                QStyle.StandardPixmap.SP_BrowserReload
            ))

        self.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                padding: 6px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
            QPushButton:pressed {
                background-color: #005a9e;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)


class SwapButton(QToolButton):
    """
    Button for swapping left and right sides.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.setText("⇄")
        self.setToolTip("Swap left and right")
        self.setAutoRaise(True)

        font = self.font()
        font.setPointSize(14)
        self.setFont(font)


class RefreshButton(QToolButton):
    """
    Button for refreshing comparison.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        style = self.style()
        if style is not None:
            self.setIcon(style.standardIcon(
                QStyle.StandardPixmap.SP_BrowserReload
            ))
        self.setToolTip("Refresh comparison (F5)")
        self.setAutoRaise(True)


class QuickActionBar(QWidget):
    """
    Bar with quick action buttons.
    
    Copy to left, copy to right, delete, etc.
    """

    # Action signals
    copy_to_left = pyqtSignal()
    copy_to_right = pyqtSignal()
    copy_all_to_left = pyqtSignal()
    copy_all_to_right = pyqtSignal()
    delete_left = pyqtSignal()
    delete_right = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup the widget."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Copy to left
        self.copy_left_btn = QToolButton()
        self.copy_left_btn.setText("◀")
        self.copy_left_btn.setToolTip("Copy to left (Alt+Left)")
        self.copy_left_btn.clicked.connect(self.copy_to_left.emit)
        layout.addWidget(self.copy_left_btn)

        # Copy to right
        self.copy_right_btn = QToolButton()
        self.copy_right_btn.setText("▶")
        self.copy_right_btn.setToolTip("Copy to right (Alt+Right)")
        self.copy_right_btn.clicked.connect(self.copy_to_right.emit)
        layout.addWidget(self.copy_right_btn)

        layout.addWidget(ToolbarSeparator())

        # Copy all to left
        self.copy_all_left_btn = QToolButton()
        self.copy_all_left_btn.setText("◀◀")
        self.copy_all_left_btn.setToolTip("Copy all to left")
        self.copy_all_left_btn.clicked.connect(self.copy_all_to_left.emit)
        layout.addWidget(self.copy_all_left_btn)

        # Copy all to right
        self.copy_all_right_btn = QToolButton()
        self.copy_all_right_btn.setText("▶▶")
        self.copy_all_right_btn.setToolTip("Copy all to right")
        self.copy_all_right_btn.clicked.connect(self.copy_all_to_right.emit)
        layout.addWidget(self.copy_all_right_btn)

    def set_enabled(self, enabled: bool) -> None:
        """Enable/disable all buttons."""
        self.copy_left_btn.setEnabled(enabled)
        self.copy_right_btn.setEnabled(enabled)
        self.copy_all_left_btn.setEnabled(enabled)
        self.copy_all_right_btn.setEnabled(enabled)


class FilterBar(QWidget):
    """
    Filter bar for folder comparison.
    
    Quick filters for showing specific file types.
    """

    # Signal when filter changes
    filter_changed = pyqtSignal(dict)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._filters = {
            'show_identical': True,
            'show_different': True,
            'show_left_only': True,
            'show_right_only': True,
        }

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup the widget."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        layout.addWidget(QLabel("Show:"))

        self._buttons: Dict[str, QToolButton] = {}

        filters = [
            ('show_identical', '=', "Identical files", "#28a745"),
            ('show_different', '≠', "Different files", "#ffc107"),
            ('show_left_only', '◀', "Left only", "#17a2b8"),
            ('show_right_only', '▶', "Right only", "#dc3545"),
        ]

        for key, icon, tooltip, color in filters:
            btn = QToolButton()
            btn.setText(icon)
            btn.setToolTip(tooltip)
            btn.setCheckable(True)
            btn.setChecked(self._filters[key])
            btn.setAutoRaise(True)

            btn.setStyleSheet(f"""
                QToolButton:checked {{
                    background-color: {color};
                    color: white;
                    border-radius: 3px;
                }}
            """)

            btn.toggled.connect(lambda checked, k=key: self._on_filter_changed(k, checked))

            self._buttons[key] = btn
            layout.addWidget(btn)

    def _on_filter_changed(self, key: str, checked: bool) -> None:
        """Handle filter toggle."""
        self._filters[key] = checked
        self.filter_changed.emit(self._filters.copy())

    def get_filters(self) -> Dict[str, bool]:
        """Get current filters."""
        return self._filters.copy()

    def set_filters(self, filters: Dict[str, bool]) -> None:
        """Set filters."""
        for key, value in filters.items():
            if key in self._buttons:
                self._buttons[key].setChecked(value)


class ToolbarFactory:
    """
    Factory for creating common toolbar configurations.
    """

    @staticmethod
    def create_file_compare_toolbar(parent: Optional[QWidget] = None) -> QToolBar:
        """Create toolbar for file comparison."""
        toolbar = QToolBar("File Compare", parent)
        toolbar.setMovable(False)

        # Path selectors
        left_selector = PathSelectorButton("file", "Left file...", "left_file")
        toolbar.addWidget(left_selector)

        swap_btn = SwapButton()
        toolbar.addWidget(swap_btn)

        right_selector = PathSelectorButton("file", "Right file...", "right_file")
        toolbar.addWidget(right_selector)

        toolbar.addSeparator()

        # Compare button
        compare_btn = CompareButton()
        toolbar.addWidget(compare_btn)

        toolbar.addSeparator()

        # Navigation
        nav_buttons = NavigationButtons()
        toolbar.addWidget(nav_buttons)

        toolbar.addSeparator()

        # View mode
        view_mode = ViewModeSelector()
        toolbar.addWidget(view_mode)

        toolbar.addSeparator()

        # Options
        options = CompareOptionsToolbar()
        toolbar.addWidget(options)

        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        # Search
        search = ToolbarSearchBox()
        toolbar.addWidget(search)

        return toolbar

    @staticmethod
    def create_folder_compare_toolbar(parent: Optional[QWidget] = None) -> QToolBar:
        """Create toolbar for folder comparison."""
        toolbar = QToolBar("Folder Compare", parent)
        toolbar.setMovable(False)

        # Path selectors
        left_selector = PathSelectorButton("folder", "Left folder...", "left_folder")
        toolbar.addWidget(left_selector)

        swap_btn = SwapButton()
        toolbar.addWidget(swap_btn)

        right_selector = PathSelectorButton("folder", "Right folder...", "right_folder")
        toolbar.addWidget(right_selector)

        toolbar.addSeparator()

        # Compare button
        compare_btn = CompareButton()
        toolbar.addWidget(compare_btn)

        refresh_btn = RefreshButton()
        toolbar.addWidget(refresh_btn)

        toolbar.addSeparator()

        # Filters
        filter_bar = FilterBar()
        toolbar.addWidget(filter_bar)

        toolbar.addSeparator()

        # Quick actions
        actions = QuickActionBar()
        toolbar.addWidget(actions)

        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        # Search
        search = ToolbarSearchBox("Filter files...")
        toolbar.addWidget(search)

        return toolbar

    @staticmethod
    def create_merge_toolbar(parent: Optional[QWidget] = None) -> QToolBar:
        """Create toolbar for merge view."""
        toolbar = QToolBar("Merge", parent)
        toolbar.setMovable(False)

        # Navigation
        nav = NavigationButtons()
        toolbar.addWidget(nav)

        toolbar.addSeparator()

        # Quick resolve buttons
        use_left = QToolButton()
        use_left.setText("◀ Left")
        use_left.setToolTip("Use left version (Alt+L)")
        toolbar.addWidget(use_left)

        use_right = QToolButton()
        use_right.setText("Right ▶")
        use_right.setToolTip("Use right version (Alt+R)")
        toolbar.addWidget(use_right)

        toolbar.addSeparator()

        # Status
        status = StatusIndicator()
        toolbar.addWidget(status)

        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        # Save
        save_btn = QPushButton("Save")
        style = toolbar.style()
        if style is not None:
            save_btn.setIcon(style.standardIcon(
                QStyle.StandardPixmap.SP_DialogSaveButton
            ))
        toolbar.addWidget(save_btn)

        return toolbar
