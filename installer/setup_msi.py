import sys
import os
from cx_Freeze import setup, Executable

# Add the current directory to sys.path so that cx_Freeze can find the 'app' package
sys.path.append(os.getcwd())

# Define the base for the executable
# "Win32GUI" means no console window.
base = "Win32GUI" if sys.platform == "win32" else None

# Paths
icon_path = os.path.abspath("images/app_icon.ico")

# GUID for the application (generated specifically for TwinScope)
# Changing this allows upgrades.
UPGRADE_CODE = "{A8271C53-96B3-4197-8CFD-ACAEB2460786}"

# Build Options
build_exe_options = {
    "packages": ["os", "sys", "ctypes", "win32com.client", "app"],
    "excludes": ["tkinter", "unittest", "email", "xmlrpc"],
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
    "initial_target_dir": r"[ProgramFilesFolder]\TwinScope",
    "install_icon": icon_path,
    "target_name": "TwinScope_Setup_1.1.0.msi",
}

# Executable Configuration
target = Executable(
    script="main.py",
    base=base,
    target_name="TwinScope.exe",
    icon=icon_path,
    shortcut_name="TwinScope",
    shortcut_dir="DesktopFolder",  # Create shortcut on Desktop
)

setup(
    name="TwinScope",
    version="1.1.0",
    description="Professional File Comparison Tool",
    author="TwinScope Team",
    options={
        "build_exe": build_exe_options,
        "bdist_msi": bdist_msi_options,
    },
    executables=[target],
)
