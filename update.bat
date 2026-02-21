@echo off
title CONTAM Pressurization Tool - Update
echo ============================================
echo  CONTAM Pressurization Tool - UPDATE
echo ============================================
echo.
echo This script updates an existing installation.
echo It will update dependencies without recreating the virtual environment.
echo.

:: Check if virtual environment exists
if not exist "venv" (
    echo ERROR: No existing installation found.
    echo Please use launch.bat for first-time setup.
    echo.
    pause
    exit /b 1
)

:: Check if Python is available
where python >nul 2>&1
if %errorlevel% neq 0 (
    where python3 >nul 2>&1
    if %errorlevel% neq 0 (
        echo ERROR: Python is not installed or not in PATH.
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

:: Activate virtual environment
call venv\Scripts\activate.bat

:: Upgrade dependencies
echo Updating dependencies...
pip install -r requirements.txt --upgrade --quiet --disable-pip-version-check 2>nul
if %errorlevel% neq 0 (
    echo WARNING: Some dependencies may not have updated correctly.
    echo Attempting to continue...
) else (
    echo Dependencies updated successfully.
)
echo.

:: Clean stale bytecode
echo Cleaning cached files...
if exist "__pycache__" rd /s /q "__pycache__" 2>nul
if exist "core\__pycache__" rd /s /q "core\__pycache__" 2>nul
echo Done.
echo.

echo ============================================
echo  Update complete!
echo  Run launch.bat to start the application.
echo ============================================
echo.
pause
