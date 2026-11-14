<#
.SYNOPSIS
Removes what install.ps1 put in place: the virtual environment, the downloaded
models and fonts, the Start-menu shortcut; your data only when you say so.

.DESCRIPTION
Double-click uninstall.cmd in the TASlation folder, which runs this script, or
from a PowerShell window:

    powershell -ExecutionPolicy Bypass -File uninstall.ps1

It first lists what goes and asks once (default: no). Then it deletes:
  * .venv and models\ in this folder;
  * the Start-menu shortcut "TASlation", only when it points into this folder;
  * your data folder ~/.taslation (or TASLATION_STATE_DIR), only after your Y:
    it holds the translation caches (the translations your reading made;
    re-reading the books takes that time again), the reader's annotations,
    series sheets (glossary), translator's notes, the capture profiles, the
    window's settings and the legal-notice state. Kept by default.
It asks whether to remove each translation model TASlation installed (the file
translator_models.json in the data folder says which) with `ollama rm`; a
model you had before stays, and is not asked about. An install from before
that file is asked about its configured model. When Ollama does not run, it
starts Ollama's server for that in a hidden window and stops it again. Then it
asks whether to uninstall Ollama itself with winget (all default: no).

Ollama's lifetime: a server TASlation started and left running (the file
ollama-started.json in the data folder names it) is stopped, unless another
TASlation still uses it or another program has a model loaded in it. When
Ollama is kept and the install stopped it from starting with Windows after
your yes (the file .ollama-autostart-by-install lists what it removed), that
start with Windows is put back. An Ollama the install installed for
TASlation (.ollama-by-install) is left not starting with Windows, and the
uninstaller says how to change that. When the install set
LLAMA_ARG_CACHE_RAM (the file .cache-ram-by-install says so) and it is still 0,
or OLLAMA_KV_CACHE_TYPE (the file .kv-cache-by-install) and it is still q8_0,
it clears that variable for your user (an Ollama already running keeps the
setting until it restarts). A value you set yourself stays. It never touches
anything else: this folder's own files, Python (also when install.cmd installed
it; it says how to remove it) and pip's download cache stay.

.PARAMETER Yes
For unattended runs and checks; uninstall.cmd asks instead. Answers Y to the
first question. It answers no about your data folder, the translation models
and Ollama itself: a run nobody watches does not destroy a person's
translations, nor what other programs may use.

