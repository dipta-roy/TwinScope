"""
Path selection widgets.

Provides file and folder path selection with:
- Browse button
- History dropdown
- Drag and drop support
- Validation
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, List
import sys

from PyQt6.QtCore import Qt, pyqtSignal, QUrl
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLineEdit,
    QPushButton, QFileDialog, QComboBox, QLabel,
    QFrame, QToolButton, QMenu, QCompleter
)

from app.services.settings import SettingsManager, ApplicationSettings # Import SettingsManager, ApplicationSettings


class PathSelector(QWidget):
    """
    Widget for selecting a file or folder path.
    
    Features:
    - Text input with completion
    - Browse button
    - History dropdown
    - Drag and drop
    """
    
    path_changed = pyqtSignal(str)
    path_validated = pyqtSignal(bool)  # True if path is valid
    
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        mode: str = 'file',  # 'file', 'folder', 'any'
        label: str = "",
        placeholder: str = "Enter path or browse...",
        history_key: str = "",
        settings_manager: Optional[SettingsManager] = None # New argument
    ):
        super().__init__(parent)
        
        self.mode = mode
        self.label_text = label
        self.placeholder = placeholder
        self.history_key = history_key
        self._history: list[str] = []
        
        self._settings_manager = settings_manager if settings_manager else SettingsManager() # Use provided or create new
        if self.history_key:
            if self.history_key == "left_paths":
                self._history = list(self._settings_manager.settings.recent_left_paths)
            elif self.history_key == "right_paths":
                self._history = list(self._settings_manager.settings.recent_right_paths)

        
        self.setAcceptDrops(True)
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup the widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Label (optional)
        if self.label_text:
            label = QLabel(self.label_text)
            layout.addWidget(label)
        
        # Input row
        input_layout = QHBoxLayout()
        input_layout.setSpacing(4)
        
        # Path input
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(self.placeholder)
        self.path_edit.textChanged.connect(self._on_text_changed)
        self.path_edit.editingFinished.connect(self._on_editing_finished) # Connect to editingFinished
        input_layout.addWidget(self.path_edit)
        
        # History button
        if self.history_key:
            self.history_btn = QToolButton()
            self.history_btn.setText("▼")
            self.history_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            self.history_menu = QMenu()
            self.history_btn.setMenu(self.history_menu)
            input_layout.addWidget(self.history_btn)
            self._update_history_menu() # Populate history menu on setup
        
        # Browse button
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._browse)
        input_layout.addWidget(self.browse_btn)
        
        layout.addLayout(input_layout)
    
    def path(self) -> str:
        """Get the current path."""
        return self.path_edit.text()
    
    def set_path(self, path: str) -> None:
        """Set the current path."""
        self.path_edit.setText(path)
    
    def is_valid(self) -> bool:
        """Check if the current path is valid."""
        path = Path(self.path())
        
        if self.mode == 'file':
            return path.is_file()
        elif self.mode == 'folder':
            return path.is_dir()
        else:
            return path.exists()
    
    def add_to_history(self, path: str) -> None:
        """Add a path to history."""
        # Get the correct list from settings
        if self.history_key == "left_paths":
            settings_history_list = self._settings_manager.settings.recent_left_paths
        elif self.history_key == "right_paths":
            settings_history_list = self._settings_manager.settings.recent_right_paths
        else:
            return # Should not happen if history_key is always "left_paths" or "right_paths"


        if path in settings_history_list:
            settings_history_list.remove(path)
        settings_history_list.insert(0, path)
        
        # Trim history
        limit = self._settings_manager.settings.ui.recent_files_limit
        # Direct modification of the list in settings
        settings_history_list[:] = settings_history_list[:limit]
        
        self._settings_manager.save()

        self._history = settings_history_list # Update internal _history to match settings

        self._update_history_menu()
    
    def set_history(self, history: list[str]) -> None:
        """Set the history list."""
        self._history = history[:20]
        self._update_history_menu()
    
    def _update_history_menu(self) -> None:
        """Update the history dropdown menu."""

        if not hasattr(self, 'history_menu'):
            return
        
        self.history_menu.clear()
        
        # Explicitly refresh _history from settings before updating the menu
        if self.history_key == "left_paths":
            self._history = self._settings_manager.settings.recent_left_paths
        elif self.history_key == "right_paths":
            self._history = self._settings_manager.settings.recent_right_paths
        else:
            self._history = [] # Should not happen, but safe fallback

        
        for path in self._history:
            action = self.history_menu.addAction(path)
            # Use a local function to ensure 'path' is captured correctly for each action
            def make_set_path_func(p_val):
                return lambda: self.set_path(p_val)
            action.triggered.connect(make_set_path_func(path))
        
        if self._history:
            self.history_menu.addSeparator()
            clear_action = self.history_menu.addAction("Clear History")
            clear_action.triggered.connect(self._clear_history)
    
    def _clear_history(self) -> None:
        """Clear the history."""
        # Get the correct list from settings
        if self.history_key == "left_paths":
            settings_history_list = self._settings_manager.settings.recent_left_paths
        elif self.history_key == "right_paths":
            settings_history_list = self._settings_manager.settings.recent_right_paths
        else:
            return # Should not happen

        settings_history_list.clear() # Clear the list directly
        self._settings_manager.save()
        self._history = settings_history_list # Update internal _history to match settings
        self._update_history_menu()
    
    def _browse(self) -> None:
        """Open file/folder browser."""
        start_path = self.path() or str(Path.home())

        if self.mode == 'file':
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Select File",
                start_path,
            )
        else:
            path = QFileDialog.getExistingDirectory(
                self,
                "Select Folder",
                start_path,
            )
        
        if path:
            self.set_path(path)
            self.add_to_history(path)
    
    def _on_editing_finished(self) -> None:
        """Handle editing finished."""
        current_path = self.path()
        if current_path and self.is_valid():
            self.add_to_history(current_path)

    def _on_text_changed(self, text: str) -> None:
        """Handle text change."""

        self.path_changed.emit(text)
        self.path_validated.emit(self.is_valid())
        
        # Update styling based on validity
        if text:
            if self.is_valid():
                self.path_edit.setStyleSheet("background-color: #e8f5e9;")
            else:
                self.path_edit.setStyleSheet("background-color: #ffebee;")
        else:
            self.path_edit.setStyleSheet("")
    
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Handle drag enter."""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and urls[0].isLocalFile():
                path = Path(urls[0].toLocalFile())
                
                if self.mode == 'file' and path.is_file():
                    event.acceptProposedAction()
                elif self.mode == 'folder' and path.is_dir():
                    event.acceptProposedAction()
                elif self.mode == 'any':
                    event.acceptProposedAction()
    
    def dropEvent(self, event: QDropEvent) -> None:
        """Handle drop."""
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            self.set_path(path)
            self.add_to_history(path)


