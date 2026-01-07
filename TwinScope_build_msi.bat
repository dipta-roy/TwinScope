@echo off
setlocal enabledelayedexpansion

echo ===============================================
echo   TwinScope - Build MSI Installer (cx_Freeze)
echo ===============================================

:: 1. Setup Environment
echo [STEP 1/2] Setting up environment...
if exist "venv\Scripts\activate.bat" call venv\Scripts\activate.bat

:: 2. Build Core Executables
echo.
echo [STEP 2/3] Building Core Executables...
echo This will create the raw binaries in the 'build' folder.

python installer\setup_msi.py build

if errorlevel 1 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
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
pause

:: 3. Package MSI
echo.
echo [STEP 3/3] Packaging MSI Installer...
echo Note: This step uses the binaries from the build folder.

python installer\setup_msi.py bdist_msi

if errorlevel 1 (
    echo [ERROR] MSI packaging failed.
    pause
    exit /b 1
)

:: Move the result to dist/
echo.
echo Moving installer to dist/...
if not exist "dist" mkdir "dist"

:: Find the generated MSI file in the dist subfolder created by cx_Freeze (usually dist/)
:: cx_Freeze outputs to "dist" relative to where setup.py is run.
:: Since we ran it from root, it should be in "dist" already.
:: However, checking specifically for the .msi file.

for %%f in (dist\*.msi) do (
    echo Found: %%f
    echo Installer built successfully!
)

echo.
echo ===============================================
echo   Installer Build Complete!
echo ===============================================
echo.
pause
