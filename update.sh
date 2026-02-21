#!/bin/bash
echo "============================================"
echo " CONTAM Pressurization Tool - UPDATE"
echo "============================================"
echo
echo "This script updates an existing installation."
echo "It will update dependencies without recreating the virtual environment."
echo

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "ERROR: No existing installation found."
    echo "Please use launch.sh for first-time setup."
    exit 1
fi

# Find Python
PYTHON=""
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "ERROR: Python is not installed."
    exit 1
fi

echo "Found Python:"
$PYTHON --version
echo

# Activate virtual environment
source venv/bin/activate

# Upgrade dependencies
echo "Updating dependencies..."
pip install -r requirements.txt --upgrade --quiet --disable-pip-version-check 2>/dev/null
echo "Dependencies updated successfully."
echo

echo "============================================"
echo " Update complete!"
echo " Run ./launch.sh to start the application."
echo "============================================"
