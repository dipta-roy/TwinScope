"""
Navigation and view control widgets for toolbar.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QSlider,
    QToolButton,
    QWidget,
)


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
