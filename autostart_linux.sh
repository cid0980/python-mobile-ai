#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

chmod +x "$SCRIPT_DIR/start_linux.sh"

if [ "${1:-}" = "--enable" ]; then
    "$SCRIPT_DIR/start_linux.sh" --setup-only
    exec "$SCRIPT_DIR/start_linux.sh" --enable-autostart
elif [ "${1:-}" = "--disable" ]; then
    "$SCRIPT_DIR/start_linux.sh" --setup-only
    exec "$SCRIPT_DIR/start_linux.sh" --disable-autostart
elif [ "${1:-}" = "--status" ]; then
    "$SCRIPT_DIR/start_linux.sh" --setup-only >/dev/null
    exec "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/autostart_manager.py" --status
fi

echo "============================================================"
echo "   SpecDeck — Linux Setup, Shortcut & Login Auto-Start"
echo "============================================================"
echo ""
echo "Step 1/2: Verifying Python 3 & all dependencies..."
"$SCRIPT_DIR/start_linux.sh" --setup-only
echo ""
"$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/autostart_manager.py" --status
echo ""
echo "Choose an option:"
echo "  [1] Enable Auto-Start on Linux Login + Create Desktop/Menu Shortcut"
echo "  [2] Create Desktop & App Menu Shortcut Only (No Login Auto-Start)"
echo "  [3] Disable Auto-Start on Linux Login"
echo "  [4] Launch SpecDeck Right Now"
echo "  [5] Exit"
echo ""
read -r -p "Enter choice [1-5]: " CHOICE

case "$CHOICE" in
    1)
        "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/autostart_manager.py" --enable
        "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/autostart_manager.py" --shortcut
        echo ""
        read -r -p "Launch SpecDeck now as well? [Y/n]: " RUN_NOW
        if [[ "${RUN_NOW:-Y}" =~ ^[Yy]$ ]]; then
            exec "$SCRIPT_DIR/start_linux.sh" --background
        fi
        ;;
    2)
        "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/autostart_manager.py" --shortcut
        ;;
    3)
        "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/autostart_manager.py" --disable
        ;;
    4)
        exec "$SCRIPT_DIR/start_linux.sh" --background
        ;;
    *)
        echo "Done."
        ;;
esac
