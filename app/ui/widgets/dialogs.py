from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QDialogButtonBox, QWidget, QHBoxLayout, QStyle, QTextBrowser,
    QComboBox, QFormLayout, QPushButton, QLineEdit, QFileDialog, QGroupBox, QCheckBox,
    QProgressBar, QMessageBox, QApplication, QSpinBox
)


from PyQt6.QtGui import QFont, QIcon, QPixmap
from PyQt6.QtGui import QIntValidator # Import QIntValidator
from PyQt6.QtCore import Qt, QTimer, QSize, QUrl, QByteArray # Import QUrl for consistency
from typing import Optional, Tuple, Any
from pathlib import Path # Import Path
from app.ui.widgets.path_selector import DualPathSelector, PathSelector
from app.ui import resources
from app.services.settings import Theme, ApplicationSettings # Import Theme and ApplicationSettings
import base64
from app.services.hashing import HashingService, HashAlgorithm, HashResult # Import HashingService, HashAlgorithm, HashResult
from app.core.models import FolderCompareResult, SyncDirection, SyncAction
from app.core.folder.sync import FolderSync

class BaseDialog(QDialog):
    def __init__(self, title: str, parent: Optional[Any] = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(400)
        
        self._main_layout = QVBoxLayout(self) # Initialize the main layout
        self._main_layout.setContentsMargins(20, 20, 20, 20)
        self._main_layout.setSpacing(15)
        
        # Placeholder for content widgets, inserted before button box
        self._content_layout = QVBoxLayout()
        self._main_layout.addLayout(self._content_layout)

        self._button_box_layout = QHBoxLayout() # Layout for buttons
        self._button_box_layout.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._main_layout.addLayout(self._button_box_layout) # Add button layout to main layout
    
    def add_button(self, text: str, role: QDialogButtonBox.ButtonRole = QDialogButtonBox.ButtonRole.NoRole, slot=None) -> QPushButton:
        button = QPushButton(text)
        if slot:
            button.clicked.connect(slot)
        self._button_box_layout.addWidget(button) # Add button to its specific layout
        return button
    
    def accept(self) -> None:
        super().accept()
    
    def reject(self) -> None:
        super().reject()
class SettingsDialog(QDialog):
    def __init__(self, settings: ApplicationSettings, parent: Optional[Any] = None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(500, 450)

        self._settings = settings
        # Deep copy settings to avoid modifying original until saved
        # Since dataclasses are not recursive by default with copy(), we'll manually copy pertinent fields
        # or rely on the fact that we're effectively creating a new state here.
        # For simplicity in this dialog logic, we'll just read from self._settings and write to a new structure on save.
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(15)

        # --- UI Settings Group ---
        ui_group = QGroupBox("User Interface")
        ui_layout = QFormLayout()
        
        # Theme selection
        self.theme_combo = QComboBox()
        for theme_option in Theme:
            self.theme_combo.addItem(theme_option.name.capitalize(), theme_option)
        
        current_theme_index = self.theme_combo.findData(self._settings.ui.theme)
        if current_theme_index != -1:
            self.theme_combo.setCurrentIndex(current_theme_index)
            
        ui_layout.addRow("Theme:", self.theme_combo)
        
        # Recent history limit
        self.history_limit_spin = QSpinBox()
        self.history_limit_spin.setRange(1, 30)
        self.history_limit_spin.setValue(self._settings.ui.recent_history_limit)
        ui_layout.addRow("Recent History Limit:", self.history_limit_spin)
        
        ui_group.setLayout(ui_layout)
        self.layout.addWidget(ui_group)

        # --- Comparison Settings Group ---
        comp_group = QGroupBox("Comparison Options")
        comp_layout = QVBoxLayout()
        
        self.ignore_whitespace_cb = QCheckBox("Ignore Whitespace")
        self.ignore_whitespace_cb.setChecked(self._settings.comparison.ignore_whitespace)
        self.ignore_whitespace_cb.setToolTip("Ignore all whitespace differences (spaces, tabs, newlines)")
        comp_layout.addWidget(self.ignore_whitespace_cb)
        
        self.ignore_case_cb = QCheckBox("Ignore Case")
        self.ignore_case_cb.setChecked(self._settings.comparison.ignore_case)
        self.ignore_case_cb.setToolTip("Treat uppercase and lowercase letters as the same")
        comp_layout.addWidget(self.ignore_case_cb)
        
        self.ignore_blank_lines_cb = QCheckBox("Ignore Blank Lines")
        self.ignore_blank_lines_cb.setChecked(self._settings.comparison.ignore_blank_lines)
        self.ignore_blank_lines_cb.setToolTip("Ignore differences involving only blank lines")
        comp_layout.addWidget(self.ignore_blank_lines_cb)
        
        self.ignore_line_endings_cb = QCheckBox("Ignore Line Endings")
        self.ignore_line_endings_cb.setChecked(self._settings.comparison.ignore_line_endings)
        self.ignore_line_endings_cb.setToolTip("Treat \\r\\n and \\n as the same")
        comp_layout.addWidget(self.ignore_line_endings_cb)
        
        comp_group.setLayout(comp_layout)
        self.layout.addWidget(comp_group)

        self.layout.addStretch()

        # Buttons
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.layout.addWidget(self.buttons)

    def get_settings(self) -> ApplicationSettings:
        """Return the modified settings."""
        # Create a copy of the current settings to ensure we don't mutate the input directly 
        # (though this implementation modifies values on a 'copy' logic basically)
        # Ideally, we should use a proper deep copy, but we'll update the specific fields we edited.
        
        # We need to reconstruction the settings object or update the existing one safely.
        # Since we want to return a 'new' state that the main window will save:
        
        from dataclasses import replace
        
        new_ui = replace(
            self._settings.ui, 
            theme=self.theme_combo.currentData(),
            recent_history_limit=self.history_limit_spin.value()
        )
        
        new_comparison = replace(
            self._settings.comparison,
            ignore_whitespace=self.ignore_whitespace_cb.isChecked(),
            ignore_case=self.ignore_case_cb.isChecked(),
            ignore_blank_lines=self.ignore_blank_lines_cb.isChecked(),
            ignore_line_endings=self.ignore_line_endings_cb.isChecked()
        )
        
        return replace(
            self._settings,
            ui=new_ui,
            comparison=new_comparison
        )

class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About TwinScope")
        self.setMinimumSize(500, 350)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(15)

        # Logo
        logo_label = QLabel()
        pixmap = QPixmap()
        pixmap.loadFromData(QByteArray.fromBase64(resources.LOGO_BASE64.encode()))
        logo_label.setPixmap(pixmap.scaledToWidth(128, Qt.TransformationMode.SmoothTransformation))
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(logo_label)

        # About content
        about_content = """
**TwinScope** is a cross-platform file and folder comparison tool inspired by Beyond Compare. Built with Python, it provides a clean, responsive interface for comparing text files, binary files, images, and entire directory trees.

**Application Version**:1.1

**Author**: Dipta Roy
        """
        
        text_browser = QTextBrowser()
        text_browser.setMarkdown(about_content)
        text_browser.setOpenExternalLinks(True)
        self.layout.addWidget(text_browser)

        # Buttons
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        self.buttons.accepted.connect(self.accept)
        self.layout.addWidget(self.buttons)


class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("TwinScope Help")
        self.setMinimumSize(700, 600)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(15)

        help_content = """
# TwinScope Help

## Welcome to TwinScope!

TwinScope is a powerful and intuitive file and folder comparison tool designed to help you quickly identify differences between files, images, and entire directories.

---

## Getting Started

### Comparing Files
1.  Go to `File` -> `Compare Files...` or click the `Compare Files` button on the welcome screen.
2.  Select the two files you wish to compare.
3.  Click `OK` to view the side-by-side or unified difference.

### Comparing Folders
1.  Go to `File` -> `Compare Folders...` or click the `Compare Folders` button on the welcome screen.
2.  Select the two folders you wish to compare.
3.  Click `OK` to view the directory comparison.

### Three-Way Merge
1.  Go to `File` -> `Three-Way Merge...` or click the `Three-Way Merge` button on the welcome screen.
2.  Select the **Base** (original), **Left** (your version), and **Right** (their version) files.
3.  Click `OK` to enter the merge view.

**Understanding Three-Way Merge:**
*   **Base (Ancestor):** The common original file. Used to determine who changed what.
*   **Auto-Merge:** If only one side changed a line compared to Base, that change is automatically kept.
*   **Conflict:** If **both** sides changed the same line differently, TwinScope flags it as a conflict. You must manually choose to use the Left, Right, or Base version (or both).

---

## Interface Overview

### File Comparison View
-   **Side-by-Side View**: Displays two files next to each other, highlighting additions, deletions, and modifications.
-   **Unified View**: Shows differences inline, similar to a traditional `diff` output.
-   **Legend**: Explains the color coding for different types of changes.
-   **Navigation**: Use `F8` (Next Difference) and `Shift+F8` (Previous Difference) to jump between changes.
-   **Find**: Press `Ctrl+F` to open the search bar and find text within the files.

### Folder Comparison View
-   Displays a tree-like structure of two folders, highlighting new, missing, and changed files/subfolders.
-   Double-click on a file to open its comparison view.

---

## Settings
Access `Edit` -> `Preferences...` to configure TwinScope's behavior, including:
-   **Theme**: Choose between System, Light, Dark, or Custom themes.
-   **Comparison Options**: Set preferences for whitespace, case sensitivity, etc.

---

## Shortcuts
-   `Ctrl+O`: Compare Files
-   `Ctrl+Shift+O`: Compare Folders
-   `Ctrl+M`: Three-Way Merge
-   `Ctrl+S`: Save
-   `Ctrl+W`: Close Current File/View
-   `Ctrl+F`: Find
-   `F3`: Find Next
-   `Shift+F3`: Find Previous
-   `F8`: Next Difference
-   `Shift+F8`: Previous Difference
-   `Ctrl+G`: Go to Line...
-   `Alt+Left`: Copy Left to Right (in merge/file compare)
-   `Alt+Right`: Copy Right to Left (in merge/file compare)

---

## Troubleshooting
-   If you encounter issues, please refer to the application logs located in `[Application Directory]/logs`.
-   Ensure your Python environment and dependencies are correctly installed.

---

Thank you for using TwinScope!
        """
        
        text_browser = QTextBrowser()
        text_browser.setMarkdown(help_content)
        text_browser.setOpenExternalLinks(True)
        self.layout.addWidget(text_browser)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        self.buttons.accepted.connect(self.accept)
        self.layout.addWidget(self.buttons)


class CompareOptionsDialog(BaseDialog):
    def __init__(self, parent=None):
        super().__init__("Compare Options", parent)

class OpenFilesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Compare Files")
        self.setMinimumWidth(500)

        # Main layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(15)
        
        # Header
        header_layout = QHBoxLayout()
        header_icon = QLabel()
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogStart)
        header_icon.setPixmap(icon.pixmap(32, 32))
        header_layout.addWidget(header_icon)
        
        header_label = QLabel("Select Files to Compare")
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        header_label.setFont(font)
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        self.layout.addLayout(header_layout)

        # Path selector
        self.path_selector = DualPathSelector(mode='file')
        self.layout.addWidget(self.path_selector)
        
        # Buttons
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        
        self.ok_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setEnabled(False)
        self.ok_button.setObjectName("okButton") # For styling

        self.path_selector.validated.connect(self.ok_button.setEnabled)
        
        self.layout.addWidget(self.buttons)

        # Stylesheet
        self.setStyleSheet("""
            QDialog {
                /* background-color: #f5f5f5; */
            }
            #okButton {
                background-color: palette(highlight);
                color: palette(highlighted-text);
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            #okButton:disabled {
                background-color: palette(alternate-base);
                color: palette(mid);
            }
            #okButton:hover {
                background-color: palette(highlight).lighter(120);
            }
        """)

    def get_paths(self) -> Tuple[str, str]:
        return self.path_selector.left_path(), self.path_selector.right_path()

    def accept(self) -> None:
        """Override accept to add paths to history."""
        self.path_selector.left_selector.add_to_history(self.path_selector.left_path())
        self.path_selector.right_selector.add_to_history(self.path_selector.right_path())
        super().accept()

class OpenFoldersDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Compare Folders")
        self.setMinimumWidth(500)

        # Main layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(15)
        
        # Header
        header_layout = QHBoxLayout()
        header_icon = QLabel()
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon)
        header_icon.setPixmap(icon.pixmap(32, 32))
        header_layout.addWidget(header_icon)
        
        header_label = QLabel("Select Folders to Compare")
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        header_label.setFont(font)
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        self.layout.addLayout(header_layout)

        # Path selector
        self.path_selector = DualPathSelector(mode='folder')
        self.layout.addWidget(self.path_selector)
        
        # Buttons
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        
        self.ok_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setEnabled(False)
        self.ok_button.setObjectName("okButton")

        self.path_selector.validated.connect(self.ok_button.setEnabled)
        
        self.layout.addWidget(self.buttons)

        # Stylesheet
        self.setStyleSheet("""
            QDialog {
                /* background-color: #f5f5f5; */
            }
            #okButton {
                background-color: palette(highlight);
                color: palette(highlighted-text);
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            #okButton:disabled {
                background-color: palette(alternate-base);
                color: palette(mid);
            }
            #okButton:hover {
                background-color: palette(highlight).lighter(120);
            }
        """)

    def get_paths(self) -> Tuple[str, str]:
        return self.path_selector.left_path(), self.path_selector.right_path()
    
    def accept(self) -> None:
        """Override accept to add paths to history."""
        self.path_selector.left_selector.add_to_history(self.path_selector.left_path())
        self.path_selector.right_selector.add_to_history(self.path_selector.right_path())
        super().accept()


