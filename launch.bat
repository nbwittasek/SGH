@echo off
title CONTAM Pressurization Tool - SGH
echo ============================================
echo  CONTAM Stairwell Pressurization Tool - SGH
echo ============================================
echo.

:: Set log file path (same directory as this script)
set LOGFILE=%~dp0crash_log.txt

:: Clear previous log
echo CONTAM Tool Launch — %date% %time% > "%LOGFILE%"

:: Check if Python is available
where python >nul 2>&1
if %errorlevel% neq 0 (
    where python3 >nul 2>&1
    if %errorlevel% neq 0 (
        echo ERROR: Python is not installed or not in PATH.
        echo.
        echo Please install Python 3.9+ from https://www.python.org/downloads/
        echo Make sure to check "Add Python to PATH" during installation.
        echo.
        pause
        exit /b 1
    )
    set PYTHON=python3
) else (
    set PYTHON=python
)

echo Found Python:
%PYTHON% --version
echo.

:: Check if virtual environment exists
if not exist "venv" (
    echo First-time setup: Creating virtual environment...
    %PYTHON% -m venv venv
    if %errorlevel% neq 0 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo Virtual environment created.
    echo.
) else (
    echo Virtual environment found. Checking for updates...
)

:: Activate virtual environment
call venv\Scripts\activate.bat

:: Install/upgrade dependencies
echo Checking dependencies...
pip install -r requirements.txt --quiet --disable-pip-version-check 2>nul
if %errorlevel% neq 0 (
    echo WARNING: Some dependencies may not have installed correctly.
    echo Attempting to continue...
    echo.
)
echo Dependencies OK.
echo.

:: Quick validation — make sure core dependencies load
echo Validating dependencies...
%PYTHON% -c "import fastapi; import uvicorn; import numpy; import pandas; import jinja2; print('Core dependencies OK')" 2>>"%LOGFILE%"
if %errorlevel% neq 0 (
    echo.
    echo ====================================================
    echo  ERROR: Missing dependencies!
    echo ====================================================
    echo.
    if exist "%LOGFILE%" (
        type "%LOGFILE%"
    )
    echo.
    echo Reinstalling dependencies...
    pip install -r requirements.txt --disable-pip-version-check
    echo.
    echo Please try launching again.
    echo.
    pause
    exit /b 1
)
echo Validation OK.
echo.

:: Clean stale bytecode (prevents crashes after file updates)
if exist "__pycache__" rd /s /q "__pycache__" 2>nul
if exist "core\__pycache__" rd /s /q "core\__pycache__" 2>nul

:: Check if port 5000 is already in use
netstat -aon 2>nul | findstr ":5000.*LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo NOTE: Port 5000 is already in use.
    echo   A previous instance may still be running.
    echo   The tool will automatically use the next available port.
    echo   To free port 5000, close the other instance or run:
    echo     netstat -aon ^| findstr :5000
    echo   to find the PID, then: taskkill /PID [pid] /F
    echo.
)

:: Launch the application
echo Starting CONTAM Pressurization Tool...
echo The browser will open automatically to http://localhost:5000
echo Close this window or press Ctrl+C to stop the server.
echo.

:: Run the app — stderr goes to log file AND console via tee workaround
:: Since Windows doesn't have tee, we capture stderr to log
%PYTHON% app.py 2>>"%LOGFILE%"
set EXIT_CODE=%errorlevel%

:: If we get here, the app has exited
echo.
if %EXIT_CODE% neq 0 (
    echo ====================================================
    echo  The application crashed! (exit code %EXIT_CODE%)
    echo ====================================================
    echo.
    if exist "%LOGFILE%" (
        echo Error log (%LOGFILE%):
        echo ----------------------------------------------------
        type "%LOGFILE%"
        echo.
        echo ----------------------------------------------------
    )
    echo.
    echo Please share crash_log.txt if reporting this issue.
) else (
    echo Application stopped.
)

echo.
echo Press any key to close...
pause >nul
