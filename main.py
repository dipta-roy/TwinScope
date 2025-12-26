"""
Main entry point for the File Comparison application.

This module handles:
- Application initialization
- Command line argument parsing
- Logging configuration
- Theme and style setup
- Main window creation
- Exception handling
- Single instance management
- Session restoration
"""

from __future__ import annotations

import argparse
import faulthandler
import logging
import os
import signal
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Optional, List, NoReturn

from PyQt6.QtCore import (
    Qt, QSettings, QTranslator, QLocale, QLibraryInfo,
    QSharedMemory, QTimer, QThread, QCoreApplication, QByteArray
)
from PyQt6.QtGui import (
    QFont, QFontDatabase, QIcon, QPalette, QColor, QPixmap
)
from PyQt6.QtWidgets import (
    QApplication, QMessageBox, QSplashScreen, QStyleFactory
)

from app.ui import resources


# =============================================================================
# Constants
# =============================================================================

APP_NAME = "FileCompare"
APP_DISPLAY_NAME = "File Compare"
APP_VERSION = "1.1.0"
APP_ORGANIZATION = "FileCompare"
APP_DOMAIN = "filecompare.example.com"

# Paths
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    APP_DIR = Path(sys.executable).parent
else:
    # Running as script
    APP_DIR = Path(__file__).parent.parent

RESOURCES_DIR = APP_DIR / "resources"
ICONS_DIR = RESOURCES_DIR / "icons"
THEMES_DIR = RESOURCES_DIR / "themes"
LOGS_DIR = APP_DIR / "logs"


# =============================================================================
# Enums
# =============================================================================

class StartupMode(Enum):
    """Application startup mode."""
    NORMAL = auto()
    FILE_COMPARE = auto()
    FOLDER_COMPARE = auto()
    MERGE = auto()
    LAST_SESSION = auto()


from app.services.settings import Theme


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class CommandLineArgs:
    """Parsed command line arguments."""
    left_path: Optional[str] = None
    right_path: Optional[str] = None
    base_path: Optional[str] = None
    output_path: Optional[str] = None
    mode: StartupMode = StartupMode.NORMAL
    theme: Optional[Theme] = None
    config_file: Optional[str] = None
    log_level: str = "INFO"
    no_plugins: bool = False
    reset_settings: bool = False
    new_instance: bool = False
    debug: bool = False


# =============================================================================
# Logging Setup
# =============================================================================

