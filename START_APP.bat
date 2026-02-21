@echo off
setlocal
title SGH Stairwell Pressurization Tool

:: ============================================================
::  One-click launcher for SGH CONTAM Pressurization Tool
::  Just double-click this file — it handles everything:
::    1. Extracts the zip (first run only)
::    2. Creates a Python virtual environment (first run only)
::    3. Installs dependencies (first run only)
::    4. Launches the app and opens your browser
:: ============================================================

echo.
echo  =============================================
echo   SGH Stairwell Pressurization Tool
echo  =============================================
echo.

:: Work from the directory where this script lives
cd /d "%~dp0"

:: ---------- Step 1: Extract zip if app folder doesn't exist ----------
set APP_DIR=%~dp0SGH_App
set ZIP_FILE=%~dp0SGH_StairPressurization.zip

if not exist "%APP_DIR%\app.py" (
    echo [1/4] Extracting application files...

    if not exist "%ZIP_FILE%" (
        echo.
        echo  ERROR: Cannot find SGH_StairPressurization.zip
        echo  Place this launcher next to the zip file and try again.
        echo.
        pause
        exit /b 1
    )

    :: Use PowerShell to extract (available on Win 10+)
    powershell -NoProfile -Command "Expand-Archive -Path '%ZIP_FILE%' -DestinationPath '%APP_DIR%' -Force" 2>nul
    if %errorlevel% neq 0 (
        echo ERROR: Failed to extract zip file.
        echo Make sure PowerShell is available and the zip is not corrupted.
        pause
        exit /b 1
    )
    echo  Extracted to %APP_DIR%
    echo.
) else (
    echo [1/4] Application files found.
)

cd /d "%APP_DIR%"

:: ---------- Step 2: Find Python ----------
echo [2/4] Checking Python...
where python >nul 2>&1
if %errorlevel% neq 0 (
    where python3 >nul 2>&1
    if %errorlevel% neq 0 (
        echo.
        echo  ERROR: Python is not installed or not in PATH.
        echo.
        echo  Please install Python 3.9+ from:
        echo    https://www.python.org/downloads/
        echo.
        echo  IMPORTANT: Check "Add Python to PATH" during installation.
        echo.
        pause
        exit /b 1
    )
    set PYTHON=python3
) else (
    set PYTHON=python
)
echo  Found: & %PYTHON% --version

:: ---------- Step 3: Virtual environment + dependencies ----------
if not exist "venv" (
    echo.
    echo [3/4] First-time setup: creating virtual environment...
    %PYTHON% -m venv venv
    if %errorlevel% neq 0 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    call venv\Scripts\activate.bat
    echo  Installing dependencies (this may take a minute)...
    pip install -r requirements.txt --quiet --disable-pip-version-check
    if %errorlevel% neq 0 (
        echo WARNING: Some dependencies may not have installed correctly.
        echo Retrying with verbose output...
        pip install -r requirements.txt --disable-pip-version-check
    )
    echo  Setup complete.
) else (
    echo [3/4] Virtual environment found.
    call venv\Scripts\activate.bat
    pip install -r requirements.txt --quiet --disable-pip-version-check 2>nul
)
echo.

:: Validate core imports
%PYTHON% -c "import fastapi; import uvicorn; import numpy; import pandas; import jinja2" 2>nul
if %errorlevel% neq 0 (
    echo  ERROR: Dependencies failed to load. Reinstalling...
    pip install -r requirements.txt --disable-pip-version-check
    echo  Please try launching again.
    pause
    exit /b 1
)

:: Clean stale bytecode
if exist "__pycache__" rd /s /q "__pycache__" 2>nul
if exist "core\__pycache__" rd /s /q "core\__pycache__" 2>nul

:: ---------- Step 4: Launch ----------
echo [4/4] Starting application...
echo.
echo  The browser will open automatically.
echo  Close this window or press Ctrl+C to stop.
echo  =============================================
echo.

%PYTHON% app.py
set EXIT_CODE=%errorlevel%

echo.
if %EXIT_CODE% neq 0 (
    echo  Application crashed (exit code %EXIT_CODE%).
    echo  Check crash_log.txt for details.
)
echo.
echo Press any key to close...
pause >nul
