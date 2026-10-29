@echo off
setlocal EnableExtensions DisableDelayedExpansion
if /I "%~1"=="--enable" goto enable
if /I "%~1"=="--disable" goto disable
if /I "%~1"=="--status" goto status
if not "%~1"=="" exit /b 1
echo SpecDeck - Windows Login Auto-Start
echo [1] Enable login auto-start, create shortcut and launch now
echo [2] Create desktop shortcut only
echo [3] Disable login auto-start
echo [4] Launch now
echo [5] Exit
choice /c 12345 /n /m "Choose [1-5]: "
if errorlevel 5 exit /b 0
if errorlevel 4 goto launch
if errorlevel 3 goto disable
if errorlevel 2 goto shortcut
:enable
call "%~dp0start_windows.bat" --enable-autostart
if errorlevel 1 exit /b 1
:launch
call "%~dp0start_windows.bat"
exit /b %ERRORLEVEL%
:disable
call "%~dp0start_windows.bat" --disable-autostart
exit /b %ERRORLEVEL%
:status
call "%~dp0start_windows.bat" --status-autostart
exit /b %ERRORLEVEL%
:shortcut
call "%~dp0start_windows.bat" --setup-only
if errorlevel 1 exit /b 1
"%~dp0.venv\Scripts\python.exe" "%~dp0autostart_manager.py" --shortcut
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
