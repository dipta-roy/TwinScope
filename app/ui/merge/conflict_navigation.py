"""
Conflict navigation and listing widgets for merge view.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.models import ConflictResolution, MergeConflict
from app.ui.merge.conflict_widget import ConflictWidget


class ConflictListWidget(QWidget):
    """Widget listing all conflicts with their status and navigation controls."""

    # Signal when a conflict is selected
    conflict_selected = pyqtSignal(int)

    # Signal when resolution changes
    resolution_changed = pyqtSignal(int, object, str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._conflict_widgets: Dict[int, ConflictWidget] = {}

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

    def set_conflicts(self, conflicts: List[MergeConflict]) -> None:
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
