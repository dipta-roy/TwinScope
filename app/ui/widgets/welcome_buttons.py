from PyQt6.QtWidgets import QPushButton, QVBoxLayout, QLabel, QWidget, QApplication, QStyle, QSizePolicy
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon
from typing import Optional

class WelcomeButton(QPushButton):
    """
    Button for the welcome screen with title, description and icon.
    """
    def __init__(self, title: str, description: str, icon_name: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.setMinimumSize(180, 120) # Adjusted size
        self.setMaximumWidth(250)
        self.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.MinimumExpanding)
        
        # Internal layout for icon, title, and description
        layout = QVBoxLayout(self)
        layout.setSpacing(5)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Icon
        icon_label = QLabel()
        icon = self._get_icon(icon_name)
        icon_label.setPixmap(icon.pixmap(QSize(48, 48)))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)
        
        # Title
        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)
        
        # Description
        description_label = QLabel(description)
        description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description_label.setWordWrap(True)
        description_label.setStyleSheet("font-size: 10px; color: palette(text);") # Use palette text color
        layout.addWidget(description_label)
        
        # Store for theme updates
        self._title_label = title_label
        self._description_label = description_label
        self._icon_label = icon_label
        
        # Apply initial styling
        self.update_theme_style()
    
    def update_theme_style(self) -> None:
        """Update button styling based on current theme."""
        from app.services.settings import SettingsManager
        settings = SettingsManager().settings
        theme = settings.ui.theme
        
        # Check if dark theme or custom theme
        theme_str = str(theme).lower()
        is_dark = theme_str.endswith('dark') or theme_str.endswith('custom')
        
        if is_dark:
            self.setStyleSheet("""
                WelcomeButton {
                    border: 1px solid #555555;
                    border-radius: 8px;
                    background-color: #3a3a3a;
                    color: #e0e0e0;
                    text-align: center;
                }
                WelcomeButton:hover {
                    border: 1px solid #2a82da;
                    background-color: #4a4a4a;
                }
                WelcomeButton:pressed {
                    background-color: #5a5a5a;
                }
            """)
            self._title_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #e0e0e0;")
            self._description_label.setStyleSheet("font-size: 10px; color: #b0b0b0;")
        else:
            # Light theme
            self.setStyleSheet("""
                WelcomeButton {
                    border: 1px solid #d0d0d0;
                    border-radius: 8px;
                    background-color: #ffffff;
                    color: #2c2c2c;
                    text-align: center;
                }
                WelcomeButton:hover {
                    border: 1px solid #0078d7;
                    background-color: #f0f0f0;
                }
                WelcomeButton:pressed {
                    background-color: #e0e0e0;
                }
            """)
            self._title_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #2c2c2c;")
            self._description_label.setStyleSheet("font-size: 10px; color: #606060;")

    def _get_icon(self, icon_name: str) -> QIcon:
        """Helper to get QIcon from name."""
        style = QApplication.style()
        if icon_name == "document-compare":
            return style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        elif icon_name == "folder-compare":
            return style.standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        elif icon_name == "merge":
            return style.standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton) # Placeholder, ideally custom icon
        return QIcon() # Fallback empty icon
