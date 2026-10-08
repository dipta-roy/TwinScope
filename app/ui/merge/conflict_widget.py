"""
Conflict widget and custom resolution dialog for merge view.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.core.merge.conflict_resolver import ConflictAnalyzer
from app.core.models import ConflictResolution, MergeConflict


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


class ConflictWidget(QFrame):
    """
    Widget for displaying and resolving a single conflict.
    
    Shows conflict details, visual markers, and resolution options.
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
