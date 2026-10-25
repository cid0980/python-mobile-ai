"""
autostart_manager.py — Cross-Platform Login Auto-Start & Shortcut Manager
Supports Windows (Startup folder hidden VBS launcher + Desktop .lnk)
and Linux (XDG ~/.config/autostart/specdeck-ai.desktop + App Menu launcher).
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Tuple

PROJECT_DIR = Path(__file__).resolve().parent
ICON_SVG_PATH = PROJECT_DIR / "specdeck_icon.svg"


# ---------------------------------------------------------------------------
# Windows Paths & Helpers
# ---------------------------------------------------------------------------
def _win_startup_dir() -> Path:
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _win_startup_vbs() -> Path:
    return _win_startup_dir() / "SpecDeckAI_Autostart.vbs"


# ---------------------------------------------------------------------------
# Linux Paths & Helpers
# ---------------------------------------------------------------------------
def _linux_autostart_file() -> Path:
    xdg_config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return xdg_config / "autostart" / "specdeck-ai.desktop"


def _linux_app_menu_file() -> Path:
    xdg_data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return xdg_data / "applications" / "specdeck-ai.desktop"


def _linux_desktop_entry_content(autostart_mode: bool = False) -> str:
    start_script = PROJECT_DIR / "start_linux.sh"
    exec_flag = " --background" if autostart_mode else ""
    icon_str = str(ICON_SVG_PATH) if ICON_SVG_PATH.exists() else "phone"
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.0",
        "Name=SpecDeck AI",
        "GenericName=Smartphone AI Advisor",
        "Comment=Live Mobile Phone Specs, Launch Dates & AI Buying Advisor",
        f'Exec="{start_script}"{exec_flag}',
        f"Path={PROJECT_DIR}",
        f"Icon={icon_str}",
        "Terminal=false",
        "StartupNotify=false",
        "Categories=Utility;Network;",
    ]
    if autostart_mode:
        lines.extend(
            [
                "X-GNOME-Autostart-enabled=true",
                "X-GNOME-Autostart-Delay=3",
            ]
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Public Cross-Platform API
# ---------------------------------------------------------------------------
def is_autostart_enabled() -> bool:
    """Return True if SpecDeck AI is configured to auto-start on OS login."""
    if os.name == "nt":
        return _win_startup_vbs().exists()
    if sys.platform.startswith("linux"):
        path = _linux_autostart_file()
        if not path.exists():
            return False
        text = path.read_text(encoding="utf-8", errors="ignore")
        return "X-GNOME-Autostart-enabled=false" not in text
    return False


def enable_autostart() -> Tuple[bool, str]:
    """Enable automatic launch when the user logs into Windows or Linux."""
    try:
        if os.name == "nt":
            startup_dir = _win_startup_dir()
            startup_dir.mkdir(parents=True, exist_ok=True)
            bat_path = PROJECT_DIR / "start_windows.bat"
            vbs_path = _win_startup_vbs()

            # Escape double quotes for VBScript string
            escaped_dir = str(PROJECT_DIR).replace('"', '""')
            escaped_bat = str(bat_path).replace('"', '""')
            vbs_content = (
                'Set WshShell = CreateObject("WScript.Shell")\r\n'
                f'WshShell.CurrentDirectory = "{escaped_dir}"\r\n'
                f'WshShell.Run """{escaped_bat}"" --silent", 0, False\r\n'
            )
            vbs_path.write_text(vbs_content, encoding="utf-8")
            return True, f"Windows Login Auto-Start enabled ({vbs_path.name})"

        if sys.platform.startswith("linux"):
            start_script = PROJECT_DIR / "start_linux.sh"
            if start_script.exists():
                start_script.chmod(start_script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

            autostart_path = _linux_autostart_file()
            autostart_path.parent.mkdir(parents=True, exist_ok=True)
            autostart_path.write_text(_linux_desktop_entry_content(autostart_mode=True), encoding="utf-8")
            autostart_path.chmod(0o755)
            return True, f"Linux Login Auto-Start enabled ({autostart_path})"

        return False, f"Auto-start is currently supported on Windows and Linux (detected: {sys.platform})."
    except Exception as exc:
        return False, f"Failed to enable auto-start: {exc}"


def disable_autostart() -> Tuple[bool, str]:
    """Disable automatic launch on Windows or Linux login."""
    try:
        if os.name == "nt":
            vbs_path = _win_startup_vbs()
            if vbs_path.exists():
                vbs_path.unlink()
            return True, "Windows Login Auto-Start disabled."

        if sys.platform.startswith("linux"):
            autostart_path = _linux_autostart_file()
            if autostart_path.exists():
                autostart_path.unlink()
            return True, "Linux Login Auto-Start disabled."

        return False, f"Unsupported OS ({sys.platform})."
    except Exception as exc:
        return False, f"Failed to disable auto-start: {exc}"


def create_shortcuts() -> Tuple[bool, str]:
    """Create Desktop / Application Menu shortcuts for Windows or Linux."""
    try:
        if os.name == "nt":
            bat_path = PROJECT_DIR / "start_windows.bat"
            vbs_launcher = PROJECT_DIR / ".launch_hidden.vbs"
            escaped_dir = str(PROJECT_DIR).replace('"', '""')
            escaped_bat = str(bat_path).replace('"', '""')
            vbs_launcher.write_text(
                'Set WshShell = CreateObject("WScript.Shell")\r\n'
                f'WshShell.CurrentDirectory = "{escaped_dir}"\r\n'
                f'WshShell.Run """{escaped_bat}"" --silent", 0, False\r\n',
                encoding="utf-8",
            )
            ps_cmd = (
                "$ws = New-Object -ComObject WScript.Shell; "
                "$desk = [Environment]::GetFolderPath('Desktop'); "
                "$lnk = $ws.CreateShortcut((Join-Path $desk 'SpecDeck AI.lnk')); "
                "$lnk.TargetPath = 'wscript.exe'; "
                f"$lnk.Arguments = '\"{vbs_launcher}\"'; "
                f"$lnk.WorkingDirectory = '{PROJECT_DIR}'; "
                "$lnk.IconLocation = 'shell32.dll,23'; "
                "$lnk.Description = 'Launch SpecDeck AI Smartphone Advisor'; "
                "$lnk.Save()"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
                check=True,
                capture_output=True,
                text=True,
            )
            return True, "Created 'SpecDeck AI' shortcut on your Windows Desktop."

        if sys.platform.startswith("linux"):
            app_menu = _linux_app_menu_file()
            app_menu.parent.mkdir(parents=True, exist_ok=True)
            content = _linux_desktop_entry_content(autostart_mode=False)
            app_menu.write_text(content, encoding="utf-8")
            app_menu.chmod(0o755)

            desktop_dir = Path.home() / "Desktop"
            if desktop_dir.is_dir():
                desk_file = desktop_dir / "SpecDeck-AI.desktop"
                desk_file.write_text(content, encoding="utf-8")
                desk_file.chmod(0o755)
                return True, f"Created Linux App Menu & Desktop shortcut ({desk_file})"
            return True, f"Created Linux Application Menu entry ({app_menu})"

        return False, f"Shortcut creation not configured for {sys.platform}."
    except Exception as exc:
        return False, f"Could not create shortcut: {exc}"


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "--status"
    if arg == "--enable":
        ok, msg = enable_autostart()
        print(msg)
        sys.exit(0 if ok else 1)
    elif arg == "--disable":
        ok, msg = disable_autostart()
        print(msg)
        sys.exit(0 if ok else 1)
    elif arg == "--shortcut":
        ok, msg = create_shortcuts()
        print(msg)
        sys.exit(0 if ok else 1)
    else:
        state = "ENABLED" if is_autostart_enabled() else "DISABLED"
        print(f"SpecDeck AI Login Auto-Start Status: {state}")
