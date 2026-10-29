#!/usr/bin/env bash
# Workflow Lite launcher (fix 3): picks a Python that actually works on this computer.
#   Mac/Linux: python3 · Windows Git Bash: python or py (skips the Microsoft Store "python3" stub)
# Usage (from .claude/settings.json): bash "$CLAUDE_PROJECT_DIR/tools/lite/run.sh" <script.py> [args...]
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
script="$1"; shift
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1
for py in python3 python py; do
  if command -v "$py" >/dev/null 2>&1 && "$py" -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >/dev/null 2>&1; then
    exec "$py" "$here/$script" "$@"
  fi
done
echo "Workflow Lite: no working Python 3.8+ found (tried python3, python, py). Install Python from python.org." >&2
exit 0   # never block Claude Code because Python is missing