class LogFormatter(logging.Formatter):
    """Custom log formatter with colors for console."""
    
    COLORS = {
        logging.INFO: '\033[32m',      # Green
        logging.WARNING: '\033[33m',   # Yellow
        logging.ERROR: '\033[31m',     # Red
        logging.CRITICAL: '\033[35m',  # Magenta
    }
    RESET = '\033[0m'
    
    def __init__(self, use_colors: bool = True):
        super().__init__(
            fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.use_colors = use_colors and sys.stdout.isatty()
    
    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        
        if self.use_colors:
            color = self.COLORS.get(record.levelno, '')
            return f"{color}{formatted}{self.RESET}"
        
        return formatted


def setup_logging(level: str = "INFO", log_file: Optional[Path] = None) -> logging.Logger:
    """
    Configure application logging.
    
    Args:
        level: Log level string
        log_file: Optional file path for logging
        
    Returns:
        Root logger instance
    """
    # Get numeric level
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Remove existing handlers
    root_logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(LogFormatter(use_colors=True))
    root_logger.addHandler(console_handler)
    
    # File handler
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(
            log_file,
            encoding='utf-8'
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(LogFormatter(use_colors=False))
        root_logger.addHandler(file_handler)
    
    # Reduce noise from third-party libraries
    logging.getLogger('PIL').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    
    return root_logger


# =============================================================================
# Exception Handling
# =============================================================================

class ExceptionHandler:
    """
    Global exception handler for unhandled exceptions. 
    
    Shows error dialog and logs the exception.
    """
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self._app: Optional[QApplication] = None
    
    def set_application(self, app: QApplication) -> None: 
        """Set the application instance for error dialogs."""
        self._app = app
    
    def handle_exception(
        self,
        exc_type: type,
        exc_value: BaseException,
        exc_tb
    ) -> None:
        """Handle an unhandled exception."""
        # Don't handle keyboard interrupt
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        
        # Log the exception
        self.logger.critical(
            "Unhandled exception",
            exc_info=(exc_type, exc_value, exc_tb)
        )
        
        # Format traceback
        tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
        tb_text = ''.join(tb_lines)
        
        # Show error dialog if application is running
        if self._app and QApplication.instance():
            self._show_error_dialog(exc_type, exc_value, tb_text)
    
    def _show_error_dialog(
        self,
        exc_type: type,
        exc_value: BaseException,
        traceback_text: str
    ) -> None:
        """Show error dialog to user."""
        dialog = QMessageBox()
        dialog.setIcon(QMessageBox.Icon.Critical)
        dialog.setWindowTitle("Application Error")
        dialog.setText(f"An unexpected error occurred:\n\n{exc_type.__name__}: {exc_value}")
        dialog.setDetailedText(traceback_text)
        dialog.setStandardButtons(
            QMessageBox.StandardButton.Ok |
            QMessageBox.StandardButton.Close
        )
        dialog.setDefaultButton(QMessageBox.StandardButton.Ok)
        
        # Add "Report Bug" button
        report_btn = dialog.addButton(
            "Copy to Clipboard",
            QMessageBox.ButtonRole.ActionRole
        )
        
        result = dialog.exec()
        
        if dialog.clickedButton() == report_btn:
            clipboard = QApplication.clipboard()
            clipboard.setText(traceback_text)
        
        if result == QMessageBox.StandardButton.Close:
            QApplication.quit()


# =============================================================================
# Single Instance
# =============================================================================

class SingleInstanceGuard:
    """
    Ensures only one instance of the application runs.
    
    Uses shared memory to detect existing instances.
    """
    
    def __init__(self, key: str):
        self._key = key
        self._shared_memory = QSharedMemory(key)
        self._is_primary = False
    
    def try_lock(self) -> bool:
        """
        Try to become the primary instance.
        
        Returns:
            True if this is the primary instance
        """
        # Try to attach to existing
        if self._shared_memory.attach():
            return False
        
        # Create new shared memory
        if self._shared_memory.create(1):
            self._is_primary = True
            return True
        
        return False
    
    def release(self) -> None:
        """Release the lock."""
        if self._is_primary:
            self._shared_memory.detach()
            self._is_primary = False
    
    def is_primary(self) -> bool:
        """Check if this is the primary instance."""
        return self._is_primary


# =============================================================================
# Command Line Parsing
# =============================================================================

def parse_arguments(args: Optional[List[str]] = None) -> CommandLineArgs:
    """
    Parse command line arguments.
    
    Args:
        args: Arguments to parse (defaults to sys.argv)
        
    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description="Professional file and folder comparison tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s file1.txt file2.txt           Compare two files
  %(prog)s -d folder1 folder2            Compare two folders
  %(prog)s -m base.txt left.txt right.txt    Three-way merge
  %(prog)s --theme dark                  Start with dark theme
        """
    )
    
    # Positional arguments
    parser.add_argument(
        'left',
        nargs='?',
        help='Left file or folder to compare'
    )
    parser.add_argument(
        'right',
        nargs='?',
        help='Right file or folder to compare'
    )
    
    # Mode selection
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        '-d', '--directory',
        action='store_true',
        help='Compare directories'
    )
    mode_group.add_argument(
        '-m', '--merge',
        action='store_true',
        help='Three-way merge mode'
    )
    mode_group.add_argument(
        '-r', '--restore',
        action='store_true',
        help='Restore last session'
    )
    
    # Merge options
    parser.add_argument(
        '-b', '--base',
        help='Base file for three-way merge'
    )
    parser.add_argument(
        '-o', '--output',
        help='Output file for merge'
    )
    
    # Display options
    parser.add_argument(
        '--theme',
        choices=['system', 'light', 'dark', 'custom'],
        default=None,
        help='Application theme'
    )
    
    # Configuration
    parser.add_argument(
        '-c', '--config',
        help='Configuration file path'
    )
    parser.add_argument(
        '--reset-settings',
        action='store_true',
        help='Reset all settings to defaults'
    )
    
    # Logging
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode'
    )
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        default='INFO',
        help='Log level'
    )
    
    # Instance control
    parser.add_argument(
        '-n', '--new-instance',
        action='store_true',
        help='Start new instance even if one is running'
    )
    
    # Plugins
    parser.add_argument(
        '--no-plugins',
        action='store_true',
        help='Disable plugins'
    )
    
    # Version
    parser.add_argument(
        '--version',
        action='version',
        version=f'{APP_NAME} {APP_VERSION}'
    )
    
    # Parse
    parsed = parser.parse_args(args)
    
    # Build result
    result = CommandLineArgs()
    result.left_path = parsed.left
    result.right_path = parsed.right
    result.base_path = parsed.base
    result.output_path = parsed.output
    result.config_file = parsed.config
    result.no_plugins = parsed.no_plugins
    result.reset_settings = parsed.reset_settings
    result.new_instance = parsed.new_instance
    result.debug = parsed.debug
    
    # Determine mode
    if parsed.restore:
        result.mode = StartupMode.LAST_SESSION
    elif parsed.merge:
        result.mode = StartupMode.MERGE
    elif parsed.directory:
        result.mode = StartupMode.FOLDER_COMPARE
    elif parsed.left and parsed.right:
        # Auto-detect mode based on paths
        left_path = Path(parsed.left)
        right_path = Path(parsed.right)
        
        if left_path.is_dir() and right_path.is_dir():
            result.mode = StartupMode.FOLDER_COMPARE
        else:
            result.mode = StartupMode.FILE_COMPARE
    else:
        result.mode = StartupMode.NORMAL
    
    # Theme
    if parsed.theme:
        result.theme = Theme.from_string(parsed.theme)
    
    # Log level
    if parsed.debug:
        result.log_level = 'DEBUG'
    elif parsed.verbose:
        result.log_level = 'DEBUG'
    else:
        result.log_level = parsed.log_level
    
    return result