.PARAMETER DryRun
For checks: print what would be deleted and what would be left; delete nothing.
#>
[CmdletBinding()]
param(
    [switch]$Yes,
    [switch]$DryRun
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$Root = $PSScriptRoot
$Venv = Join-Path $Root '.venv'
$Models = Join-Path $Root 'models'
$KvMarker = Join-Path $Root '.kv-cache-by-install'
$CacheRamMarker = Join-Path $Root '.cache-ram-by-install'
# what install.ps1 changed about Ollama's start with Windows (each lists what it removed, one line each)
$OllamaMarker = Join-Path $Root '.ollama-by-install'  # Ollama installed for TASlation: kept from starting with Windows
$AutostartMarker = Join-Path $Root '.ollama-autostart-by-install'  # an Ollama there before, after the person's yes
$StartupFolder = [Environment]::GetFolderPath('Startup')
$RunKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$OllamaUrl = 'http://127.0.0.1:11434'
$OllamaStartWaitS = 30  # how long the server started for `ollama rm` is given to answer (install.ps1 gives as long)
$ServerRecord = 'ollama-started.json'  # in the data folder: the server TASlation started (taslation/ollama_start.py)
$OwnModels = @('taslation-plamo3-translate-2b', 'qwen3.5:4b')  # TASlation's translators (taslation/translate/models.py)
$script:OwnServer = $null
$ShortcutPath = Join-Path ([Environment]::GetFolderPath('Programs')) 'TASlation.lnk'
$Interactive = (-not [Console]::IsInputRedirected) -and [Environment]::UserInteractive
$script:Deleted = New-Object System.Collections.Generic.List[string]
$script:Left = New-Object System.Collections.Generic.List[string]
$script:Failed = $false

function Write-Step([string]$Text) { Write-Host ''; Write-Host $Text -ForegroundColor Cyan }
function Write-Info([string]$Text) { Write-Host "  $Text" }
function Write-Plan([string]$Text) { Write-Host "  dry run, would: $Text" -ForegroundColor DarkYellow }

# With -YesKeeps the question is one -Yes answers no: what a run nobody watches must not destroy.
function Confirm-Choice([string]$Question, [bool]$YesKeeps = $false) {
    if ($Yes -and $YesKeeps) { Write-Info "$Question [y/N] n (-Yes keeps this)"; return $false }
    if ($Yes) { Write-Info "$Question [y/N] y (-Yes)"; return $true }
    if ($DryRun) { Write-Info "$Question [y/N] (dry run: would ask; counted as n)"; return $false }
    if (-not $Interactive) { Write-Info "$Question [y/N] n (no console to ask)"; return $false }
    $answer = Read-Host "  $Question [y/N]"
    # also what a Japanese input method gives: full-width y and yes, hai
    return ($answer -match '^\s*(y|yes|\uFF59|\uFF59\uFF45\uFF53|\u306F\u3044)\s*$')
}

function Get-SizeText([string]$Path) {
    try {
        $sum = (Get-ChildItem -LiteralPath $Path -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        if ($null -eq $sum) { $sum = 0 }
        if ($sum -ge 1GB) { return '{0:N1} GB' -f ($sum / 1GB) }
        return '{0:N0} MB' -f ($sum / 1MB)
    } catch { return '? MB' }
}

function Get-FullPath([string]$Path) {
    return [IO.Path]::GetFullPath($Path).TrimEnd('\')
}

# A folder this script may delete: not a drive root, not the user folder, not the TASlation folder itself.
function Test-SafeTarget([string]$Path) {
    $full = Get-FullPath $Path
    if ($full.Length -le 3) { return $false }
    if ($full -ieq (Get-FullPath $env:USERPROFILE)) { return $false }
    if ($full -ieq (Get-FullPath $Root)) { return $false }
    if ((Get-FullPath $Root).StartsWith($full + '\', [StringComparison]::OrdinalIgnoreCase)) { return $false }
    return $true
}

function Remove-Target([string]$What, [string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        Write-Info "$What`: not there ($Path)"
        return
    }
    if (-not (Test-SafeTarget $Path)) {
        Write-Info "$What`: $Path is not a folder this script deletes; left"
        $script:Left.Add("$What ($Path)")
        return
    }
    $size = Get-SizeText $Path
    if ($DryRun) {
        Write-Plan "delete $What ($Path, $size)"
        $script:Deleted.Add("$What ($Path, $size)")
        return
    }
    try {
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
        Write-Info "deleted $What ($Path, $size)"
        $script:Deleted.Add("$What ($Path, $size)")
    } catch {
        Write-Host "  could not delete $Path`: $_" -ForegroundColor Red
        $script:Left.Add("$What ($Path; deletion failed, close what uses it and run uninstall.cmd again)")
        $script:Failed = $true
    }
}

function Get-TomlValue([string]$Key) {
    $toml = Join-Path $Root 'taslation.toml'
    if (-not (Test-Path -LiteralPath $toml)) { return $null }
    foreach ($line in Get-Content -LiteralPath $toml -Encoding UTF8) {
        if ($line -match ('^\s*' + $Key + '\s*=\s*["'']([^"'']+)["'']')) { return $Matches[1] }
    }
    return $null
}

# The model an install from before the record (translator_models.json) pulled: the one taslation.toml names, else
# qwen3.5:4b, the default then ("auto", today's default, names no model: the record lists what was installed since).
function Get-ModelName {
    $configured = Get-TomlValue 'ollama_model'
    if ($configured -and $configured.Trim().ToLower() -ne 'auto') { return $configured }
    return 'qwen3.5:4b'
}

function Find-OllamaExe {
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $user = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
    if (Test-Path -LiteralPath $user) { return $user }
    return $null
}

function Invoke-Shown([string]$Exe, [string[]]$Arguments) {
    Write-Info ('> ' + (Split-Path $Exe -Leaf) + ' ' + ($Arguments -join ' '))
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Exe @Arguments | Out-Host; $code = $LASTEXITCODE } finally { $ErrorActionPreference = $old }
    if ($null -eq $code) { $code = 0 }
    return $code
}

# The data folder: TASLATION_STATE_DIR (or its old name), else ~/.taslation; and which of the two it came from.
function Get-StateDir {
    foreach ($name in @('TASLATION_STATE_DIR', 'SELFTRANS_STATE_DIR')) {
        $v = [Environment]::GetEnvironmentVariable($name)
        if ($v) { return $v }
    }
    return (Join-Path $env:USERPROFILE '.taslation')
}

# The translation models TASlation installed (name -> GB), from the record setup_models.py keeps; $null when there
# is no record (an install from before it).
function Get-OurModels([string]$StateDir) {
    $path = Join-Path $StateDir 'translator_models.json'
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    $ours = [ordered]@{}
    try {
        $record = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($record.installed) {
            foreach ($p in $record.installed.PSObject.Properties) {
                $gb = 0.0
                try { $gb = [double]$p.Value.size_gb } catch { $gb = 0.0 }
                $ours[$p.Name] = $gb
            }
        }
    } catch { }
    return $ours
}

# The record without *Name* (it was removed), written back as UTF-8 without a byte order mark, as Python reads it.
function Remove-FromRecord([string]$StateDir, [string]$Name) {
    $path = Join-Path $StateDir 'translator_models.json'
    if (-not (Test-Path -LiteralPath $path)) { return }
    try {
        $record = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($record.installed) { $record.installed.PSObject.Properties.Remove($Name) }
        [IO.File]::WriteAllText($path, ($record | ConvertTo-Json -Depth 6), (New-Object Text.UTF8Encoding $false))
    } catch { }
}

function Get-UserEnv([string]$Name) { return [Environment]::GetEnvironmentVariable($Name, 'User') }
function Set-UserEnv([string]$Name, [string]$Value) { [Environment]::SetEnvironmentVariable($Name, $Value, 'User') }

# A variable the install set for this user (its *Marker* says so) cleared while it still has the install's *Value*;
# one changed since is the person's and stays. The marker goes either way.
function Clear-InstallSetting([string]$Marker, [string]$Name, [string]$Value) {
    if (-not (Test-Path -LiteralPath $Marker)) { return }
    if ((Get-UserEnv $Name) -eq $Value) {
        if ($DryRun) {
            Write-Plan "clear $Name for this user"
        } else {
            Set-UserEnv $Name $null
        }
        $script:Deleted.Add("the Ollama setting the install made ($Name=$Value)")
    }
    if (-not $DryRun) { Remove-Item -LiteralPath $Marker -Force -ErrorAction SilentlyContinue }
}

function Test-OllamaServer {
    try {
        $null = Invoke-RestMethod -Uri "$OllamaUrl/api/version" -TimeoutSec 3 -UseBasicParsing
        return $true
    } catch { return $false }
}

# The models loaded in Ollama now (its /api/ps); $null when it does not answer.
function Get-LoadedModels {
    try {
        $ps = Invoke-RestMethod -Uri "$OllamaUrl/api/ps" -TimeoutSec 3 -UseBasicParsing
        return @($ps.models | ForEach-Object { $_.name })
    } catch { return $null }
}

# Whether Ollama's server answers within $OllamaStartWaitS seconds of being started (the time counts, not the tries).
function Wait-OllamaServer {
    $clock = [Diagnostics.Stopwatch]::StartNew()
    while ($clock.Elapsed.TotalSeconds -lt $OllamaStartWaitS) {
        Start-Sleep -Seconds 1
        if (Test-OllamaServer) { return $true }
    }
    return $false
}

# `ollama serve` itself in a hidden window (never Ollama's app, which would stay in the tray, and whose first start
# would make Ollama start with Windows); the process, $null when it did not start.
function Start-HiddenServe([string]$Exe) {
    try {
        return (Start-Process -FilePath $Exe -ArgumentList 'serve' -WindowStyle Hidden -PassThru)
    } catch { return $null }
}

# A process this run started ended with the processes it started (taskkill /T, as Ollama's own uninstaller ends
# Ollama's), while it is still that process.
function Stop-ProcessTree($Process) {
    if ($null -eq $Process -or $Process.HasExited) { return }
    $null = & "$env:SystemRoot\System32\taskkill.exe" /PID $Process.Id /T /F 2>&1
    try { $null = $Process.WaitForExit(5000) } catch { }
}

# Ollama's server for `ollama rm`, when it does not answer (the ollama command would start Ollama's app instead):
# started by this run and stopped again once the models are asked about (Stop-OwnOllama), so that the run leaves Ollama
# as it found it. Whether the server answers.
function Start-OwnOllama([string]$Exe) {
    if (Test-OllamaServer) { return $true }
    Write-Info 'starting Ollama (ollama serve, in a hidden window) for ollama rm; it is stopped again afterwards'
    $script:OwnServer = Start-HiddenServe $Exe
    if ($null -ne $script:OwnServer -and (Wait-OllamaServer)) { return $true }
    Stop-OwnOllama
    return $false
}

function Stop-OwnOllama {
    if ($null -eq $script:OwnServer) { return }
    Stop-ProcessTree $script:OwnServer
    $script:OwnServer = $null
}

# The running process *Id* as TASlation's record names one: Process, Path (its program) and Started (when it
# started, a FILETIME in UTC, as Windows gives it to taslation/ollama_start.py); $null when no process runs under that
# number or it cannot be asked.
function Get-ProcessInfo([long]$Id) {
    if ($Id -le 0) { return $null }
    try {
        $p = Get-Process -Id $Id -ErrorAction Stop
        return [pscustomobject]@{ Process = $p; Path = [string]$p.Path; Started = [long]$p.StartTime.ToFileTimeUtc() }
    } catch { return $null }
}

# Whether *Entry* (an object with pid and started, from the record) is a process that still runs: the same number and
# the same start (a number is reused once its process has ended).
function Test-StillRuns($Entry) {
    try {
        $info = Get-ProcessInfo ([long]$Entry.pid)
        return ($null -ne $info -and $info.Started -eq [long]$Entry.started)
    } catch { return $false }
}

# The record of the Ollama server TASlation started ($ServerRecord in *StateDir*: pid, exe, started, url, users);
# $null when there is none or it cannot be read. Read before the data folder may go.
function Get-ServerRecord([string]$StateDir) {
    $path = Join-Path $StateDir $ServerRecord
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    try { return (Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json) } catch { return $null }
}

function Test-SameModel([string]$A, [string]$B) {
    $a1 = $A.Trim().ToLower(); $b1 = $B.Trim().ToLower()
    if (-not $a1.Contains(':')) { $a1 += ':latest' }
    if (-not $b1.Contains(':')) { $b1 += ':latest' }
    return $a1 -eq $b1
}

# The server TASlation started and left running (a TASlation that crashed, or one whose end could not stop it),
# stopped as TASlation itself would stop it (taslation/ollama_start.py): only while it is still the process that was
# started (its number, program and start), no TASlation that uses it still runs, and Ollama has no model loaded but
# TASlation's own (*Own*). Otherwise it is left running, and the run says why. Nothing when there is no record.
function Stop-LeftServer($Record, [string[]]$Own, [string]$StateDir) {
    if ($null -eq $Record) { return }
    $path = Join-Path $StateDir $ServerRecord
    $info = $null
    try { $info = Get-ProcessInfo ([long]$Record.pid) } catch { $info = $null }
    $same = $false
    try { $same = ($null -ne $info -and $info.Started -eq [long]$Record.started -and $info.Path -ieq [string]$Record.exe) } catch { $same = $false }
    if (-not $same) {  # it ended long ago: the record alone is left
        if (-not $DryRun -and (Test-Path -LiteralPath $path)) { Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue }
        return
    }
    $users = @()
    try { $users = @($Record.users | Where-Object { $_ -and (Test-StillRuns $_) }) } catch { $users = @() }
    if ($users.Count -gt 0) {
        Write-Info 'The Ollama server TASlation started is left running: another copy of TASlation still uses it, and stops it when it ends.'
        return
    }
    $foreign = @()
    $loaded = Get-LoadedModels
    foreach ($m in @($loaded)) {
        if (-not $m) { continue }
        $ours = $false
        foreach ($o in $Own) { if ($o -and (Test-SameModel $m $o)) { $ours = $true } }
        if (-not $ours) { $foreign += $m }
    }
    if ($foreign.Count -gt 0) {
        Write-Info ("The Ollama server TASlation started is left running: another program has {0} model(s) loaded in it ({1})." -f $foreign.Count, ($foreign -join ', '))
        if (-not $DryRun -and (Test-Path -LiteralPath $path)) { Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue }
        return
    }
    if ($DryRun) {
        Write-Plan "stop the Ollama server TASlation started and left running (process $($Record.pid))"
        return
    }
    Stop-ProcessTree $info.Process
    if (Get-ProcessInfo ([long]$Record.pid)) {
        Write-Info "The Ollama server TASlation started (process $($Record.pid)) did not stop; it ends when you sign out."
        $script:Left.Add('the Ollama server TASlation started, still running (it ends when you sign out)')
    } else {
        Write-Info 'stopped the Ollama server TASlation had started and left running'
        $script:Deleted.Add('the Ollama server TASlation had left running (stopped)')
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue }
    }
}

# The values of the Run key (name and command), which Windows runs at sign-in.
function Get-RunValues {
    try { $key = Get-Item -LiteralPath $RunKey -ErrorAction Stop } catch { return }
    foreach ($name in @($key.GetValueNames())) {
        if ($name) { [pscustomobject]@{ Name = $name; Data = [string]$key.GetValue($name) } }
    }
}
function Set-RunValue([string]$Name, [string]$Data) {
    if (-not (Test-Path -LiteralPath $RunKey)) { $null = New-Item -Path $RunKey -Force }
    Set-ItemProperty -LiteralPath $RunKey -Name $Name -Value $Data -ErrorAction Stop
}

# What install.ps1 removed of Ollama's start with Windows, as its *Marker* lists it: Kind 'shortcut' (Name: the
# shortcut's path, Data: what it pointed to) or 'run' (Name, Data: the Run key's value). Nothing without the marker.
function Read-AutostartMarker([string]$Marker) {
    if (-not (Test-Path -LiteralPath $Marker)) { return }
    foreach ($line in @(Get-Content -LiteralPath $Marker -Encoding UTF8)) {
        $parts = @($line -split "`t")
        if ($parts.Count -ge 2 -and $parts[0] -eq 'shortcut') {
            $target = ''
            if ($parts.Count -ge 3) { $target = $parts[2] }
            [pscustomobject]@{ Kind = 'shortcut'; Name = $parts[1]; Data = $target }
        } elseif ($parts.Count -ge 3 -and $parts[0] -eq 'run') {
            [pscustomobject]@{ Kind = 'run'; Name = $parts[1]; Data = ($parts[2..($parts.Count - 1)] -join "`t") }
        }
    }
}

# Ollama's app as *OllamaExe*'s folder has it (what its start with Windows runs).
function Get-OllamaApp([string]$OllamaExe) {
    if (-not $OllamaExe) { return $null }
    $app = Join-Path (Split-Path -Parent $OllamaExe) 'ollama app.exe'
    if (Test-Path -LiteralPath $app) { return $app }
    return $null
}

# One shortcut of Ollama's start with Windows put back at *Path*: a copy of the one Ollama's app itself copies there
# (lib\Ollama.lnk beside the app), else a shortcut to the app. Whether it is there now.
function Restore-OllamaShortcut([string]$Path, [string]$App) {
    if (Test-Path -LiteralPath $Path) { return $true }
    if (-not $App) { return $false }
    try {
        $template = Join-Path (Split-Path -Parent $App) 'lib\Ollama.lnk'
        if (Test-Path -LiteralPath $template) {
            Copy-Item -LiteralPath $template -Destination $Path -ErrorAction Stop
        } else {
            $lnk = (New-Object -ComObject WScript.Shell).CreateShortcut($Path)
            $lnk.TargetPath = $App
            $lnk.WorkingDirectory = (Split-Path -Parent $App)
            $lnk.Save()
        }
        return (Test-Path -LiteralPath $Path)
    } catch { return $false }
}

# What the install changed about Ollama's start with Windows, said, and undone where that is sure:
# * after the person's yes (.ollama-autostart-by-install), an Ollama that is kept starts with Windows again as before:
#   each shortcut and Run value the marker lists is put back, unless something is there under its name now;
# * an Ollama the install installed for TASlation (.ollama-by-install) never started with Windows for this person
#   (its app's first start made that, and the install removed it at once): it is left so, and the run says how to
#   change that.
# Nothing is put back when Ollama itself is gone (its uninstaller removes its start with Windows). The markers go.
function Undo-AutostartChange([string]$OllamaExe, [bool]$OllamaRemoved) {
    $app = Get-OllamaApp $OllamaExe
    $kept = [bool]$OllamaExe -and -not $OllamaRemoved
    $before = @(Read-AutostartMarker $AutostartMarker)
    if ($kept -and $before.Count -gt 0 -and $DryRun) {
        foreach ($entry in $before) { Write-Plan "put back Ollama's start with Windows: $($entry.Kind) $($entry.Name)" }
    } elseif ($kept -and $before.Count -gt 0) {
        $all = $true
        $names = @(Get-RunValues | ForEach-Object { $_.Name })
        foreach ($entry in $before) {
            if ($entry.Kind -eq 'shortcut') {
                $target = $entry.Data
                if (-not $target -or -not (Test-Path -LiteralPath $target)) { $target = $app }
                if (-not (Restore-OllamaShortcut $entry.Name $target)) { $all = $false }
            } elseif ($names -notcontains $entry.Name) {
                try { Set-RunValue $entry.Name $entry.Data } catch { $all = $false }
            }
        }
        if ($all) {
            Write-Info 'Ollama starts with Windows again, as it did before TASlation''s install (to change that: Task Manager > Startup apps).'
            $script:Deleted.Add('the install''s change to Ollama''s start with Windows (put back)')
        } else {
            Write-Info 'The install had stopped Ollama from starting with Windows, and that could not be put back.'
            Write-Info 'To have Ollama start with Windows again: press Win+R, type shell:startup, and put a shortcut to "ollama app.exe" (in Ollama''s folder) there.'
            $script:Left.Add('Ollama not starting with Windows (to change that, see above)')
        }
    }
    if ($kept -and (Test-Path -LiteralPath $OllamaMarker)) {
        Write-Info 'Ollama was installed for TASlation and does not start with Windows; it stays so.'
        Write-Info 'To have it start with Windows: press Win+R, type shell:startup, and copy Ollama.lnk from the lib folder in Ollama''s folder there. Or start Ollama from the Start menu when you need it.'
    }
    if (-not $DryRun) {
        foreach ($m in @($AutostartMarker, $OllamaMarker)) { Remove-Item -LiteralPath $m -Force -ErrorAction SilentlyContinue }
    }
}

# ---------------------------------------------------------------- start
Write-Host 'TASlation uninstaller' -ForegroundColor Cyan
# out of the folders it deletes
Push-Location -LiteralPath $Root
Write-Host "  folder: $Root"
if ($DryRun) { Write-Host '  DRY RUN: nothing is deleted.' -ForegroundColor DarkYellow }

# Python running from the environment (the window, a batch) would hold its files open.
$running = @()
try {
    $prefix = (Get-FullPath $Venv) + '\'
    $running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
        try { $_.Path -and $_.Path.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) } catch { $false }
    })
} catch { $running = @() }
if ($running.Count -gt 0) {
    $list = ($running | ForEach-Object { "$($_.ProcessName) (pid $($_.Id))" }) -join ', '
    if ($DryRun) {
        Write-Info "note: TASlation is running ($list); close it before the real run."
    } else {
        Write-Host "  TASlation is running from this folder: $list. Close it (and any batch) and run uninstall.cmd again." -ForegroundColor Red
        Pop-Location
        exit 1
    }
}