class ThreeWayMergeDialog(BaseDialog):
    def __init__(self, parent=None):
        super().__init__("Three Way Merge", parent)
        self.setMinimumWidth(500)

        # Header
        header_layout = QHBoxLayout()
        header_icon = QLabel()
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogStart)
        header_icon.setPixmap(icon.pixmap(32, 32))
        header_layout.addWidget(header_icon)
        
        header_label = QLabel("Select Files to Merge")
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        header_label.setFont(font)
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        self._content_layout.addLayout(header_layout)

        # Base Selector
        self.base_selector = PathSelector(
            mode='file',
            label="Base (Ancestor):",
            placeholder="Select base file...",
            history_key="left_paths" # Reuse history
        )
        self._content_layout.addWidget(self.base_selector)

        # Left Selector
        self.left_selector = PathSelector(
            mode='file',
            label="Left (Ours):",
            placeholder="Select left file...",
            history_key="left_paths"
        )
        self._content_layout.addWidget(self.left_selector)

        # Right Selector
        self.right_selector = PathSelector(
            mode='file',
            label="Right (Theirs):",
            placeholder="Select right file...",
            history_key="right_paths"
        )
        self._content_layout.addWidget(self.right_selector)

        # Buttons
        self.ok_button = self.add_button("OK", QDialogButtonBox.ButtonRole.AcceptRole, self.accept)
        self.add_button("Cancel", QDialogButtonBox.ButtonRole.RejectRole, self.reject)
        self.ok_button.setEnabled(False)

        # Validation
        self.base_selector.path_validated.connect(self._validate)
        self.left_selector.path_validated.connect(self._validate)
        self.right_selector.path_validated.connect(self._validate)

    def _validate(self):
        valid = (self.base_selector.is_valid() and 
                 self.left_selector.is_valid() and 
                 self.right_selector.is_valid())
        self.ok_button.setEnabled(valid)

    def get_paths(self) -> Tuple[str, str, str]:
        return (self.base_selector.path(), 
                self.left_selector.path(), 
                self.right_selector.path())
    
    def accept(self) -> None:
        """Add to history."""
        if self.base_selector.is_valid():
            self.base_selector.add_to_history(self.base_selector.path())
        if self.left_selector.is_valid():
            self.left_selector.add_to_history(self.left_selector.path())
        if self.right_selector.is_valid():
            self.right_selector.add_to_history(self.right_selector.path())
        super().accept()

