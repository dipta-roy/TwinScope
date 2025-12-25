from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel, QApplication, QStyle, QWidget
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData, QUrl
from PyQt6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent, QPalette, QColor
from typing import Optional, List

class DropArea(QFrame):
    """
    A widget that acts as a drag-and-drop target for files and folders.
    Provides visual feedback during drag operations.
    """
    
    files_dropped = pyqtSignal(list) # Emits a list of file paths (str)

    def __init__(self, message: str = "Drag and drop files/folders here", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self.setLineWidth(2)
        
        self._default_message = message
        
        layout = QVBoxLayout(self)
        self._label = QLabel(self._default_message)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("font-size: 14px; font-weight: bold; color: palette(text);")
        layout.addWidget(self._label)
        
        self._is_dragging = False
        self._update_style()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._is_dragging = True
            self._update_style()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        event.accept()
        self._is_dragging = False
        self._update_style()

    def dropEvent(self, event: QDropEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            urls = event.mimeData().urls()
            file_paths = [url.toLocalFile() for url in urls if url.isLocalFile()]
            self.files_dropped.emit(file_paths)
            self._is_dragging = False
            self._update_style()
        else:
            event.ignore()
        
    def _update_style(self):
        palette = self.palette()
        if self._is_dragging:
            # Change border and background when dragging over
            self.setStyleSheet(f"""
                QFrame {{
                    border: 2px dashed {palette.highlight().color().name()};
                    background-color: {palette.highlight().color().lighter(180).name()};
                    border-radius: 8px;
                }}
                QLabel {{
                    color: {palette.highlight().color().name()};
                }}
            """)
        else:
            # Revert to default style
            self.setStyleSheet(f"""
                QFrame {{
                    border: 1px solid {palette.midlight().color().name()};
                    background-color: {palette.base().color().name()};
                    border-radius: 8px;
                }}
                QLabel {{
                    color: {palette.text().color().name()};
                }}
            """)