# Double-clicking is no agreement: what goes is listed, and Enter leaves everything.
Write-Host ''
Write-Info 'This removes:'
Write-Info '  - the program files (.venv in this folder)'
Write-Info '  - the reading model and fonts (models in this folder)'
Write-Info '  - the Start-menu shortcut'
Write-Info 'Your translations, notes and Ollama stay, unless you say otherwise after this.'
if ($DryRun) {
    Write-Info 'Remove TASlation? [y/N] (dry run: would ask; counted as y)'
} elseif (-not (Confirm-Choice 'Remove TASlation?')) {
    Write-Info 'Nothing was removed.'
    Pop-Location
    exit 0
}

# what TASlation installed into Ollama, and the Ollama server it started, read before the data folder may go
$ourModels = Get-OurModels (Get-StateDir)
$leftServer = Get-ServerRecord (Get-StateDir)

# 1. the environment and the models ---------------------------------------
Write-Step 'Virtual environment and models in this folder'
Remove-Target 'the virtual environment' $Venv
Remove-Target 'the OCR model and fonts' $Models
foreach ($name in @('TASLATION_MODELS_DIR', 'SELFTRANS_MODELS_DIR')) {
    $v = [Environment]::GetEnvironmentVariable($name)
    if ($v) { $script:Left.Add("models in $v (set by $name; delete by hand if you want)") }
}
$tomlModels = Get-TomlValue 'models_dir'
if ($tomlModels) { $script:Left.Add("models in $tomlModels (models_dir in taslation.toml; delete by hand if you want)") }

