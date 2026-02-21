#!/bin/bash
echo "============================================"
echo " CONTAM Stairwell Pressurization Tool - SGH"
echo "============================================"
echo

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
LOGFILE="$SCRIPT_DIR/crash_log.txt"
echo "CONTAM Tool Launch — $(date)" > "$LOGFILE"

# Find Python
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "ERROR: Python is not installed."
    echo "Install Python 3.9+ from https://www.python.org/downloads/"
    exit 1
fi

echo "Found Python: $($PYTHON --version)"
echo

# Create or reuse virtual environment
if [ ! -d "venv" ]; then
    echo "First-time setup: Creating virtual environment..."
    $PYTHON -m venv venv
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to create virtual environment."
        read -p "Press Enter to close..."
        exit 1
    fi
    echo "Virtual environment created."
else
    echo "Virtual environment found. Checking for updates..."
fi

source venv/bin/activate

echo "Checking dependencies..."
pip install -r requirements.txt --quiet --disable-pip-version-check 2>/dev/null
echo "Dependencies OK."
echo

# Validate core imports
echo "Validating dependencies..."
$PYTHON -c "import fastapi; import uvicorn; import numpy; import pandas; import jinja2; print('Core dependencies OK')" 2>>"$LOGFILE"
if [ $? -ne 0 ]; then
    echo "ERROR: Missing dependencies!"
    cat "$LOGFILE"
    echo
    echo "Reinstalling..."
    pip install -r requirements.txt
    echo "Please try launching again."
    read -p "Press Enter to close..."
    exit 1
fi
echo "Validation OK."
echo

# Clean stale bytecode (prevents crashes after file updates)
rm -rf __pycache__ core/__pycache__ 2>/dev/null

echo "Starting CONTAM Pressurization Tool..."
echo "The browser will open automatically to http://localhost:5000"
echo "Press Ctrl+C to stop the server."
echo

$PYTHON app.py 2>>"$LOGFILE"
EXIT_CODE=$?

echo
if [ $EXIT_CODE -ne 0 ]; then
    echo "===================================================="
    echo " The application crashed! (exit code $EXIT_CODE)"
    echo "===================================================="
    echo
    if [ -f "$LOGFILE" ]; then
        echo "Error log ($LOGFILE):"
        echo "----------------------------------------------------"
        cat "$LOGFILE"
        echo "----------------------------------------------------"
    fi
    echo
    echo "Please share crash_log.txt if reporting this issue."
else
    echo "Application stopped."
fi

echo
read -p "Press Enter to close..."
