"""
Custom toolbar widgets for the comparison application.

Provides:
- Path selector buttons with history
- Navigation buttons (next/prev diff)
- View mode selectors
- Comparison option toggles
- Progress indicators
- Zoom controls
- Status indicators
- Search box for toolbar
- Split button with dropdown
- Icon buttons with badges
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Optional, List, Callable, Dict, Any

from PyQt6.QtCore import (
    Qt, pyqtSignal, pyqtSlot, QSize, QTimer, QPoint,
    QPropertyAnimation, QEasingCurve, QSettings, QRect,
    QEvent
)
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QIcon, QPixmap, QPen, QBrush,
    QAction, QKeySequence, QPalette, QCursor, QFontMetrics,
    QMouseEvent, QPaintEvent, QEnterEvent, QResizeEvent
)
from PyQt6.QtWidgets import (
    QWidget, QToolButton, QPushButton, QLabel, QLineEdit,
    QComboBox, QSpinBox, QSlider, QProgressBar, QMenu,
    QHBoxLayout, QVBoxLayout, QFrame, QSizePolicy,
    QFileDialog, QToolBar, QWidgetAction, QStyle,
    QStyleOptionToolButton, QApplication, QCompleter,
    QButtonGroup, QRadioButton, QCheckBox, QToolTip
)


class PathSelectorButton(QToolButton):
    """
    Button for selecting files or folders with history dropdown.
    
    Features:
    - Click to browse
    - Dropdown for recent paths
    - Drag and drop support
    - Path validation
    - Tooltip with full path
    """
    
    # Signal when path is selected
    path_selected = pyqtSignal(str)
    
    # Signal when path is cleared
    path_cleared = pyqtSignal()
    
    MAX_HISTORY = 10
    
    def __init__(
        self,
        mode: str = "file",  # "file", "folder", "any"
        label: str = "Select...",
        settings_key: Optional[str] = None,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        
        self._mode = mode
        self._label = label
        self._settings_key = settings_key
        self._current_path: Optional[Path] = None
        self._history: List[str] = []
        self._file_filter = "All Files (*.*)"
        
        self._setup_ui()
        self._load_history()
        
        # Enable drag and drop
        self.setAcceptDrops(True)
    
    def _setup_ui(self) -> None:
        """Setup the button UI."""
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(150)
        
        # Set icon based on mode
        style = self.style()
        if self._mode == "folder":
            icon = style.standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        else:
            icon = style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        self.setIcon(icon)
        
        self._update_text()
        
        # Create menu
        self._menu = QMenu(self)
        self._update_menu()
        self.setMenu(self._menu)
        
        # Connect click
        self.clicked.connect(self._browse)
    
    def _update_text(self) -> None:
        """Update button text based on current path."""
        if self._current_path:
            # Show filename or folder name
            name = self._current_path.name
            if len(name) > 30:
                name = name[:27] + "..."
            self.setText(name)
            self.setToolTip(str(self._current_path))
        else:
            self.setText(self._label)
            self.setToolTip(f"Click to select {self._mode}")
    
    def _update_menu(self) -> None:
        """Update the dropdown menu."""
        self._menu.clear()
        
        # Browse action
        browse_action = self._menu.addAction(f"Browse {self._mode.title()}...")
        browse_action.triggered.connect(self._browse)
        
        if self._current_path:
            # Clear action
            clear_action = self._menu.addAction("Clear")
            clear_action.triggered.connect(self.clear_path)
            
            # Open in explorer
            self._menu.addSeparator()
            open_action = self._menu.addAction("Open in Explorer")
            open_action.triggered.connect(self._open_in_explorer)
            
            # Copy path
            copy_action = self._menu.addAction("Copy Path")
            copy_action.triggered.connect(self._copy_path)
        
        # History
        if self._history:
            self._menu.addSeparator()
            history_menu = self._menu.addMenu("Recent")
            
            for path in self._history[:self.MAX_HISTORY]:
                action = history_menu.addAction(self._format_path(path))
                action.setData(path)
                action.triggered.connect(lambda checked, p=path: self.set_path(p))
            
            history_menu.addSeparator()
            clear_history = history_menu.addAction("Clear History")
            clear_history.triggered.connect(self._clear_history)
    
    def _format_path(self, path: str) -> str:
        """Format path for display in menu."""
        p = Path(path)
        name = p.name
        parent = str(p.parent)
        
        if len(parent) > 30:
            parent = "..." + parent[-27:]
        
        return f"{name} ({parent})"
    
    def _browse(self) -> None:
        """Open browse dialog."""
        start_dir = ""
        if self._current_path:
            start_dir = str(self._current_path.parent)
        elif self._history:
            start_dir = str(Path(self._history[0]).parent)
        
        if self._mode == "folder":
            path = QFileDialog.getExistingDirectory(
                self,
                "Select Folder",
                start_dir
            )
        else:
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Select File",
                start_dir,
                self._file_filter
            )
        
        if path:
            self.set_path(path)
    
    def set_path(self, path: str | Path) -> None:
        """Set the current path."""
        path = Path(path)
        
        if not path.exists():
            return
        
        # Validate mode
        if self._mode == "folder" and not path.is_dir():
            return
        if self._mode == "file" and not path.is_file():
            return
        
        self._current_path = path
        self._add_to_history(str(path))
        self._update_text()
        self._update_menu()
        
        self.path_selected.emit(str(path))
    
    def get_path(self) -> Optional[Path]:
        """Get the current path."""
        return self._current_path
    
    def clear_path(self) -> None:
        """Clear the current path."""
        self._current_path = None
        self._update_text()
        self._update_menu()
        self.path_cleared.emit()
    
    def set_file_filter(self, filter_str: str) -> None:
        """Set file filter for browse dialog."""
        self._file_filter = filter_str
    
    def _add_to_history(self, path: str) -> None:
        """Add path to history."""
        if path in self._history:
            self._history.remove(path)
        
        self._history.insert(0, path)
        self._history = self._history[:self.MAX_HISTORY]
        
        self._save_history()
    
    def _load_history(self) -> None:
        """Load history from settings."""
        if self._settings_key:
            settings = QSettings()
            self._history = settings.value(
                f"path_history/{self._settings_key}",
                [],
                type=list
            )
    
    def _save_history(self) -> None:
        """Save history to settings."""
        if self._settings_key:
            settings = QSettings()
            settings.setValue(
                f"path_history/{self._settings_key}",
                self._history
            )
    
    def _clear_history(self) -> None:
        """Clear path history."""
        self._history.clear()
        self._save_history()
        self._update_menu()
    
    def _open_in_explorer(self) -> None:
        """Open path in system file explorer."""
        if not self._current_path:
            return
        
        import subprocess
        import sys
        
        path = self._current_path
        if path.is_file():
            path = path.parent
        
        if sys.platform == 'win32':
            subprocess.run(['explorer', str(path)])
        elif sys.platform == 'darwin':
            subprocess.run(['open', str(path)])
        else:
            subprocess.run(['xdg-open', str(path)])
    
    def _copy_path(self) -> None:
        """Copy path to clipboard."""
        if self._current_path:
            clipboard = QApplication.clipboard()
            clipboard.setText(str(self._current_path))
    
    def dragEnterEvent(self, event) -> None:
        """Handle drag enter."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
    
    def dropEvent(self, event) -> None:
        """Handle drop."""
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            self.set_path(path)


