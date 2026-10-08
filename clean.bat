@echo off
SETLOCAL EnableDelayedExpansion

:: ============================================================================
:: TwinScope - Project Cleanup Script
:: ============================================================================

set "NON_INTERACTIVE=0"
set "CLEAN_VENV=N"
set "VENV_EXPLICIT=0"
set "NO_PAUSE=0"
set "KEEP_DIST=0"

:: ----------------------------------------------------------------------------
:: Argument Parsing
:: ----------------------------------------------------------------------------
:parse_args
if "%~1"=="" goto done_args

if /i "%~1"=="-y" (
    set "NON_INTERACTIVE=1"
    set "NO_PAUSE=1"
    shift
    goto parse_args
)
if /i "%~1"=="/y" (
    set "NON_INTERACTIVE=1"
    set "NO_PAUSE=1"
    shift
    goto parse_args
)
if /i "%~1"=="--yes" (
    set "NON_INTERACTIVE=1"
    set "NO_PAUSE=1"
    shift
    goto parse_args
)
if /i "%~1"=="-f" (
    set "NON_INTERACTIVE=1"
    set "NO_PAUSE=1"
    shift
    goto parse_args
)
if /i "%~1"=="/f" (
    set "NON_INTERACTIVE=1"
    set "NO_PAUSE=1"
    shift
    goto parse_args
)
if /i "%~1"=="--force" (
    set "NON_INTERACTIVE=1"
    set "NO_PAUSE=1"
    shift
    goto parse_args
)
if /i "%~1"=="--non-interactive" (
    set "NON_INTERACTIVE=1"
    set "NO_PAUSE=1"
    shift
    goto parse_args
)
if /i "%~1"=="--venv" (
    set "CLEAN_VENV=Y"
    set "VENV_EXPLICIT=1"
    shift
    goto parse_args
)
if /i "%~1"=="/venv" (
    set "CLEAN_VENV=Y"
    set "VENV_EXPLICIT=1"
    shift
    goto parse_args
)
if /i "%~1"=="--all" (
    set "NON_INTERACTIVE=1"
    set "CLEAN_VENV=Y"
    set "VENV_EXPLICIT=1"
    set "NO_PAUSE=1"
    shift
    goto parse_args
)
if /i "%~1"=="/all" (
    set "NON_INTERACTIVE=1"
    set "CLEAN_VENV=Y"
    set "VENV_EXPLICIT=1"
    set "NO_PAUSE=1"
    shift
    goto parse_args
)
if /i "%~1"=="--no-pause" (
    set "NO_PAUSE=1"
    shift
    goto parse_args
)
if /i "%~1"=="--keep-dist" (
    set "KEEP_DIST=1"
    shift
    goto parse_args
)
if /i "%~1"=="--help" goto show_help
if /i "%~1"=="-h" goto show_help
if /i "%~1"=="/?" goto show_help

echo [WARNING] Unknown option: %~1
shift
goto parse_args

:show_help
echo.
echo ===============================================
echo   TwinScope - Cleanup Utility
echo ===============================================
echo Usage: clean.bat [OPTIONS]
echo.
echo Options:
echo   -y, --yes, -f, --force    Run non-interactively without confirmation prompts
echo   --non-interactive         Alias for -y
echo   --venv                    Remove the virtual environment (venv\)
echo   --all                     Clean everything including venv non-interactively
echo   --no-pause                Do not pause upon completion
echo   -h, --help, /?            Display this help message
echo.
exit /b 0

:done_args

echo ===============================================
echo   TwinScope - Cleanup
echo ===============================================
echo.

:: ----------------------------------------------------------------------------
:: Confirmation Prompt (Interactive Mode Only)
:: ----------------------------------------------------------------------------
if "!NON_INTERACTIVE!"=="0" (
    set /p CONFIRM="This will remove build artifacts and cache files. Continue? (Y/N): "
    if /i not "!CONFIRM!"=="Y" (
        echo [INFO] Cleanup cancelled.
        if "!NO_PAUSE!"=="0" pause
        exit /b 0
    )
)

echo.
echo [INFO] Cleaning build artifacts and cache files...
echo.

set FILES_CLEANED=0

:: Remove build folder
if exist "build\" (
    rmdir /s /q build
    echo [SUCCESS] Removed build\ folder.
    set /a FILES_CLEANED+=1
)

:: Remove dist folder
if "!KEEP_DIST!"=="0" (
    if exist "dist\" (
        rmdir /s /q dist
        echo [SUCCESS] Removed dist\ folder.
        set /a FILES_CLEANED+=1
    )
)

:: Remove leftover build / crash reports
if exist "installer\nuitka-crash-report.xml" (
    del /q installer\nuitka-crash-report.xml
    echo [SUCCESS] Removed nuitka crash report.
    set /a FILES_CLEANED+=1
)

:: Remove test and lint caches
if exist ".pytest_cache\" (
    rmdir /s /q .pytest_cache
    echo [INFO] Removed .pytest_cache\
    set /a FILES_CLEANED+=1
)

if exist ".mypy_cache\" (
    rmdir /s /q .mypy_cache
    echo [INFO] Removed .mypy_cache\
    set /a FILES_CLEANED+=1
)

if exist ".ruff_cache\" (
    rmdir /s /q .ruff_cache
    echo [INFO] Removed .ruff_cache\
    set /a FILES_CLEANED+=1
)

:: Remove __pycache__ folders in project source
if exist "__pycache__\" (
    rmdir /s /q __pycache__
    echo [INFO] Removed root __pycache__\
    set /a FILES_CLEANED+=1
)
for /d /r app %%d in (__pycache__) do @if exist "%%d" (
    rmdir /s /q "%%d"
    echo [INFO] Removed %%d
    set /a FILES_CLEANED+=1
)
for /d /r installer %%d in (__pycache__) do @if exist "%%d" (
    rmdir /s /q "%%d"
    echo [INFO] Removed %%d
    set /a FILES_CLEANED+=1
)

:: Remove .pyc and .pyo files in project source
for /r app %%f in (*.pyc *.pyo) do @if exist "%%f" (
    del /q "%%f"
    set /a FILES_CLEANED+=1
)
for /r installer %%f in (*.pyc *.pyo) do @if exist "%%f" (
    del /q "%%f"
    set /a FILES_CLEANED+=1
)
for %%f in (*.pyc *.pyo) do @if exist "%%f" (
    del /q "%%f"
    set /a FILES_CLEANED+=1
)


echo.
if !FILES_CLEANED! gtr 0 (
    echo [SUCCESS] Cleanup completed. Removed !FILES_CLEANED! item categories.
) else (
    echo [INFO] Nothing to clean - project is already clean.
)
echo.

:: ----------------------------------------------------------------------------
:: Virtual Environment Cleanup
:: ----------------------------------------------------------------------------
if "!NON_INTERACTIVE!"=="0" (
    if "!VENV_EXPLICIT!"=="0" (
        set /p CLEAN_VENV="Do you also want to remove the virtual environment? (Y/N): "
    )
)

if /i "!CLEAN_VENV!"=="Y" (
    if exist "venv\" (
        echo [INFO] Removing virtual environment...
        rmdir /s /q venv
        echo [SUCCESS] Virtual environment removed.
    ) else (
        echo [INFO] No virtual environment found.
    )
)

echo.
echo ===============================================
echo   Cleanup completed.
echo ===============================================
echo.

if "!NO_PAUSE!"=="0" (
    pause
)

exit /b 0