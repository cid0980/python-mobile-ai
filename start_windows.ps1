param([string]$Mode = '')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$logDir = Join-Path $env:LOCALAPPDATA 'SpecDeck\logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$transcribing = $false
try {
    Start-Transcript -Path (Join-Path $logDir 'setup.log') -Append | Out-Null
    $transcribing = $true
    function Invoke-Checked([string]$Exe, [string[]]$Arguments) {
        & $Exe @Arguments
        if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE): $Exe $($Arguments -join ' ')" }
    }
    function Find-Python {
        # Prefer tested Python 3.12; do not accept Store aliases or unsupported runtimes.
        $candidates = @()
        foreach ($v in @('312','313','311','310')) {
            $candidates += Join-Path $env:LOCALAPPDATA "Programs\Python\Python$v\python.exe"
            $candidates += Join-Path $env:ProgramFiles "Python$v\python.exe"
        }
        $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($launcher) {
            foreach ($version in @('-3.12','-3.13','-3.11','-3.10')) {
                $resolved = & $launcher.Source $version -c 'import sys; print(sys.executable)' 2>$null
                if ($LASTEXITCODE -eq 0 -and $resolved) { $candidates += [string]$resolved }
            }
        }
        $onPath = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($onPath -and $onPath.Source -notlike '*\WindowsApps\*') { $candidates += $onPath.Source }
        foreach ($candidate in $candidates) {
            if (Test-Path -LiteralPath $candidate) {
                & $candidate -c 'import sys, venv, ensurepip; sys.exit(0 if (3,10) <= sys.version_info[:2] < (3,14) else 1)' 2>$null
                if ($LASTEXITCODE -eq 0) { return $candidate }
            }
        }
        return $null
    }
    $venv = Join-Path $PSScriptRoot '.venv'
    $python = Join-Path $venv 'Scripts\python.exe'
    $stamp = Join-Path $venv '.reqs.sha256'
    $requirements = Join-Path $PSScriptRoot 'requirements.txt'
    $hash = (Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash
    $healthy = $false
    if (Test-Path -LiteralPath $python) {
        & $python -c 'import sys, venv; sys.exit(0 if (3,10) <= sys.version_info[:2] < (3,14) else 1)' 2>$null
        $healthy = $LASTEXITCODE -eq 0
    }
    if (-not $healthy) {
        $basePython = Find-Python
        if (-not $basePython) {
            Write-Host '[SpecDeck] Installing official Python 3.12 for the current user (no admin required)...'
            $arch = $env:PROCESSOR_ARCHITECTURE
            if ($env:PROCESSOR_ARCHITEW6432) { $arch = $env:PROCESSOR_ARCHITEW6432 }
            $suffix = switch ($arch) { 'ARM64' {'arm64'} 'AMD64' {'amd64'} default {''} }
            $filename = if ($suffix) { "python-3.12.10-$suffix.exe" } else { 'python-3.12.10.exe' }
            $installer = Join-Path $env:TEMP (([guid]::NewGuid().ToString()) + '.exe')
            try {
                [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
                Invoke-WebRequest -UseBasicParsing -Uri "https://www.python.org/ftp/python/3.12.10/$filename" -OutFile $installer
                $signature = Get-AuthenticodeSignature -LiteralPath $installer
                if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
                    throw 'Python installer signature validation failed; refusing to run it.'
                }
                $process = Start-Process -FilePath $installer -ArgumentList '/quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_pip=1 Include_launcher=0' -Wait -PassThru
                if ($process.ExitCode -notin @(0,3010)) { throw "Python installation failed: $($process.ExitCode)" }
            } finally {
                Remove-Item -LiteralPath $installer -Force -ErrorAction SilentlyContinue
            }
            $basePython = Find-Python
            if (-not $basePython) { throw 'Python was not found after installation. Restart Windows if requested, or install Python 3.12 from python.org.' }
        }
        if (Test-Path -LiteralPath $venv) {
            # Keep the broken environment for diagnosis instead of deleting user files.
            Move-Item -LiteralPath $venv -Destination "$venv.broken-$([guid]::NewGuid().ToString('N'))"
        }
        Invoke-Checked $basePython @('-m','venv',$venv)
    }
    $ready = $false
    if ((Test-Path -LiteralPath $stamp) -and ((Get-Content -LiteralPath $stamp -Raw).Trim() -eq $hash)) {
        & $python -c 'import fastapi, uvicorn, groq, ddgs, dotenv, requests, edge_tts' 2>$null
        $ready = $LASTEXITCODE -eq 0
    }
    if (-not $ready) {
        Write-Host '[SpecDeck] Installing dependencies...'
        Invoke-Checked $python @('-m','ensurepip','--upgrade')
        Invoke-Checked $python @('-m','pip','install','--upgrade','pip','--disable-pip-version-check')
        Invoke-Checked $python @('-m','pip','install','--retries','3','--timeout','60','-r',$requirements)
        Invoke-Checked $python @('-m','pip','check')
        Invoke-Checked $python @('-c','import fastapi, uvicorn, groq, ddgs, dotenv, requests, edge_tts')
        Set-Content -LiteralPath $stamp -Value $hash -Encoding ASCII
    }
    switch ($Mode) {
        '--setup-only' { }
        '--enable-autostart' {
            Invoke-Checked $python @((Join-Path $PSScriptRoot 'autostart_manager.py'),'--enable')
            Invoke-Checked $python @((Join-Path $PSScriptRoot 'autostart_manager.py'),'--shortcut')
        }
        '--disable-autostart' { Invoke-Checked $python @((Join-Path $PSScriptRoot 'autostart_manager.py'),'--disable') }
        '--status-autostart' { Invoke-Checked $python @((Join-Path $PSScriptRoot 'autostart_manager.py'),'--status') }
        '--console' { Invoke-Checked $python @((Join-Path $PSScriptRoot 'app.py')) }
        default {
            if ($Mode -notin @('', '--silent')) { throw "Unknown option: $Mode" }
            Write-Host "[SpecDeck] Opening application. Logs: $logDir"
            # Use a supervised launcher: pythonw alone hides import/startup failures.
            Invoke-Checked $python @((Join-Path $PSScriptRoot 'windows_launcher.py'))
        }
    }
} catch {
    Write-Host "`n[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Log: $(Join-Path $logDir 'setup.log')"
    exit 1
} finally {
    if ($transcribing) { Stop-Transcript | Out-Null }
}