def set_app_icon(app: QApplication) -> None:
    """Set the application icon."""
    pixmap = QPixmap()
    pixmap.loadFromData(QByteArray.fromBase64(resources.LOGO_BASE64.encode()))
    app.setWindowIcon(QIcon(pixmap))


# =============================================================================
# Application Setup
# =============================================================================

def setup_application(args: CommandLineArgs) -> QApplication:
    """
    Create and configure the QApplication.
    
    Args:
        args: Parsed command line arguments
        
    Returns:
        Configured QApplication instance
    """
    # High DPI settings (must be before QApplication creation)
    # Qt6 enables high DPI by default
    
    # Create application
    app = QApplication(sys.argv)
    
    # Set application metadata
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_ORGANIZATION)
    app.setOrganizationDomain(APP_DOMAIN)
    
    # Set application icon
    set_app_icon(app)
    
    # Enable quit on last window closed
    app.setQuitOnLastWindowClosed(True)
    
    return app


def setup_settings(args: CommandLineArgs) -> QSettings:
    """
    Set up application settings.
    
    Args:
        args: Parsed command line arguments
        
    Returns:
        QSettings instance
    """
    # Use INI format for cross-platform compatibility
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    
    settings = QSettings()
    
    # Reset if requested
    if args.reset_settings:
        settings.clear()
        settings.sync()
    
    return settings


def setup_fonts(app: QApplication) -> None:
    """
    Set up application fonts.
    
    Args:
        app: QApplication instance
    """
    # Load custom fonts
    fonts_dir = RESOURCES_DIR / "fonts"
    if fonts_dir.exists():
        for font_file in fonts_dir.glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(font_file))
        for font_file in fonts_dir.glob("*.otf"):
            QFontDatabase.addApplicationFont(str(font_file))
    
    # Set default monospace font for code views
    monospace_fonts = [
        "JetBrains Mono",
        "Fira Code",
        "Source Code Pro",
        "Consolas",
        "Monaco",
        "Courier New",
    ]
    
    available_fonts = QFontDatabase.families()
    
    for font_name in monospace_fonts:
        if font_name in available_fonts:
            # Store preferred monospace font in settings
            settings = QSettings()
            if not settings.contains("appearance/monospace_font"):
                settings.setValue("appearance/monospace_font", font_name)
            break


