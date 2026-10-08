"""
UI theme setup and styling for TwinScope.
"""

from __future__ import annotations
import logging
from typing import Optional
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QStyleFactory
from app.services.settings import SettingsManager, Theme

def setup_theme(app: Optional[QApplication] = None, theme: Optional[Theme] = None) -> None:
    """
    Set up application theme.
    
    Args:
        app: QApplication instance (defaults to QApplication.instance())
        theme: Theme to apply (defaults to theme from settings)
    """
    target_app: Optional[QApplication] = app if isinstance(app, QApplication) else None
    if target_app is None:
        inst = QApplication.instance()
        if isinstance(inst, QApplication):
            target_app = inst
    if target_app is None:
        return

    logging.info(f"Setting up theme: {theme}")

    # Get theme from settings if not specified
    if theme is None:
        manager = SettingsManager()
        theme = manager.settings.ui.theme

    # Clear existing stylesheet before applying new theme
    target_app.setStyleSheet("")

    # Apply theme
    if theme == Theme.DARK:
        _apply_dark_theme(target_app)
    elif theme == Theme.LIGHT:
        _apply_light_theme(target_app)
    elif theme == Theme.CUSTOM:
        _apply_custom_theme(target_app)
    else:
        # System theme - use Fusion style for consistency
        target_app.setStyle(QStyleFactory.create("Fusion"))


def _apply_dark_theme(app: QApplication) -> None:
    """Apply dark theme to application."""
    app.setStyle(QStyleFactory.create("Fusion"))

    dark_palette = QPalette()

    # Base colors
    dark_color = QColor(45, 45, 45)
    darker_color = QColor(35, 35, 35)
    text_color = QColor(212, 212, 212)
    highlight_color = QColor(42, 130, 218)
    disabled_color = QColor(127, 127, 127)

    # Set palette colors
    dark_palette.setColor(QPalette.ColorRole.Window, dark_color)
    dark_palette.setColor(QPalette.ColorRole.WindowText, text_color)
    dark_palette.setColor(QPalette.ColorRole.Base, darker_color)
    dark_palette.setColor(QPalette.ColorRole.AlternateBase, dark_color)
    dark_palette.setColor(QPalette.ColorRole.ToolTipBase, dark_color)
    dark_palette.setColor(QPalette.ColorRole.ToolTipText, text_color)
    dark_palette.setColor(QPalette.ColorRole.Text, text_color)
    dark_palette.setColor(QPalette.ColorRole.Button, dark_color)
    dark_palette.setColor(QPalette.ColorRole.ButtonText, text_color)
    dark_palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    dark_palette.setColor(QPalette.ColorRole.Link, highlight_color)
    dark_palette.setColor(QPalette.ColorRole.Highlight, highlight_color)
    dark_palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)

    # Disabled colors
    dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled_color)
    dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled_color)
    dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled_color)

    app.setPalette(dark_palette)

    # Additional stylesheet for fine-tuning
    app.setStyleSheet("""
        QToolTip {
            color: #d4d4d4;
            background-color: #2d2d2d;
            border: 1px solid #3d3d3d;
            padding: 4px;
        }
        
        QMenuBar {
            background-color: #2d2d2d;
        }
        
        QMenuBar::item:selected {
            background-color: #3d3d3d;
        }
        
        QMenu {
            background-color: #2d2d2d;
            border: 1px solid #3d3d3d;
        }
        
        QMenu::item:selected {
            background-color: #2a82da;
        }
        
        QScrollBar:vertical {
            background: #2d2d2d;
            width: 14px;
        }
        
        QScrollBar::handle:vertical {
            background: #5d5d5d;
            min-height: 20px;
            border-radius: 4px;
            margin: 2px;
        }
        
        QScrollBar::handle:vertical:hover {
            background: #7d7d7d;
        }
        
        QScrollBar:horizontal {
            background: #2d2d2d;
            height: 14px;
        }
        
        QScrollBar::handle:horizontal {
            background: #5d5d5d;
            min-width: 20px;
            border-radius: 4px;
            margin: 2px;
        }
        
        QScrollBar::handle:horizontal:hover {
            background: #7d7d7d;
        }
        
        QTabWidget::pane {
            border: 1px solid #3d3d3d;
        }
        
        QTabBar::tab {
            background-color: #2d2d2d;
            padding: 8px 16px;
            border: 1px solid #3d3d3d;
        }
        
        QTabBar::tab:selected {
            background-color: #3d3d3d;
        }
        
        QSplitter::handle {
            background-color: #3d3d3d;
        }
        
        QSplitter::handle:hover {
            background-color: #2a82da;
        }
    """)


