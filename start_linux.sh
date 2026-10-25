#!/usr/bin/env bash
# ============================================================================
# start_linux.sh — SpecDeck AI One-Click Linux Auto-Installer & Launcher
# Automatically installs Python 3 + Tkinter + venv if missing, sets up .venv,
# installs all requirements.txt dependencies, and launches SpecDeck AI.
# ============================================================================

set -euo pipefail

# Resolve real project directory (even if launched from symlink or .desktop)
SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do
    DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
    SOURCE="$(readlink "$SOURCE")"
    [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
cd "$SCRIPT_DIR"

MODE="${1:-launch}"
VENV_DIR="$SCRIPT_DIR/.venv"
VENV_PY="$VENV_DIR/bin/python"
STAMP_FILE="$VENV_DIR/.reqs.sha256"

log()  { printf "\033[1;34m[SpecDeck AI]\033[0m %s\n" "$*"; }
ok()   { printf "\033[1;32m[  OK  ]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[ WARN ]\033[0m %s\n" "$*"; }
err()  { printf "\033[1;31m[ERROR ]\033[0m %s\n" "$*" >&2; }

# ----------------------------------------------------------------------------
# 1. Check & Auto-Install Python 3.9+ with venv, ensurepip, and tkinter
# ----------------------------------------------------------------------------
check_system_python() {
    command -v python3 >/dev/null 2>&1 || return 1
    python3 -c "import sys, venv, tkinter; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >/dev/null 2>&1
}

run_privileged() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    elif command -v pkexec >/dev/null 2>&1; then
        pkexec "$@"
    else
        err "Root privileges are required to install Python packages, and neither sudo nor pkexec was found."
        return 1
    fi
}

install_system_python() {
    warn "Python 3.9+ (or python3-tk / python3-venv) is missing. Installing automatically..."

    if command -v apt-get >/dev/null 2>&1; then
        run_privileged apt-get update
        run_privileged env DEBIAN_FRONTEND=noninteractive apt-get install -y \
            python3 python3-pip python3-venv python3-tk ca-certificates curl
    elif command -v dnf >/dev/null 2>&1; then
        run_privileged dnf install -y python3 python3-pip python3-tkinter ca-certificates curl
    elif command -v yum >/dev/null 2>&1; then
        run_privileged yum install -y python3 python3-pip python3-tkinter ca-certificates curl
    elif command -v pacman >/dev/null 2>&1; then
        run_privileged pacman -Sy --noconfirm --needed python python-pip tk ca-certificates curl
    elif command -v zypper >/dev/null 2>&1; then
        run_privileged zypper --non-interactive install python3 python3-pip python3-tk ca-certificates curl
    elif command -v apk >/dev/null 2>&1; then
        run_privileged apk add --no-cache python3 py3-pip python3-tkinter ca-certificates curl
    elif command -v xbps-install >/dev/null 2>&1; then
        run_privileged xbps-install -Sy python3 python3-pip python3-tkinter ca-certificates curl
    else
        err "Unsupported Linux package manager. Please install Python 3.9+, pip, venv, and tkinter manually."
        exit 1
    fi
}

if ! check_system_python; then
    install_system_python
    if ! check_system_python; then
        err "Python 3.9+ with Tkinter still not ready after installation attempt."
        exit 1
    fi
fi
ok "System Python ($(python3 --version 2>&1)) + Tkinter verified."

# ----------------------------------------------------------------------------
# 2. Create Virtual Environment (.venv) & Bootstrap pip
# ----------------------------------------------------------------------------
if [ ! -x "$VENV_PY" ]; then
    log "Creating isolated Python virtual environment (.venv)..."
    rm -rf "$VENV_DIR"
    if ! python3 -m venv "$VENV_DIR" 2>/dev/null; then
        warn "ensurepip unavailable in distro build — bootstrapping pip directly..."
        if command -v apt-get >/dev/null 2>&1; then
            PY_MINOR="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
            run_privileged env DEBIAN_FRONTEND=noninteractive apt-get install -y "python${PY_MINOR}-venv" python3-venv || true
        fi
        rm -rf "$VENV_DIR"
        if ! python3 -m venv "$VENV_DIR" 2>/dev/null; then
            python3 -m venv --without-pip "$VENV_DIR"
            python3 -c "import urllib.request; urllib.request.urlretrieve('https://bootstrap.pypa.io/get-pip.py', '/tmp/get-pip.py')"
            "$VENV_PY" /tmp/get-pip.py
            rm -f /tmp/get-pip.py
        fi
    fi
fi

# ----------------------------------------------------------------------------
# 3. Install / Verify All Dependencies from requirements.txt
# ----------------------------------------------------------------------------
REQ_HASH="$(python3 -c "import hashlib, pathlib; print(hashlib.sha256(pathlib.Path('requirements.txt').read_bytes()).hexdigest())")"
SAVED_HASH=""
[ -f "$STAMP_FILE" ] && SAVED_HASH="$(cat "$STAMP_FILE" 2>/dev/null || true)"

deps_already_valid() {
    [ "$REQ_HASH" = "$SAVED_HASH" ] || return 1
    "$VENV_PY" -c "import customtkinter, groq, ddgs, dotenv, requests, edge_tts, pygame, tkinter" >/dev/null 2>&1
}

if ! deps_already_valid; then
    log "Installing / updating SpecDeck AI Python dependencies..."
    "$VENV_PY" -m pip install --upgrade pip --quiet
    "$VENV_PY" -m pip install -r "$SCRIPT_DIR/requirements.txt"
    echo "$REQ_HASH" > "$STAMP_FILE"
    ok "All dependencies installed successfully!"
else
    ok "All dependencies already up to date."
fi

# ----------------------------------------------------------------------------
# 4. Handle CLI Modes (Setup-Only / Auto-Start / Background / Foreground Launch)
# ----------------------------------------------------------------------------
case "$MODE" in
    --setup-only)
        "$VENV_PY" "$SCRIPT_DIR/autostart_manager.py" --shortcut >/dev/null 2>&1 || true
        ok "Setup complete! Run ./start_linux.sh anytime to open SpecDeck AI."
        exit 0
        ;;
    --enable-autostart)
        "$VENV_PY" "$SCRIPT_DIR/autostart_manager.py" --enable
        "$VENV_PY" "$SCRIPT_DIR/autostart_manager.py" --shortcut || true
        exit 0
        ;;
    --disable-autostart)
        "$VENV_PY" "$SCRIPT_DIR/autostart_manager.py" --disable
        exit 0
        ;;
    --status-autostart)
        "$VENV_PY" "$SCRIPT_DIR/autostart_manager.py" --status
        exit 0
        ;;
    --background)
        log "Launching SpecDeck AI in background..."
        nohup "$VENV_PY" "$SCRIPT_DIR/app.py" >/tmp/specdeck_ai.log 2>&1 &
        exit 0
        ;;
    *)
        log "Starting SpecDeck AI..."
        exec "$VENV_PY" "$SCRIPT_DIR/app.py"
        ;;
esac