def setup_theme(app: QApplication, theme: Optional[Theme] = None) -> None:
    """
    Set up application theme.
    
    Args:
        app: QApplication instance
        theme: Theme to apply
    """
    logging.info(f"Setting up theme: {theme}")
    # Get theme from settings if not specified
    if theme is None:
        from app.services.settings import SettingsManager
        manager = SettingsManager()
        theme = manager.settings.ui.theme
    
    # Clear existing stylesheet before applying new theme
    app.setStyleSheet("")
    
    # Apply theme
    if theme == Theme.DARK:
        _apply_dark_theme(app)
    elif theme == Theme.LIGHT:
        _apply_light_theme(app)
    elif theme == Theme.CUSTOM:
        _apply_custom_theme(app)
    else:
        # System theme - use Fusion style for consistency
        app.setStyle(QStyleFactory.create("Fusion"))


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
    bg_darkest = QColor("#1e1e2e")      # Deep navy/charcoal background
    bg_dark = QColor("#262637")         # Slightly lighter background
    bg_medium = QColor("#313244")       # Medium background for inputs
    text_primary = QColor("#cdd6f4")    # Soft white text
    text_secondary = QColor("#a6adc8")  # Muted text
    accent_primary = QColor("#00d4aa")  # Vibrant cyan/teal
    accent_secondary = QColor("#f38ba8") # Soft pink for secondary accents
    accent_tertiary = QColor("#89b4fa")  # Soft blue
    text_disabled = QColor("#6c7086")   # Disabled text
    
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
    
    # Comprehensive stylesheet for modern look
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



def setup_translations(app: QApplication) -> None:
    """
    Set up translations.
    
    Args:
        app: QApplication instance
    """
    # Qt built-in translations
    qt_translator = QTranslator(app)
    translations_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    
    if qt_translator.load(QLocale.system(), "qt", "_", translations_path):
        app.installTranslator(qt_translator)
    
    # Application translations
    app_translator = QTranslator(app)
    translations_dir = RESOURCES_DIR / "translations"
    
    if translations_dir.exists():
        locale = QLocale.system().name()
        if app_translator.load(f"filecompare_{locale}", str(translations_dir)):
            app.installTranslator(app_translator)


def show_splash_screen(app: QApplication) -> Optional[QSplashScreen]:
    """
    Show splash screen during startup.
    
    Args:
        app: QApplication instance
        
    Returns:
        QSplashScreen instance or None
    """
    splash_path = RESOURCES_DIR / "splash.png"
    
    if splash_path.exists():
        pixmap = QPixmap(str(splash_path))
        splash = QSplashScreen(pixmap)
        splash.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint
        )
        splash.show()
        
        # Process events to show splash immediately
        app.processEvents()
        
        return splash
    
    return None


def update_splash(splash: Optional[QSplashScreen], message: str) -> None:
    """Update splash screen message."""
    if splash:
        splash.showMessage(
            message,
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
            Qt.GlobalColor.white
        )
        QApplication.processEvents()


# =============================================================================
# Main Window Creation
# =============================================================================

def create_main_window(args: CommandLineArgs):
    """
    Create and configure the main window.
    
    Args:
        args: Parsed command line arguments
        
    Returns:
        MainWindow instance
    """
    from app.ui.main_window import MainWindow
    
    window = MainWindow()
    
    # Apply startup mode
    if args.mode == StartupMode.FILE_COMPARE:
        if args.left_path and args.right_path:
            window.compare_files(args.left_path, args.right_path)
    
    elif args.mode == StartupMode.FOLDER_COMPARE:
        if args.left_path and args.right_path:
            window.compare_folders(args.left_path, args.right_path)
    
    elif args.mode == StartupMode.MERGE:
        if args.base_path and args.left_path and args.right_path:
            window.show_merge(
                args.base_path,
                args.left_path,
                args.right_path,
                args.output_path
            )
    
    elif args.mode == StartupMode.LAST_SESSION:
        window.restore_session()
    
    return window


