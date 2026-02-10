#!/bin/bash
set -euo pipefail

# Only run in Claude Code remote environments
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

# Install Python dependencies from requirements.txt if it exists
if [ -f "requirements.txt" ]; then
  pip install -r requirements.txt
fi

# Install Python project if pyproject.toml exists
if [ -f "pyproject.toml" ]; then
  pip install -e ".[dev]" 2>/dev/null || pip install -e .
fi