def _apply_light_theme(app: QApplication) -> None:
    """Apply light theme to application."""
    app.setStyle(QStyleFactory.create("Fusion"))

    light_palette = QPalette()

    # Base colors
    light_color = QColor(240, 240, 240)
    white_color = QColor(255, 255, 255)
    text_color = QColor(0, 0, 0)
    highlight_color = QColor(0, 120, 215)
    disabled_color = QColor(160, 160, 160)

    # Set palette colors
    light_palette.setColor(QPalette.ColorRole.Window, light_color)
    light_palette.setColor(QPalette.ColorRole.WindowText, text_color)
    light_palette.setColor(QPalette.ColorRole.Base, white_color)
    light_palette.setColor(QPalette.ColorRole.AlternateBase, light_color)
    light_palette.setColor(QPalette.ColorRole.ToolTipBase, white_color)
    light_palette.setColor(QPalette.ColorRole.ToolTipText, text_color)
    light_palette.setColor(QPalette.ColorRole.Text, text_color)
    light_palette.setColor(QPalette.ColorRole.Button, light_color)
    light_palette.setColor(QPalette.ColorRole.ButtonText, text_color)
    light_palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    light_palette.setColor(QPalette.ColorRole.Link, highlight_color)
    light_palette.setColor(QPalette.ColorRole.Highlight, highlight_color)
    light_palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)

    # Disabled colors
    light_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled_color)
    light_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled_color)
    light_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled_color)

    app.setPalette(light_palette)


