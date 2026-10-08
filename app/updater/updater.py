"""
Application updater service for TwinScope.

Checks GitHub releases for new versions, downloads MSI packages
with SHA-256 integrity verification, and launches silent installers.
"""

from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import sys
import tempfile
import threading
from typing import Any, Callable, Optional

from PyQt6.QtCore import QObject, pyqtSignal
import requests

from app.constants.constants import APP_VERSION, GITHUB_API_URL

logger = logging.getLogger(__name__)


class Updater(QObject):
    """
    Background updater for TwinScope.

    Emits `status_changed(status_code, data)` signal to safely interface
    with the PyQt GUI across worker threads, while maintaining backwards
    compatibility with callback functions.
    """

    status_changed = pyqtSignal(str, object)

    def __init__(self, callback: Optional[Callable[[str, Any], None]] = None, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.callback = callback

    def _notify(self, status_code: str, data: Any = None) -> None:
        """Notify listeners via both PyQt signal and legacy callback."""
        try:
            self.status_changed.emit(status_code, data)
        except Exception as e:
            logger.debug(f"Signal emit error: {e}")

        if self.callback:
            try:
                self.callback(status_code, data)
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def check_for_updates(self) -> None:
        """Checks for updates in a background thread."""
        thread = threading.Thread(target=self._check_update_worker, daemon=True)
        thread.start()

    def _check_update_worker(self) -> None:
        try:
            headers = {
                "User-Agent": f"TwinScope/{APP_VERSION}",
                "Accept": "application/vnd.github.v3+json",
            }
            response = requests.get(GITHUB_API_URL, headers=headers, timeout=10)
            response.raise_for_status()
            release_data = response.json()

            tag_name = release_data.get("tag_name", "").lstrip("vV").strip()
            latest_version = tag_name or "0.0.0"

            assets = release_data.get("assets", [])
            msi_url: Optional[str] = None
            hash_url: Optional[str] = None

            for asset in assets:
                name = asset.get("name", "").lower()
                if name.endswith(".msi"):
                    msi_url = asset.get("browser_download_url")
                elif name.endswith("sha256.txt") or name.endswith(".sha256"):
                    hash_url = asset.get("browser_download_url")

            update_info = {
                "version": latest_version,
                "current_version": APP_VERSION,
                "url": msi_url,
                "hash_url": hash_url,
                "release_name": release_data.get("name", f"TwinScope v{latest_version}"),
                "release_notes": release_data.get("body", ""),
                "html_url": release_data.get("html_url", ""),
            }

            if self._is_newer(latest_version, APP_VERSION):
                if msi_url:
                    self._notify("UPDATE_AVAILABLE", update_info)
                else:
                    self._notify("NO_MSI_FOUND", update_info)
            else:
                self._notify("NO_UPDATE", update_info)

        except Exception as e:
            logger.error(f"Update check failed: {e}")
            self._notify("ERROR", str(e))

    def _is_newer(self, latest: str, current: str) -> bool:
        """Determine whether the latest version string is higher than current."""
        try:
            l_clean = latest.lstrip("vV").strip()
            c_clean = current.lstrip("vV").strip()
            l_parts = [int(x) for x in l_clean.split(".") if x.isdigit()]
            c_parts = [int(x) for x in c_clean.split(".") if x.isdigit()]

            max_len = max(len(l_parts), len(c_parts))
            l_parts += [0] * (max_len - len(l_parts))
            c_parts += [0] * (max_len - len(c_parts))

            return l_parts > c_parts
        except Exception:
            return str(latest) > str(current)

    def download_update(self, url: str, hash_url: Optional[str] = None) -> None:
        """Starts background download of the update."""
        thread = threading.Thread(target=self._download_worker, args=(url, hash_url), daemon=True)
        thread.start()

    def _download_worker(self, url: str, hash_url: Optional[str]) -> None:
        try:
            self._notify("DOWNLOADING", 0)

            headers = {"User-Agent": f"TwinScope/{APP_VERSION}"}
            response = requests.get(url, headers=headers, stream=True, timeout=30)
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0

            temp_dir = tempfile.gettempdir()
            msi_path = os.path.join(temp_dir, "TwinScope_Update.msi")

            with open(msi_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            progress = int((downloaded / total_size) * 100)
                            self._notify("DOWNLOADING", progress)

            # Verify Hash if provided
            if hash_url:
                self._notify("VERIFYING_HASH", None)
                hash_response = requests.get(hash_url, headers=headers, timeout=10)
                hash_response.raise_for_status()
                expected_hash = hash_response.text.split()[0].strip().lower()
                local_hash = self._calculate_file_hash(msi_path)

                if local_hash != expected_hash:
                    if os.path.exists(msi_path):
                        os.remove(msi_path)
                    raise ValueError(f"Hash verification failed (expected {expected_hash}, got {local_hash}).")

            self._notify("DOWNLOAD_COMPLETE", msi_path)

        except Exception as e:
            logger.error(f"Download failed: {e}")
            self._notify("ERROR", str(e))

    def _calculate_file_hash(self, filepath: str) -> str:
        """Calculates SHA-256 hash of a file."""
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest().lower()

    def install_update(self, msi_path: str) -> None:
        """Starts installation of the downloaded MSI."""
        thread = threading.Thread(target=self._install_worker, args=(msi_path,), daemon=False)
        thread.start()

    def _install_worker(self, msi_path: str) -> None:
        try:
            current_exe = sys.executable

            # Command chain:
            # 1. Wait 2s for current process shutdown
            # 2. Run MSI installer
            # 3. Wait 2s for files release
            # 4. Relaunch application
            # 5. Clean up temporary installer
            cmd = (
                f'timeout /t 2 /nobreak & '
                f'start /wait "" msiexec /i "{msi_path}" /qn /norestart & '
                f'timeout /t 2 /nobreak & '
                f'start "" "{current_exe}" & '
                f'del /q "{msi_path}"'
            )

            subprocess.Popen(cmd, shell=True)  # nosec B602
            self._notify("INSTALL_STARTED", msi_path)

        except Exception as e:
            logger.error(f"Install failed: {e}")
            self._notify("ERROR", str(e))
