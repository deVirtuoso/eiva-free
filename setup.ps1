# EIVA - Free edition - one-time setup.
#
# Safe to re-run: it repairs rather than duplicates. Installs Python if the
# machine has none, creates a project virtual environment next to this script,
# and installs the dependencies. No administrator rights needed.
#
# Run it by double-clicking setup.cmd next to this file, which starts it with
# the execution policy set for that one process. Windows refuses to run an
# unsigned .ps1 that came from a download, and no amount of care inside this
# file can change that - the refusal happens before line 1.

param(
    # For anyone who would rather install Python themselves.
    [switch]$NoPythonInstall
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Say($t)  { Write-Host $t }
function Good($t) { Write-Host "  OK    $t" -ForegroundColor Green }
function Warn($t) { Write-Host "  note  $t" -ForegroundColor Yellow }
function Bad($t)  { Write-Host "  FAIL  $t" -ForegroundColor Red }
# --- 0. get out of our own way ----------------------------------------------

# Explorer will run a script straight out of a zip preview, from a throwaway
# folder under Temp. Setup would build a virtual environment there and the
# whole install would go when the folder does, leaving someone with an app
# that worked once and then was not anywhere. Matched with -like rather than
# -match so the path needs no regex escaping to be read at a glance.
if ($PSScriptRoot -like "*\AppData\Local\Temp\*.zip\*" -or
    $PSScriptRoot -like "*\Temp\*.zip\*") {
    Bad "this is running from inside the zip file, not from a real folder"
    Say ""
    Say "  Windows is showing you what is in the zip without unpacking it."
    Say "  Anything installed here is thrown away when the window closes."
    Say ""
    Say "  Right-click the zip and choose 'Extract All...', put it somewhere"
    Say "  like your Documents folder, and run setup.cmd from there."
    Say ""
    exit 1
}

# Every file in a folder that arrived as a download carries a mark saying so,
# and RemoteSigned - the policy people are usually told to set - answers that
# mark by refusing to run an unsigned script at all. Clearing it here is what
# makes .\setup.ps1 work directly from the second run onwards, rather than
# needing setup.cmd forever. Best effort: failing to unblock is not worth
# stopping for, since we are plainly already running.
Get-ChildItem $PSScriptRoot -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -in ".ps1", ".cmd", ".vbs", ".py" } |
    Unblock-File -ErrorAction SilentlyContinue

Say ""
Say "EIVA (Free) - setup"
Say "==============================="

# --- 1. find a usable Python, installing one if the machine has none --------
Say ""
Say "1. Python"

# The Python this installs when the machine has none. Bumping it is a
# one-line change; python.org keeps every release at the same URL shape.
$PY_VERSION = "3.12.10"

# Native programs write to stderr for ordinary things - "no runtime found" from
# py.exe is one - and with $ErrorActionPreference set to Stop that ends the
# script before it can say anything useful. That is what a machine with no
# Python used to hit. So every call to an .exe goes through here instead: it
# hands back the output and whether it worked, and never terminates.
function Invoke-Exe($exe, [string[]]$exeArgs) {
    $before = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    # Cleared first, so that a stale code left by some earlier command cannot
    # be read back here as this one having failed.
    $global:LASTEXITCODE = 0
    try {
        $text = (& $exe @exeArgs 2>&1 | Out-String).Trim()
        $code = $LASTEXITCODE
    } catch {
        $text = "$_"
        $code = 1
    } finally {
        $ErrorActionPreference = $before
    }
    # Callers that want a single value back read Last rather than Text. A
    # program is free to print a warning alongside the answer, and a two-line
    # Text would fail every ^...$ test and silently discard a working Python.
    $last = ($text -split "`r?`n" | Where-Object { $_.Trim() } |
             Select-Object -Last 1)
    [pscustomobject]@{ Ok = ($code -eq 0); Text = $text; Last = "$last".Trim() }
}

