@echo off
SETLOCAL EnableDelayedExpansion

echo ===============================================
echo   Can Cache Files
echo ===============================================
echo.

set /p CONFIRM="This will remove build artifacts and cache files. Continue? (Y/N): "
if /i not "!CONFIRM!"=="Y" (
    echo [INFO] Cleanup cancelled.
    pause
    exit /b 0
)

echo.
echo [INFO] Cleaning build artifacts...
echo.

set FILES_CLEANED=0

REM Remove build folder
if exist "build\" (
    rmdir /s /q build
    echo [SUCCESS] Removed build\ folder.
    set /a FILES_CLEANED+=1
)

REM Remove dist folder
if exist "dist\" (
    rmdir /s /q dist
    echo [SUCCESS] Removed dist\ folder.
    set /a FILES_CLEANED+=1
)

REM Remove spec files
if exist "*.spec" (
    del /q *.spec
    echo [SUCCESS] Removed .spec files.
    set /a FILES_CLEANED+=1
)

REM Remove __pycache__ folders
for /d /r . %%d in (__pycache__) do @if exist "%%d" (
    rmdir /s /q "%%d"
    echo [INFO] Removed %%d
    set /a FILES_CLEANED+=1
)

REM Remove .pyc files
for /r . %%f in (*.pyc) do @if exist "%%f" (
    del /q "%%f"
    set /a FILES_CLEANED+=1
)


echo.
if !FILES_CLEANED! gtr 0 (
    echo [SUCCESS] Cleanup completed! Removed !FILES_CLEANED! items.
) else (
    echo [INFO] Nothing to clean - project is already clean.
)
echo.

set /p CLEAN_VENV="Do you also want to remove the virtual environment? (Y/N): "
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
echo   Cleanup complete!
echo ===============================================
pause