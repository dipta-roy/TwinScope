"""
Main application window.

Provides the primary UI container with:
- Menu bar
- Toolbar
- Central widget area (stacked views)
- Status bar
- Docking support
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any, Optional

from PyQt6.QtCore import Qt, QSize, pyqtSignal, pyqtSlot, QTimer, QByteArray
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QCloseEvent, QDragEnterEvent, QDropEvent, QPixmap
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QMenuBar, QMenu, QToolBar,
    QStatusBar, QFileDialog, QMessageBox, QApplication,
    QSplitter, QLabel, QProgressBar, QDockWidget, QPushButton, QTabWidget, # QTabWidget added
)

from app.ui.file_compare_view import FileCompareView
from app.ui.folder_compare_view import FolderCompareView
from app.ui.merge_view import MergeView
from app.ui.widgets.dialogs import (
    SettingsDialog, AboutDialog, CompareOptionsDialog,
    OpenFilesDialog, OpenFoldersDialog, HelpDialog, ThreeWayMergeDialog, HashVerifyDialog, SyncDialog # Added missing dialogs
)
from app.services.settings import SettingsManager, ApplicationSettings
from app.workers.compare_worker import (
    TextCompareWorker, FolderCompareWorker, BinaryCompareWorker, ImageCompareWorker
)
from app.workers.base_worker import WorkerThread
from app.ui import resources
from main import setup_theme, APP_NAME, APP_VERSION # Import setup_theme and app constants
from app.ui.widgets.drop_area import DropArea # Import DropArea
from app.ui.widgets.welcome_buttons import WelcomeButton
from app.ui.widgets.welcome_page import WelcomePage
from app.services.file_io import FileIOService, ReadResult
from app.core.diff.binary_diff import BinaryCompareOptions
from app.core.diff.text_diff import TextCompareOptions, WhitespaceMode
from app.core.diff.image_diff import ImageCompareOptions
from app.core.folder.comparer import CompareOptions
from app.ui.widgets.file_preview import FilePreviewPanel


class MainWindow(QMainWindow):
    """
    Main application window.
    
    Manages the overall application layout and coordinates
    between different views.
    """
    
    # Signals
    # comparison_started = pyqtSignal()
    # comparison_finished = pyqtSignal(object)
    comparison_error = pyqtSignal(str)
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self._settings_manager = SettingsManager()
        self._settings = self._settings_manager.settings # Load settings initially
        
        # Trim recent comparisons list immediately after loading settings
        limit = self._settings.ui.recent_history_limit
        self._settings.recent_comparisons = self._settings.recent_comparisons[:limit]
        
        self._current_worker: Optional[WorkerThread] = None
        self._position_label: Optional[QLabel] = None 
        self._stats_label: Optional[QLabel] = None
        self._stats_identical: Optional[QLabel] = None
        self._stats_modified: Optional[QLabel] = None
        self._stats_left_only: Optional[QLabel] = None
        self._stats_right_only: Optional[QLabel] = None
        self._progress_bar: Optional[QProgressBar] = None
        self._sidebar_widget: Optional[QWidget] = None # Added for sidebar
        self._splitter: Optional[QSplitter] = None # Added for splitter
        
        # Register for settings changes
        self._settings_manager.add_observer(self._on_settings_changed)
        
        self._setup_ui()
        self._setup_menus()
        self._setup_toolbar()
        self._setup_statusbar()
        self._setup_connections() # Note: _setup_connections will need adjustment
        self._load_settings()
        
        # Accept drops
        self.setAcceptDrops(True)

        # Hide toolbar on welcome page
        self._main_toolbar.hide()
        # Update menu action checked state
        if hasattr(self, '_action_toggle_main_toolbar'):
            self._action_toggle_main_toolbar.setChecked(False)
    
    def _setup_ui(self) -> None:
        """Set up the main UI layout."""
        self.setWindowTitle("TwinScope")
        self.setMinimumSize(800, 600)
        
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(self._splitter)
        
        # Create and add sidebar
        self._sidebar_widget = self._create_sidebar_widget()
        self._splitter.addWidget(self._sidebar_widget)
        
        # Main content area (tab widget)
        self._stack = QTabWidget() 
        self._stack.setTabsClosable(True)
        self._stack.tabCloseRequested.connect(self._close_tab)
        
        # Add a container widget for the _stack to apply layout correctly if needed
        # For a simple QTabWidget, adding it directly to the splitter is fine.
        main_content_container = QWidget()
        main_content_layout = QVBoxLayout(main_content_container)
        main_content_layout.setContentsMargins(0, 0, 0, 0)
        main_content_layout.setSpacing(0)
        main_content_layout.addWidget(self._stack)
        
        self._splitter.addWidget(main_content_container)
        
        # Set initial sizes for splitter (sidebar small, main content large)
        self._splitter.setSizes([150, 600]) # Example sizes, can be adjusted
        
        # Welcome/start page as the first tab
        self._welcome_page = self._create_welcome_page()
        self._stack.addTab(self._welcome_page, "Welcome") 
        
        # Start with welcome page selected
        self._stack.setCurrentWidget(self._welcome_page)
        

        
    def _create_sidebar_widget(self) -> QWidget:
        """Create the sidebar widget with recent comparisons."""
        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(10, 10, 10, 10)
        sidebar.setStyleSheet(
            "background-color: #c04944;"
            "color: #fdfefe;"
        )
        
        recent_label = QLabel("Recent Comparisons")
        recent_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #fdfefe;")
        sidebar_layout.addWidget(recent_label)
        
        self._recent_list = QWidget()
        self._recent_layout = QVBoxLayout(self._recent_list)
        self._recent_layout.setContentsMargins(0, 10, 0, 0)
        sidebar_layout.addWidget(self._recent_list)
        
        sidebar_layout.addStretch() # Push content to the top
        
        return sidebar
    
    def _create_welcome_page(self) -> QWidget:
        """Create the welcome/start page."""
        page = WelcomePage()
        page.compare_files_requested.connect(self._on_compare_files)
        page.compare_folders_requested.connect(self._on_compare_folders)
        page.merge_requested.connect(self._on_three_way_merge)
        page.files_dropped.connect(self._on_files_dropped_from_area)
        return page
    
    def _setup_menus(self) -> None:
        """Set up the menu bar."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        
        self._action_compare_files = QAction("Compare &Files...", self)
        self._action_compare_files.setShortcut(QKeySequence("Ctrl+O"))
        self._action_compare_files.triggered.connect(self._on_compare_files)
        file_menu.addAction(self._action_compare_files)
        
        self._action_compare_folders = QAction("Compare F&olders...", self)
        self._action_compare_folders.setShortcut(QKeySequence("Ctrl+Shift+O"))
        self._action_compare_folders.triggered.connect(self._on_compare_folders)
        file_menu.addAction(self._action_compare_folders)
        
        self._action_three_way = QAction("&Three-Way Merge...", self)
        self._action_three_way.setShortcut(QKeySequence("Ctrl+M"))
        self._action_three_way.triggered.connect(self._on_three_way_merge)
        file_menu.addAction(self._action_three_way)
        
        file_menu.addSeparator()
        
        self._action_save = QAction("&Save", self)
        self._action_save.setShortcut(QKeySequence.StandardKey.Save)
        self._action_save.triggered.connect(self._on_save)
        self._action_save.setEnabled(False)
        file_menu.addAction(self._action_save)
        
        self._action_save_as = QAction("Save &As...", self)
        self._action_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        self._action_save_as.triggered.connect(self._on_save_as)
        self._action_save_as.setEnabled(False)
        file_menu.addAction(self._action_save_as)
        
        file_menu.addSeparator()
        
        # Recent files submenu
        self._recent_menu = file_menu.addMenu("&Recent")
        self._update_recent_menu()
        
        # Add clear history action
        self._action_clear_history = QAction("Clear History", self)
        self._action_clear_history.triggered.connect(self._clear_recent)
        file_menu.addAction(self._action_clear_history)
        
        file_menu.addSeparator()
        
        self._action_close_file = QAction("&Close File", self)
        self._action_close_file.setShortcut(QKeySequence("Ctrl+W"))
        self._action_close_file.triggered.connect(self._on_close_current_file)
        file_menu.addAction(self._action_close_file)
        
        self._action_exit = QAction("E&xit", self)
        self._action_exit.setShortcut(QKeySequence.StandardKey.Quit)
        self._action_exit.triggered.connect(self.close)
        file_menu.addAction(self._action_exit)
        
        # Edit menu
        edit_menu = menubar.addMenu("&Edit")
        
        self._action_copy = QAction("&Copy", self)
        self._action_copy.setShortcut(QKeySequence.StandardKey.Copy)
        self._action_copy.triggered.connect(self._on_copy)
        edit_menu.addAction(self._action_copy)
        
        self._action_find = QAction("&Find...", self)
        self._action_find.setShortcut(QKeySequence.StandardKey.Find)
        self._action_find.triggered.connect(self._on_find)
        edit_menu.addAction(self._action_find)
        
        self._action_find_next = QAction("Find &Next", self)
        self._action_find_next.setShortcut(QKeySequence.StandardKey.FindNext)
        self._action_find_next.triggered.connect(self._on_find_next)
        edit_menu.addAction(self._action_find_next)
        
        edit_menu.addSeparator()
        
        self._action_preferences = QAction("&Preferences...", self)
        self._action_preferences.setShortcut(QKeySequence.StandardKey.Preferences)
        self._action_preferences.triggered.connect(self._on_preferences)
        edit_menu.addAction(self._action_preferences)
        
        # View menu
        view_menu = menubar.addMenu("&View")
        
        self._action_toggle_line_numbers = QAction("Show &Line Numbers", self)
        self._action_toggle_line_numbers.setCheckable(True)
        self._action_toggle_line_numbers.setChecked(True)
        self._action_toggle_line_numbers.triggered.connect(self._on_toggle_line_numbers)
        view_menu.addAction(self._action_toggle_line_numbers)
        
        self._action_toggle_whitespace = QAction("Show &Whitespace", self)
        self._action_toggle_whitespace.setCheckable(True)
        self._action_toggle_whitespace.triggered.connect(self._on_toggle_whitespace)
        view_menu.addAction(self._action_toggle_whitespace)
        
        self._action_word_wrap = QAction("&Word Wrap", self)
        self._action_word_wrap.setCheckable(True)
        self._action_word_wrap.triggered.connect(self._on_toggle_word_wrap)
        view_menu.addAction(self._action_word_wrap)
        
        view_menu.addSeparator() # Separator after general display options

        self._action_toggle_main_toolbar = QAction("Show Main &Toolbar", self)
        self._action_toggle_main_toolbar.setCheckable(True)
        self._action_toggle_main_toolbar.setChecked(True) # Toolbar is visible by default
        self._action_toggle_main_toolbar.triggered.connect(self._on_toggle_main_toolbar)
        view_menu.addAction(self._action_toggle_main_toolbar)

        view_menu.addSeparator() # Separator before diff view options
        
        self._action_unified_diff = QAction("&Unified Diff View", self)
        self._action_unified_diff.setCheckable(True)
        self._action_unified_diff.triggered.connect(self._on_toggle_unified)
        view_menu.addAction(self._action_unified_diff)
        
        self._action_side_by_side = QAction("&Side-by-Side View", self)
        self._action_side_by_side.setCheckable(True)
        self._action_side_by_side.setChecked(True)
        self._action_side_by_side.triggered.connect(self._on_toggle_side_by_side)
        view_menu.addAction(self._action_side_by_side)
        
        view_menu.addSeparator()
        
        self._action_refresh = QAction("&Refresh", self)
        self._action_refresh.setShortcut(QKeySequence.StandardKey.Refresh)
        self._action_refresh.triggered.connect(self._on_refresh)
        view_menu.addAction(self._action_refresh)
        
        # Navigate menu
        navigate_menu = menubar.addMenu("&Navigate")
        
        self._action_next_diff = QAction("&Next Difference", self)
        self._action_next_diff.setShortcut(QKeySequence("F8"))
        self._action_next_diff.triggered.connect(self._on_next_diff)
        navigate_menu.addAction(self._action_next_diff)
        
        self._action_prev_diff = QAction("&Previous Difference", self)
        self._action_prev_diff.setShortcut(QKeySequence("Shift+F8"))
        self._action_prev_diff.triggered.connect(self._on_prev_diff)
        navigate_menu.addAction(self._action_prev_diff)
        
        self._action_first_diff = QAction("&First Difference", self)
        self._action_first_diff.setShortcut(QKeySequence("Ctrl+Home"))
        self._action_first_diff.triggered.connect(self._on_first_diff)
        navigate_menu.addAction(self._action_first_diff)
        
        self._action_last_diff = QAction("&Last Difference", self)
        self._action_last_diff.setShortcut(QKeySequence("Ctrl+End"))
        self._action_last_diff.triggered.connect(self._on_last_diff)
        navigate_menu.addAction(self._action_last_diff)
        
        navigate_menu.addSeparator()
        
        self._action_goto_line = QAction("&Go to Line...", self)
        self._action_goto_line.setShortcut(QKeySequence("Ctrl+G"))
        self._action_goto_line.triggered.connect(self._on_goto_line)
        navigate_menu.addAction(self._action_goto_line)
        
        # Merge menu
        merge_menu = menubar.addMenu("&Merge")
        
        self._action_copy_left_to_right = QAction("Copy &Left to Right", self)
        self._action_copy_left_to_right.setShortcut(QKeySequence("Alt+Right"))
        self._action_copy_left_to_right.triggered.connect(self._on_copy_left_to_right)
        merge_menu.addAction(self._action_copy_left_to_right)
        
        self._action_copy_right_to_left = QAction("Copy &Right to Left", self)
        self._action_copy_right_to_left.setShortcut(QKeySequence("Alt+Left"))
        self._action_copy_right_to_left.triggered.connect(self._on_copy_right_to_left)
        merge_menu.addAction(self._action_copy_right_to_left)
        
        merge_menu.addSeparator()
        
        self._action_use_left = QAction("Use &Left for All", self)
        self._action_use_left.triggered.connect(self._on_use_left_all)
        merge_menu.addAction(self._action_use_left)
        
        self._action_use_right = QAction("Use &Right for All", self)
        self._action_use_right.triggered.connect(self._on_use_right_all)
        merge_menu.addAction(self._action_use_right)
        
        # Tools menu
        tools_menu = menubar.addMenu("&Tools")
        
        self._action_sync_folders = QAction("&Synchronize Folders...", self)
        self._action_sync_folders.triggered.connect(self._on_sync_folders)
        tools_menu.addAction(self._action_sync_folders)
        
        self._action_generate_report = QAction("&Generate Report...", self)
        self._action_generate_report.triggered.connect(self._on_generate_report)
        tools_menu.addAction(self._action_generate_report)
        
        tools_menu.addSeparator()
        
        self._action_verify_hashes = QAction("&Verify File Hashes...", self)
        self._action_verify_hashes.triggered.connect(self._on_verify_hashes)
        tools_menu.addAction(self._action_verify_hashes)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        
        self._action_help = QAction("&Help Contents", self)
        self._action_help.setShortcut(QKeySequence.StandardKey.HelpContents)
        self._action_help.triggered.connect(self._on_help)
        help_menu.addAction(self._action_help)
        
        self._action_about = QAction("&About", self)
        self._action_about.triggered.connect(self._on_about)
        help_menu.addAction(self._action_about)
    
    def _setup_toolbar(self) -> None:
        """Set up the toolbar."""
        self._main_toolbar = QToolBar("Main Toolbar")
        self._main_toolbar.setObjectName("MainToolbar")
        self._main_toolbar.setMovable(False)
        self._main_toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(self._main_toolbar)
        
        self._main_toolbar.addAction(self._action_compare_files)
        self._main_toolbar.addAction(self._action_compare_folders)
        self._main_toolbar.addSeparator()
        self._main_toolbar.addAction(self._action_refresh)
        self._main_toolbar.addSeparator()
        self._main_toolbar.addAction(self._action_prev_diff)
        self._main_toolbar.addAction(self._action_next_diff)
        self._main_toolbar.addSeparator()
        self._main_toolbar.addAction(self._action_copy_left_to_right)
        self._main_toolbar.addAction(self._action_copy_right_to_left)
    
    def _setup_statusbar(self) -> None:
        """Set up the status bar."""
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        
        # Cursor position label
        self._position_label = QLabel("Ln 1, Col 1") # Initialize here
        self._statusbar.addPermanentWidget(self._position_label) # Add to status bar
        
        # Status message
        self._status_label = QLabel("Ready")
        self._statusbar.addWidget(self._status_label, 1)
        
        # Progress bar (hidden by default)
        self._progress_bar = QProgressBar()
        self._progress_bar.setMaximumWidth(200)
        self._progress_bar.hide()
        self._statusbar.addPermanentWidget(self._progress_bar)
        
        # Diff statistics
        self._stats_label = QLabel()
        self._statusbar.addPermanentWidget(self._stats_label)
        
        self._stats_identical = QLabel()
        self._statusbar.addPermanentWidget(self._stats_identical)
        self._stats_modified = QLabel()
        self._statusbar.addPermanentWidget(self._stats_modified)
        self._stats_left_only = QLabel()
        self._statusbar.addPermanentWidget(self._stats_left_only)
        self._stats_right_only = QLabel()
        self._statusbar.addPermanentWidget(self._stats_right_only)
    
    def _setup_connections(self) -> None:
        """Set up signal connections."""
        self._stack.currentChanged.connect(self._on_tab_changed)
    
    def _load_settings(self) -> None:
        """Load application settings."""
        # Window geometry
        if self._settings.ui.window_maximized:
            self.showMaximized()
        else:
            self.resize(self._settings.ui.window_width, self._settings.ui.window_height)
            # Only set position if not maximized, to avoid conflicts
            if self._settings.ui.window_width == 0 and self._settings.ui.window_height == 0:
                self._center_on_screen()
        
        # Restore splitter position if it exists
        if hasattr(self, '_splitter'):
            splitter_state = self._settings.ui.splitter_position
            if isinstance(splitter_state, str) and splitter_state: # Check if it's a non-empty string
                self._splitter.restoreState(QByteArray.fromHex(splitter_state.encode()))
    
    def _save_settings(self) -> None:
        """Save application settings."""
        self._settings.ui.window_width = self.width()
        self._settings.ui.window_height = self.height()
        self._settings.ui.window_maximized = self.isMaximized()

        # Save splitter position if it exists
        if hasattr(self, '_splitter') and self._splitter is not None:
            self._settings.ui.splitter_position = self._splitter.saveState().toHex().data().decode()
        
        self._settings_manager.save()
    
    def _center_on_screen(self) -> None:
        """Center window on screen."""
        screen = QApplication.primaryScreen()
        if screen:
            screen_geometry = screen.availableGeometry()
            x = (screen_geometry.width() - self.width()) // 2
            y = (screen_geometry.height() - self.height()) // 2
            self.move(x, y)
    
    def _update_recent_menu(self) -> None:
        """Update the recent files menu and homescreen display."""
        self._recent_menu.clear()
        
        # Clear existing homescreen recent comparison buttons
        for i in reversed(range(self._recent_layout.count())):
            widget = self._recent_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        
        recent_items = list(self._settings.recent_comparisons)
        limit = self._settings.ui.recent_history_limit
        
        if not recent_items:
            no_recent_label = QLabel("No recent comparisons.")
            no_recent_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._recent_layout.addWidget(no_recent_label)
            return

        for left, right in recent_items[:limit]:
            # Update menu
            action = QAction(f"{Path(left).name} ↔ {Path(right).name}", self)
            action.setData((left, right))
            action.triggered.connect(lambda checked, l=left, r=right: self._open_recent(l, r))
            self._recent_menu.addAction(action)
            
            # Add to homescreen display (now sidebar)
            recent_button = QPushButton(f"{Path(left).name} ↔ {Path(right).name}")
            recent_button.setToolTip(f"{left} ↔ {right}")
            recent_button.clicked.connect(lambda checked, l=left, r=right: self._open_recent(l, r))
            # Apply styling for the button to fit the sidebar theme
            recent_button.setStyleSheet(
                "QPushButton { text-align: left; padding: 5px; border: none; background-color: transparent; color: #fdfefe; }"
                "QPushButton:hover { background-color: #d05a55; }"
                "QPushButton:pressed { background-color: #a03833; }"
            )
            self._recent_layout.addWidget(recent_button)
        
        if recent_items:
            self._recent_menu.addSeparator()
            clear_action = QAction("Clear Recent", self)
            clear_action.triggered.connect(self._clear_recent)
            self._recent_menu.addAction(clear_action)
    
    def _add_to_recent(self, left: str, right: str) -> None:
        """Add a comparison to recent files."""
        item = (left, right)
        
        # Access the list directly from settings
        recent_comparisons_list = self._settings.recent_comparisons
        
        if item in recent_comparisons_list:
            recent_comparisons_list.remove(item)
        recent_comparisons_list.insert(0, item)
        
        # Trim history to the limit defined in settings
        limit = self._settings.ui.recent_history_limit
        self._settings.recent_comparisons = recent_comparisons_list[:limit]
        
        # Save the updated settings
        self._settings_manager.save()
        
        # Update the internal _recent_files list for UI display
        self._recent_files = list(self._settings.recent_comparisons)
        self._update_recent_menu()
    
    def _clear_recent(self) -> None:
        """Clear recent files list."""
        self._settings.recent_comparisons.clear()
        self._settings_manager.save()
        self._recent_files = [] # Update internal list
        self._update_recent_menu()
    
    def _open_recent(self, left: str, right: str) -> None:
        """Open a recent comparison."""
        left_path = Path(left)
        right_path = Path(right)
        
        if left_path.is_dir() and right_path.is_dir():
            self.compare_folders(left, right)
        else:
            self.compare_files(left, right)
    
    # === Public API ===
    
    def _remove_welcome_page_if_active(self) -> None:
        """Removes the welcome page tab if it is currently the only and active tab."""
        if self._stack.count() == 1 and self._stack.currentWidget() == self._welcome_page:
            self._stack.removeTab(self._stack.indexOf(self._welcome_page))
            self._welcome_page.deleteLater() # Ensure widget is properly deleted
            self._welcome_page = None # Clear reference

    def compare_files(
        self,
        left_path: str,
        right_path: str,
        encoding: str = 'utf-8' # This encoding parameter is not currently used by the worker
    ) -> None:
        """
        Initiates a file comparison.
        """
        self._remove_welcome_page_if_active()

        # Create a new view for this comparison
        new_view = FileCompareView(self)
        self._setup_file_compare_view(new_view, Path(left_path), Path(right_path))

        # Start the file comparison worker, passing the newly created view
        self._start_file_comparison_worker(left_path, right_path, target_view=new_view)

        self._add_to_recent(left_path, right_path)
        self._update_recent_menu()

        
    def compare_folders(
        self,
        left_path: str,
        right_path: str
    ) -> None:
        """
        Initiates a folder comparison.

        Args:
            left_path: The path to the left folder.
            right_path: The path to the right folder.
        """
        self._remove_welcome_page_if_active()

        view = FolderCompareView(self)
        view.comparison_requested.connect(self._start_folder_comparison_worker)
        view.file_comparison_requested.connect(self._start_file_comparison_worker)
        view.preview_comparison_requested.connect(self._on_preview_comparison_requested)

        tab_title = f"{Path(left_path).name} ↔ {Path(right_path).name}"
        index = self._stack.addTab(view, tab_title)
        self._stack.setCurrentIndex(index)

        self._add_to_recent(left_path, right_path)
        self._update_recent_menu()
        
        # Start the comparison process in the view
        view.start_comparison(left_path, right_path)
        
    def _start_folder_comparison_worker(self, left_path: str, right_path: str) -> None:
        """
        Starts the FolderCompareWorker.
        """
        self._show_progress("Comparing folders...")
        current_view = self._stack.currentWidget()
        if isinstance(current_view, FolderCompareView):
            # Pass options from settings
            compare_options = CompareOptions(
                compare_contents=self._settings.comparison.compare_file_contents,
                quick_compare=self._settings.comparison.quick_compare_by_size,
                ignore_case=self._settings.comparison.ignore_case,
                ignore_whitespace=self._settings.comparison.ignore_whitespace,
                ignore_line_endings=self._settings.comparison.ignore_line_endings,
                recursive=self._settings.comparison.recursive,
                follow_symlinks=self._settings.comparison.follow_symlinks,
                include_patterns=self._settings.comparison.include_patterns,
                exclude_patterns=self._settings.comparison.exclude_patterns,
            )
            worker = FolderCompareWorker(Path(left_path), Path(right_path), options=compare_options)
            thread = WorkerThread(worker)

            worker.signals.progress_detail.connect(self._on_folder_progress)
            worker.signals.finished.connect(
                lambda result: self._on_folder_compare_complete(result, left_path, right_path, current_view)
            )
            worker.signals.error.connect(self._on_worker_error)

            self._current_worker = thread
            thread.start()
        else:
            logging.error(f"MainWindow._start_folder_comparison_worker: current widget is not FolderCompareView but {type(current_view)}")


    def _start_file_comparison_worker(self, left_path: str, right_path: str, target_view: Optional[FileCompareView] = None) -> None:
        """
        Starts a file comparison worker (Text or Binary).
        """
        left_name = Path(left_path).name if left_path else "(none)"
        right_name = Path(right_path).name if right_path else "(none)"
        self._show_progress(f"Comparing {left_name} and {right_name}...")

        left_p = Path(left_path) if left_path else None
        right_p = Path(right_path) if right_path else None
        
        # Create a new view for this comparison if not provided
        if target_view is None:
            new_view = FileCompareView(self)
            self._setup_file_compare_view(new_view, left_p, right_p)
        else:
            new_view = target_view

        file_io_service = FileIOService()
        
        # known image extensions from compare_worker.py
        IMAGE_EXTENSIONS = {
            '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.tif',
            '.webp', '.ico', '.svg',
        }
        
        # Document extensions that support text extraction
        DOC_EXTENSIONS = {'.pdf', '.docx', '.xlsx', '.pptx'}
        
        is_image = (left_p and left_p.suffix.lower() in IMAGE_EXTENSIONS) or (right_p and right_p.suffix.lower() in IMAGE_EXTENSIONS)
        is_doc = (left_p and left_p.suffix.lower() in DOC_EXTENSIONS) or (right_p and right_p.suffix.lower() in DOC_EXTENSIONS)
        
        # Decide which worker to use
        if is_image:
            worker = ImageCompareWorker(left_p or "", right_p or "", ImageCompareOptions())
        elif is_doc:
             # Use TextCompareWorker for documents (it will extract text)
            compare_options = TextCompareOptions(
                ignore_case=self._settings.comparison.ignore_case,
                ignore_blank_lines=self._settings.comparison.ignore_blank_lines,
                ignore_line_endings=self._settings.comparison.ignore_line_endings,
                context_lines=self._settings.comparison.context_lines,
                whitespace_mode=(
                    WhitespaceMode.IGNORE_ALL
                    if self._settings.comparison.ignore_whitespace
                    else WhitespaceMode.EXACT
                ),
            )
            worker = TextCompareWorker(left_p or "", right_p or "", compare_options)
        elif (left_p and file_io_service._is_binary_file(left_p)) or (right_p and file_io_service._is_binary_file(right_p)):
            worker = BinaryCompareWorker(left_p or "", right_p or "", BinaryCompareOptions())
        else:
            compare_options = TextCompareOptions(
                ignore_case=self._settings.comparison.ignore_case,
                ignore_blank_lines=self._settings.comparison.ignore_blank_lines,
                ignore_line_endings=self._settings.comparison.ignore_line_endings,
                context_lines=self._settings.comparison.context_lines,
                whitespace_mode=(
                    WhitespaceMode.IGNORE_ALL
                    if self._settings.comparison.ignore_whitespace
                    else WhitespaceMode.EXACT
                ),
            )
            worker = TextCompareWorker(left_p or "", right_p or "", compare_options)

        thread = WorkerThread(worker)
        worker.signals.finished.connect(
            lambda result: self._on_file_compare_complete(result, left_path, right_path, new_view)
        )
        worker.signals.error.connect(self._on_worker_error)

        self._current_worker = thread
        thread.start()

    @pyqtSlot(str, str, FilePreviewPanel)
    def _on_preview_comparison_requested(self, left_path: str, right_path: str, preview_panel: FilePreviewPanel) -> None:
        """Handle comparison request from a FilePreviewPanel."""
        # Use the _start_file_comparison_worker but target the FileCompareView within the preview_panel
        self._start_file_comparison_worker(left_path, right_path, target_view=preview_panel._compare_view)


    def _setup_file_compare_view(self, view: FileCompareView, left_p: Path, right_p: Path):
        """Helper to set up common properties of FileCompareView."""
        # Connect signals from the new view
        view.position_changed.connect(self._on_position_changed)
        view.modified_changed.connect(self._on_modified_changed)

        tab_title = f"{left_p.name} ↔ {right_p.name}"
        index = self._stack.addTab(view, tab_title)
        self._stack.setCurrentIndex(index)


        



    def three_way_merge(
        self,
        base_path: str,
        left_path: str,
        right_path: str
    ) -> None:
        """
        Start three-way merge.
        
        Args:
            base_path: Path to base/ancestor file
            left_path: Path to left/ours file
            right_path: Path to right/theirs file
        """
        # Create a new MergeView for this comparison
        new_merge_view = MergeView(self)

        # Connect signals from the new view
        new_merge_view.modified_changed.connect(self._on_modified_changed)

        tab_title = f"Merge: {Path(base_path).name}"
        index = self._stack.addTab(new_merge_view, tab_title)
        self._stack.setCurrentIndex(index)

        new_merge_view.load_files(base_path, left_path, right_path)
    
    # === Slots ===
    
    @pyqtSlot()
    def _on_compare_files(self) -> None:
        """Handle compare files action."""
        dialog = OpenFilesDialog(self)
        if dialog.exec():
            left, right = dialog.get_paths()
            self.compare_files(left, right)
    
    @pyqtSlot()
    def _on_compare_folders(self) -> None:
        """Handle compare folders action."""
        dialog = OpenFoldersDialog(self)
        if dialog.exec():
            left, right = dialog.get_paths()
            self.compare_folders(left, right)
    
    @pyqtSlot()
    def _on_three_way_merge(self) -> None:
        """Handle three-way merge action."""
        from app.ui.widgets.dialogs import ThreeWayMergeDialog
        dialog = ThreeWayMergeDialog(self)
        if dialog.exec():
            base, left, right = dialog.get_paths()
            self.three_way_merge(base, left, right)
    
    @pyqtSlot()
    def _on_save(self) -> None:
        """Handle save action."""
        current = self._stack.currentWidget()
        if hasattr(current, 'save'):
            current.save()
    
    @pyqtSlot()
    def _on_save_as(self) -> None:
        """Handle save as action."""
        current = self._stack.currentWidget()
        if hasattr(current, 'save_as'):
            current.save_as()
    
    @pyqtSlot()
    def _on_copy(self) -> None:
        """Handle copy action."""
        current = self._stack.currentWidget()
        if hasattr(current, 'copy_selection'):
            current.copy_selection()
    
    @pyqtSlot()
    def _on_find(self) -> None:
        """Handle find action."""
        current = self._stack.currentWidget()
        if hasattr(current, 'show_find'):
            current.show_find()
    
    @pyqtSlot()
    def _on_find_next(self) -> None:
        """Handle find next action."""
        current = self._stack.currentWidget()
        if hasattr(current, 'find_next'):
            current.find_next()
    
    @pyqtSlot()
    def _on_preferences(self) -> None:
        """Handle preferences action."""
        dialog = SettingsDialog(self._settings_manager.settings, self)
        if dialog.exec():
            self._settings_manager.save(dialog.get_settings())
    
    @pyqtSlot()
    def _on_toggle_line_numbers(self) -> None:
        """Toggle line numbers display."""
        show = self._action_toggle_line_numbers.isChecked()
        current_view = self._get_current_file_compare_view()
        if current_view:
            current_view.set_show_line_numbers(show)
    
    @pyqtSlot()
    def _on_toggle_whitespace(self) -> None:
        """Toggle whitespace display."""
        show = self._action_toggle_whitespace.isChecked()
        current_view = self._get_current_file_compare_view()
        if current_view:
            current_view.set_show_whitespace(show)
    
    @pyqtSlot()
    def _on_toggle_word_wrap(self) -> None:
        """Toggle word wrap."""
        wrap = self._action_word_wrap.isChecked()
        current_view = self._get_current_file_compare_view()
        if current_view:
            current_view.set_word_wrap(wrap)
    
    @pyqtSlot()
    def _on_toggle_unified(self) -> None:
        """Switch to unified diff view."""
        self._action_side_by_side.setChecked(False)
        current_view = self._get_current_file_compare_view()
        if current_view:
            current_view.set_view_mode('unified')
    
    @pyqtSlot()
    def _on_toggle_side_by_side(self) -> None:
        """Switch to side-by-side view."""
        self._action_unified_diff.setChecked(False)
        current_view = self._get_current_file_compare_view()
        if current_view:
            current_view.set_view_mode('side_by_side')
    
    @pyqtSlot()
    def _on_toggle_main_toolbar(self) -> None:
        """Toggle the visibility of the main toolbar."""
        checked = self._action_toggle_main_toolbar.isChecked()
        self._main_toolbar.setVisible(checked)
    
    
    @pyqtSlot()
    def _on_refresh(self) -> None:
        """Refresh current comparison."""
        current = self._stack.currentWidget()
        if hasattr(current, 'refresh'):
            current.refresh()
    
    @pyqtSlot()
    def _on_next_diff(self) -> None:
        """Navigate to next difference."""
        current = self._stack.currentWidget()
        if hasattr(current, 'goto_next_diff'):
            current.goto_next_diff()
    
    @pyqtSlot()
    def _on_prev_diff(self) -> None:
        """Navigate to previous difference."""
        current = self._stack.currentWidget()
        if hasattr(current, 'goto_prev_diff'):
            current.goto_prev_diff()
    
    @pyqtSlot()
    def _on_first_diff(self) -> None:
        """Navigate to first difference."""
        current = self._stack.currentWidget()
        if hasattr(current, 'goto_first_diff'):
            current.goto_first_diff()
    
    @pyqtSlot()
    def _on_last_diff(self) -> None:
        """Navigate to last difference."""
        current = self._stack.currentWidget()
        if hasattr(current, 'goto_last_diff'):
            current.goto_last_diff()
    
    @pyqtSlot()
    def _on_goto_line(self) -> None:
        """Go to specific line."""
        from app.ui.widgets.dialogs import GotoLineDialog
        dialog = GotoLineDialog(self)
        if dialog.exec():
            line = dialog.get_line_number()
            current = self._stack.currentWidget()
            if hasattr(current, 'goto_line'):
                current.goto_line(line)
    
    @pyqtSlot()
    def _on_copy_left_to_right(self) -> None:
        """Copy current difference from left to right."""
        current = self._stack.currentWidget()
        if hasattr(current, 'copy_left_to_right'):
            current.copy_left_to_right()
    
    @pyqtSlot()
    def _on_copy_right_to_left(self) -> None:
        """Copy current difference from right to left."""
        current = self._stack.currentWidget()
        if hasattr(current, 'copy_right_to_left'):
            current.copy_right_to_left()
    
    @pyqtSlot()
    def _on_use_left_all(self) -> None:
        """Use left version for all differences."""
        current = self._stack.currentWidget()
        if hasattr(current, 'use_left_all'):
            current.use_left_all()
    
    @pyqtSlot()
    def _on_use_right_all(self) -> None:
        """Use right version for all differences."""
        current = self._stack.currentWidget()
        if hasattr(current, 'use_right_all'):
            current.use_right_all()
    
    @pyqtSlot()
    def _on_sync_folders(self) -> None:
        """Open folder sync dialog."""
        current = self._stack.currentWidget()
        if isinstance(current, FolderCompareView) and current._result:
            from app.ui.widgets.dialogs import SyncDialog
            dialog = SyncDialog(current._result, self)
            if dialog.exec():
                current.refresh()
        else:
            QMessageBox.warning(self, "No Active Comparison", "Please open a folder comparison first to synchronize folders.")
    
    @pyqtSlot()
    def _on_generate_report(self) -> None:
        """Generate comparison report."""
        current = self._stack.currentWidget()
        if hasattr(current, 'generate_report'):
            current.generate_report()
    
    @pyqtSlot()
    def _on_verify_hashes(self) -> None:
        """Open hash verification dialog."""
        from app.ui.widgets.dialogs import HashVerifyDialog
        dialog = HashVerifyDialog(self)
        dialog.exec()
    
    @pyqtSlot()
    def _on_help(self) -> None:
        """Show help."""
        dialog = HelpDialog(self)
        dialog.exec()
    
    @pyqtSlot()
    def _on_about(self) -> None:
        """Show about dialog."""
        dialog = AboutDialog(self)
        dialog.exec()
    
    @pyqtSlot()
    def _on_close_current_file(self) -> None:
        """Close the currently active tab."""
        current_index = self._stack.currentIndex()
        if current_index != -1:
            self._close_tab(current_index)
        
    @pyqtSlot(int, int, str)
    def _on_worker_progress(self, current: int, total: int, message: str) -> None:
        """Handle worker progress update."""
        if total > 0:
            self._progress_bar.setMaximum(total)
            self._progress_bar.setValue(current)
        else:
            self._progress_bar.setMaximum(0)
        self._status_label.setText(message)
    
    @pyqtSlot(object)
    def _on_folder_progress(self, info) -> None:
        """Handle folder comparison progress."""
        self._status_label.setText(f"{info.message}: {info.detail}")
        if info.total > 0:
            self._progress_bar.setMaximum(info.total)
            self._progress_bar.setValue(info.current)
    
    @pyqtSlot(str, str)
    def _on_worker_error(self, error_type: str, message: str) -> None:
        """Handle worker error."""
        self._hide_progress()
        QMessageBox.critical(self, error_type, message)
    
    def _on_file_compare_complete(self, result, left_path: str, right_path: str, view: FileCompareView) -> None:
        """Handle file comparison completion."""
        self._hide_progress()
        view.set_diff_result(result)
        # No need to set current widget here, already done when tab is added
        self._add_to_recent(left_path, right_path)
        # Title updated by _on_tab_changed (which is triggered when current tab is set)
        self._update_stats(result)
    
    def _on_folder_compare_complete(self, result, left_path: str, right_path: str, view: FolderCompareView) -> None:
        """Handle folder comparison completion."""
        self._hide_progress()
        view.set_compare_result(result)
        # No need to set current widget here, already done when tab is added
        self._add_to_recent(left_path, right_path)
        # Title updated by _on_tab_changed
        self._update_stats(result) # Update stats with folder compare result
    
    @pyqtSlot(str)
    def _on_folder_file_selected(self, rel_path: str) -> None:
        """Handle file selection in folder view."""
        pass
    
    @pyqtSlot(str, str)
    def _compare_selected_files(self, left: str, right: str) -> None:
        """Compare files selected in folder view."""
        self.compare_files(left, right)
    
    @pyqtSlot(int, int)
    def _on_position_changed(self, line: int, column: int) -> None:
        """Handle cursor position change."""
        self._position_label.setText(f"Ln {line}, Col {column}")
    
    @pyqtSlot(bool)
    def _on_modified_changed(self, modified: bool) -> None:
        """Handle modified state change."""
        self._action_save.setEnabled(modified)
        title = self.windowTitle()
        if modified and not title.startswith("*"):
            self.setWindowTitle("*" + title)
        elif not modified and title.startswith("*"):
            self.setWindowTitle(title[1:])
    
    def _show_progress(self, message: str) -> None:
        """Show progress indicator."""
        self._status_label.setText(message)
        self._progress_bar.setMaximum(0)  # Indeterminate
        self._progress_bar.show()
    
    def _hide_progress(self) -> None:
        """Hide progress indicator."""
        self._progress_bar.hide()
        self._status_label.setText("Ready")
    
    def _update_window_title(self, subtitle: str) -> None:
        """Update window title."""
        self.setWindowTitle(f"{subtitle} - File Compare")

    def _get_current_file_compare_view(self) -> Optional[FileCompareView]:
        """Returns the current FileCompareView if it is the active tab."""
        current_widget = self._stack.currentWidget()
        if isinstance(current_widget, FileCompareView):
            return current_widget
        return None

    def _update_stats(self, result: Any) -> None:
        """Update statistics display based on the type of comparison result."""
        self._stats_label.clear()
        self._stats_identical.clear()
        self._stats_modified.clear()
        self._stats_left_only.clear()
        self._stats_right_only.clear()

        # Import necessary models to check type
        from app.core.models import DiffResult, FolderCompareResult

        if isinstance(result, DiffResult):
            if result.statistics:
                stats = result.statistics
                self._stats_label.setText(
                    f"Line Diffs: +{stats.added_lines} -{stats.removed_lines} ~{stats.modified_lines}"
                )
        elif isinstance(result, FolderCompareResult):
            self._stats_label.setText(
                f"Total: {result.total_files} files, {result.total_directories} folders"
            )
            self._stats_identical.setText(f"Identical: {result.identical_count}")
            self._stats_modified.setText(f"Modified: {result.modified_count}")
            self._stats_left_only.setText(f"Left Only: {result.left_only_count}")
            self._stats_right_only.setText(f"Right Only: {result.right_only_count}")
            
    @pyqtSlot(ApplicationSettings)
    def _on_settings_changed(self, new_settings: ApplicationSettings) -> None:
        """Handle application settings changes."""
        self._settings = new_settings
        
        # Re-apply theme based on the new settings
        setup_theme(QApplication.instance(), self._settings.ui.theme)
        
        # Update UI elements that depend on settings
        self._update_recent_menu()
        
        # Refresh all views in tabs if needed
        for i in range(self._stack.count()):
            widget = self._stack.widget(i)
            if hasattr(widget, 'refresh_style'):
                widget.refresh_style()

    def _clear_stats_and_position(self) -> None:
        """Clear status bar statistics and position."""
        if self._position_label: self._position_label.setText("Ln 1, Col 1")
        if self._stats_label: self._stats_label.clear()
        if self._stats_identical: self._stats_identical.clear()
        if self._stats_modified: self._stats_modified.clear()
        if self._stats_left_only: self._stats_left_only.clear()
        if self._stats_right_only: self._stats_right_only.clear()

    @pyqtSlot(int)
    def _close_tab(self, index: int) -> None:
        """Close the tab at the given index."""
        widget = self._stack.widget(index)
        if widget and widget == self._welcome_page: # Don't close welcome page
            return

        if widget:
            # Optionally, ask for confirmation if the widget has unsaved changes
            if hasattr(widget, 'is_modified') and widget.is_modified():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    f"There are unsaved changes in tab '{self._stack.tabText(index)}'. Do you want to close it anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    return

            self._stack.removeTab(index)
            widget.deleteLater()  # Schedule for deletion

            if self._stack.count() == 0:  # If the last tab was closed
                # Re-add the welcome page
                self._welcome_page = self._create_welcome_page()
                self._stack.addTab(self._welcome_page, "Welcome")
                self._stack.setCurrentWidget(self._welcome_page)
                self._sidebar_widget.show() # Show sidebar


    @pyqtSlot(int)
    def _on_tab_changed(self, index: int) -> None:
        """Handle active tab change."""
        widget = self._stack.widget(index)
        if widget:
            # Update window title
            if widget == self._welcome_page:
                self.setWindowTitle("TwinScope")
                self._sidebar_widget.show()
            else:
                self.setWindowTitle(self._stack.tabText(index) + " - TwinScope")
                self._sidebar_widget.hide()
            
            # --- New toolbar visibility logic ---
            if widget == self._welcome_page:
                self._main_toolbar.hide()
                if hasattr(self, '_action_toggle_main_toolbar'):
                    self._action_toggle_main_toolbar.setChecked(False)
            elif isinstance(widget, (FileCompareView, FolderCompareView, MergeView)):
                self._main_toolbar.show()
                if hasattr(self, '_action_toggle_main_toolbar'):
                    self._action_toggle_main_toolbar.setChecked(True)
            # --- End new toolbar visibility logic ---

        else:
            self._update_window_title("TwinScope")
            self._clear_stats_and_position()
            self._sidebar_widget.show() # Show sidebar if no tabs are open

    # === Events ===
    
    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle window close."""
        # Check for unsaved changes in all tabs
        for i in range(self._stack.count()):
            widget = self._stack.widget(i)
            # Exclude the welcome page (index 0) from unsaved changes check
            if i > 0 and hasattr(widget, 'is_modified') and widget.is_modified():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    f"There are unsaved changes in tab '{self._stack.tabText(i)}'. Do you want to close it anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    event.ignore()
                    return
        
        # Check for unsaved application settings
        if self._check_unsaved_changes(): # This will now only check for unsaved settings
            self._save_settings()
            
            # Cancel any running worker
            if self._current_worker and self._current_worker.isRunning():
                self._current_worker.cancel()
                self._current_worker.wait(1000)
            
            event.accept()
        else:
            event.ignore()
    
    def _check_unsaved_changes(self) -> bool:
        """Check for unsaved *application settings* and prompt user."""
        # This method is now specifically for application settings, not individual tabs
        return True # For now, assume settings don't have unsaved changes that need explicit prompt
    
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Handle drag enter."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
    
    def dropEvent(self, event: QDropEvent) -> None:
        """Handle drop."""
        urls = event.mimeData().urls()
        paths = [url.toLocalFile() for url in urls if url.isLocalFile()]
        self._on_files_dropped_from_area(paths)

    @pyqtSlot(list)
    def _on_files_dropped_from_area(self, paths: list[str]) -> None:
        """Handle files dropped onto the DropArea."""
        if len(paths) == 2:
            left, right = paths
            if Path(left).is_dir() and Path(right).is_dir():
                self.compare_folders(left, right)
            else:
                self.compare_files(left, right)
        elif len(paths) == 1:
            # Single file/folder - prompt for second
            path = paths[0]
            if Path(path).is_dir():
                dialog = QFileDialog(self)
                dialog.setFileMode(QFileDialog.FileMode.Directory)
                if dialog.exec():
                    other = dialog.selectedFiles()[0]
                    self.compare_folders(path, other)
            else:
                other, _ = QFileDialog.getOpenFileName(self, "Select Second File")
                if other:
                    self.compare_files(path, other)