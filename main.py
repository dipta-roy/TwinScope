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
from types import TracebackType
from typing import List, Optional

from PyQt6.QtCore import (
    QByteArray,
    QLibraryInfo,
    QLocale,
    QSettings,
    QSharedMemory,
    Qt,
    QTimer,
    QTranslator,
)
from PyQt6.QtGui import QFontDatabase, QIcon, QPixmap
from PyQt6.QtWidgets import QApplication, QMessageBox, QSplashScreen

from app.constants.constants import (
    APP_NAME,
    APP_DISPLAY_NAME,
    APP_VERSION,
    APP_ORGANIZATION,
    APP_DOMAIN,
    RESOURCES_DIR_NAME,
    ICONS_DIR_NAME,
    THEMES_DIR_NAME,
    LOGS_DIR_NAME,
)
from app.services.settings import Theme
from app.ui import resources
from app.ui.theme import setup_theme

# Paths
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    APP_DIR = Path(sys.executable).parent
else:
    # Running as script
    APP_DIR = Path(__file__).parent.parent

RESOURCES_DIR = APP_DIR / RESOURCES_DIR_NAME
ICONS_DIR = RESOURCES_DIR / ICONS_DIR_NAME
THEMES_DIR = RESOURCES_DIR / THEMES_DIR_NAME
LOGS_DIR = APP_DIR / LOGS_DIR_NAME


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
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: Optional[TracebackType]
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
        exc_type: type[BaseException],
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
    
    # Installer support
    parser.add_argument(
        '--create-shortcut',
        action='store_true',
        help='Create desktop shortcut (internal use)'
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
    
    # Check for shortcut creation request
    if parsed.create_shortcut:
        create_desktop_shortcut()
        sys.exit(0)
    
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


def create_desktop_shortcut():
    """Create a desktop shortcut for the application."""
    try:
        from pathlib import Path

        import win32com.client
        
        # Get paths
        if getattr(sys, 'frozen', False):
            target_path = sys.executable
        else:
            target_path = sys.argv[0]
            
        target_path = str(Path(target_path).resolve())
        work_dir = str(Path(target_path).parent)
        
        desktop = Path(os.environ['USERPROFILE']) / 'Desktop'
        shortcut_path = desktop / f"{APP_DISPLAY_NAME}.lnk"
        
        # Create shortcut
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(str(shortcut_path))
        shortcut.TargetPath = target_path
        shortcut.WorkingDirectory = work_dir
        shortcut.IconLocation = target_path
        shortcut.WindowStyle = 1  # Normal window
        shortcut.Description = "TwinScope File Comparison Tool"
        shortcut.Save()
        
    except Exception as e:
        # Silently fail or log to a file if possible, as we don't have a console
        with open(os.path.join(os.environ['TEMP'], 'twinscope_shortcut_error.log'), 'w') as f:
            f.write(str(e))
        sys.exit(1)


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
            _app = QApplication(sys.argv)
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
        setup_settings(args)
        
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