# A just-installed Python is on the PATH of every new process except this one.
function Refresh-Path {
    $paths = @([Environment]::GetEnvironmentVariable("PATH", "Machine"),
               [Environment]::GetEnvironmentVariable("PATH", "User"))
    $env:PATH = ($paths | Where-Object { $_ }) -join ";"
}

# Suitable means 3.10 or newer and carrying tkinter - the whole window is Tk,
# so a Python without it would install everything and then fail to start.
function Find-Python {
    $candidates = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($v in @("3.12", "3.11", "3.13", "3.10")) {
            $r = Invoke-Exe py @("-$v", "-c", "import sys; print(sys.executable)")
            if ($r.Ok -and $r.Last) { $candidates += $r.Last }
        }
    }
    foreach ($dir in @("$env:LOCALAPPDATA\Programs\Python\Python3*",
                       "$env:ProgramFiles\Python3*", "C:\Python3*")) {
        foreach ($hit in (Get-ChildItem $dir -Directory -ErrorAction SilentlyContinue |
                          Sort-Object Name -Descending)) {
            $exe = Join-Path $hit.FullName "python.exe"
            if (Test-Path $exe) { $candidates += $exe }
        }
    }

    foreach ($exe in ($candidates | Select-Object -Unique)) {
        $r = Invoke-Exe $exe @("-c",
            "import tkinter, sys; print('%d.%d' % sys.version_info[:2])")
        if ($r.Ok -and $r.Last -match '^\d+\.\d+$' -and
            [version]$r.Last -ge [version]"3.10") {
            return [pscustomobject]@{ Path = $exe; Version = $r.Last }
        }
    }
    $null
}

# Nothing here needs administrator rights: both routes install Python for this
# user only, which is all a virtual environment next to this script needs.
function Install-Python {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Say "  installing Python with winget - a few minutes"
        $null = Invoke-Exe winget @("install", "--id", "Python.Python.3.12", "-e",
                              "--source", "winget", "--scope", "user", "--silent",
                              "--accept-package-agreements",
                              "--accept-source-agreements",
                              "--disable-interactivity")
        Refresh-Path
        if (Find-Python) { return $true }
        Warn "winget could not do it - falling back to python.org"
    }

    $arch = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "arm64" } else { "amd64" }
    $url  = "https://www.python.org/ftp/python/$PY_VERSION/python-$PY_VERSION-$arch.exe"
    $file = Join-Path $env:TEMP "python-$PY_VERSION-$arch.exe"

    Say "  downloading $url"
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $ProgressPreference = "SilentlyContinue"     # or the bar slows it down
        Invoke-WebRequest -Uri $url -OutFile $file -UseBasicParsing
    } catch {
        Bad "download failed: $($_.Exception.Message)"
        return $false
    }

    # Never run a downloaded installer on someone's machine without checking
    # Windows agrees it is genuinely from the people who publish Python.
    $sig = Get-AuthenticodeSignature $file
    if ($sig.Status -ne "Valid" -or
        $sig.SignerCertificate.Subject -notmatch "Python Software Foundation") {
        Bad "that download is not signed by the Python Software Foundation"
        Remove-Item $file -Force -ErrorAction SilentlyContinue
        return $false
    }
    Good "installer signature checked"

    Say "  installing Python $PY_VERSION for your account"
    $run = Start-Process $file -Wait -PassThru -ArgumentList @(
        "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_launcher=1",
        "Include_tcltk=1", "Include_test=0", "Include_doc=0", "Shortcuts=0")
    Remove-Item $file -Force -ErrorAction SilentlyContinue
    if ($run.ExitCode -ne 0) {
        Bad "the Python installer returned $($run.ExitCode)"
        return $false
    }
    Refresh-Path
    $true
}

