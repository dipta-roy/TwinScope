"""
Software update modal dialog for TwinScope.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from PyQt6.QtCore import QByteArray, Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.constants.constants import APP_NAME, APP_VERSION
from app.ui import resources
from app.updater.updater import Updater

logger = logging.getLogger(__name__)


class UpdateDialog(QDialog):
    """
    Modal dialog to check for updates, view release notes,
    and download / install new versions of TwinScope.
    """

    def __init__(self, parent: Optional[QWidget] = None, initial_update_info: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} Software Update")
        self.setModal(True)
        self.setMinimumWidth(480)
        self.setMinimumHeight(320)
        self.resize(500, 360)

        self._update_info: Optional[dict] = initial_update_info
        self._updater = Updater(parent=self)
        self._updater.status_changed.connect(self._on_updater_status)

        self._setup_ui()

        if self._update_info:
            self._display_update_available(self._update_info)
        else:
            self._start_check()

    def _setup_ui(self) -> None:
        """Construct the dialog layout and widgets."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header with Logo and App Information
        header_layout = QHBoxLayout()
        header_layout.setSpacing(16)

        logo_label = QLabel()
        if resources.LOGO_BASE64:
            pixmap = QPixmap()
            pixmap.loadFromData(QByteArray.fromBase64(resources.LOGO_BASE64.encode()))
            logo_label.setPixmap(pixmap.scaled(56, 56, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        header_layout.addWidget(logo_label)

        title_info_layout = QVBoxLayout()
        title_info_layout.setSpacing(4)

        title_label = QLabel(f"{APP_NAME} Software Update")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_info_layout.addWidget(title_label)

        self._version_label = QLabel(f"Current Version: <b>v{APP_VERSION}</b>")
        self._version_label.setStyleSheet("color: #666;")
        title_info_layout.addWidget(self._version_label)

        header_layout.addLayout(title_info_layout)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Status text
        self._status_label = QLabel("Checking for updates...")
        self._status_label.setWordWrap(True)
        self._status_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self._status_label)

        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)  # Indeterminate initially
        self._progress_bar.setTextVisible(True)
        layout.addWidget(self._progress_bar)

        # Release notes text browser (hidden until needed)
        self._notes_browser = QTextBrowser()
        self._notes_browser.setMaximumHeight(140)
        self._notes_browser.setOpenExternalLinks(True)
        self._notes_browser.hide()
        layout.addWidget(self._notes_browser)

        layout.addStretch()

        # Action Buttons Layout
        self._buttons_layout = QHBoxLayout()
        self._buttons_layout.setSpacing(10)
        self._buttons_layout.addStretch()

        self._action_button = QPushButton("Update Now")
        self._action_button.setStyleSheet("font-weight: bold; padding: 6px 14px;")
        self._action_button.clicked.connect(self._on_action_clicked)
        self._action_button.hide()
        self._buttons_layout.addWidget(self._action_button)

        self._secondary_button = QPushButton("Later")
        self._secondary_button.setStyleSheet("padding: 6px 14px;")
        self._secondary_button.clicked.connect(self.reject)
        self._buttons_layout.addWidget(self._secondary_button)

        layout.addLayout(self._buttons_layout)

    def _start_check(self) -> None:
        """Trigger update check."""
        self._status_label.setText("Connecting to update server and checking for new versions...")
        self._progress_bar.show()
        self._progress_bar.setRange(0, 0)
        self._notes_browser.hide()
        self._action_button.hide()
        self._secondary_button.setText("Cancel")
        self._secondary_button.setEnabled(True)
        self._updater.check_for_updates()

    @pyqtSlot(str, object)
    def _on_updater_status(self, status_code: str, data: Any) -> None:
        """Handle updater status events emitted from worker threads."""
        logger.debug(f"UpdateDialog received status: {status_code}")

        if status_code == "UPDATE_AVAILABLE":
            self._update_info = data
            self._display_update_available(data)

        elif status_code == "NO_UPDATE":
            self._progress_bar.hide()
            self._notes_browser.hide()
            self._status_label.setText(
                f"<div style='color: #28a745; font-size: 13px; font-weight: bold;'>You are up to date!</div>"
                f"<p>{APP_NAME} <b>v{APP_VERSION}</b> is currently the newest version available.</p>"
            )
            self._action_button.setText("Check Again")
            self._action_button.clicked.disconnect()
            self._action_button.clicked.connect(self._start_check)
            self._action_button.show()
            self._secondary_button.setText("Close")

        elif status_code == "NO_MSI_FOUND":
            self._progress_bar.hide()
            ver = data.get("version", "newer") if isinstance(data, dict) else "newer"
            url = data.get("html_url", "") if isinstance(data, dict) else ""
            self._status_label.setText(
                f"<div style='color: #d73a49; font-weight: bold;'>New version v{ver} was found, but no Windows installer (.msi) was attached.</div>"
                f"<p>Please check the <a href='{url}'>GitHub Release page</a> to download manually.</p>"
            )
            self._action_button.hide()
            self._secondary_button.setText("Close")

        elif status_code == "DOWNLOADING":
            progress = int(data) if data is not None else 0
            self._progress_bar.show()
            self._progress_bar.setRange(0, 100)
            self._progress_bar.setValue(progress)
            self._status_label.setText(f"Downloading update package... <b>{progress}%</b>")
            self._action_button.setEnabled(False)
            self._secondary_button.setText("Cancel")

        elif status_code == "VERIFYING_HASH":
            self._progress_bar.show()
            self._progress_bar.setRange(0, 0)
            self._status_label.setText("Verifying package SHA-256 integrity...")

        elif status_code == "DOWNLOAD_COMPLETE":
            msi_path = str(data)
            self._progress_bar.show()
            self._progress_bar.setRange(0, 0)
            self._status_label.setText(
                "<b>Download verified!</b> Starting installer...<br>"
                "<span style='color: #666;'>TwinScope will close and restart automatically after update.</span>"
            )
            self._action_button.hide()
            self._secondary_button.setEnabled(False)
            self._updater.install_update(msi_path)

        elif status_code == "INSTALL_STARTED":
            self._status_label.setText(
                "<b>Installer launched successfully.</b><br>"
                "Closing TwinScope now..."
            )
            QTimer.singleShot(1500, self._exit_for_install)

        elif status_code == "ERROR":
            self._progress_bar.hide()
            error_msg = str(data)
            self._status_label.setText(
                f"<div style='color: #d73a49; font-weight: bold;'>Update check failed</div>"
                f"<p style='color: #666;'>{error_msg}</p>"
            )
            self._action_button.setText("Retry")
            self._action_button.clicked.disconnect()
            self._action_button.clicked.connect(self._start_check)
            self._action_button.show()
            self._action_button.setEnabled(True)
            self._secondary_button.setText("Close")

    def _display_update_available(self, info: dict) -> None:
        """Render update available details and action buttons."""
        version = info.get("version", "New")
        release_name = info.get("release_name", f"v{version}")
        release_notes = info.get("release_notes", "").strip()

        self._progress_bar.hide()
        self._status_label.setText(
            f"<div style='color: #0366d6; font-size: 13px; font-weight: bold;'>A new version of {APP_NAME} is available!</div>"
            f"<p>Latest Version: <b>v{version}</b> ({release_name})<br>"
            f"Installed Version: <b>v{APP_VERSION}</b></p>"
            f"<p>Would you like to download and install this update now?</p>"
        )

        if release_notes:
            self._notes_browser.setMarkdown(f"### Release Notes\n\n{release_notes}")
            self._notes_browser.show()
        else:
            self._notes_browser.hide()

        self._action_button.setText("Update Now")
        self._action_button.setEnabled(True)
        self._action_button.clicked.disconnect()
        self._action_button.clicked.connect(self._on_action_clicked)
        self._action_button.show()

        self._secondary_button.setText("Update Later")
        self._secondary_button.setEnabled(True)

    def _on_action_clicked(self) -> None:
        """Start downloading the update."""
        if not self._update_info or not self._update_info.get("url"):
            return

        url = self._update_info["url"]
        hash_url = self._update_info.get("hash_url")

        self._notes_browser.hide()
        self._action_button.setEnabled(False)
        self._status_label.setText("Preparing download...")
        self._progress_bar.show()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._updater.download_update(url, hash_url)

    def _exit_for_install(self) -> None:
        """Close dialog and trigger application exit for MSI installer."""
        self.accept()
        app = QApplication.instance()
        if app:
            app.quit()
