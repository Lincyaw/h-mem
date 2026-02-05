#!/bin/bash
# Auto-remember wrapper script for Claude Code hooks
# This script is called by the Stop hook to automatically memorize conversations

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HMEM_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Run the auto-remember script with uv
cd "$HMEM_DIR" && uv run python "$SCRIPT_DIR/auto_remember.py" 2>/dev/null &

# Don't block the hook - run in background
exit 0
