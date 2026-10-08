"""
TwinScope - GUI Automation Tool for Building, Signing, and Packaging MSI.

This tool provides an automated GUI interface to:
1. Accept the latest version number and update project constants/environment.
2. Accept SignTool path, private key (.pfx/.p12), and password.
3. Automatically perform pre-build cleanup via clean.bat.
4. Build core executables via TwinScope_build_msi.bat.
5. Digitally sign TwinScope.exe.
6. Package the MSI installer via TwinScope_build_msi.bat.
7. Digitally sign the final MSI installer.
8. Automatically generate SHA1 (.sha1) and SHA256 checksums via generate_hash.bat and installer/generate_hash.py.
9. Perform automated post-build cleanup.
10. Display a live progress bar, real-time logs, and a final summary with direct access to output files.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtCore import QThread, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QIcon, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


# Root directory of TwinScope
REPO_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = REPO_ROOT / "installer" / ".builder_config.json"


def get_current_app_version() -> str:
    """Retrieve current version from app/constants/constants.py or default."""
    try:
        from app.constants.constants import APP_VERSION
        return str(APP_VERSION)
    except Exception:
        # Fallback regex extraction
        const_file = REPO_ROOT / "app" / "constants" / "constants.py"
        if const_file.exists():
            match = re.search(r'APP_VERSION:\s*str\s*=\s*["\']([^"\']+)["\']', const_file.read_text(encoding="utf-8"))
            if match:
                return match.group(1)
        return "1.2.0"


def update_constants_version(new_version: str) -> bool:
    """Update APP_VERSION in app/constants/constants.py."""
    const_file = REPO_ROOT / "app" / "constants" / "constants.py"
    if not const_file.exists():
        return False
    try:
        content = const_file.read_text(encoding="utf-8")
        updated = re.sub(
            r'(APP_VERSION:\s*str\s*=\s*["\'])([^"\']+)(["\'])',
            rf"\g<1>{new_version}\g<3>",
            content,
            count=1,
        )
        if updated != content:
            const_file.write_text(updated, encoding="utf-8")
        return True
    except Exception:
        return False


def find_default_signtool() -> str:
    """Attempt to locate signtool.exe in PATH or common Windows SDK paths."""
    # 1. System PATH
    found = shutil.which("signtool.exe") or shutil.which("signtool")
    if found:
        return os.path.abspath(found)

    # 2. Windows Kits directories
    kit_roots = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Windows Kits\10\bin"),
        os.path.expandvars(r"%ProgramFiles%\Windows Kits\10\bin"),
    ]
    candidates: List[str] = []
    for root in kit_roots:
        if os.path.isdir(root):
            try:
                for entry in os.listdir(root):
                    dir_path = os.path.join(root, entry)
                    if os.path.isdir(dir_path):
                        for arch in ["x64", "x86"]:
                            tool_path = os.path.join(dir_path, arch, "signtool.exe")
                            if os.path.isfile(tool_path):
                                candidates.append(tool_path)
            except OSError:
                continue

    if candidates:
        candidates.sort(reverse=True)
        return candidates[0]

    return ""


# =============================================================================
# Background Worker Thread
# =============================================================================
class BuildWorker(QThread):
    """Executes the full automated build, sign, and checksum pipeline."""

    sig_progress = pyqtSignal(int, str)
    sig_log = pyqtSignal(str)
    sig_finished = pyqtSignal(dict)
    sig_error = pyqtSignal(str)

    def __init__(
        self,
        version: str,
        signtool_path: str,
        pfx_path: str,
        password: str,
        timestamp_url: str,
        sign_enabled: bool,
        clean_pre: bool,
        clean_post: bool,
    ) -> None:
        super().__init__()
        self.version = version.strip()
        self.signtool_path = signtool_path.strip()
        self.pfx_path = pfx_path.strip()
        self.password = password
        self.timestamp_url = timestamp_url.strip() or "http://timestamp.digicert.com"
        self.sign_enabled = sign_enabled
        self.clean_pre = clean_pre
        self.clean_post = clean_post
        self._is_cancelled = False
        self._current_process: Optional[subprocess.Popen] = None

    def cancel(self) -> None:
        """Cancel the running build pipeline."""
        self._is_cancelled = True
        if self._current_process and self._current_process.poll() is None:
            try:
                self._current_process.terminate()
            except Exception:
                pass

    def _run_cmd(self, cmd_args: List[str], env: Optional[Dict[str, str]] = None, mask_pwd: bool = False) -> int:
        """Run a command, streaming stdout/stderr to sig_log, masking secrets."""
        if self._is_cancelled:
            return -1

        # Format log display without exposing secrets
        display_cmd = []
        for arg in cmd_args:
            if self.password and arg == self.password:
                display_cmd.append("********")
            else:
                display_cmd.append(arg)

        self.sig_log.emit(f"\n[EXEC] {' '.join(display_cmd)}\n")

        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        try:
            self._current_process = subprocess.Popen(
                cmd_args,
                cwd=str(REPO_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=merged_env,
                shell=False,
            )

            assert self._current_process.stdout is not None
            for line in iter(self._current_process.stdout.readline, ""):
                if self._is_cancelled:
                    self._current_process.terminate()
                    break
                clean_line = line.rstrip()
                if self.password:
                    clean_line = clean_line.replace(self.password, "********")
                if clean_line:
                    self.sig_log.emit(clean_line)

            self._current_process.stdout.close()
            return_code = self._current_process.wait()
            self._current_process = None
            return return_code
        except Exception as e:
            self.sig_log.emit(f"[ERROR] Failed to execute process: {e}")
            return 1

    def _sign_file(self, file_path: str, description: str) -> bool:
        """Sign a target binary or MSI using SignTool."""
        if not self.sign_enabled:
            self.sig_log.emit(f"[SIGN] Skipping signing for {description} (signing disabled).")
            return True

        if not os.path.exists(file_path):
            self.sig_log.emit(f"[ERROR] Signing target file not found: {file_path}")
            return False

        self.sig_log.emit(f"[SIGN] Signing {description}: {file_path}")

        # Attempt 1: With Timestamp Server
        cmd = [
            self.signtool_path,
            "sign",
            "/f",
            self.pfx_path,
            "/p",
            self.password,
            "/fd",
            "SHA256",
            "/tr",
            self.timestamp_url,
            "/td",
            "SHA256",
            file_path,
        ]

        code = self._run_cmd(cmd)
        if code == 0:
            self.sig_log.emit(f"[SUCCESS] Digitally signed {description} with timestamp.")
            return True

        self.sig_log.emit(f"[WARNING] Timestamp signing failed for {description}. Retrying without timestamp...")

        # Attempt 2: Fallback without Timestamp Server
        cmd_no_ts = [
            self.signtool_path,
            "sign",
            "/f",
            self.pfx_path,
            "/p",
            self.password,
            "/fd",
            "SHA256",
            file_path,
        ]
        code = self._run_cmd(cmd_no_ts)
        if code == 0:
            self.sig_log.emit(f"[SUCCESS] Digitally signed {description} (without timestamp).")
            return True

        self.sig_log.emit(f"[ERROR] SignTool failed with code {code}.")
        return False

    def run(self) -> None:
        """Pipeline execution routine."""
        try:
            self.sig_progress.emit(5, "Validating inputs...")
            self.sig_log.emit("==================================================")
            self.sig_log.emit(f" Starting TwinScope Automated Build for v{self.version}")
            self.sig_log.emit("==================================================")

            if self.sign_enabled:
                if not os.path.isfile(self.signtool_path):
                    self.sig_error.emit(f"SignTool executable not found: {self.signtool_path}")
                    return
                if not os.path.isfile(self.pfx_path):
                    self.sig_error.emit(f"Certificate/Private Key file not found: {self.pfx_path}")
                    return

            # Step 1: Pre-Build Cleanup
            if self.clean_pre:
                self.sig_progress.emit(10, "Cleaning previous build artifacts...")
                clean_bat = str(REPO_ROOT / "clean.bat")
                cmd = [clean_bat, "-y"]
                res = self._run_cmd(cmd)
                if res != 0:
                    self.sig_log.emit("[WARNING] Pre-build clean returned non-zero, continuing...")

            if self._is_cancelled:
                return

            # Step 2: Version Configuration
            self.sig_progress.emit(20, f"Setting version to v{self.version}...")
            if not update_constants_version(self.version):
                self.sig_log.emit("[WARNING] Could not update version in constants.py; relying on env override.")
            else:
                self.sig_log.emit(f"[INFO] Updated APP_VERSION in app/constants/constants.py to {self.version}")


            env_vars = {"TWINSCOPE_BUILD_VERSION": self.version}

            if self._is_cancelled:
                return

            # Step 3: Build Core Executables
            self.sig_progress.emit(35, "Building core binaries (TwinScope_build_msi.bat)...")
            build_bat = str(REPO_ROOT / "TwinScope_build_msi.bat")
            res = self._run_cmd([build_bat, "--build-only"], env=env_vars)
            if res != 0:
                self.sig_error.emit("Core binary build step failed. See logs for details.")
                return

            if self._is_cancelled:
                return

            # Step 4: Sign TwinScope.exe
            if self.sign_enabled:
                self.sig_progress.emit(50, "Digitally signing TwinScope.exe...")
                # Locate TwinScope.exe inside build/exe.*
                exe_candidates = list((REPO_ROOT / "build").glob("exe.*/TwinScope.exe"))
                if not exe_candidates:
                    self.sig_error.emit("Could not find compiled TwinScope.exe in build/ directory.")
                    return
                target_exe = str(exe_candidates[0])
                if not self._sign_file(target_exe, "TwinScope.exe"):
                    self.sig_error.emit("Failed to sign TwinScope.exe.")
                    return

            if self._is_cancelled:
                return

            # Step 5: Package MSI Installer
            self.sig_progress.emit(65, "Packaging MSI installer (TwinScope_build_msi.bat)...")
            res = self._run_cmd([build_bat, "--package-only"], env=env_vars)
            if res != 0:
                self.sig_error.emit("MSI packaging step failed. See logs for details.")
                return

            if self._is_cancelled:
                return

            # Locate newly created MSI
            dist_dir = REPO_ROOT / "dist"
            msi_candidates = sorted(dist_dir.glob(f"*{self.version}*.msi"), key=os.path.getmtime, reverse=True)
            if not msi_candidates:
                msi_candidates = sorted(dist_dir.glob("*.msi"), key=os.path.getmtime, reverse=True)

            if not msi_candidates:
                self.sig_error.emit("No MSI installer found in dist/ directory after packaging.")
                return

            final_msi = str(msi_candidates[0])
            self.sig_log.emit(f"[INFO] Found MSI installer: {final_msi}")

            if self._is_cancelled:
                return

            # Step 6: Sign MSI Installer
            if self.sign_enabled:
                self.sig_progress.emit(80, "Digitally signing MSI installer package...")
                if not self._sign_file(final_msi, "MSI Installer"):
                    self.sig_error.emit("Failed to sign MSI installer package.")
                    return

            if self._is_cancelled:
                return

            # Step 7: Generate Hashes (.sha1 and .sha256)
            self.sig_progress.emit(90, "Generating SHA1 and SHA256 checksums...")
            hash_bat = str(REPO_ROOT / "generate_hash.bat")
            res = self._run_cmd([hash_bat, final_msi, "--no-pause"])
            if res != 0:
                self.sig_error.emit("Checksum generation step failed. See logs for details.")
                return

            sha1_path = final_msi + ".sha1"
            sha256_path = final_msi + ".sha256.txt"

            sha1_val = ""
            if os.path.exists(sha1_path):
                content = Path(sha1_path).read_text(encoding="utf-8").strip()
                sha1_val = content.split()[0] if content else ""

            sha256_val = ""
            if os.path.exists(sha256_path):
                content = Path(sha256_path).read_text(encoding="utf-8").strip()
                sha256_val = content.split()[0] if content else ""

            # Step 8: Post-Build Cleanup
            if self.clean_post:
                self.sig_progress.emit(96, "Performing post-build cleanup...")
                clean_bat = str(REPO_ROOT / "clean.bat")
                self._run_cmd([clean_bat, "-y", "--keep-dist"])

            self.sig_progress.emit(100, "Build, signing, and checksums completed successfully!")
            self.sig_log.emit("\n==================================================")
            self.sig_log.emit(" BUILD PIPELINE COMPLETED SUCCESSFULLY!")
            self.sig_log.emit(f" Final MSI:  {final_msi}")
            self.sig_log.emit(f" SHA1 Hash:  {sha1_val}")
            self.sig_log.emit(f" SHA1 File:  {sha1_path}")
            self.sig_log.emit("==================================================\n")

            self.sig_finished.emit({
                "msi_path": final_msi,
                "sha1_path": sha1_path,
                "sha1_val": sha1_val,
                "sha256_path": sha256_path,
                "sha256_val": sha256_val,
            })

        except Exception as e:
            self.sig_error.emit(f"Unexpected error during build pipeline: {e}")


# =============================================================================
# Main GUI Window
# =============================================================================
class BuildMsiGui(QMainWindow):
    """Modern GUI application for automated TwinScope MSI building and signing."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("TwinScope - MSI Builder & Automated Signer")
        self.resize(880, 800)
        self.setMinimumSize(780, 700)

        # Apply app icon if available
        icon_path = REPO_ROOT / "images" / "app_icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.worker: Optional[BuildWorker] = None
        self._last_result: Optional[Dict[str, str]] = None

        self._apply_dark_theme()
        self._init_ui()
        self._load_saved_config()

    def _apply_dark_theme(self) -> None:
        """Apply modern dark stylesheet tailored for TwinScope tools."""
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #161822;
                color: #e2e8f0;
                font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
                font-size: 13px;
            }
            QGroupBox {
                border: 1px solid #2d3748;
                border-radius: 8px;
                margin-top: 14px;
                padding-top: 14px;
                font-weight: bold;
                color: #818cf8;
                background-color: #1e2230;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }
            QLabel {
                color: #cbd5e1;
            }
            QLineEdit {
                background-color: #0f111a;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 7px 10px;
                color: #f8fafc;
                selection-background-color: #6366f1;
            }
            QLineEdit:focus {
                border: 1px solid #6366f1;
            }
            QPushButton {
                background-color: #312e81;
                border: 1px solid #4338ca;
                border-radius: 6px;
                padding: 7px 14px;
                color: #e0e7ff;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #3730a3;
                border: 1px solid #6366f1;
            }
            QPushButton:pressed {
                background-color: #1e1b4b;
            }
            QPushButton:disabled {
                background-color: #1e2230;
                border: 1px solid #2d3748;
                color: #64748b;
            }
            QPushButton#primaryBtn {
                background-color: #4f46e5;
                border: 1px solid #6366f1;
                color: #ffffff;
                font-size: 14px;
                font-weight: 600;
                padding: 9px 20px;
            }
            QPushButton#primaryBtn:hover {
                background-color: #4338ca;
            }
            QPushButton#cancelBtn {
                background-color: #7f1d1d;
                border: 1px solid #991b1b;
                color: #fecaca;
                font-weight: 600;
            }
            QPushButton#cancelBtn:hover {
                background-color: #991b1b;
            }
            QCheckBox {
                color: #cbd5e1;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 17px;
                height: 17px;
                border-radius: 4px;
                border: 1px solid #475569;
                background-color: #0f111a;
            }
            QCheckBox::indicator:checked {
                background-color: #6366f1;
                border-color: #6366f1;
            }
            QProgressBar {
                border: 1px solid #334155;
                border-radius: 8px;
                text-align: center;
                background-color: #0f111a;
                color: #f8fafc;
                font-weight: bold;
                height: 22px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4f46e5, stop:1 #10b981);
                border-radius: 7px;
            }
            QPlainTextEdit {
                background-color: #090a10;
                border: 1px solid #1e293b;
                border-radius: 6px;
                color: #a5b4fc;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                padding: 8px;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
        """)

    def _init_ui(self) -> None:
        """Initialize all user interface components."""
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        # Header Title
        title_label = QLabel("TwinScope - MSI Builder & Automated Signer")
        title_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #f8fafc; margin-bottom: 2px;")
        subtitle_label = QLabel("Builds raw binaries, signs executables, packages MSI, generates SHA1 checksums, and cleans artifacts.")
        subtitle_label.setStyleSheet("color: #94a3b8; font-size: 12px; margin-bottom: 4px;")
        main_layout.addWidget(title_label)
        main_layout.addWidget(subtitle_label)

        # Scroll area for configurations
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(12)

        # ---------------------------------------------------------------------
        # 1. Version Box
        # ---------------------------------------------------------------------
        ver_group = QGroupBox("Release Version")
        ver_layout = QHBoxLayout(ver_group)
        ver_layout.setContentsMargins(14, 14, 14, 14)

        ver_lbl = QLabel("Target Version:")
        self.ver_input = QLineEdit()
        self.ver_input.setPlaceholderText("e.g. 1.2.0")
        self.ver_input.setText(get_current_app_version())

        reset_ver_btn = QPushButton("Reset to constants.py")
        reset_ver_btn.clicked.connect(lambda: self.ver_input.setText(get_current_app_version()))

        ver_layout.addWidget(ver_lbl)
        ver_layout.addWidget(self.ver_input, stretch=1)
        ver_layout.addWidget(reset_ver_btn)
        scroll_layout.addWidget(ver_group)

        # ---------------------------------------------------------------------
        # 2. Code Signing Credentials Box
        # ---------------------------------------------------------------------
        sign_group = QGroupBox("Code Signing Credentials (SignTool)")
        sign_grid = QGridLayout(sign_group)
        sign_grid.setContentsMargins(14, 14, 14, 14)
        sign_grid.setSpacing(10)

        # Sign Enable Toggle
        self.sign_enabled_cb = QCheckBox("Enable Digital Signing (TwinScope.exe & MSI Installer)")
        self.sign_enabled_cb.setChecked(True)
        self.sign_enabled_cb.toggled.connect(self._on_sign_toggle)
        sign_grid.addWidget(self.sign_enabled_cb, 0, 0, 1, 3)

        # SignTool Path
        sign_grid.addWidget(QLabel("SignTool Path:"), 1, 0)
        self.signtool_input = QLineEdit()
        self.signtool_input.setPlaceholderText("Path to signtool.exe (e.g. C:\\Program Files (x86)\\Windows Kits\\10\\bin\\...\\signtool.exe)")
        browse_signtool_btn = QPushButton("Browse...")
        browse_signtool_btn.clicked.connect(self._browse_signtool)
        detect_signtool_btn = QPushButton("Auto-Detect")
        detect_signtool_btn.clicked.connect(self._auto_detect_signtool)

        signtool_btn_layout = QHBoxLayout()
        signtool_btn_layout.setSpacing(6)
        signtool_btn_layout.addWidget(browse_signtool_btn)
        signtool_btn_layout.addWidget(detect_signtool_btn)

        sign_grid.addWidget(self.signtool_input, 1, 1)
        sign_grid.addLayout(signtool_btn_layout, 1, 2)

        # Certificate / Private Key Path
        sign_grid.addWidget(QLabel("Private Key (.pfx/.p12):"), 2, 0)
        self.pfx_input = QLineEdit()
        self.pfx_input.setPlaceholderText("Path to code-signing certificate / private key (.pfx, .p12)")
        browse_pfx_btn = QPushButton("Browse...")
        browse_pfx_btn.clicked.connect(self._browse_pfx)
        sign_grid.addWidget(self.pfx_input, 2, 1)
        sign_grid.addWidget(browse_pfx_btn, 2, 2)

        # Password
        sign_grid.addWidget(QLabel("Certificate Password:"), 3, 0)
        self.pwd_input = QLineEdit()
        self.pwd_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd_input.setPlaceholderText("Enter certificate password")

        self.toggle_pwd_btn = QPushButton("Show")
        self.toggle_pwd_btn.setCheckable(True)
        self.toggle_pwd_btn.toggled.connect(self._toggle_pwd_visibility)

        sign_grid.addWidget(self.pwd_input, 3, 1)
        sign_grid.addWidget(self.toggle_pwd_btn, 3, 2)

        # Timestamp URL
        sign_grid.addWidget(QLabel("RFC 3161 Timestamp Server:"), 4, 0)
        self.ts_input = QLineEdit()
        self.ts_input.setText("http://timestamp.digicert.com")
        self.ts_input.setPlaceholderText("http://timestamp.digicert.com")
        sign_grid.addWidget(self.ts_input, 4, 1, 1, 2)

        scroll_layout.addWidget(sign_group)

        # ---------------------------------------------------------------------
        # 3. Automation & Cleanup Options Box
        # ---------------------------------------------------------------------
        opts_group = QGroupBox("Automation & Cleanup Workflow")
        opts_layout = QVBoxLayout(opts_group)
        opts_layout.setContentsMargins(14, 14, 14, 14)
        opts_layout.setSpacing(8)

        self.clean_pre_cb = QCheckBox("Clean prior build and cache files before build (clean.bat -y)")
        self.clean_pre_cb.setChecked(True)

        self.clean_post_cb = QCheckBox("Clean intermediate build folder upon completion (keeps dist/ and hashes)")
        self.clean_post_cb.setChecked(True)

        opts_layout.addWidget(self.clean_pre_cb)
        opts_layout.addWidget(self.clean_post_cb)
        scroll_layout.addWidget(opts_group)

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll, stretch=0)

        # ---------------------------------------------------------------------
        # 4. Progress & Action Section
        # ---------------------------------------------------------------------
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)

        self.start_btn = QPushButton("Build, Sign & Package MSI")
        self.start_btn.setObjectName("primaryBtn")
        self.start_btn.setMinimumHeight(42)
        self.start_btn.clicked.connect(self._start_build)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.setMinimumHeight(42)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_build)

        action_layout.addWidget(self.start_btn, stretch=3)
        action_layout.addWidget(self.cancel_btn, stretch=1)
        main_layout.addLayout(action_layout)

        # Status and Progress Bar
        self.status_lbl = QLabel("Ready to build.")
        self.status_lbl.setStyleSheet("color: #94a3b8; font-size: 13px; font-weight: 500;")
        main_layout.addWidget(self.status_lbl)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        main_layout.addWidget(self.progress_bar)

        # ---------------------------------------------------------------------
        # 5. Results Box (Hidden until completion)
        # ---------------------------------------------------------------------
        self.results_frame = QFrame()
        self.results_frame.setStyleSheet("""
            QFrame {
                background-color: #1e293b;
                border: 1px solid #10b981;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        self.results_frame.setVisible(False)
        res_layout = QVBoxLayout(self.results_frame)
        res_layout.setContentsMargins(12, 10, 12, 10)
        res_layout.setSpacing(6)

        res_title = QLabel("Build and Packaging Completed Successfully!")
        res_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #34d399;")
        res_layout.addWidget(res_title)

        # MSI Path Row
        msi_row = QHBoxLayout()
        self.msi_path_lbl = QLabel("MSI File: ")
        self.msi_path_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.msi_path_lbl.setStyleSheet("color: #f1f5f9; font-weight: 500;")
        open_dist_btn = QPushButton("Open Dist Folder")
        open_dist_btn.clicked.connect(self._open_dist_folder)
        msi_row.addWidget(self.msi_path_lbl, stretch=1)
        msi_row.addWidget(open_dist_btn)
        res_layout.addLayout(msi_row)

        # SHA1 Row
        sha1_row = QHBoxLayout()
        self.sha1_val_lbl = QLabel("SHA1 Hash: ")
        self.sha1_val_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.sha1_val_lbl.setStyleSheet("color: #cbd5e1; font-family: monospace;")
        copy_sha1_btn = QPushButton("Copy SHA1")
        copy_sha1_btn.clicked.connect(self._copy_sha1)
        sha1_row.addWidget(self.sha1_val_lbl, stretch=1)
        sha1_row.addWidget(copy_sha1_btn)
        res_layout.addLayout(sha1_row)

        main_layout.addWidget(self.results_frame)

        # ---------------------------------------------------------------------
        # 6. Real-time Log Console
        # ---------------------------------------------------------------------
        log_header = QHBoxLayout()
        log_title = QLabel("Execution Log:")
        log_title.setStyleSheet("color: #94a3b8; font-weight: 600;")
        clear_log_btn = QPushButton("Clear")
        clear_log_btn.setMaximumWidth(70)
        clear_log_btn.clicked.connect(self._clear_log)
        log_header.addWidget(log_title)
        log_header.addStretch()
        log_header.addWidget(clear_log_btn)
        main_layout.addLayout(log_header)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(180)
        main_layout.addWidget(self.log_view, stretch=1)

        self.setCentralWidget(main_widget)

    # =========================================================================
    # UI Callbacks & Helpers
    # =========================================================================
    def _on_sign_toggle(self, checked: bool) -> None:
        """Enable or disable signing-related inputs."""
        self.signtool_input.setEnabled(checked)
        self.pfx_input.setEnabled(checked)
        self.pwd_input.setEnabled(checked)
        self.toggle_pwd_btn.setEnabled(checked)
        self.ts_input.setEnabled(checked)

    def _browse_signtool(self) -> None:
        """Browse file dialog for signtool.exe."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select SignTool Executable",
            str(Path(self.signtool_input.text()).parent if self.signtool_input.text() else "C:\\"),
            "Executables (*.exe);;All Files (*)",
        )
        if file_path:
            self.signtool_input.setText(os.path.normpath(file_path))

    def _auto_detect_signtool(self) -> None:
        """Auto-detect signtool.exe."""
        found = find_default_signtool()
        if found:
            self.signtool_input.setText(os.path.normpath(found))
            self._log(f"[INFO] Auto-detected SignTool: {found}")
        else:
            QMessageBox.information(
                self,
                "SignTool Not Found",
                "SignTool was not automatically detected in PATH or Windows Kits.\nPlease browse to locate signtool.exe manually.",
            )

    def _browse_pfx(self) -> None:
        """Browse file dialog for private key / certificate."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Code Signing Certificate / Private Key",
            str(REPO_ROOT),
            "Certificate Files (*.pfx *.p12 *.cer);;All Files (*)",
        )
        if file_path:
            self.pfx_input.setText(os.path.normpath(file_path))

    def _toggle_pwd_visibility(self, checked: bool) -> None:
        """Toggle mask/unmask on password field."""
        if checked:
            self.pwd_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.toggle_pwd_btn.setText("Hide")
        else:
            self.pwd_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.toggle_pwd_btn.setText("Show")

    def _clear_log(self) -> None:
        """Clear text in log view."""
        self.log_view.clear()

    def _log(self, text: str) -> None:
        """Append line to log view and scroll to end."""
        self.log_view.appendPlainText(text)
        self.log_view.moveCursor(QTextCursor.MoveOperation.End)

    def _open_dist_folder(self) -> None:
        """Open dist folder in Windows Explorer."""
        dist_dir = REPO_ROOT / "dist"
        if dist_dir.exists():
            if self._last_result and os.path.exists(self._last_result.get("msi_path", "")):
                subprocess.run(["explorer.exe", f"/select,{self._last_result['msi_path']}"])
            else:
                subprocess.run(["explorer.exe", str(dist_dir)])

    def _copy_sha1(self) -> None:
        """Copy SHA1 hash to system clipboard."""
        if self._last_result and self._last_result.get("sha1_val"):
            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setText(self._last_result["sha1_val"])
                self.status_lbl.setText("SHA1 hash copied to clipboard!")

    # =========================================================================
    # Configuration Load / Save (Password is NEVER saved to disk)
    # =========================================================================
    def _load_saved_config(self) -> None:
        """Load non-sensitive configuration values from config file."""
        # Pre-populate signtool if detectable
        detected = find_default_signtool()
        if detected:
            self.signtool_input.setText(os.path.normpath(detected))

        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                if "signtool_path" in data and data["signtool_path"]:
                    self.signtool_input.setText(data["signtool_path"])
                if "pfx_path" in data and data["pfx_path"]:
                    self.pfx_input.setText(data["pfx_path"])
                if "timestamp_url" in data and data["timestamp_url"]:
                    self.ts_input.setText(data["timestamp_url"])
                if "sign_enabled" in data:
                    self.sign_enabled_cb.setChecked(bool(data["sign_enabled"]))
                if "clean_pre" in data:
                    self.clean_pre_cb.setChecked(bool(data["clean_pre"]))
                if "clean_post" in data:
                    self.clean_post_cb.setChecked(bool(data["clean_post"]))
            except Exception:
                pass

    def _save_config(self) -> None:
        """Save non-sensitive settings to config file (Password is excluded)."""
        data = {
            "signtool_path": self.signtool_input.text().strip(),
            "pfx_path": self.pfx_input.text().strip(),
            "timestamp_url": self.ts_input.text().strip(),
            "sign_enabled": self.sign_enabled_cb.isChecked(),
            "clean_pre": self.clean_pre_cb.isChecked(),
            "clean_post": self.clean_post_cb.isChecked(),
        }
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    # =========================================================================
    # Build Execution Control
    # =========================================================================
    def _start_build(self) -> None:
        """Validate settings and launch the worker thread."""
        version = self.ver_input.text().strip()
        if not version:
            QMessageBox.warning(self, "Invalid Version", "Please enter a valid version number (e.g. 1.2.0).")
            return

        signtool = self.signtool_input.text().strip()
        pfx = self.pfx_input.text().strip()
        pwd = self.pwd_input.text()
        sign_enabled = self.sign_enabled_cb.isChecked()

        if sign_enabled:
            if not signtool or not os.path.isfile(signtool):
                QMessageBox.warning(self, "SignTool Not Found", "Please specify a valid path to signtool.exe.")
                return
            if not pfx or not os.path.isfile(pfx):
                QMessageBox.warning(self, "Certificate Not Found", "Please specify a valid path to your .pfx/.p12 file.")
                return
            if not pwd:
                reply = QMessageBox.question(
                    self,
                    "Empty Password",
                    "The certificate password is currently empty. Continue without a password?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

        # Persist non-sensitive configuration
        self._save_config()

        # Update UI state
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.results_frame.setVisible(False)
        self.status_lbl.setText("Starting build pipeline...")
        self._clear_log()

        # Launch Worker Thread
        self.worker = BuildWorker(
            version=version,
            signtool_path=signtool,
            pfx_path=pfx,
            password=pwd,
            timestamp_url=self.ts_input.text().strip(),
            sign_enabled=sign_enabled,
            clean_pre=self.clean_pre_cb.isChecked(),
            clean_post=self.clean_post_cb.isChecked(),
        )
        self.worker.sig_progress.connect(self._on_worker_progress)
        self.worker.sig_log.connect(self._log)
        self.worker.sig_finished.connect(self._on_worker_finished)
        self.worker.sig_error.connect(self._on_worker_error)
        self.worker.start()

    def _cancel_build(self) -> None:
        """Cancel active worker thread."""
        if self.worker:
            self.status_lbl.setText("Cancelling build...")
            self.worker.cancel()
            self.cancel_btn.setEnabled(False)

    @pyqtSlot(int, str)
    def _on_worker_progress(self, percent: int, message: str) -> None:
        """Handle progress updates from worker."""
        self.progress_bar.setValue(percent)
        self.status_lbl.setText(message)

    @pyqtSlot(dict)
    def _on_worker_finished(self, results: dict) -> None:
        """Handle successful build pipeline completion."""
        self._last_result = results
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setValue(100)
        self.status_lbl.setText("Build, signing, and checksum generation complete!")

        # Display results box
        msi_path = results.get("msi_path", "")
        sha1_val = results.get("sha1_val", "")
        self.msi_path_lbl.setText(f"MSI File:  {msi_path}")
        self.sha1_val_lbl.setText(f"SHA1:      {sha1_val}")
        self.results_frame.setVisible(True)

        QMessageBox.information(
            self,
            "Build Succeeded",
            f"TwinScope MSI built and signed successfully!\n\nInstaller:\n{msi_path}\n\nSHA1:\n{sha1_val}",
        )

    @pyqtSlot(str)
    def _on_worker_error(self, error_message: str) -> None:
        """Handle build pipeline error."""
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.status_lbl.setText(f"Failed: {error_message}")
        self._log(f"\n[FATAL ERROR] {error_message}\n")
        QMessageBox.critical(self, "Build Failed", error_message)


# =============================================================================
# Entry Point
# =============================================================================
def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("TwinScope MSI Builder")
    window = BuildMsiGui()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
