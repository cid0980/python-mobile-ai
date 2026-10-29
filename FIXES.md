# Windows installation and startup fixes

- Replaced fragile batch setup logic with a checked PowerShell installer.
- Detects supported Python executables directly, including newly installed per-user Python.
- Waits for official installer completion, checks its signature and exit code, and disables the all-users launcher install.
- Rebuilds broken virtual environments without deleting them; verifies package imports and pip consistency before recording success.
- Correct exit-code propagation; errors stay visible, with persistent setup and app logs.
- Launches after dependency installation; optional administrator entry point included.
- Native per-user Startup/Desktop shortcuts, Unicode-safe encoded PowerShell and apostrophe-safe paths; removes legacy Startup VBS on migration.
- Autostart option 1 now enables, creates shortcut, and launches without a second confirmation.
- Browser process handoff no longer prematurely shuts down the server; server timeout increased.
- Settings API reports autostart failures rather than silently claiming success.

Validation: Python compile checks and three regression tests passed in Linux.
Not validated here: actual Windows PowerShell execution, Python installation, UAC, Windows login, or browser UI. Dependencies remain unpinned as in the original project; future upstream changes can still require maintenance.

See README.md for use and known server-lifetime limitation.
