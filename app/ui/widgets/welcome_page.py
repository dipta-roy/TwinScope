"""Welcome page widget for the application."""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt, pyqtSignal, QByteArray
from PyQt6.QtGui import QPixmap
from typing import Optional

from app.ui.widgets.welcome_buttons import WelcomeButton
from app.ui.widgets.drop_area import DropArea
from app.ui import resources


class WelcomePage(QWidget):
    """
    Welcome/start page widget with quick action buttons.
    """
    # Signals
    compare_files_requested = pyqtSignal()
    compare_folders_requested = pyqtSignal()
    merge_requested = pyqtSignal()
    files_dropped = pyqtSignal(list)
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Logo
        self._logo_label = QLabel()
        pixmap = QPixmap()
        pixmap.loadFromData(QByteArray.fromBase64(resources.LOGO_BASE64.encode()))
        self._logo_label.setPixmap(pixmap.scaledToWidth(200, Qt.TransformationMode.SmoothTransformation))
        self._logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._logo_label)
        
        self._subtitle = QLabel("Compare files and folders with ease")
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._subtitle)
        
        # Quick actions
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(20)
        
        self._compare_files_btn = WelcomeButton(
            "Compare Files",
            "Compare two text or binary files",
            "document-compare"
        )
        self._compare_files_btn.clicked.connect(self.compare_files_requested.emit)
        actions_layout.addWidget(self._compare_files_btn)
        
        self._compare_folders_btn = WelcomeButton(
            "Compare Folders", 
            "Compare directory contents",
            "folder-compare"
        )
        self._compare_folders_btn.clicked.connect(self.compare_folders_requested.emit)
        actions_layout.addWidget(self._compare_folders_btn)
        
        self._merge_btn = WelcomeButton(
            "Three-Way Merge",
            "Merge changes from two sources",
            "merge"
        )
        self._merge_btn.clicked.connect(self.merge_requested.emit)
        actions_layout.addWidget(self._merge_btn)
        
        layout.addLayout(actions_layout)
        
        # Drop hint
        self._drop_area = DropArea("Or drag and drop files/folders here")
        self._drop_area.files_dropped.connect(self.files_dropped.emit)
        layout.addWidget(self._drop_area)
        
        # Apply initial theme
        self.refresh_style()
    
    def refresh_style(self) -> None:
        """Refresh the welcome page style based on current theme."""
        from app.services.settings import SettingsManager
        settings = SettingsManager().settings
        theme = settings.ui.theme
        
        # Check if dark theme or custom theme
        theme_str = str(theme).lower()
        is_dark = theme_str.endswith('dark') or theme_str.endswith('custom')
        
        if is_dark:
            self._subtitle.setStyleSheet("font-size: 14px; margin-bottom: 30px; color: #e0e0e0;")
        else:
            self._subtitle.setStyleSheet("font-size: 14px; margin-bottom: 30px; color: #2c2c2c;")
        
        # Update all buttons
        self._compare_files_btn.update_theme_style()
        self._compare_folders_btn.update_theme_style()
        self._merge_btn.update_theme_style()
        
        # Update drop area if it has a refresh method
        if hasattr(self._drop_area, 'refresh_style'):
            self._drop_area.refresh_style()
