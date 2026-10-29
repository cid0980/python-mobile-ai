from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Tuple

PROJECT_DIR = Path(__file__).resolve().parent
ICON_SVG_PATH = PROJECT_DIR / "specdeck_icon.svg"


def _win_startup_dir() -> Path:
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _win_startup_vbs() -> Path:
    return _win_startup_dir() / "SpecDeckAI_Autostart.vbs"


def _win_startup_link() -> Path:
    return _win_startup_dir() / "SpecDeckAI_Autostart.lnk"


def _create_windows_link(destination: Path) -> None:
    """Use native shortcuts instead of VBScript (disabled on some Windows PCs)."""
    def quote(value: object) -> str:
        return "'" + str(value).replace("'", "''") + "'"

    destination.parent.mkdir(parents=True, exist_ok=True)
    script = PROJECT_DIR / "start_windows.ps1"
    command = (
        "$ErrorActionPreference = 'Stop'; "
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$lnk = $ws.CreateShortcut({quote(destination)}); "
        "$lnk.TargetPath = Join-Path $env:SystemRoot 'System32\\WindowsPowerShell\\v1.0\\powershell.exe'; "
        f"$lnk.Arguments = {quote('-NoLogo -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + str(script) + '" --silent')}; "
        f"$lnk.WorkingDirectory = {quote(PROJECT_DIR)}; "
        "$lnk.IconLocation = 'shell32.dll,23'; "
        "$lnk.Description = 'Launch SpecDeck'; $lnk.Save()"
    )
    # EncodedCommand preserves Unicode paths and avoids nested shell quoting.
    import base64
    encoded = base64.b64encode(command.encode("utf-16le")).decode("ascii")
    subprocess.run(["powershell.exe", "-NoProfile", "-EncodedCommand", encoded],
                   check=True, capture_output=True, text=True)


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
        "Name=SpecDeck",
        "GenericName=Smartphone Hardware Intelligence",
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


def is_autostart_enabled() -> bool:
    if os.name == "nt":
        return _win_startup_link().exists() or _win_startup_vbs().exists()
    if sys.platform.startswith("linux"):
        path = _linux_autostart_file()
        if not path.exists():
            return False
        text = path.read_text(encoding="utf-8", errors="ignore")
        return "X-GNOME-Autostart-enabled=false" not in text
    return False


def enable_autostart() -> Tuple[bool, str]:
    try:
        if os.name == "nt":
            _create_windows_link(_win_startup_link())
            _win_startup_vbs().unlink(missing_ok=True)
            return True, "Windows Login Auto-Start enabled for the current user."

        if sys.platform.startswith("linux"):
            start_script = PROJECT_DIR / "start_linux.sh"
            if start_script.exists():
                start_script.chmod(start_script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

            autostart_path = _linux_autostart_file()
            autostart_path.parent.mkdir(parents=True, exist_ok=True)
            autostart_path.write_text(_linux_desktop_entry_content(autostart_mode=True), encoding="utf-8")
            autostart_path.chmod(0o755)
            return True, f"Linux Login Auto-Start enabled ({autostart_path})"

        return False, f"Auto-start is supported on Windows and Linux (detected: {sys.platform})."
    except Exception as exc:
        return False, f"Failed to enable auto-start: {exc}"


def disable_autostart() -> Tuple[bool, str]:
    try:
        if os.name == "nt":
            _win_startup_vbs().unlink(missing_ok=True)
            _win_startup_link().unlink(missing_ok=True)
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
    try:
        if os.name == "nt":
            # Resolve the real Desktop (including OneDrive redirection).
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command",
                 "[Console]::OutputEncoding = [Text.Encoding]::UTF8; [Environment]::GetFolderPath('Desktop')"],
                check=True, capture_output=True, encoding="utf-8",
            )
            desktop = result.stdout.strip()
            if not desktop:
                raise RuntimeError("Windows did not return a Desktop folder")
            _create_windows_link(Path(desktop) / "SpecDeck.lnk")
            return True, "Created 'SpecDeck' shortcut on your Windows Desktop."

        if sys.platform.startswith("linux"):
            app_menu = _linux_app_menu_file()
            app_menu.parent.mkdir(parents=True, exist_ok=True)
            content = _linux_desktop_entry_content(autostart_mode=False)
            app_menu.write_text(content, encoding="utf-8")
            app_menu.chmod(0o755)

            desktop_dir = Path.home() / "Desktop"
            if desktop_dir.is_dir():
                desk_file = desktop_dir / "SpecDeck.desktop"
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
        print(f"SpecDeck Login Auto-Start Status: {state}")
