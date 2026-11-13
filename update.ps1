<#
.SYNOPSIS
Updates TASlation in this folder from a newer copy you downloaded yourself: the
ZIP of the repository or the folder you unpacked it into. Then it runs
install.ps1, which asks before any download, as on the first install. That run
keeps the PyTorch of the program files as it is: a CPU build on a computer with
an NVIDIA GPU stays (install.cmd replaces it with the GPU build, about 2.6 GB),
so that an update never starts that download unasked.

.DESCRIPTION
Download the new ZIP (on GitHub: Code > Download ZIP) and close TASlation.
Then double-click update.cmd in this folder and give it the ZIP when it asks:
drag the file into the window and press Enter. From a PowerShell window:

    powershell -ExecutionPolicy Bypass -File update.ps1 -From <the ZIP or folder>

It finds the new copy in the ZIP or the folder (at the top or one folder down,
as in GitHub's ZIP), shows both versions and dates and asks once. Then it
copies the new files over these. What is yours stays: taslation.toml, the
folders .venv and models and the files install.ps1 leaves here are never
copied over, and your data folder (~/.taslation, or TASLATION_STATE_DIR) is not
touched. The program folder taslation\ is made the same as the new one (a file
the new version no longer has goes); nothing else is deleted. A ZIP is unpacked
into a temporary folder, which is removed afterwards.
This script uses no network: it reads only the ZIP or folder you give it.

.PARAMETER From
The new copy: a .zip file or a folder. Without it the script asks, offering the
newest taslation*.zip in your Downloads folder.

.PARAMETER Yes
For unattended runs and checks (with -From): no question, and install.ps1 runs
with -Yes too.

.PARAMETER DryRun
For checks: print what would be copied and deleted; change nothing and run
nothing.
#>
[CmdletBinding()]
param(
    [string]$From = '',
    [switch]$Yes,
    [switch]$DryRun
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$Root = $PSScriptRoot
$Venv = Join-Path $Root '.venv'
$Interactive = (-not [Console]::IsInputRedirected) -and [Environment]::UserInteractive
# Never copied over (at the top of the folder): the person's settings, what install.ps1 made, the clone's own history.
$KeptNames = @('taslation.toml', '.venv', 'models', '.git', '.kv-cache-by-install', '.cache-ram-by-install')
$Downloads = Join-Path $env:USERPROFILE 'Downloads'
$script:Temp = $null

function Write-Step([string]$Text) { Write-Host ''; Write-Host $Text -ForegroundColor Cyan }
function Write-Ok([string]$Text) { Write-Host "  ok: $Text" -ForegroundColor Green }
function Write-Info([string]$Text) { Write-Host "  $Text" }
function Write-Plan([string]$Text) { Write-Host "  dry run, would: $Text" -ForegroundColor DarkYellow }

# The window of update.cmd stays open to read the result (update.cmd says so), unless nobody watches.
function Exit-Update([int]$Code) {
    try { Pop-Location } catch { }
    if ($script:Temp -and (Test-Path -LiteralPath $script:Temp)) {
        Remove-Item -LiteralPath $script:Temp -Recurse -Force -ErrorAction SilentlyContinue
    }
    if ($env:TASLATION_UPDATE_PAUSE -eq '1' -and $Interactive -and -not $Yes) {
        Write-Host ''
        [void](Read-Host 'Press Enter to close this window')
    }
    exit $Code
}

function Stop-Update([string]$Text) {
    Write-Host "  error: $Text" -ForegroundColor Red
    Write-Host ''
    Write-Host 'Nothing was changed.'
    Exit-Update 1
}

# Asks a yes/no question; -Yes and a dry run answer it without a prompt, a run without a console answers no.
function Confirm-Choice([string]$Question, [bool]$DefaultYes = $false) {
    $hint = '[y/N]'
    if ($DefaultYes) { $hint = '[Y/n]' }
    if ($Yes) { Write-Info "$Question $hint y (-Yes)"; return $true }
    if ($DryRun) { Write-Info "$Question $hint (dry run: would ask; counted as y)"; return $true }
    if (-not $Interactive) { Write-Info "$Question $hint n (no console to ask)"; return $false }
    $answer = Read-Host "  $Question $hint"
    # also what a Japanese input method gives: full-width y and yes, hai
    $words = 'y|yes|\uFF59|\uFF59\uFF45\uFF53|\u306F\u3044'
    if ($DefaultYes) { return ($answer -match "^\s*($words)?\s*$") }
    return ($answer -match "^\s*($words)\s*$")
}

function Get-FullPath([string]$Path) { return [IO.Path]::GetFullPath($Path).TrimEnd('\') }

# A folder that holds a whole TASlation: its install script, its project file naming it, its package.
function Test-Copy([string]$Folder) {
    $project = Join-Path $Folder 'pyproject.toml'
    if (-not (Test-Path -LiteralPath (Join-Path $Folder 'install.ps1'))) { return $false }
    if (-not (Test-Path -LiteralPath (Join-Path $Folder 'taslation\__init__.py'))) { return $false }
    if (-not (Test-Path -LiteralPath $project)) { return $false }
    foreach ($line in Get-Content -LiteralPath $project -Encoding UTF8) {
        if ($line -match '^\s*name\s*=\s*"taslation"') { return $true }
    }
    return $false
}

# The copy in *Folder*: the folder itself, or the one folder in it that is one (GitHub's ZIP holds taslation-main).
function Find-Copy([string]$Folder) {
    if (Test-Copy $Folder) { return $Folder }
    $inside = @(Get-ChildItem -LiteralPath $Folder -Directory -Force -ErrorAction SilentlyContinue | Where-Object { Test-Copy $_.FullName })
    if ($inside.Count -eq 1) { return $inside[0].FullName }
    return $null
}

# The version, and the date of the newest program file (as Help > About shows it).
function Get-VersionLine([string]$Folder) {
    $version = '?'
    foreach ($line in Get-Content -LiteralPath (Join-Path $Folder 'pyproject.toml') -Encoding UTF8) {
        if ($line -match '^\s*version\s*=\s*"([^"]+)"') { $version = $Matches[1]; break }
    }
    $newest = Get-ChildItem -LiteralPath (Join-Path $Folder 'taslation') -Filter '*.py' -File -Recurse -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime | Select-Object -Last 1
    if ($newest) { return [pscustomobject]@{ Text = ('{0}, files dated {1}' -f $version, $newest.LastWriteTime.ToString('yyyy-MM-dd')); Date = $newest.LastWriteTime } }
    return [pscustomobject]@{ Text = $version; Date = $null }
}

# The newest taslation*.zip in the Downloads folder, offered when nothing is given; $null when there is none.
function Find-DownloadedZip {
    if (-not (Test-Path -LiteralPath $Downloads)) { return $null }
    $zip = Get-ChildItem -LiteralPath $Downloads -Filter 'taslation*.zip' -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime | Select-Object -Last 1
    if ($zip) { return $zip.FullName }
    return $null
}

# What the person gave: -From, else asked for (a file dragged into the window comes in quotes).
function Get-Source {
    if ($From) { return $From }
    $offered = $null
    if ($Interactive -and -not $Yes) { $offered = Find-DownloadedZip }
    if ($Yes -or $DryRun -or -not $Interactive) {
        Write-Info 'Give the new copy with -From <the ZIP or folder>, or run update.cmd and answer its question.'
        Exit-Update 1
    }
    $question = 'Where is the new TASlation? A ZIP file or its folder (drag it here)'
    if ($offered) { $question += "; Enter: $offered" }
    $answer = Read-Host "  $question"
    $answer = "$answer".Trim().Trim('"').Trim()
    if (-not $answer -and $offered) { return $offered }
    if (-not $answer) { Stop-Update 'no new copy given.' }
    return $answer
}

# Files of *Folder* by their path in it, with the kept names at the top and Python's caches left out.
function Get-Files([string]$Folder) {
    $base = (Get-FullPath $Folder) + '\'
    $files = @{}
    foreach ($f in Get-ChildItem -LiteralPath $Folder -Recurse -File -Force -ErrorAction SilentlyContinue) {
        $rel = $f.FullName.Substring($base.Length)
        $top = ($rel -split '\\')[0]
        if ($KeptNames -contains $top -or $top -like '*.egg-info') { continue }
        if (($rel -split '\\') -contains '__pycache__') { continue }
        $files[$rel] = $f.FullName
    }
    return $files
}

# ---------------------------------------------------------------- start
Write-Host 'TASlation update' -ForegroundColor Cyan
Push-Location -LiteralPath $Root
Write-Host "  folder: $Root"
if ($DryRun) { Write-Host '  DRY RUN: nothing is copied, deleted or run.' -ForegroundColor DarkYellow }
if (-not (Test-Copy $Root)) { Stop-Update 'this folder holds no TASlation to update. Run update.cmd in the TASlation folder.' }

# Python running from the environment (the window, a batch) runs the old files: it is closed first.
$running = @()
try {
    $prefix = (Get-FullPath $Venv) + '\'
    $running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
        try { $_.Path -and $_.Path.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) } catch { $false }
    })
} catch { $running = @() }
if ($running.Count -gt 0 -and -not $DryRun) {
    $list = ($running | ForEach-Object { "$($_.ProcessName) (pid $($_.Id))" }) -join ', '
    Stop-Update "TASlation is running from this folder: $list. Close it (and any batch) and run update.cmd again."
}

Write-Step 'The new copy'
$source = Get-Source
if (-not (Test-Path -LiteralPath $source)) { Stop-Update "there is no file or folder $source." }
$source = Get-FullPath (Resolve-Path -LiteralPath $source).ProviderPath
$where = $source
if (Test-Path -LiteralPath $source -PathType Leaf) {
    if ($source -notmatch '\.zip$') { Stop-Update "$source is neither a ZIP file nor a folder." }
    $script:Temp = Join-Path ([IO.Path]::GetTempPath()) ('taslation-update-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [IO.Compression.ZipFile]::ExtractToDirectory($source, $script:Temp)
    } catch {
        Stop-Update "the ZIP could not be unpacked: $($_.Exception.Message)"
    }
    $where = $script:Temp
}
$new = Find-Copy $where
if ($null -eq $new) { Stop-Update "$source holds no TASlation (no install.ps1, pyproject.toml and taslation folder in it)." }
$new = Get-FullPath $new
$here = Get-FullPath $Root
if ($new -ieq $here) { Stop-Update 'that is this folder itself. Give the ZIP you downloaded, or the folder you unpacked it into.' }
if ($here.StartsWith($new + '\', [StringComparison]::OrdinalIgnoreCase)) { Stop-Update "$new holds this folder; give the new copy itself." }
$nested = $new.StartsWith($here + '\', [StringComparison]::OrdinalIgnoreCase)

$now = Get-VersionLine $Root
$next = Get-VersionLine $new
Write-Info "this one: $($now.Text)"
Write-Info "the new:  $($next.Text)"
$older = ($null -ne $now.Date) -and ($null -ne $next.Date) -and ($next.Date.Date -lt $now.Date.Date)
if ($older) { Write-Info 'The new copy is OLDER than this one.' }

$newFiles = Get-Files $new
$oldFiles = @{}
foreach ($pair in (Get-Files $Root).GetEnumerator()) {
    if ($pair.Key -like 'taslation\*') { $oldFiles[$pair.Key] = $pair.Value }
}
$gone = @($oldFiles.Keys | Where-Object { -not $newFiles.ContainsKey($_) } | Sort-Object)
Write-Info ("{0} files to copy over these; {1} program files the new version no longer has to delete." -f $newFiles.Count, $gone.Count)
Write-Info 'Kept as they are: taslation.toml, .venv, models and your data folder.'
if (-not (Confirm-Choice "Update this TASlation to $($next.Text)?" (-not $older))) {
    Write-Host ''
    Write-Host 'Nothing was changed.'
    Exit-Update 1
}

Write-Step 'Copying'
if ($DryRun) {
    foreach ($rel in ($newFiles.Keys | Sort-Object)) { Write-Plan "copy $rel" }
    foreach ($rel in $gone) { Write-Plan "delete $rel" }
    Write-Host ''
    Write-Host 'Dry run finished; nothing was changed.' -ForegroundColor Cyan
    Exit-Update 0
}
$copied = 0
try {
    foreach ($rel in ($newFiles.Keys | Sort-Object)) {
        $target = Join-Path $Root $rel
        $folder = Split-Path -Parent $target
        if (-not (Test-Path -LiteralPath $folder)) { New-Item -ItemType Directory -Path $folder -Force | Out-Null }
        Copy-Item -LiteralPath $newFiles[$rel] -Destination $target -Force
        $copied++
    }
    foreach ($rel in $gone) { Remove-Item -LiteralPath (Join-Path $Root $rel) -Force }
} catch {
    Write-Host "  error: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "  $copied files were copied before it stopped. Close what uses this folder and run update.cmd again." -ForegroundColor Red
    Exit-Update 1
}
Write-Ok "$copied files copied, $($gone.Count) deleted"
if ($nested) { Write-Info "The folder $(Split-Path -Leaf $new) inside this one is not needed any more; you can delete it." }

Write-Step 'Install'
Write-Info 'install.ps1 now checks what the new version needs, and asks before any download.'
$shell = (Get-Process -Id $PID).Path
$installArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $Root 'install.ps1'))
if ($Yes) { $installArgs += '-Yes' }
# install.ps1 then keeps the program files' PyTorch as it is (a CPU build on a computer with an NVIDIA GPU too)
$env:TASLATION_UPDATING = '1'
& $shell @installArgs
$code = $LASTEXITCODE
if ($null -eq $code) { $code = 0 }
Exit-Update $code
