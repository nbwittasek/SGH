#!/bin/bash
# ============================================================
#  One-click launcher for SGH CONTAM Pressurization Tool
#  Just double-click this file — it handles everything:
#    1. Extracts the zip (first run only)
#    2. Creates a Python virtual environment (first run only)
#    3. Installs dependencies (first run only)
#    4. Launches the app and opens your browser
# ============================================================

echo
echo " ============================================="
echo "  SGH Stairwell Pressurization Tool"
echo " ============================================="
echo

# Work from the directory where this script lives
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

APP_DIR="$SCRIPT_DIR/SGH_App"
ZIP_FILE="$SCRIPT_DIR/SGH_StairPressurization.zip"

# ---------- Step 1: Extract zip if app folder doesn't exist ----------
if [ ! -f "$APP_DIR/app.py" ]; then
    echo "[1/4] Extracting application files..."

    if [ ! -f "$ZIP_FILE" ]; then
        echo
        echo " ERROR: Cannot find SGH_StairPressurization.zip"
        echo " Place this launcher next to the zip file and try again."
        echo
        read -p "Press Enter to close..."
        exit 1
    fi

    mkdir -p "$APP_DIR"
    unzip -o "$ZIP_FILE" -d "$APP_DIR"
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to extract zip file."
        read -p "Press Enter to close..."
        exit 1
    fi
    echo " Extracted to $APP_DIR"
    echo
else
    echo "[1/4] Application files found."
fi

cd "$APP_DIR"

# ---------- Step 2: Find Python ----------
echo "[2/4] Checking Python..."
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo
    echo " ERROR: Python is not installed."
    echo " Install Python 3.9+ from https://www.python.org/downloads/"
    echo
    read -p "Press Enter to close..."
    exit 1
fi
echo " Found: $($PYTHON --version)"

# ---------- Step 3: Virtual environment + dependencies ----------
if [ ! -d "venv" ]; then
    echo
    echo "[3/4] First-time setup: creating virtual environment..."
    $PYTHON -m venv venv
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to create virtual environment."
        read -p "Press Enter to close..."
        exit 1
    fi
    source venv/bin/activate
    echo " Installing dependencies (this may take a minute)..."
    pip install -r requirements.txt --quiet --disable-pip-version-check
    if [ $? -ne 0 ]; then
        echo "WARNING: Retrying with verbose output..."
        pip install -r requirements.txt --disable-pip-version-check
    fi
    echo " Setup complete."
else
    echo "[3/4] Virtual environment found."
    source venv/bin/activate
    pip install -r requirements.txt --quiet --disable-pip-version-check 2>/dev/null
fi
echo

# Validate core imports
$PYTHON -c "import fastapi; import uvicorn; import numpy; import pandas; import jinja2" 2>/dev/null
if [ $? -ne 0 ]; then
    echo " ERROR: Dependencies failed to load. Reinstalling..."
    pip install -r requirements.txt --disable-pip-version-check
    echo " Please try launching again."
    read -p "Press Enter to close..."
    exit 1
fi

# Clean stale bytecode
rm -rf __pycache__ core/__pycache__ 2>/dev/null

# ---------- Step 4: Launch ----------
echo "[4/4] Starting application..."
echo
echo " The browser will open automatically."
echo " Press Ctrl+C to stop the server."
echo " ============================================="
echo

$PYTHON app.py
EXIT_CODE=$?

echo
if [ $EXIT_CODE -ne 0 ]; then
    echo " Application crashed (exit code $EXIT_CODE)."
    echo " Check crash_log.txt for details."
fi
echo
read -p "Press Enter to close..."