# 2. the shortcut ----------------------------------------------------------
Write-Step 'Start-menu shortcut'
if (Test-Path -LiteralPath $ShortcutPath) {
    $ours = $false
    try {
        $shell = New-Object -ComObject WScript.Shell
        $lnk = $shell.CreateShortcut($ShortcutPath)
        $rootPrefix = (Get-FullPath $Root) + '\'
        $ours = ($lnk.TargetPath -and $lnk.TargetPath.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase))
    } catch { $ours = $false }
    if (-not $ours) {
        Write-Info "$ShortcutPath points elsewhere (another copy of TASlation?); left"
        $script:Left.Add("the Start-menu shortcut $ShortcutPath (not this folder's)")
    } elseif ($DryRun) {
        Write-Plan "delete the Start-menu shortcut $ShortcutPath"
        $script:Deleted.Add("the Start-menu shortcut ($ShortcutPath)")
    } else {
        try {
            Remove-Item -LiteralPath $ShortcutPath -Force -ErrorAction Stop
            Write-Info "deleted $ShortcutPath"
            $script:Deleted.Add("the Start-menu shortcut ($ShortcutPath)")
        } catch {
            Write-Host "  could not delete $ShortcutPath`: $_" -ForegroundColor Red
            $script:Failed = $true
        }
    }
} else {
    Write-Info 'none'
}