$found = Find-Python
if (-not $found -and -not $NoPythonInstall) {
    Warn "no suitable Python on this machine - installing one"
    if (Install-Python) { $found = Find-Python }
}
if (-not $found) {
    Bad "no suitable Python (3.10 or newer, with tkinter)"
    Say ""
    Say "  Install it by hand from https://www.python.org/downloads/,"
    Say "  tick 'Add python.exe to PATH', then run this script again."
    exit 1
}
$python = $found.Path
Good "using Python $($found.Version) at $python"
# --- 2. virtual environment -------------------------------------------------
Say ""
Say "2. Virtual environment"
$venv = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

# A virtual environment records an absolute path to the Python it was built
# from. Upgrade or uninstall that Python and this folder is still here, but
# nothing inside it runs - which looks, from the outside, exactly like the app
# being broken. Ask it to run, and rebuild rather than limp on.
if ((Test-Path $venv) -and -not (Invoke-Exe $venv @("-c", "pass")).Ok) {
    Warn "the existing .venv no longer runs - rebuilding it"
    Remove-Item (Join-Path $PSScriptRoot ".venv") -Recurse -Force `
                -ErrorAction SilentlyContinue
}

if (Test-Path $venv) {
    Good "already exists"
} else {
    $made = Invoke-Exe $python @("-m", "venv", ".venv")
    if (-not (Test-Path $venv)) {
        Bad "could not create .venv"
        if ($made.Text) { Say "        $($made.Text)" }
        exit 1
    }
    Good "created .venv"
}

# --- 3. dependencies --------------------------------------------------------
Say ""
Say "3. Dependencies"
& $venv -m pip install --upgrade pip --quiet
& $venv -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { Bad "pip install failed"; exit 1 }

# pip can report success and still leave a package unimportable. Ask the
# interpreter that will actually run the app, rather than take pip's word.
$missing = & $venv -c @"
import importlib.util
need = {'anthropic': 'anthropic', 'openai': 'openai',
        'google.genai': 'google-genai', 'PIL': 'pillow', 'tkinter': 'tkinter'}
def gone(mod):
    # find_spec raises rather than returning None when a parent package is
    # absent, and google.genai has one. A raise here would fail the whole
    # probe and report every package as unverifiable.
    try:
        return importlib.util.find_spec(mod) is None
    except Exception:
        return True
print(','.join(pkg for mod, pkg in need.items() if gone(mod)))
"@
if ($LASTEXITCODE -ne 0) { Bad "could not verify the packages - see above"; exit 1 }
if ($missing.Trim()) { Bad "still missing: $($missing.Trim())"; exit 1 }
Good "installed anthropic + openai + google-genai + pillow"

# --- 4. key reminder --------------------------------------------------------
Say ""
Say "4. Your API key - any one of the three"

# The User environment as well as this process: a key set by a previous run of
# setup, or by the app itself, is in the registry but not in this shell.
$found = @()
foreach ($pair in @(@('ANTHROPIC_API_KEY','Anthropic'),
                    @('OPENAI_API_KEY','OpenAI'),
                    @('GEMINI_API_KEY','Google Gemini'))) {
    $value = [Environment]::GetEnvironmentVariable($pair[0], 'User')
    if (-not $value) { $value = [Environment]::GetEnvironmentVariable($pair[0]) }
    if ($value) { $found += $pair[1] }
}
if ($found.Count -gt 0) {
    Good "key found for: $($found -join ', ')"
    Say  "  Pick which one answers from the Model menu in the app."
} else {
    Say "  None set yet. You need only one - whichever you already have."
    Say "  Add it from inside the app (the Keys button), or run one of:"
    Say '     setx ANTHROPIC_API_KEY "sk-ant-..."     console.anthropic.com'
    Say '     setx OPENAI_API_KEY    "sk-..."         platform.openai.com'
    Say '     setx GEMINI_API_KEY    "AIza..."        aistudio.google.com'
    Say "  The app never ships with a key."
}

Say ""
Good "Setup complete. Start it with eiva.cmd (or eiva.vbs for no console)."
Say ""