class DualPathSelector(QWidget):
    """
    Widget for selecting two paths (left and right).
    
    Used for comparison setup.
    """
    
    paths_changed = pyqtSignal(str, str)  # (left, right)
    validated = pyqtSignal(bool)
    
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        mode: str = 'folder',
        settings_manager: Optional[SettingsManager] = None # New argument
    ):
        super().__init__(parent)
        
        self.mode = mode
        self._settings_manager = settings_manager if settings_manager else SettingsManager() # Use provided or create new
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup the widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # Left path
        self.left_selector = PathSelector(
            mode=self.mode,
            label="Left / Source:",
            history_key="left_paths",
            settings_manager=self._settings_manager # Pass the shared settings manager
        )
        self.left_selector.path_changed.connect(self._on_path_changed)
        self.left_selector.path_validated.connect(self._on_validation_changed)
        layout.addWidget(self.left_selector)
        
        # Right path
        self.right_selector = PathSelector(
            mode=self.mode,
            label="Right / Target:",
            history_key="right_paths",
            settings_manager=self._settings_manager # Pass the shared settings manager
        )
        self.right_selector.path_changed.connect(self._on_path_changed)
        self.right_selector.path_validated.connect(self._on_validation_changed)
        layout.addWidget(self.right_selector)
        
        # Swap button
        swap_layout = QHBoxLayout()
        swap_layout.addStretch()
        
        self.swap_btn = QPushButton("⇄ Swap")
        self.swap_btn.clicked.connect(self._swap_paths)
        swap_layout.addWidget(self.swap_btn)
        
        layout.addLayout(swap_layout)
    
    def left_path(self) -> str:
        """Get left path."""
        return self.left_selector.path()
    
    def right_path(self) -> str:
        """Get right path."""
        return self.right_selector.path()
    
    def set_paths(self, left: str, right: str) -> None:
        """Set both paths."""
        self.left_selector.set_path(left)
        self.right_selector.set_path(right)
    
    def is_valid(self) -> bool:
        """Check if both paths are valid."""
        return self.left_selector.is_valid() and self.right_selector.is_valid()
    
    def _swap_paths(self) -> None:
        """Swap left and right paths."""
        left = self.left_path()
        right = self.right_path()
        self.left_selector.set_path(right)
        self.right_selector.set_path(left)
    
    def _on_path_changed(self) -> None:
        """Handle path change."""
        self.paths_changed.emit(self.left_path(), self.right_path())

    def _on_validation_changed(self, is_valid: bool) -> None:
        """Handle validation change."""
        self.validated.emit(self.is_valid())


class PathHistoryCombo(QComboBox):
    """
    Combo box with path history.
    
    Editable with completion support.
    """
    
    path_selected = pyqtSignal(str)
    
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        max_history: int = 20
    ):
        super().__init__(parent)
        
        self.max_history = max_history
        
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        
        self.currentTextChanged.connect(self._on_text_changed)
    
    def add_path(self, path: str) -> None:
        """Add a path to history."""
        # Remove if exists
        index = self.findText(path)
        if index >= 0:
            self.removeItem(index)
        
        # Insert at top
        self.insertItem(0, path)
        self.setCurrentIndex(0)
        
        # Trim history
        while self.count() > self.max_history:
            self.removeItem(self.count() - 1)
    
    def set_history(self, paths: list[str]) -> None:
        """Set the history list."""
        self.clear()
        for path in paths[:self.max_history]:
            self.addItem(path)
    
    def get_history(self) -> list[str]:
        """Get the history list."""
        return [self.itemText(i) for i in range(self.count())]
    
    def _on_text_changed(self, text: str) -> None:
        """Handle text change."""
        self.path_selected.emit(text)