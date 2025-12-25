@echo off
setlocal enabledelayedexpansion

echo ===============================================
echo   TwinScope - Build Script
echo ===============================================

:: 1. Setup Environment
echo [STEP 1/4] Setting up environment...

:: Check for virtual environment
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

:: Ensure PyInstaller is installed
pip install pyinstaller

echo.

:: 2. Identify Options
set PYINSTALLER_OPTS=--onedir --windowed --name="TwinScope" --icon="images/app_icon.ico"

:: Entry point
set ENTRY_POINT=main.py

:: 3. Build Core Application
echo [STEP 2/4] Generating Spec file...
pyi-makespec %PYINSTALLER_OPTS% --specpath . main.py

if errorlevel 1 (
    echo [ERROR] Failed to generate spec file.
    pause
    exit /b 1
)

echo [STEP 2.5/4] Preparing Spec file...
python installer\prepare_spec.py TwinScope.spec

echo [STEP 2.6/4] Building from Spec file...
pyinstaller --noconfirm TwinScope.spec

if errorlevel 1 (
    echo [ERROR] PyInstaller failed.
    pause
    exit /b 1
)

echo.
echo [STEP 3/4] Copying resources...
:: If we have resources folder, copy it
if exist "resources" (
    xcopy /E /I /Y "resources" "dist\TwinScope\resources\"
)

echo.
echo [STEP 4/4] Build complete!
echo Output directory: dist\TwinScope\
echo.
if "%~1"=="--no-pause" goto :eof
pause
