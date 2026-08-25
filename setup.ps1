# EIVA - Free edition - one-time setup.
#
# Safe to re-run: it repairs rather than duplicates. Creates a project virtual
# environment next to this script and installs the two dependencies.
#
#   powershell -ExecutionPolicy Bypass -File setup.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Say($t)  { Write-Host $t }
function Good($t) { Write-Host "  OK    $t" -ForegroundColor Green }
function Bad($t)  { Write-Host "  FAIL  $t" -ForegroundColor Red }

Say ""
Say "EIVA (Free) - setup"
Say "==============================="

# --- 1. find a usable Python (3.10+) ----------------------------------------
Say ""
Say "1. Python"
$python = $null
$candidates = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($v in @("3.12", "3.11", "3.13", "3.10")) {
        $found = & py "-$v" -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $found) { $candidates += $found.Trim() }
    }
}
foreach ($p in @(
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe")) {
    if (Test-Path $p) { $candidates += $p }
}
foreach ($c in $candidates) {
    $ver = & $c -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
    if ($LASTEXITCODE -eq 0 -and [version]$ver -ge [version]"3.10") {
        $python = $c; Good "using Python $ver"; break
    }
}
if (-not $python) {
    Bad "no suitable Python found (3.10 or newer)"
    Say "  Install from https://www.python.org/downloads/ and tick"
    Say "  'Add python.exe to PATH', then run this script again."
    exit 1
}

# --- 2. virtual environment -------------------------------------------------
Say ""
Say "2. Virtual environment"
$venv = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (Test-Path $venv) {
    Good "already exists"
} else {
    & $python -m venv .venv
    if (-not (Test-Path $venv)) { Bad "could not create .venv"; exit 1 }
    Good "created .venv"
}

# --- 3. dependencies --------------------------------------------------------
Say ""
Say "3. Dependencies"
& $venv -m pip install --upgrade pip --quiet
& $venv -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { Bad "pip install failed"; exit 1 }
Good "installed anthropic + pillow"

# --- 4. key reminder --------------------------------------------------------
Say ""
Say "4. Your Anthropic API key"
if ($env:ANTHROPIC_API_KEY) {
    Good "ANTHROPIC_API_KEY is set"
} else {
    Say "  Not set yet. Add it from inside the app (the Keys button), or run:"
    Say '     setx ANTHROPIC_API_KEY "sk-ant-..."'
    Say "  Get one at console.anthropic.com. The app never ships with a key."
}

Say ""
Good "Setup complete. Start it with eiva.cmd (or eiva.vbs for no console)."
Say ""