# =============================================================================
# Signal Handlers
# =============================================================================

def setup_signal_handlers() -> None:
    """Set up Unix signal handlers."""
    if sys.platform != 'win32':
        # Handle SIGINT (Ctrl+C) gracefully
        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)
        
        # Allow Qt to process signals
        timer = QTimer()
        timer.timeout.connect(lambda: None)
        timer.start(500)


def _signal_handler(signum, frame) -> None:
    """Handle Unix signals."""
    logging.info(f"Received signal {signum}, shutting down...")
    QApplication.quit()


# =============================================================================
# Cleanup
# =============================================================================

def cleanup(
    logger: logging.Logger,
    instance_guard: Optional[SingleInstanceGuard] = None
) -> None:
    """
    Perform cleanup on application exit.
    
    Args:
        logger: Logger instance
        instance_guard: Single instance guard to release
    """
    logger.info("Cleaning up...")
    
    # Release single instance lock
    if instance_guard:
        instance_guard.release()
    
    # Clean up temporary files
    try:
        from app.services.file_io import TempFileManager
        # Note: Actual cleanup would be done by context manager
    except ImportError:
        pass
    
    logger.info("Cleanup complete")


# =============================================================================
# Main Function
# =============================================================================

def main() -> int:
    """
    Application main entry point.
    
    Returns:
        Exit code (0 for success)
    """
    # Redirect stdout/stderr if None (common in frozen apps)
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w')
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w')

    # Enable faulthandler for debugging crashes
    faulthandler.enable()
    
    # Parse command line arguments
    args = parse_arguments()
    
    # Set up logging
    log_file = LOGS_DIR / f"{APP_NAME}_{datetime.now():%Y%m%d}.log" if args.debug else None
    logger = setup_logging(args.log_level, log_file)
    logger.info(f"Starting {APP_NAME} v{APP_VERSION}")
    
    # Set up exception handler
    exception_handler = ExceptionHandler(logger)
    sys.excepthook = exception_handler.handle_exception
    
    # Single instance check
    instance_guard = None
    if not args.new_instance:
        instance_guard = SingleInstanceGuard(f"{APP_NAME}_instance")
        
        if not instance_guard.try_lock():
            logger.warning("Another instance is already running")
            
            # TODO: Send arguments to existing instance
            # For now, just show a message
            temp_app = QApplication(sys.argv)
            QMessageBox.warning(
                None,
                APP_NAME,
                "Another instance of the application is already running.\n\nUse --new-instance to start a new instance."
            )
            return 1
    
    try:
        # Create application
        app = setup_application(args)
        exception_handler.set_application(app)
        
        # Show splash screen
        splash = show_splash_screen(app)
        
        # Setup
        update_splash(splash, "Loading settings...")
        settings = setup_settings(args)
        
        update_splash(splash, "Setting up fonts...")
        setup_fonts(app)
        
        update_splash(splash, "Applying theme...")
        setup_theme(app, args.theme)
        
        update_splash(splash, "Loading translations...")
        setup_translations(app)
        
        update_splash(splash, "Initializing...")
        setup_signal_handlers()
        
        # Create main window
        update_splash(splash, "Creating main window...")
        main_window = create_main_window(args)
        
        # Close splash and show main window
        if splash:
            splash.finish(main_window)
        
        main_window.show()
        
        logger.info("Application started successfully")
        
        # Run event loop
        exit_code = app.exec()
        
        # Cleanup
        cleanup(logger, instance_guard)
        
        logger.info(f"Application exiting with code {exit_code}")
        return exit_code
        
    except Exception as e:
        logger.critical(f"Fatal error during startup: {e}", exc_info=True)
        
        # Show error message if possible
        if QApplication.instance():
            QMessageBox.critical(
                None,
                "Fatal Error",
                f"The application failed to start:\n\n{e}\n\n" 
                "Please check the logs for more information."
            )
        
        cleanup(logger, instance_guard)
        return 1


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == '__main__':
    sys.exit(main())
