@echo off
setlocal enabledelayedexpansion

echo ===============================================
echo   Generating SHA1 and SHA256 Hashes
echo ===============================================

set "NO_PAUSE=0"
set "MSI_INPUT="

:parse_args
if "%~1"=="" goto done_args
if /i "%~1"=="--no-pause" (set "NO_PAUSE=1" & shift & goto parse_args)
if /i "%~1"=="-y" (set "NO_PAUSE=1" & shift & goto parse_args)
if "%MSI_INPUT%"=="" (set "MSI_INPUT=%~1" & shift & goto parse_args)
shift
goto parse_args

:done_args

if not "%MSI_INPUT%"=="" (
    set "MSI_FILE=%MSI_INPUT%"
    goto check_file
)

if not exist "dist" (
    echo [ERROR] 'dist' folder not found. Please build the MSI first.
    if "!NO_PAUSE!"=="0" pause
    exit /b 1
)

:: Find the latest MSI file in dist
set "MSI_FILE="
for %%f in (dist\*.msi) do (
    set "MSI_FILE=%%f"
)

if "%MSI_FILE%"=="" (
    echo [ERROR] No MSI file found in 'dist' folder.
    if "!NO_PAUSE!"=="0" pause
    exit /b 1
)

:check_file
echo Target: %MSI_FILE%
echo.

python installer\generate_hash.py "%MSI_FILE%"

if errorlevel 1 (
    echo.
    echo [ERROR] Failed to generate hashes.
    if "!NO_PAUSE!"=="0" pause
    exit /b 1
) else (
    echo.
    echo [SUCCESS] SHA1 and SHA256 files generated successfully.
)

if "!NO_PAUSE!"=="0" pause
exit /b 0

