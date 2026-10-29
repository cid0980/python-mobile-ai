@echo off
setlocal EnableExtensions DisableDelayedExpansion
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_windows.ps1" "%~1"
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" if /I not "%~1"=="--silent" pause
exit /b %RESULT%