def _apply_custom_theme(app: QApplication) -> None:
    """Apply custom theme to application using modern color palette."""
    app.setStyle(QStyleFactory.create("Fusion"))

    custom_palette = QPalette()

    # Modern color palette - Deep navy with vibrant cyan accents
    bg_darkest = QColor("#1e1e2e")
    bg_dark = QColor("#262637")
    bg_medium = QColor("#313244")
    text_primary = QColor("#cdd6f4")
    text_secondary = QColor("#a6adc8")
    accent_primary = QColor("#00d4aa")
    accent_secondary = QColor("#f38ba8")
    accent_tertiary = QColor("#89b4fa")
    text_disabled = QColor("#6c7086")

    # Set palette colors
    custom_palette.setColor(QPalette.ColorRole.Window, bg_dark)
    custom_palette.setColor(QPalette.ColorRole.WindowText, text_primary)
    custom_palette.setColor(QPalette.ColorRole.Base, bg_medium)
    custom_palette.setColor(QPalette.ColorRole.AlternateBase, bg_dark)
    custom_palette.setColor(QPalette.ColorRole.ToolTipBase, bg_darkest)
    custom_palette.setColor(QPalette.ColorRole.ToolTipText, text_primary)
    custom_palette.setColor(QPalette.ColorRole.Text, text_primary)
    custom_palette.setColor(QPalette.ColorRole.Button, bg_medium)
    custom_palette.setColor(QPalette.ColorRole.ButtonText, text_primary)
    custom_palette.setColor(QPalette.ColorRole.BrightText, accent_secondary)
    custom_palette.setColor(QPalette.ColorRole.Link, accent_primary)
    custom_palette.setColor(QPalette.ColorRole.Highlight, accent_primary)
    custom_palette.setColor(QPalette.ColorRole.HighlightedText, bg_darkest)

    # Disabled colors
    custom_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, text_disabled)
    custom_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, text_disabled)
    custom_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, text_disabled)

    app.setPalette(custom_palette)

    app.setStyleSheet(f"""
        /* Tooltips */
        QToolTip {{
            color: {text_primary.name()};
            background-color: {bg_darkest.name()};
            border: 1px solid {accent_primary.name()};
            border-radius: 4px;
            padding: 6px;
        }}
        
        /* Menu Bar */
        QMenuBar {{
            background-color: {bg_dark.name()};
            color: {text_primary.name()};
            border-bottom: 1px solid {bg_medium.name()};
        }}
        
        QMenuBar::item {{
            padding: 6px 12px;
            background-color: transparent;
        }}
        
        QMenuBar::item:selected {{
            background-color: {bg_medium.name()};
            border-radius: 4px;
        }}
        
        QMenuBar::item:pressed {{
            background-color: {accent_primary.name()};
            color: {bg_darkest.name()};
        }}
        
        /* Menus */
        QMenu {{
            background-color: {bg_dark.name()};
            color: {text_primary.name()};
            border: 1px solid {bg_medium.name()};
            border-radius: 6px;
            padding: 4px;
        }}
        
        QMenu::item {{
            padding: 6px 24px;
            border-radius: 4px;
            margin: 2px;
        }}
        
        QMenu::item:selected {{
            background-color: {accent_primary.name()};
            color: {bg_darkest.name()};
        }}
        
        QMenu::separator {{
            height: 1px;
            background-color: {bg_medium.name()};
            margin: 4px 8px;
        }}
        
        /* Scrollbars */
        QScrollBar:vertical {{
            background: {bg_dark.name()};
            width: 12px;
            border-radius: 6px;
            margin: 2px;
        }}
        
        QScrollBar::handle:vertical {{
            background: {accent_tertiary.name()};
            min-height: 30px;
            border-radius: 5px;
            margin: 2px;
        }}
        
        QScrollBar::handle:vertical:hover {{
            background: {accent_primary.name()};
        }}
        
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        
        QScrollBar:horizontal {{
            background: {bg_dark.name()};
            height: 12px;
            border-radius: 6px;
            margin: 2px;
        }}
        
        QScrollBar::handle:horizontal {{
            background: {accent_tertiary.name()};
            min-width: 30px;
            border-radius: 5px;
            margin: 2px;
        }}
        
        QScrollBar::handle:horizontal:hover {{
            background: {accent_primary.name()};
        }}
        
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}
        
        /* Tab Widget */
        QTabWidget::pane {{
            border: 1px solid {bg_medium.name()};
            border-radius: 6px;
            background-color: {bg_dark.name()};
        }}
        
        QTabBar::tab {{
            background-color: {bg_dark.name()};
            color: {text_secondary.name()};
            padding: 8px 16px;
            border: 1px solid {bg_medium.name()};
            border-bottom: none;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            margin-right: 2px;
        }}
        
        QTabBar::tab:selected {{
            background-color: {bg_medium.name()};
            color: {accent_primary.name()};
            border-bottom: 2px solid {accent_primary.name()};
        }}
        
        QTabBar::tab:hover {{
            background-color: {bg_medium.name()};
            color: {text_primary.name()};
        }}
        
        /* Splitter */
        QSplitter::handle {{
            background-color: {bg_medium.name()};
        }}
        
        QSplitter::handle:hover {{
            background-color: {accent_primary.name()};
        }}
        
        QSplitter::handle:vertical {{
            height: 3px;
        }}
        
        QSplitter::handle:horizontal {{
            width: 3px;
        }}
        
        /* Push Buttons */
        QPushButton {{
            background-color: {bg_medium.name()};
            color: {text_primary.name()};
            border: 1px solid {bg_medium.name()};
            border-radius: 6px;
            padding: 6px 16px;
        }}
        
        QPushButton:hover {{
            background-color: {accent_tertiary.name()};
            border: 1px solid {accent_tertiary.name()};
        }}
        
        QPushButton:pressed {{
            background-color: {accent_primary.name()};
            color: {bg_darkest.name()};
        }}
        
        QPushButton:disabled {{
            background-color: {bg_dark.name()};
            color: {text_disabled.name()};
        }}
        
        /* Line Edits */
        QLineEdit {{
            background-color: {bg_medium.name()};
            color: {text_primary.name()};
            border: 1px solid {bg_medium.name()};
            border-radius: 4px;
            padding: 4px 8px;
        }}
        
        QLineEdit:focus {{
            border: 1px solid {accent_primary.name()};
        }}
        
        /* Tool Bar */
        QToolBar {{
            background-color: {bg_dark.name()};
            border-bottom: 1px solid {bg_medium.name()};
            spacing: 4px;
            padding: 4px;
        }}
        
        QToolBar::separator {{
            background-color: {bg_medium.name()};
            width: 1px;
            margin: 4px;
        }}
        
        /* Status Bar */
        QStatusBar {{
            background-color: {bg_dark.name()};
            color: {text_secondary.name()};
            border-top: 1px solid {bg_medium.name()};
        }}
    """)
