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
that file is asked about its configured model. Then it asks whether to
uninstall Ollama itself with winget (all default: no). When the install set
OLLAMA_KV_CACHE_TYPE (the file .kv-cache-by-install says so) and it is still
q8_0, it clears that variable for your user. It never touches
anything else: this folder's own files, Python (also when install.cmd installed
it; it says how to remove it) and pip's download cache stay.

.PARAMETER Yes
For unattended runs and checks; uninstall.cmd asks instead. Answers Y to the
first question and to removing the translation model. It answers no about your data folder and about
Ollama itself: a run nobody watches does not destroy a person's translations.

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

# what TASlation installed into Ollama, read before the data folder may go
$ourModels = Get-OurModels (Get-StateDir)

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
if (-not $ollamaExe) {
    Write-Info 'Ollama not found; nothing to do'
} else {
    $modelsLeft = New-Object System.Collections.Generic.List[string]
    $ollamaRemoved = $false
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
                Write-Plan "ollama rm $name"
            } else {
                $code = Invoke-Shown $ollamaExe @('rm', $name)
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

# 5. the setting the install made ------------------------------------------
if (Test-Path -LiteralPath $KvMarker) {
    if ((Get-UserEnv 'OLLAMA_KV_CACHE_TYPE') -eq 'q8_0') {
        if ($DryRun) {
            Write-Plan 'clear OLLAMA_KV_CACHE_TYPE for this user'
        } else {
            Set-UserEnv 'OLLAMA_KV_CACHE_TYPE' $null
        }
        $script:Deleted.Add('the Ollama setting the install made (OLLAMA_KV_CACHE_TYPE)')
    }
    if (-not $DryRun) { Remove-Item -LiteralPath $KvMarker -Force -ErrorAction SilentlyContinue }
}

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