class NavigationButtons(QWidget):
    """
    Navigation buttons for moving between differences.
    
    Provides previous/next buttons with count display.
    """
    
    # Navigation signals
    previous_clicked = pyqtSignal()
    next_clicked = pyqtSignal()
    first_clicked = pyqtSignal()
    last_clicked = pyqtSignal()
    
    def __init__(
        self,
        show_first_last: bool = True,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        
        self._current = 0
        self._total = 0
        self._show_first_last = show_first_last
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup the widget."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        
        # First button
        if self._show_first_last:
            self.first_btn = QToolButton()
            self.first_btn.setText("⏮")
            self.first_btn.setToolTip("First difference (Ctrl+Home)")
            self.first_btn.clicked.connect(self.first_clicked.emit)
            layout.addWidget(self.first_btn)
        
        # Previous button
        self.prev_btn = QToolButton()
        self.prev_btn.setText("◀")
        self.prev_btn.setToolTip("Previous difference (F7)")
        self.prev_btn.clicked.connect(self.previous_clicked.emit)
        layout.addWidget(self.prev_btn)
        
        # Counter
        self.counter_label = QLabel("0 / 0")
        self.counter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.counter_label.setMinimumWidth(60)
        layout.addWidget(self.counter_label)
        
        # Next button
        self.next_btn = QToolButton()
        self.next_btn.setText("▶")
        self.next_btn.setToolTip("Next difference (F8)")
        self.next_btn.clicked.connect(self.next_clicked.emit)
        layout.addWidget(self.next_btn)
        
        # Last button
        if self._show_first_last:
            self.last_btn = QToolButton()
            self.last_btn.setText("⏭")
            self.last_btn.setToolTip("Last difference (Ctrl+End)")
            self.last_btn.clicked.connect(self.last_clicked.emit)
            layout.addWidget(self.last_btn)
        
        self._update_buttons()
    
    def set_count(self, current: int, total: int) -> None:
        """Set the current and total counts."""
        self._current = current
        self._total = total
        self._update_buttons()
    
    def _update_buttons(self) -> None:
        """Update button states and counter."""
        self.counter_label.setText(f"{self._current} / {self._total}")
        
        has_items = self._total > 0
        at_start = self._current <= 1
        at_end = self._current >= self._total
        
        self.prev_btn.setEnabled(has_items and not at_start)
        self.next_btn.setEnabled(has_items and not at_end)
        
        if self._show_first_last:
            self.first_btn.setEnabled(has_items and not at_start)
            self.last_btn.setEnabled(has_items and not at_end)
        
        # Color based on state
        if self._total == 0:
            self.counter_label.setStyleSheet("color: gray;")
        elif self._current > 0:
            self.counter_label.setStyleSheet("color: black; font-weight: bold;")
        else:
            self.counter_label.setStyleSheet("color: black;")


class ViewModeSelector(QWidget):
    """
    Selector for comparison view modes.
    
    Allows switching between side-by-side, unified, inline modes.
    """
    
    # Signal when mode changes
    mode_changed = pyqtSignal(str)
    
    class Mode(Enum):
        SIDE_BY_SIDE = "side_by_side"
        UNIFIED = "unified"
        INLINE = "inline"
    
    def __init__(
        self,
        modes: Optional[List[str]] = None,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        
        self._modes = modes or ["side_by_side", "unified"]
        self._current_mode = self._modes[0]
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup the widget."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self._button_group = QButtonGroup(self)
        self._buttons: Dict[str, QToolButton] = {}
        
        mode_info = {
            "side_by_side": ("⊏⊐", "Side by Side"),
            "unified": ("≡", "Unified"),
            "inline": ("⊏", "Inline"),
        }
        
        for mode in self._modes:
            icon, tooltip = mode_info.get(mode, ("?", mode))
            
            btn = QToolButton()
            btn.setText(icon)
            btn.setToolTip(tooltip)
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            
            if mode == self._current_mode:
                btn.setChecked(True)
            
            btn.clicked.connect(lambda checked, m=mode: self._on_mode_clicked(m))
            
            self._button_group.addButton(btn)
            self._buttons[mode] = btn
            layout.addWidget(btn)
    
    def _on_mode_clicked(self, mode: str) -> None:
        """Handle mode button click."""
        if mode != self._current_mode:
            self._current_mode = mode
            self.mode_changed.emit(mode)
    
    def get_mode(self) -> str:
        """Get current mode."""
        return self._current_mode
    
    def set_mode(self, mode: str) -> None:
        """Set current mode."""
        if mode in self._buttons:
            self._buttons[mode].setChecked(True)
            self._current_mode = mode


class CompareOptionsToolbar(QWidget):
    """
    Toolbar widget for comparison options.
    
    Toggle buttons for various comparison settings.
    """
    
    # Signal when any option changes
    options_changed = pyqtSignal(dict)
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self._options: Dict[str, bool] = {
            'ignore_whitespace': False,
            'ignore_case': False,
            'ignore_blank_lines': False,
            'show_line_numbers': True,
            'word_wrap': False,
            'syntax_highlight': True,
        }
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup the widget."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        self._buttons: Dict[str, QToolButton] = {}
        
        # Option definitions: (key, icon, tooltip)
        options = [
            ('ignore_whitespace', '␣', "Ignore whitespace"),
            ('ignore_case', 'Aa', "Ignore case"),
            ('ignore_blank_lines', '⊟', "Ignore blank lines"),
            ('show_line_numbers', '#', "Show line numbers"),
            ('word_wrap', '↩', "Word wrap"),
            ('syntax_highlight', '🎨', "Syntax highlighting"),
        ]
        
        for key, icon, tooltip in options:
            btn = QToolButton()
            btn.setText(icon)
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
        """Get all options."""
        return self._options.copy()
    
    def set_option(self, key: str, value: bool) -> None:
        """Set a specific option."""
        if key in self._buttons:
            self._buttons[key].setChecked(value)
    
    def set_options(self, options: Dict[str, bool]) -> None:
        """Set multiple options."""
        for key, value in options.items():
            self.set_option(key, value)


class ZoomControl(QWidget):
    """
    Zoom control widget with slider and buttons.
    """
    
    # Signal when zoom changes
    zoom_changed = pyqtSignal(int)  # percentage
    
    def __init__(
        self,
        min_zoom: int = 50,
        max_zoom: int = 200,
        default_zoom: int = 100,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        
        self._min_zoom = min_zoom
        self._max_zoom = max_zoom
        self._current_zoom = default_zoom
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup the widget."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # Zoom out button
        self.zoom_out_btn = QToolButton()
        self.zoom_out_btn.setText("−")
        self.zoom_out_btn.setToolTip("Zoom out (Ctrl+-)")
        self.zoom_out_btn.setAutoRepeat(True)
        self.zoom_out_btn.clicked.connect(self._zoom_out)
        layout.addWidget(self.zoom_out_btn)
        
        # Zoom slider
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(self._min_zoom, self._max_zoom)
        self.slider.setValue(self._current_zoom)
        self.slider.setFixedWidth(80)
        self.slider.setToolTip("Zoom level")
        self.slider.valueChanged.connect(self._on_slider_changed)
        layout.addWidget(self.slider)
        
        # Zoom in button
        self.zoom_in_btn = QToolButton()
        self.zoom_in_btn.setText("+")
        self.zoom_in_btn.setToolTip("Zoom in (Ctrl++)")
        self.zoom_in_btn.setAutoRepeat(True)
        self.zoom_in_btn.clicked.connect(self._zoom_in)
        layout.addWidget(self.zoom_in_btn)
        
        # Zoom label
        self.zoom_label = QLabel(f"{self._current_zoom}%")
        self.zoom_label.setMinimumWidth(40)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.zoom_label)
        
        # Reset button
        self.reset_btn = QToolButton()
        self.reset_btn.setText("⟲")
        self.reset_btn.setToolTip("Reset zoom (Ctrl+0)")
        self.reset_btn.clicked.connect(self.reset_zoom)
        layout.addWidget(self.reset_btn)
        
        self._update_buttons()
    
    def _on_slider_changed(self, value: int) -> None:
        """Handle slider change."""
        self._current_zoom = value
        self._update_buttons()
        self.zoom_changed.emit(value)
    
    def _zoom_in(self) -> None:
        """Increase zoom."""
        new_zoom = min(self._current_zoom + 10, self._max_zoom)
        self.set_zoom(new_zoom)
    
    def _zoom_out(self) -> None:
        """Decrease zoom."""
        new_zoom = max(self._current_zoom - 10, self._min_zoom)
        self.set_zoom(new_zoom)
    
    def reset_zoom(self) -> None:
        """Reset to 100%."""
        self.set_zoom(100)
    
    def set_zoom(self, value: int) -> None:
        """Set zoom level."""
        value = max(self._min_zoom, min(self._max_zoom, value))
        self.slider.setValue(value)
    
    def get_zoom(self) -> int:
        """Get current zoom level."""
        return self._current_zoom
    
    def _update_buttons(self) -> None:
        """Update button states."""
        self.zoom_out_btn.setEnabled(self._current_zoom > self._min_zoom)
        self.zoom_in_btn.setEnabled(self._current_zoom < self._max_zoom)
        self.zoom_label.setText(f"{self._current_zoom}%")


class ProgressIndicator(QWidget):
    """
    Progress indicator for toolbar.
    
    Shows progress bar with cancel button during operations.
    """
    
    # Signal when cancel is clicked
    cancel_clicked = pyqtSignal()
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self._is_running = False
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup the widget."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # Status label
        self.status_label = QLabel()
        self.status_label.setMinimumWidth(100)
        layout.addWidget(self.status_label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(120)
        self.progress_bar.setMaximumHeight(16)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)
        
        # Cancel button
        self.cancel_btn = QToolButton()
        self.cancel_btn.setText("✕")
        self.cancel_btn.setToolTip("Cancel operation")
        self.cancel_btn.clicked.connect(self.cancel_clicked.emit)
        layout.addWidget(self.cancel_btn)
        
        self.hide()
    
    def start(self, message: str = "Working...", indeterminate: bool = False) -> None:
        """Start showing progress."""
        self._is_running = True
        self.status_label.setText(message)
        
        if indeterminate:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
        
        self.show()
    
    def update_progress(self, value: int, message: Optional[str] = None) -> None:
        """Update progress value."""
        self.progress_bar.setValue(value)
        if message:
            self.status_label.setText(message)
    
    def finish(self, message: str = "Done") -> None:
        """Finish and hide after delay."""
        self._is_running = False
        self.status_label.setText(message)
        self.progress_bar.setValue(100)
        
        QTimer.singleShot(1500, self.hide)
    
    def is_running(self) -> bool:
        """Check if operation is running."""
        return self._is_running


class StatusIndicator(QWidget):
    """
    Status indicator showing comparison state.
    
    Shows icons/colors for identical, different, error states.
    """
    
    class State(Enum):
        NONE = auto()
        IDENTICAL = auto()
        DIFFERENT = auto()
        ERROR = auto()
        LOADING = auto()
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self._state = self.State.NONE
        self._message = ""
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup the widget."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        
        # Icon label
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(16, 16)
        layout.addWidget(self.icon_label)
        
        # Message label
        self.message_label = QLabel()
        layout.addWidget(self.message_label)
        
        self.setAutoFillBackground(True)
        self._update_display()
    
    def set_state(self, state: State, message: str = "") -> None:
        """Set the indicator state."""
        self._state = state
        self._message = message
        self._update_display()
    
    def _update_display(self) -> None:
        """Update display based on state."""
        state_info = {
            self.State.NONE: ("", "", "#f0f0f0", "#000000"),
            self.State.IDENTICAL: ("✓", "Identical", "#d4edda", "#155724"),
            self.State.DIFFERENT: ("≠", "Different", "#fff3cd", "#856404"),
            self.State.ERROR: ("⚠", "Error", "#f8d7da", "#721c24"),
            self.State.LOADING: ("⟳", "Loading...", "#cce5ff", "#004085"),
        }
        
        icon, default_msg, bg_color, text_color = state_info[self._state]
        
        self.icon_label.setText(icon)
        self.message_label.setText(self._message or default_msg)
        
        self.setStyleSheet(f"""
            StatusIndicator {{
                background-color: {bg_color};
                border-radius: 3px;
            }}
            QLabel {{
                color: {text_color};
            }}
        """)


class SplitButton(QToolButton):
    """
    Button with dropdown menu split from main action.
    
    Click executes default action, dropdown shows alternatives.
    """
    
    def __init__(
        self,
        text: str = "",
        icon: Optional[QIcon] = None,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        
        self._default_action: Optional[QAction] = None
        
        if icon:
            self.setIcon(icon)
        if text:
            self.setText(text)
        
        self.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        
        self._menu = QMenu(self)
        self.setMenu(self._menu)
        
        self.clicked.connect(self._on_clicked)
    
    def set_default_action(self, action: QAction) -> None:
        """Set the default action (executed on button click)."""
        self._default_action = action
        self.setText(action.text())
        if action.icon():
            self.setIcon(action.icon())
        self.setToolTip(action.toolTip())
    
    def add_action(self, action: QAction, is_default: bool = False) -> None:
        """Add an action to the dropdown."""
        self._menu.addAction(action)
        
        if is_default:
            self.set_default_action(action)
    
    def add_separator(self) -> None:
        """Add a separator to the menu."""
        self._menu.addSeparator()
    
    def _on_clicked(self) -> None:
        """Handle button click."""
        if self._default_action:
            self._default_action.trigger()


class BadgeButton(QToolButton):
    """
    Tool button with notification badge.
    
    Shows a count badge in the corner.
    """
    
    def __init__(
        self,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        
        self._badge_count = 0
        self._badge_color = QColor(255, 0, 0)
        self._badge_text_color = QColor(255, 255, 255)
    
    def set_badge(self, count: int) -> None:
        """Set the badge count (0 to hide)."""
        self._badge_count = count
        self.update()
    
    def set_badge_color(self, color: QColor) -> None:
        """Set badge background color."""
        self._badge_color = color
        self.update()
    
    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint with badge overlay."""
        super().paintEvent(event)
        
        if self._badge_count <= 0:
            return
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Badge dimensions
        badge_size = 14
        margin = 2
        
        # Position (top-right)
        x = self.width() - badge_size - margin
        y = margin
        
        # Draw badge circle
        painter.setBrush(QBrush(self._badge_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(x, y, badge_size, badge_size)
        
        # Draw count text
        painter.setPen(self._badge_text_color)
        font = painter.font()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        
        text = str(self._badge_count) if self._badge_count < 100 else "99+"
        painter.drawText(
            QRect(x, y, badge_size, badge_size),
            Qt.AlignmentFlag.AlignCenter,
            text
        )


class ToolbarSearchBox(QLineEdit):
    """
    Search box optimized for toolbar use.
    
    Compact with clear button and search icon.
    """
    
    # Signal for search (with slight delay)
    search_triggered = pyqtSignal(str)
    
    def __init__(
        self,
        placeholder: str = "Search...",
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        
        self._delay_timer = QTimer()
        self._delay_timer.setSingleShot(True)
        self._delay_timer.timeout.connect(self._emit_search)
        
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self.setMaximumWidth(200)
        
        # Add search icon
        self.addAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView),
            QLineEdit.ActionPosition.LeadingPosition
        )
        
        self.textChanged.connect(self._on_text_changed)
        self.returnPressed.connect(self._emit_search)
    
    def _on_text_changed(self, text: str) -> None:
        """Handle text changes with delay."""
        self._delay_timer.stop()
        self._delay_timer.start(300)  # 300ms delay
    
    def _emit_search(self) -> None:
        """Emit search signal."""
        self.search_triggered.emit(self.text())


class ToolbarSeparator(QFrame):
    """
    Vertical separator for toolbars.
    """
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.setFrameShape(QFrame.Shape.VLine)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self.setFixedWidth(2)
        self.setMinimumHeight(20)


class ToolbarLabel(QLabel):
    """
    Label styled for toolbar use.
    """
    
    def __init__(
        self,
        text: str = "",
        bold: bool = False,
        parent: Optional[QWidget] = None
    ):
        super().__init__(text, parent)
        
        if bold:
            font = self.font()
            font.setBold(True)
            self.setFont(font)
        
        self.setContentsMargins(4, 0, 4, 0)


class EncodingSelector(QComboBox):
    """
    Dropdown for selecting text encoding.
    """
    
    # Signal when encoding changes
    encoding_changed = pyqtSignal(str)
    
    COMMON_ENCODINGS = [
        ("UTF-8", "utf-8"),
        ("UTF-16", "utf-16"),
        ("ASCII", "ascii"),
        ("Latin-1", "iso-8859-1"),
        ("Windows-1252", "cp1252"),
        ("UTF-8 BOM", "utf-8-sig"),
        ("UTF-16 LE", "utf-16-le"),
        ("UTF-16 BE", "utf-16-be"),
    ]
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        for name, encoding in self.COMMON_ENCODINGS:
            self.addItem(name, encoding)
        
        self.setCurrentIndex(0)
        self.currentIndexChanged.connect(self._on_changed)
        
        self.setToolTip("File encoding")
        self.setMinimumWidth(100)
    
    def _on_changed(self, index: int) -> None:
        """Handle selection change."""
        encoding = self.currentData()
        self.encoding_changed.emit(encoding)
    
    def get_encoding(self) -> str:
        """Get selected encoding."""
        return self.currentData()
    
    def set_encoding(self, encoding: str) -> None:
        """Set encoding by value."""
        for i in range(self.count()):
            if self.itemData(i) == encoding:
                self.setCurrentIndex(i)
                return


class LineEndingSelector(QComboBox):
    """
    Dropdown for selecting line ending style.
    """
    
    # Signal when line ending changes
    line_ending_changed = pyqtSignal(str)
    
    LINE_ENDINGS = [
        ("LF (Unix)", "lf"),
        ("CRLF (Windows)", "crlf"),
        ("CR (Mac)", "cr"),
        ("Auto", "auto"),
    ]
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        for name, value in self.LINE_ENDINGS:
            self.addItem(name, value)
        
        self.setCurrentIndex(0)
        self.currentIndexChanged.connect(self._on_changed)
        
        self.setToolTip("Line ending style")
        self.setMinimumWidth(100)
    
    def _on_changed(self, index: int) -> None:
        """Handle selection change."""
        value = self.currentData()
        self.line_ending_changed.emit(value)
    
    def get_line_ending(self) -> str:
        """Get selected line ending."""
        return self.currentData()
    
    def set_line_ending(self, value: str) -> None:
        """Set line ending by value."""
        for i in range(self.count()):
            if self.itemData(i) == value:
                self.setCurrentIndex(i)
                return


class FontSizeSpinner(QSpinBox):
    """
    Spinner for font size selection.
    """
    
    def __init__(
        self,
        min_size: int = 6,
        max_size: int = 72,
        default_size: int = 10,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        
        self.setRange(min_size, max_size)
        self.setValue(default_size)
        self.setSuffix(" pt")
        self.setToolTip("Font size")
        self.setFixedWidth(70)


class CompareButton(QPushButton):
    """
    Prominent compare button for toolbar.
    """
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.setText("Compare")
        self.setIcon(self.style().standardIcon(
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
        
        self.setIcon(self.style().standardIcon(
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
        save_btn.setIcon(toolbar.style().standardIcon(
            QStyle.StandardPixmap.SP_DialogSaveButton
        ))
        toolbar.addWidget(save_btn)
        
        return toolbar