class GotoLineDialog(BaseDialog):
    def __init__(self, parent=None):
        super().__init__("Go To Line", parent)
        
        # Layout for input
        input_layout = QHBoxLayout()
        self._content_layout.addLayout(input_layout) # Add to content layout
        
        input_layout.addWidget(QLabel("Line number:"))
        self._line_edit = QLineEdit()
        self._line_edit.setValidator(QIntValidator(1, 999999)) # Only allow integers, min 1
        self._line_edit.setText("1") # Default value
        self._line_edit.selectAll() # Select default for easy overwrite
        input_layout.addWidget(self._line_edit)
        
        # Add OK and Cancel buttons
        self.add_button("OK", QDialogButtonBox.ButtonRole.AcceptRole, self.accept)
        self.add_button("Cancel", QDialogButtonBox.ButtonRole.RejectRole, self.reject)
        
        # Set focus to the line edit when dialog opens
        self._line_edit.setFocus()
    
    def get_line_number(self) -> int:
        return int(self._line_edit.text()) if self._line_edit.text() else 1

class SyncDialog(BaseDialog):
    def __init__(self, result: FolderCompareResult, parent: Optional[QWidget] = None):
        super().__init__("Synchronize Folders", parent)
        self.setMinimumWidth(600)
        self._result = result
        self._sync_engine = FolderSync()
        self._plan = None

        self._setup_sync_ui()
        self._on_direction_changed() # Initial update

    def _setup_sync_ui(self):
        # Info section
        info_group = QGroupBox("Comparison Info")
        info_layout = QFormLayout(info_group)
        info_layout.addRow("Left Path:", QLabel(self._result.left_path))
        info_layout.addRow("Right Path:", QLabel(self._result.right_path))
        self._content_layout.addWidget(info_group)

        # Direction section
        direction_group = QGroupBox("Synchronization Direction")
        direction_layout = QVBoxLayout(direction_group)
        
        self._direction_combo = QComboBox()
        self._direction_combo.addItem("Update Left to Right (Add/Update)", SyncDirection.LEFT_TO_RIGHT)
        self._direction_combo.addItem("Update Right to Left (Add/Update)", SyncDirection.RIGHT_TO_LEFT)
        self._direction_combo.addItem("Mirror Left to Right (Exact Copy)", "MIRROR_LR")
        self._direction_combo.addItem("Mirror Right to Left (Exact Copy)", "MIRROR_RL")
        self._direction_combo.addItem("Bidirectional (Keep Both)", SyncDirection.BIDIRECTIONAL)
        
        self._direction_combo.currentIndexChanged.connect(self._on_direction_changed)
        direction_layout.addWidget(self._direction_combo)
        
        # Options
        self._delete_extra_cb = QCheckBox("Delete extra files in destination")
        self._delete_extra_cb.setEnabled(False) # Mirror modes set this
        self._delete_extra_cb.stateChanged.connect(self._update_plan)
        direction_layout.addWidget(self._delete_extra_cb)
        
        self._content_layout.addWidget(direction_group)

        # Plan Summary section
        self._summary_group = QGroupBox("Sync Plan Summary")
        summary_layout = QVBoxLayout(self._summary_group)
        
        self._copy_lr_label = QLabel("To be copied (L -> R): 0")
        self._copy_rl_label = QLabel("To be copied (R -> L): 0")
        self._delete_l_label = QLabel("To be deleted (L): 0")
        self._delete_r_label = QLabel("To be deleted (R): 0")
        self._conflicts_label = QLabel("Conflicts: 0")
        
        summary_layout.addWidget(self._copy_lr_label)
        summary_layout.addWidget(self._copy_rl_label)
        summary_layout.addWidget(self._delete_l_label)
        summary_layout.addWidget(self._delete_r_label)
        summary_layout.addWidget(self._conflicts_label)
        
        self._content_layout.addWidget(self._summary_group)

        # Progress section (initially hidden)
        self._progress_group = QGroupBox("Progress")
        self._progress_group.setVisible(False)
        progress_layout = QVBoxLayout(self._progress_group)
        
        self._progress_bar = QProgressBar()
        progress_layout.addWidget(self._progress_bar)
        
        self._status_label = QLabel("Ready")
        progress_layout.addWidget(self._status_label)
        
        self._content_layout.addWidget(self._progress_group)

        self._content_layout.addStretch()

        # Buttons
        self._sync_button = self.add_button("Synchronize", QDialogButtonBox.ButtonRole.ActionRole, self._on_sync_clicked)
        self.add_button("Close", QDialogButtonBox.ButtonRole.RejectRole, self.reject)

    def _on_direction_changed(self):
        data = self._direction_combo.currentData()
        
        if data == "MIRROR_LR":
            self._sync_engine.options.direction = SyncDirection.LEFT_TO_RIGHT
            self._sync_engine.options.sync_deletions = True
            self._delete_extra_cb.setChecked(True)
            self._delete_extra_cb.setEnabled(False)
        elif data == "MIRROR_RL":
            self._sync_engine.options.direction = SyncDirection.RIGHT_TO_LEFT
            self._sync_engine.options.sync_deletions = True
            self._delete_extra_cb.setChecked(True)
            self._delete_extra_cb.setEnabled(False)
        else:
            self._sync_engine.options.direction = data
            self._sync_engine.options.sync_deletions = self._delete_extra_cb.isChecked()
            self._delete_extra_cb.setEnabled(True)
            
        self._update_plan()

    def _update_plan(self):
        self._sync_engine.options.sync_deletions = self._delete_extra_cb.isChecked()
        self._plan = self._sync_engine.create_plan(self._result)
        
        stats = {
            SyncAction.COPY_TO_RIGHT: 0,
            SyncAction.COPY_TO_LEFT: 0,
            SyncAction.DELETE_LEFT: 0,
            SyncAction.DELETE_RIGHT: 0,
            SyncAction.CONFLICT: 0,
        }
        
        for item in self._plan.items:
            if item.action in stats:
                stats[item.action] += 1
        
        self._copy_lr_label.setText(f"To be copied (L -> R): {stats[SyncAction.COPY_TO_RIGHT]}")
        self._copy_rl_label.setText(f"To be copied (R -> L): {stats[SyncAction.COPY_TO_LEFT]}")
        self._delete_l_label.setText(f"To be deleted (L): {stats[SyncAction.DELETE_LEFT]}")
        self._delete_r_label.setText(f"To be deleted (R): {stats[SyncAction.DELETE_RIGHT]}")
        self._conflicts_label.setText(f"Conflicts: {stats[SyncAction.CONFLICT]}")
        
        total_changes = sum(stats.values()) - stats[SyncAction.CONFLICT]
        self._sync_button.setEnabled(total_changes > 0)

    def _on_sync_clicked(self):
        if not self._plan:
            return

        if self._conflicts_label.text() != "Conflicts: 0":
            reply = QMessageBox.warning(
                self, "Conflicts Detected",
                "There are conflicts that will be skipped. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return

        self._progress_group.setVisible(True)
        self._summary_group.setVisible(False)
        self._sync_button.setEnabled(False)
        self._direction_combo.setEnabled(False)
        self._delete_extra_cb.setEnabled(False)

        # Run sync
        try:
            self._sync_engine.execute(self._plan, self._on_progress)
            QMessageBox.information(self, "Success", "Synchronization completed successfully.")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Synchronization failed: {e}")
            self._sync_button.setEnabled(True)
            self._direction_combo.setEnabled(True)
            self._progress_group.setVisible(False)
            self._summary_group.setVisible(True)

    def _on_progress(self, progress):
        self._progress_bar.setMaximum(progress.total_items)
        self._progress_bar.setValue(progress.items_completed)
        self._status_label.setText(f"Syncing: {progress.current_item}")
        QApplication.processEvents()

class HashVerifyDialog(BaseDialog):
    def __init__(self, parent=None):
        super().__init__("Verify Hashes", parent)
        
        self.setMinimumSize(600, 450)
        
        self._hashing_service = HashingService()

        # File 1 selection
        file1_layout = QHBoxLayout()
        self._file1_label = QLabel("File 1:")
        self._file1_path = QLineEdit()
        self._file1_browse_btn = QPushButton("Browse...")
        self._file1_browse_btn.clicked.connect(lambda: self._browse_file(self._file1_path))
        file1_layout.addWidget(self._file1_label)
        file1_layout.addWidget(self._file1_path)
        file1_layout.addWidget(self._file1_browse_btn)
        self._content_layout.addLayout(file1_layout)

        # File 2 selection (optional, for comparison)
        file2_layout = QHBoxLayout()
        self._file2_label = QLabel("File 2 (optional):")
        self._file2_path = QLineEdit()
        self._file2_browse_btn = QPushButton("Browse...")
        self._file2_browse_btn.clicked.connect(lambda: self._browse_file(self._file2_path))
        file2_layout.addWidget(self._file2_label)
        file2_layout.addWidget(self._file2_path)
        file2_layout.addWidget(self._file2_browse_btn)
        self._content_layout.addLayout(file2_layout)

        # Hash algorithm selection
        algo_layout = QHBoxLayout()
        self._algo_label = QLabel("Algorithm:")
        self._algo_combo = QComboBox()
        for algo in HashAlgorithm:
            self._algo_combo.addItem(algo.name.upper(), algo)
        self._algo_combo.setCurrentText(self._hashing_service.default_algorithm.name.upper())
        algo_layout.addWidget(self._algo_label)
        algo_layout.addWidget(self._algo_combo)
        self._content_layout.addLayout(algo_layout)

        # Expected hash input (optional, for single file verification)
        expected_hash_layout = QHBoxLayout()
        self._expected_hash_label = QLabel("Expected Hash (optional):")
        self._expected_hash_input = QLineEdit()
        expected_hash_layout.addWidget(self._expected_hash_label)
        expected_hash_layout.addWidget(self._expected_hash_input)
        self._content_layout.addLayout(expected_hash_layout)
        
        # Verify Button
        self._verify_button = QPushButton("Calculate / Verify")
        self._verify_button.clicked.connect(self._on_verify_button_clicked)
        self._content_layout.addWidget(self._verify_button)
        
        # Results Group
        results_group = QGroupBox("Results")
        results_layout = QVBoxLayout(results_group)
        
        self._hash1_display = QLabel("Hash 1:")
        self._hash2_display = QLabel("Hash 2:")
        self._comparison_result = QLabel("Comparison: ")
        
        results_layout.addWidget(self._hash1_display)
        results_layout.addWidget(self._hash2_display)
        results_layout.addWidget(self._comparison_result)
        
        self._content_layout.addWidget(results_group)
        
        self._content_layout.addStretch() # Push everything to the top

        # Dialog buttons (OK / Cancel from BaseDialog)
        self.add_button("Close", QDialogButtonBox.ButtonRole.AcceptRole, self.accept)

    def _browse_file(self, line_edit: QLineEdit):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select File")
        if file_path:
            line_edit.setText(file_path)

    def _on_verify_button_clicked(self):
        file1_path_str = self._file1_path.text()
        file2_path_str = self._file2_path.text()
        expected_hash_str = self._expected_hash_input.text()
        selected_algo = self._algo_combo.currentData()

        if not file1_path_str:
            QMessageBox.warning(self, "Input Error", "Please select File 1.")
            return

        file1_path = Path(file1_path_str)
        if not file1_path.is_file():
            QMessageBox.warning(self, "Input Error", f"File 1 does not exist: {file1_path_str}")
            return
        
        self._hash1_display.setText("Hash 1: Calculating...")
        self._hash2_display.setText("Hash 2:")
        self._comparison_result.setText("Comparison: ")
        QApplication.processEvents() # Update UI immediately

        try:
            hash1_result = self._hashing_service.hash_file(file1_path, selected_algo)
            self._hash1_display.setText(f"Hash 1 ({hash1_result.algorithm.name.upper()}): {hash1_result.hash_hex}")

            if file2_path_str:
                file2_path = Path(file2_path_str)
                if not file2_path.is_file():
                    QMessageBox.warning(self, "Input Error", f"File 2 does not exist: {file2_path_str}")
                    return

                hash2_result = self._hashing_service.hash_file(file2_path, selected_algo)
                self._hash2_display.setText(f"Hash 2 ({hash2_result.algorithm.name.upper()}): {hash2_result.hash_hex}")

                if hash1_result.matches(hash2_result):
                    self._comparison_result.setText("<font color='green'><b>Comparison: Hashes Match!</b></font>")
                else:
                    self._comparison_result.setText("<font color='red'><b>Comparison: Hashes Differ!</b></font>")
            elif expected_hash_str:
                if self._hashing_service.verify_hash(file1_path, expected_hash_str, selected_algo):
                    self._comparison_result.setText("<font color='green'><b>Verification: Hash Matches Expected!</b></font>")
                else:
                    self._comparison_result.setText("<font color='red'><b>Verification: Hash Does NOT Match Expected!</b></font>")
            else:
                self._comparison_result.setText("<font color='blue'><b>Hash Calculated.</b></font>")

        except Exception as e:
            QMessageBox.critical(self, "Hashing Error", f"An error occurred: {e}")
            self._hash1_display.setText("Hash 1: Error")
            self._hash2_display.setText("Hash 2:")
            self._comparison_result.setText("Comparison: Error")