# 3. the data --------------------------------------------------------------
Write-Step 'Your data (translation caches, notes, settings)'
$stateDir = Get-StateDir
$stateSource = '~/.taslation'
foreach ($name in @('TASLATION_STATE_DIR', 'SELFTRANS_STATE_DIR')) {
    if ([Environment]::GetEnvironmentVariable($name) -and $stateSource -eq '~/.taslation') { $stateSource = $name }
}
$tomlState = Get-TomlValue 'state_dir'
if ($tomlState) { $script:Left.Add("data in $tomlState (state_dir in taslation.toml; delete by hand if you want)") }
if (-not (Test-Path -LiteralPath $stateDir)) {
    Write-Info "no data folder ($stateDir)"
} else {
    Write-Info "$stateDir ($stateSource, $(Get-SizeText $stateDir)) holds your translations, notes and settings."
    if (Confirm-Choice "Delete $stateDir and everything in it? This cannot be undone" $true) {
        Remove-Target 'your data folder' $stateDir
    } else {
        Write-Info 'kept'
        $script:Left.Add("your data ($stateDir); a later install finds it again")
    }
}

# 4. Ollama ----------------------------------------------------------------
Write-Step 'Ollama and the translation model'
$model = Get-ModelName
$ollamaExe = Find-OllamaExe
# the models that count as TASlation's own in a server it left running: its translators, those it installed, the
# configured one
$ownNames = @($OwnModels) + @($model)
if ($null -ne $ourModels) { $ownNames += @($ourModels.Keys) }
$ollamaRemoved = $false
if (-not $ollamaExe) {
    Write-Info 'Ollama not found; nothing to do'
    Stop-LeftServer $leftServer $ownNames $stateDir
} else {
    $modelsLeft = New-Object System.Collections.Generic.List[string]
    $serverAsked = $false  # whether Ollama's server was made to answer for ollama rm (started by this run if need be)
    $serverAnswers = $false
    # the models TASlation installed, each asked about; without a record (an install from before it), the configured one
    $asked = [ordered]@{}
    if ($null -eq $ourModels) { $asked[$model] = 3.3 }
    else { foreach ($k in $ourModels.Keys) { $asked[$k] = $ourModels[$k] } }
    if ($asked.Count -eq 0) { Write-Info 'TASlation installed no translation model; any model in Ollama is yours and stays' }
    foreach ($name in $asked.Keys) {
        $question = "Remove the translation model $name from Ollama (ollama rm, about {0:N1} GB)?" -f $asked[$name]
        if ($null -ne $ourModels) { $question = "Remove the translation model $name that TASlation installed (ollama rm, about {0:N1} GB)?" -f $asked[$name] }
        if (Confirm-Choice "$question Other programs using it lose it too" $true) {
            if ($DryRun) {
                Write-Plan "ollama rm $name (with ollama serve started in a hidden window first when nothing answers, and stopped again)"
            } else {
                if (-not $serverAsked) {
                    $serverAsked = $true
                    $serverAnswers = Start-OwnOllama $ollamaExe
                    if (-not $serverAnswers) { Write-Info 'Ollama''s server did not answer, so ollama rm cannot remove a model.' }
                }
                $code = 1
                if ($serverAnswers) { $code = Invoke-Shown $ollamaExe @('rm', $name) }
                if ($code -eq 0) {
                    $script:Deleted.Add("the Ollama model $name")
                    if (Test-Path -LiteralPath $stateDir) { Remove-FromRecord $stateDir $name }
                } else {
                    Write-Info "ollama rm ended with exit code $code (is Ollama running? is the model installed?)"
                    $modelsLeft.Add($name)
                }
            }
        } else {
            $modelsLeft.Add($name)
        }
    }
    Stop-OwnOllama  # the run leaves Ollama as it found it: a server it started for ollama rm goes again
    Stop-LeftServer $leftServer $ownNames $stateDir
    if (Confirm-Choice 'Uninstall Ollama itself with winget too (winget uninstall Ollama.Ollama)? Other programs using it lose it' $true) {
        $winget = Get-Command winget -ErrorAction SilentlyContinue
        if (-not $winget) {
            Write-Info 'winget is not available: remove Ollama in Settings > Apps > Installed apps'
            $script:Left.Add('Ollama (remove it in Settings > Apps)')
        } else {
            $code = Invoke-Shown $winget.Source @('uninstall', '--id', 'Ollama.Ollama', '--exact')
            if ($code -eq 0) { $script:Deleted.Add('Ollama'); $ollamaRemoved = $true }
            else {
                Write-Info "winget ended with exit code $code"
                $script:Left.Add('Ollama (remove it with: winget uninstall Ollama.Ollama, or in Settings > Apps)')
            }
        }
    } else {
        Write-Info 'Ollama itself is kept. To remove it: winget uninstall Ollama.Ollama (or Settings > Apps).'
        Write-Info 'Its other models stay in ~/.ollama until you remove them.'
        $script:Left.Add('Ollama (winget uninstall Ollama.Ollama, or Settings > Apps)')
    }
    # ollama rm is no way out once Ollama itself is gone
    if ($ollamaRemoved) {
        $script:Left.Add('the models in Ollama''s model folder (~/.ollama, or OLLAMA_MODELS): delete it by hand if you want')
    } else {
        foreach ($name in $modelsLeft) { $script:Left.Add("the Ollama model $name (remove it later: ollama rm $name)") }
    }
}
# what the install changed about Ollama's start with Windows
Undo-AutostartChange $ollamaExe $ollamaRemoved

# 5. the settings the install made -----------------------------------------
Clear-InstallSetting $KvMarker 'OLLAMA_KV_CACHE_TYPE' 'q8_0'
Clear-InstallSetting $CacheRamMarker 'LLAMA_ARG_CACHE_RAM' '0'

# summary ------------------------------------------------------------------
$script:Left.Add("this folder itself ($Root): delete it by hand when you no longer want it")
$script:Left.Add('Python, never removed here: other programs may use it (Settings > Apps > Installed apps, or winget uninstall Python.Python.3.13 if the installer put it there)')
Write-Host ''
if ($DryRun) { Write-Host 'Dry run: would delete' -ForegroundColor Cyan } else { Write-Host 'Deleted' -ForegroundColor Cyan }
if ($script:Deleted.Count -eq 0) { Write-Host '  nothing' }
foreach ($d in $script:Deleted) { Write-Host "  - $d" }
Write-Host 'Left in place' -ForegroundColor Cyan
foreach ($l in $script:Left) { Write-Host "  - $l" }
Pop-Location
if ($script:Failed) { exit 1 }
exit 0
