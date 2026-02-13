@echo off
title CONTAM Pressurization Tool - SGH
echo ============================================
echo  CONTAM Stairwell Pressurization Tool - SGH
echo ============================================
echo.

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
    echo Creating virtual environment...
    %PYTHON% -m venv venv
    if %errorlevel% neq 0 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo Virtual environment created.
    echo.
)

:: Activate virtual environment
call venv\Scripts\activate.bat

:: Install/upgrade dependencies
echo Checking dependencies...
pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)
echo Dependencies OK.
echo.

:: Launch the application
echo Starting CONTAM Pressurization Tool...
echo The browser will open automatically.
echo Close this window or press Ctrl+C to stop the server.
echo.
%PYTHON% app.py
