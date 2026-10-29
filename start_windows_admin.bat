@echo off
setlocal DisableDelayedExpansion
rem Optional elevation only. Normal setup is per-user and does not need this.
set "SPECDECK_SETUP=%~dp0start_windows.bat"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { $p = Start-Process -FilePath $env:SPECDECK_SETUP -Verb RunAs -Wait -PassThru; exit $p.ExitCode } catch { Write-Host $_; exit 1 }"
if errorlevel 1 pause
