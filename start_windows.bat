@echo off
setlocal EnableExtensions

cd /d "%~dp0"

set "MODE=%~1"
set "VENV_DIR=%~dp0.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "VENV_PYW=%VENV_DIR%\Scripts\pythonw.exe"
set "STAMP_FILE=%VENV_DIR%\.reqs.sha256"
set "PY_EXE="
set "USE_PY_LAUNCHER=0"

if not exist "%VENV_PY%" goto :ensure_python
if not exist "%STAMP_FILE%" goto :ensure_python

"%VENV_PY%" -c "import hashlib, pathlib, sys; h=hashlib.sha256(pathlib.Path('requirements.txt').read_bytes()).hexdigest(); s=pathlib.Path(r'%STAMP_FILE%').read_text().strip(); import fastapi, uvicorn, groq, ddgs, dotenv, requests, edge_tts; sys.exit(0 if h==s else 1)" >nul 2>&1
if errorlevel 1 goto :ensure_python
goto :dispatch_mode

:ensure_python
echo [SpecDeck] Checking Python 3.9+ runtime...
call :find_python
if not errorlevel 1 goto :python_ready

echo [SpecDeck] Python 3.9+ not found. Installing Python 3.12 automatically...

where winget >nul 2>&1
if errorlevel 1 goto :download_python_org

echo [SpecDeck] Installing Python 3.12 via winget (per-user, no admin needed)...
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
call :find_python
if not errorlevel 1 goto :python_ready

:download_python_org
echo [SpecDeck] Downloading official Python 3.12 installer from python.org...
set "PY_URL=https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe"
if /I "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "PY_URL=https://www.python.org/ftp/python/3.12.8/python-3.12.8-arm64.exe"
if /I "%PROCESSOR_ARCHITECTURE%"=="x86" set "PY_URL=https://www.python.org/ftp/python/3.12.8/python-3.12.8.exe"

set "INSTALLER=%TEMP%\specdeck_python_312_setup.exe"
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PY_URL%' -OutFile '%INSTALLER%' -UseBasicParsing"
if not exist "%INSTALLER%" goto :python_install_failed

echo [SpecDeck] Running silent Python 3.12 setup...
"%INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_pip=1 Include_launcher=1
del /f /q "%INSTALLER%" >nul 2>&1

call :find_python
if not errorlevel 1 goto :python_ready

:python_install_failed
echo.
echo [ERROR] Automatic Python installation could not complete.
echo Please install Python 3.12+ from https://www.python.org/downloads/ and re-run this file.
if /I not "%MODE%"=="--silent" pause
exit /b 1

:python_ready
if "%USE_PY_LAUNCHER%"=="1" (
    echo [  OK  ] Found working Python via py -3 launcher.
) else (
    echo [  OK  ] Found working Python: "%PY_EXE%"
)

if exist "%VENV_PY%" goto :install_deps
echo [SpecDeck] Creating local virtual environment (.venv)...
if "%USE_PY_LAUNCHER%"=="1" (
    py -3 -m venv "%VENV_DIR%"
) else (
    "%PY_EXE%" -m venv "%VENV_DIR%"
)
if not exist "%VENV_PY%" (
    echo [ERROR] Failed to create virtual environment at "%VENV_DIR%".
    if /I not "%MODE%"=="--silent" pause
    exit /b 1
)

:install_deps
echo [SpecDeck] Installing / verifying Python packages...
"%VENV_PY%" -m pip install --upgrade pip --quiet
"%VENV_PY%" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies from requirements.txt.
    if /I not "%MODE%"=="--silent" pause
    exit /b 1
)

"%VENV_PY%" -c "import hashlib, pathlib; pathlib.Path(r'%STAMP_FILE%').write_text(hashlib.sha256(pathlib.Path('requirements.txt').read_bytes()).hexdigest())"
echo [  OK  ] All dependencies verified!

:dispatch_mode
if /I "%MODE%"=="--setup-only" exit /b 0

if /I "%MODE%"=="--enable-autostart" (
    "%VENV_PY%" "%~dp0autostart_manager.py" --enable
    "%VENV_PY%" "%~dp0autostart_manager.py" --shortcut
    exit /b %ERRORLEVEL%
)

if /I "%MODE%"=="--disable-autostart" (
    "%VENV_PY%" "%~dp0autostart_manager.py" --disable
    exit /b %ERRORLEVEL%
)

if /I "%MODE%"=="--status-autostart" (
    "%VENV_PY%" "%~dp0autostart_manager.py" --status
    exit /b %ERRORLEVEL%
)

if /I "%MODE%"=="--console" (
    echo [SpecDeck] Launching in console mode...
    "%VENV_PY%" "%~dp0app.py"
    exit /b %ERRORLEVEL%
)

if exist "%VENV_PYW%" (
    start "" "%VENV_PYW%" "%~dp0app.py"
) else (
    start "" "%VENV_PY%" "%~dp0app.py"
)
exit /b 0

:find_python
set "PY_EXE="
set "USE_PY_LAUNCHER=0"

py -3 -c "import sys, venv; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "USE_PY_LAUNCHER=1"
    exit /b 0
)

python -c "import sys, venv; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "PY_EXE=python"
    exit /b 0
)

for %%V in (313 312 311 310 39) do (
    call :probe_exe "%LocalAppData%\Programs\Python\Python%%V\python.exe"
    if defined PY_EXE exit /b 0
    call :probe_exe "%ProgramFiles%\Python%%V\python.exe"
    if defined PY_EXE exit /b 0
    call :probe_exe "%ProgramFiles(x86)%\Python%%V-32\python.exe"
    if defined PY_EXE exit /b 0
)
exit /b 1

:probe_exe
if not exist "%~1" exit /b 1
"%~1" -c "import sys, venv; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
if errorlevel 1 exit /b 1
set "PY_EXE=%~1"
exit /b 0
