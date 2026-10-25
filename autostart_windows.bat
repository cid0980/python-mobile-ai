@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "ARG=%~1"

if /I "%ARG%"=="--enable" (
    call "%~dp0start_windows.bat" --setup-only
    if errorlevel 1 exit /b 1
    call "%~dp0start_windows.bat" --enable-autostart
    exit /b %ERRORLEVEL%
)

if /I "%ARG%"=="--disable" (
    call "%~dp0start_windows.bat" --setup-only
    if errorlevel 1 exit /b 1
    call "%~dp0start_windows.bat" --disable-autostart
    exit /b %ERRORLEVEL%
)

if /I "%ARG%"=="--status" (
    call "%~dp0start_windows.bat" --setup-only
    if errorlevel 1 exit /b 1
    call "%~dp0start_windows.bat" --status-autostart
    exit /b %ERRORLEVEL%
)

echo ============================================================
echo    SpecDeck AI — Windows Setup, Shortcut ^& Login Auto-Start
echo ============================================================
echo.
echo Step 1/2: Verifying Python 3, Tkinter ^& all dependencies...
call "%~dp0start_windows.bat" --setup-only
if errorlevel 1 (
    echo.
    echo [ERROR] Environment setup did not complete.
    pause
    exit /b 1
)

echo.
call "%~dp0start_windows.bat" --status-autostart
echo.
echo Choose an option:
echo   [1] Enable Auto-Start on Windows Login + Create Desktop Shortcut
echo   [2] Create Desktop Shortcut Only (No Login Auto-Start)
echo   [3] Disable Auto-Start on Windows Login
echo   [4] Launch SpecDeck AI Right Now
echo   [5] Exit
echo.
set /p "CHOICE=Enter choice [1-5]: "

if "%CHOICE%"=="1" goto :opt_enable
if "%CHOICE%"=="2" goto :opt_shortcut
if "%CHOICE%"=="3" goto :opt_disable
if "%CHOICE%"=="4" goto :opt_launch
goto :eof_done

:opt_enable
call "%~dp0start_windows.bat" --enable-autostart
echo.
set /p "RUN_NOW=Launch SpecDeck AI right now as well? [Y/N]: "
if /I "%RUN_NOW%"=="Y" call "%~dp0start_windows.bat" --silent
pause
exit /b 0

:opt_shortcut
"%~dp0.venv\Scripts\python.exe" "%~dp0autostart_manager.py" --shortcut
pause
exit /b 0

:opt_disable
call "%~dp0start_windows.bat" --disable-autostart
pause
exit /b 0

:opt_launch
call "%~dp0start_windows.bat" --silent
exit /b 0

:eof_done
exit /b 0
