@echo off
setlocal enabledelayedexpansion

echo ===============================================
echo   TwinScope - Launching MSI Builder & Signer
echo ===============================================

:: 1. Check for existing virtual environment
if exist "venv\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment: venv
    call venv\Scripts\activate.bat
    goto run_app
)

if exist ".venv\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment: .venv
    call .venv\Scripts\activate.bat
    goto run_app
)

:: 2. If neither exists, create venv and install dependencies
echo [INFO] Virtual environment not found.
echo [INFO] Creating virtual environment at 'venv'...

python -m venv venv
if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment. Ensure Python 3.10+ is in PATH.
    pause
    exit /b 1
)

echo [SUCCESS] Virtual environment created.
echo [INFO] Activating virtual environment...
call venv\Scripts\activate.bat

if exist "requirements.txt" (
    echo.
    echo [INFO] Installing required dependencies from requirements.txt...
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies from requirements.txt.
        pause
        exit /b 1
    )
    echo [SUCCESS] Dependencies installed successfully.
    echo.
) else (
    echo [WARNING] requirements.txt not found.
)

:run_app
python build_msi_gui.py %*

if errorlevel 1 (
    echo.
    echo [ERROR] Builder GUI closed with an error.
    pause
    exit /b 1
)

exit /b 0

