@echo off
setlocal enabledelayedexpansion

echo =========================================
echo TwinScope Code Quality ^& Security Scan
echo =========================================

echo.
echo Activating virtual environment...
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    echo [INFO] Activated virtual environment: venv
) else if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo [INFO] Activated virtual environment: .venv
) else (
    echo [WARNING] Neither venv nor .venv activate script was found!
    echo           Scans will run in the current Python environment.
)

:: Target folders and files for TwinScope
set SCAN_TARGETS=app main.py installer

echo.
echo [1/3] Running Ruff Linter ^& Formatter...
python -m ruff check --fix %SCAN_TARGETS% > ruff_report.txt 2>&1
if !ERRORLEVEL! EQU 0 (
    echo [OK] Ruff passed!
) else (
    echo [!] Ruff found issues. See ruff_report.txt
)

echo.
echo [2/3] Running MyPy Static Type Check...
python -m mypy --config-file mypy.ini %SCAN_TARGETS% > mypy_report.txt 2>&1
if !ERRORLEVEL! EQU 0 (
    echo [OK] MyPy passed!
) else (
    echo [!] MyPy found issues. See mypy_report.txt
)

echo.
echo [3/3] Running Bandit Security Scan...
python -m bandit -r %SCAN_TARGETS% -ll > bandit_report.txt 2>&1
if !ERRORLEVEL! EQU 0 (
    echo [OK] Bandit passed!
) else (
    echo [!] Bandit found issues. See bandit_report.txt
)

echo.
echo =========================================
echo All scans complete! Reports generated:
echo - ruff_report.txt
echo - mypy_report.txt
echo - bandit_report.txt
echo =========================================
pause
