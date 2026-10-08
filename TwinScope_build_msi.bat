@echo off
setlocal enabledelayedexpansion

echo ===============================================
echo   TwinScope - Build MSI Installer (cx_Freeze)
echo ===============================================

set "NO_PAUSE=0"
set "STAGE="

:parse_args
if "%~1"=="" goto done_args
if /i "%~1"=="--no-pause" (set "NO_PAUSE=1" & shift & goto parse_args)
if /i "%~1"=="-y" (set "NO_PAUSE=1" & shift & goto parse_args)
if /i "%~1"=="--build-only" (set "STAGE=build" & set "NO_PAUSE=1" & shift & goto parse_args)
if /i "%~1"=="--package-only" (set "STAGE=package" & set "NO_PAUSE=1" & shift & goto parse_args)
shift
goto parse_args

:done_args

:: 1. Setup Environment
echo [STEP 1/3] Setting up environment...
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo [INFO] Virtual environment not found. Creating 'venv'...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        if "!NO_PAUSE!"=="0" pause
        exit /b 1
    )
    call venv\Scripts\activate.bat
    if exist "requirements.txt" (
        echo [INFO] Installing dependencies from requirements.txt...
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        if errorlevel 1 (
            echo [ERROR] Failed to install dependencies.
            if "!NO_PAUSE!"=="0" pause
            exit /b 1
        )
    )
)


if "%STAGE%"=="package" goto step_package

:: 2. Build Core Executables
echo.
echo [STEP 2/3] Building Core Executables...
echo This will create the raw binaries in the 'build' folder.

python installer\setup_msi.py build

if errorlevel 1 (
    echo [ERROR] Build failed.
    if "!NO_PAUSE!"=="0" pause
    exit /b 1
)

if "%STAGE%"=="build" (
    echo [SUCCESS] Core executables built successfully.
    exit /b 0
)

echo.
echo ===============================================================================
echo   [PAUSE FOR SIGNING]
echo.
echo   The raw executables have been built in the 'build' directory.
echo   (Look for a folder like build\exe.win-amd64-3.11\)
echo.
echo   If you wish to digitally sign 'TwinScope.exe' (to avoid Unknown Publisher
echo   warnings when the app runs), please do so NOW.
echo.
echo   When you are finished signing the files in the build folder,
echo   press any key to continue to packaging.
echo ===============================================================================
if "!NO_PAUSE!"=="0" pause

:step_package
:: 3. Package MSI
echo.
echo [STEP 3/3] Packaging MSI Installer...
echo Note: This step uses the binaries from the build folder.

python installer\setup_msi.py bdist_msi

if errorlevel 1 (
    echo [ERROR] MSI packaging failed.
    if "!NO_PAUSE!"=="0" pause
    exit /b 1
)

:: Move the result to dist/
echo.
echo Moving installer to dist/...
if not exist "dist" mkdir "dist"

for %%f in (dist\*.msi) do (
    echo Found: %%f
    echo Installer built successfully.
)

echo.
echo ===============================================
echo   Installer Build Complete.
echo ===============================================
echo.
if "!NO_PAUSE!"=="0" pause

exit /b 0

