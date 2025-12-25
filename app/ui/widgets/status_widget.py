"""
Status display widgets.

Provides status indicators, progress bars, and info displays.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QBrush, QPen
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QProgressBar, QFrame, QStatusBar, QSizePolicy
)


class StatusIndicator(QWidget):
    """
    Small colored status indicator.
    
    Shows a colored dot indicating status.
    """
    
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        size: int = 12
    ):
        super().__init__(parent)
        
        self._color = QColor(128, 128, 128)
        self._size = size
        self._pulsing = False
        self._pulse_timer: Optional[QTimer] = None
        self._pulse_alpha = 255
        
        self.setFixedSize(size, size)
    
    def set_color(self, color: QColor) -> None:
        """Set indicator color."""
        self._color = color
        self.update()
    
    def set_status(self, status: str) -> None:
        """Set status by name."""
        colors = {
            'idle': QColor(128, 128, 128),
            'running': QColor(0, 150, 255),
            'success': QColor(0, 200, 0),
            'warning': QColor(255, 180, 0),
            'error': QColor(255, 0, 0),
        }
        self._color = colors.get(status, QColor(128, 128, 128))
        self.update()
    
    def start_pulsing(self) -> None:
        """Start pulsing animation."""
        if self._pulse_timer is None:
            self._pulse_timer = QTimer(self)
            self._pulse_timer.timeout.connect(self._pulse_step)
        
        self._pulsing = True
        self._pulse_timer.start(50)
    
    def stop_pulsing(self) -> None:
        """Stop pulsing animation."""
        self._pulsing = False
        if self._pulse_timer:
            self._pulse_timer.stop()
        self._pulse_alpha = 255
        self.update()
    
    def _pulse_step(self) -> None:
        """Update pulse animation."""
        import math
        self._pulse_alpha = int(127 + 128 * math.sin(
            QTimer.staticMetaObject.className()  # Use time-based
        ))
        self.update()
    
    def paintEvent(self, event) -> None:
        """Paint the indicator."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw circle
        color = QColor(self._color)
        color.setAlpha(self._pulse_alpha if self._pulsing else 255)
        
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(color.darker(120), 1))
        
        margin = 2
        painter.drawEllipse(
            margin, margin,
            self._size - margin * 2,
            self._size - margin * 2
        )


class ProgressWidget(QWidget):
    """
    Progress display with label and cancel button.
    """
    
    cancelled = pyqtSignal()
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Status label
        self.status_label = QLabel()
        layout.addWidget(self.status_label)
        
        # Progress bar
        progress_layout = QHBoxLayout()
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        progress_layout.addWidget(self.progress_bar)
        
        from PyQt6.QtWidgets import QPushButton
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.cancelled.emit)
        progress_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(progress_layout)
    
    def set_progress(
        self,
        current: int,
        total: int,
        message: str = ""
    ) -> None:
        """Update progress."""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        
        if message:
            self.status_label.setText(message)
    
    def set_indeterminate(self, message: str = "") -> None:
        """Set indeterminate progress."""
        self.progress_bar.setMaximum(0)
        self.progress_bar.setValue(0)
        
        if message:
            self.status_label.setText(message)
    
    def set_complete(self, message: str = "Complete") -> None:
        """Set complete state."""
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(100)
        self.status_label.setText(message)
        self.cancel_btn.setEnabled(False)
    
    def reset(self) -> None:
        """Reset to initial state."""
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.status_label.setText("")
        self.cancel_btn.setEnabled(True)


class CompareStatusBar(QStatusBar):
    """
    Status bar with comparison-specific information.
    """
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self._setup_widgets()
    
    def _setup_widgets(self) -> None:
        """Setup status bar widgets."""
        # Status indicator
        self.indicator = StatusIndicator()
        self.addWidget(self.indicator)
        
        # Main message
        self.message_label = QLabel()
        self.addWidget(self.message_label, 1)
        
        # Stats
        self.stats_label = QLabel()
        self.addPermanentWidget(self.stats_label)
        
        # Position info
        self.position_label = QLabel()
        self.addPermanentWidget(self.position_label)
    
    def set_idle(self) -> None:
        """Set idle state."""
        self.indicator.set_status('idle')
        self.message_label.setText("Ready")
    
    def set_comparing(self, message: str = "Comparing...") -> None:
        """Set comparing state."""
        self.indicator.set_status('running')
        self.indicator.start_pulsing()
        self.message_label.setText(message)
    
    def set_complete(
        self,
        identical: int,
        modified: int,
        added: int,
        removed: int
    ) -> None:
        """Set complete with statistics."""
        self.indicator.stop_pulsing()
        
        if modified + added + removed == 0:
            self.indicator.set_status('success')
            self.message_label.setText("Files are identical")
        else:
            self.indicator.set_status('warning')
            self.message_label.setText("Differences found")
        
        self.stats_label.setText(
            f"={identical} ~{modified} +{added} -{removed}"
        )
    
    def set_error(self, message: str) -> None:
        """Set error state."""
        self.indicator.stop_pulsing()
        self.indicator.set_status('error')
        self.message_label.setText(f"Error: {message}")
    
    def set_position(self, line: int, column: int) -> None:
        """Update cursor position display."""
        self.position_label.setText(f"Ln {line}, Col {column}")


class FileInfoWidget(QFrame):
    """
    Widget displaying file information.
    """
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        
        self.name_label = QLabel()
        self.name_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.name_label)
        
        self.size_label = QLabel()
        layout.addWidget(self.size_label)
        
        self.modified_label = QLabel()
        layout.addWidget(self.modified_label)
        
        self.encoding_label = QLabel()
        layout.addWidget(self.encoding_label)
    
    def set_info(
        self,
        name: str,
        size: int,
        modified: str,
        encoding: str = ""
    ) -> None:
        """Set file information."""
        self.name_label.setText(name)
        self.size_label.setText(f"Size: {self._format_size(size)}")
        self.modified_label.setText(f"Modified: {modified}")
        
        if encoding:
            self.encoding_label.setText(f"Encoding: {encoding}")
            self.encoding_label.show()
        else:
            self.encoding_label.hide()
    
    def clear(self) -> None:
        """Clear information."""
        self.name_label.setText("")
        self.size_label.setText("")
        self.modified_label.setText("")
        self.encoding_label.setText("")
    
    def _format_size(self, size: int) -> str:
        """Format file size."""
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.2f} GB"