from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, pyqtSignal # Import pyqtSignal
from pathlib import Path
from typing import Optional
from app.ui.file_compare_view import FileCompareView

class FilePreviewPanel(QWidget):
    """
    Panel for previewing file content with diff highlighting.
    """
    # Signal to request a file comparison from the main window
    comparison_requested = pyqtSignal(str, str) # left_path, right_path

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._setup_ui()
        
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        self._left_label = QLabel("Left: ")
        self._left_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        main_layout.addWidget(self._left_label)

        self._right_label = QLabel("Right: ")
        self._right_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        main_layout.addWidget(self._right_label)
        
        self._compare_view = FileCompareView()
        main_layout.addWidget(self._compare_view)
        
    def show_preview(self, left_path: Optional[Path], right_path: Optional[Path]):
        """Show preview for the given paths."""
        self._left_label.setText(f"Left: {left_path}" if left_path else "Left:")
        self._right_label.setText(f"Right: {right_path}" if right_path else "Right:")

        if not left_path and not right_path:
            self._compare_view.clear()
            return
        
        self.comparison_requested.emit(str(left_path or ""), str(right_path or ""))

    def set_diff_result(self, result):
        """Set the diff result to display in the internal FileCompareView."""
        self._compare_view.set_diff_result(result)