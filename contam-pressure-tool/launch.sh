#!/bin/bash
echo "============================================"
echo " CONTAM Stairwell Pressurization Tool - SGH"
echo "============================================"
echo

# Find Python
PYTHON=""
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "ERROR: Python is not installed."
    echo "Please install Python 3.9+ from https://www.python.org/downloads/"
    exit 1
fi

echo "Found Python:"
$PYTHON --version
echo

# Create virtual environment if needed
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON -m venv venv
    echo "Virtual environment created."
    echo
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "Checking dependencies..."
pip install -r requirements.txt --quiet
echo "Dependencies OK."
echo

# Launch
echo "Starting CONTAM Pressurization Tool..."
echo "The browser will open automatically."
echo "Press Ctrl+C to stop the server."
echo
$PYTHON app.py
