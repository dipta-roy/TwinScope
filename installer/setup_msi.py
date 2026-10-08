import os
import sys

# Add repository root to sys.path so that cx_Freeze can find the 'app' package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cx_Freeze import Executable, setup  # noqa: E402
from app.constants.constants import (  # noqa: E402
    APP_AUTHOR,
    APP_DESCRIPTION,
    APP_NAME,
    APP_VERSION,
    UPGRADE_CODE,
)

# Allow version override via environment variable
APP_VERSION = os.environ.get("TWINSCOPE_BUILD_VERSION", APP_VERSION).strip() or APP_VERSION


# Define the base for the executable
# "Win32GUI" means no console window.
base = "Win32GUI" if sys.platform == "win32" else None

# Paths
icon_path = os.path.abspath("images/app_icon.ico")

# Build Options
build_exe_options = {
    "packages": ["os", "sys", "ctypes", "win32com.client", "app", "chardet", "defusedxml", "pypdf", "docx", "openpyxl", "pptx", "PIL", "requests", "PyQt6"],
    "excludes": ["tkinter", "unittest", "email", "xmlrpc", "PySide6", "PySide2", "PyQt5"],
    "include_files": [
        (icon_path, "images/app_icon.ico"),
    ],
    "include_msvcr": True,  # Include Microsoft Visual C++ Redistributable
    "zip_include_packages": ["*"],  # Bundle all packages into library.zip
    "zip_exclude_packages": [],
    "optimize": 2,  # Optimize bytecode (remove docstrings)
}

# MSI Options
bdist_msi_options = {
    "add_to_path": False,
    "upgrade_code": UPGRADE_CODE,
    "initial_target_dir": rf"[ProgramFilesFolder]\{APP_NAME}",
    "install_icon": icon_path,
    "target_name": f"{APP_NAME}_Setup_{APP_VERSION}.msi",
}

# Executable Configuration
target = Executable(
    script="main.py",
    base=base,
    target_name=f"{APP_NAME}.exe",
    icon=icon_path,
    shortcut_name=APP_NAME,
    shortcut_dir="DesktopFolder",  # Create shortcut on Desktop
)

setup(
    name=APP_NAME,
    version=APP_VERSION,
    description=APP_DESCRIPTION,
    author=APP_AUTHOR,
    options={
        "build_exe": build_exe_options,
        "bdist_msi": bdist_msi_options,
    },
    executables=[target],
)
