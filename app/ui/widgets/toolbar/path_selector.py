"""
Path selector button widget for toolbar.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMenu,
    QSizePolicy,
    QStyle,
    QToolButton,
    QWidget,
)

from app.constants.constants import MAX_PATH_HISTORY


class PathSelectorButton(QToolButton):
    """
    Button for selecting files or folders with history dropdown.
    
    Features:
    - Click to browse
    - Dropdown for recent paths
    - Drag and drop support
    - Path validation
    - Tooltip with full path
    """

    # Signal when path is selected
    path_selected = pyqtSignal(str)

    # Signal when path is cleared
    path_cleared = pyqtSignal()

    MAX_HISTORY = MAX_PATH_HISTORY

    def __init__(
        self,
        mode: str = "file",  # "file", "folder", "any"
        label: str = "Select...",
        settings_key: Optional[str] = None,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)

        self._mode = mode
        self._label = label
        self._settings_key = settings_key
        self._current_path: Optional[Path] = None
        self._history: List[str] = []
        self._file_filter = "All Files (*.*)"

        self._setup_ui()
        self._load_history()

        # Enable drag and drop
        self.setAcceptDrops(True)

    def _setup_ui(self) -> None:
        """Setup the button UI."""
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(150)

        # Set icon based on mode
        style = self.style()
        if style is not None:
            if self._mode == "folder":
                icon = style.standardIcon(QStyle.StandardPixmap.SP_DirIcon)
            else:
                icon = style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)
            self.setIcon(icon)

        self._update_text()

        # Create menu
        self._menu = QMenu(self)
        self._update_menu()
        self.setMenu(self._menu)

        # Connect click
        self.clicked.connect(self._browse)

    def _update_text(self) -> None:
        """Update button text based on current path."""
        if self._current_path:
            # Show filename or folder name
            name = self._current_path.name
            if len(name) > 30:
                name = name[:27] + "..."
            self.setText(name)
            self.setToolTip(str(self._current_path))
        else:
            self.setText(self._label)
            self.setToolTip(f"Click to select {self._mode}")

    def _update_menu(self) -> None:
        """Update the dropdown menu."""
        self._menu.clear()

        # Browse action
        browse_action = self._menu.addAction(f"Browse {self._mode.title()}...")
        if browse_action is not None:
            browse_action.triggered.connect(self._browse)

        if self._current_path:
            # Clear action
            clear_action = self._menu.addAction("Clear")
            if clear_action is not None:
                clear_action.triggered.connect(self.clear_path)

            # Open in explorer
            self._menu.addSeparator()
            open_action = self._menu.addAction("Open in Explorer")
            if open_action is not None:
                open_action.triggered.connect(self._open_in_explorer)

            # Copy path
            copy_action = self._menu.addAction("Copy Path")
            if copy_action is not None:
                copy_action.triggered.connect(self._copy_path)

        # History
        if self._history:
            self._menu.addSeparator()
            history_menu = self._menu.addMenu("Recent")
            if history_menu is not None:
                for path in self._history[:self.MAX_HISTORY]:
                    action = history_menu.addAction(self._format_path(path))
                    if action is not None:
                        action.setData(path)
                        action.triggered.connect(lambda checked, p=path: self.set_path(p))

                history_menu.addSeparator()
                clear_history = history_menu.addAction("Clear History")
                if clear_history is not None:
                    clear_history.triggered.connect(self._clear_history)

    def _format_path(self, path: str) -> str:
        """Format path for display in menu."""
        p = Path(path)
        name = p.name
        parent = str(p.parent)

        if len(parent) > 30:
            parent = "..." + parent[-27:]

        return f"{name} ({parent})"

    def _browse(self) -> None:
        """Open browse dialog."""
        start_dir = ""
        if self._current_path:
            start_dir = str(self._current_path.parent)
        elif self._history:
            start_dir = str(Path(self._history[0]).parent)

        if self._mode == "folder":
            path = QFileDialog.getExistingDirectory(
                self,
                "Select Folder",
                start_dir
            )
        else:
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Select File",
                start_dir,
                self._file_filter
            )

        if path:
            self.set_path(path)

    def set_path(self, path: str | Path) -> None:
        """Set the current path."""
        path = Path(path)

        if not path.exists():
            return

        # Validate mode
        if self._mode == "folder" and not path.is_dir():
            return
        if self._mode == "file" and not path.is_file():
            return

        self._current_path = path
        self._add_to_history(str(path))
        self._update_text()
        self._update_menu()

        self.path_selected.emit(str(path))

    def get_path(self) -> Optional[Path]:
        """Get the current path."""
        return self._current_path

    def clear_path(self) -> None:
        """Clear the current path."""
        self._current_path = None
        self._update_text()
        self._update_menu()
        self.path_cleared.emit()

    def set_file_filter(self, filter_str: str) -> None:
        """Set file filter for browse dialog."""
        self._file_filter = filter_str

    def _add_to_history(self, path: str) -> None:
        """Add path to history."""
        if path in self._history:
            self._history.remove(path)

        self._history.insert(0, path)
        self._history = self._history[:self.MAX_HISTORY]

        self._save_history()

    def _load_history(self) -> None:
        """Load history from settings."""
        if self._settings_key:
            settings = QSettings()
            self._history = settings.value(
                f"path_history/{self._settings_key}",
                [],
                type=list
            )

    def _save_history(self) -> None:
        """Save history to settings."""
        if self._settings_key:
            settings = QSettings()
            settings.setValue(
                f"path_history/{self._settings_key}",
                self._history
            )

    def _clear_history(self) -> None:
        """Clear path history."""
        self._history.clear()
        self._save_history()
        self._update_menu()

    def _open_in_explorer(self) -> None:
        """Open path in system file explorer."""
        if not self._current_path:
            return

        import subprocess
        import sys

        path = self._current_path
        if path.is_file():
            path = path.parent

        if sys.platform == 'win32':
            subprocess.run(['explorer', str(path)])
        elif sys.platform == 'darwin':
            subprocess.run(['open', str(path)])
        else:
            subprocess.run(['xdg-open', str(path)])

    def _copy_path(self) -> None:
        """Copy path to clipboard."""
        if self._current_path:
            clipboard = QApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(str(self._current_path))

    def dragEnterEvent(self, a0: Optional[QDragEnterEvent]) -> None:
        """Handle drag enter."""
        if a0 is None:
            return
        mime_data = a0.mimeData()
        if mime_data is not None and mime_data.hasUrls():
            a0.acceptProposedAction()

    def dropEvent(self, a0: Optional[QDropEvent]) -> None:
        """Handle drop."""
        if a0 is None:
            return
        mime_data = a0.mimeData()
        if mime_data is not None:
            urls = mime_data.urls()
            if urls:
                path = urls[0].toLocalFile()
                self.set_path(path)
