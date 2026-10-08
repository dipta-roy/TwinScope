"""
Indicator and badge widgets for toolbar.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Optional

from PyQt6.QtCore import QRect, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QPainter, QPaintEvent
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QToolButton,
    QWidget,
)


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

    def paintEvent(self, a0: Optional[QPaintEvent]) -> None:
        """Paint with badge overlay."""
        if a0 is not None:
            super().paintEvent(a0)

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
