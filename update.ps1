<#
.SYNOPSIS
Updates TASlation in this folder to a newer version: one downloaded from GitHub
when you agree to it, or a copy you downloaded yourself (the ZIP of the
repository or the folder you unpacked it into). Then it runs install.ps1, which
asks before any download of its own, as on the first install. That run keeps
the PyTorch of the program files as it is: a CPU build on a computer with an
NVIDIA GPU stays (install.cmd replaces it with the GPU build, about 2.6 GB), so
that an update never starts that download unasked.

.DESCRIPTION
Close TASlation, then double-click update.cmd in this folder. It first asks
whether to look on GitHub for the newest version and download it. A yes runs
check_update.py beside this script with the program files' Python: it asks
GitHub for one small file (the project's CHANGELOG.md), and this script shows
both versions and what changed and asks once more before anything is
downloaded; then check_update.py downloads that version's ZIP (about 5 MB) into
a temporary folder. A no goes on as before: give it the ZIP or the folder you
downloaded yourself (on GitHub: Code > Download ZIP), dragged into the window.
In TASlation, Help > Check for updates... starts update.cmd the same way when
you choose Update now (-Download -Version -WaitFor -Confirmed -Restart).
From a PowerShell window:

    powershell -ExecutionPolicy Bypass -File update.ps1 -From <the ZIP or folder>
    powershell -ExecutionPolicy Bypass -File update.ps1 -Download

It finds the new copy in the ZIP or the folder (at the top or one folder down,
as in GitHub's ZIP), shows both versions and dates and asks once. Before it
copies the new files over these, it keeps the files they replace or delete in
the folder .previous, with a note of their version and of the files the update
adds: one earlier version only, which the next update replaces. update.cmd
-Back puts it back. What is yours stays: taslation.toml, the folders .venv and
models and the files install.ps1 leaves here are never copied over, and your
data folder (~/.taslation, or TASLATION_STATE_DIR) is not touched. The program
folder taslation\ is made the same as the new one (a file the new version no
longer has goes); nothing else is deleted. A ZIP is unpacked into a temporary
folder, which is removed afterwards.
When the installation then stops (after a no to a question, or a download that
failed three times), the new files are already in place; the last lines say
how to go on (update.cmd again with the same ZIP: a ZIP downloaded from GitHub
is kept for it, and its place is said) and how to go back (update.cmd -Back).
The Start-menu shortcut stays only if TASlation starts as it is; the exit code
is install.ps1's (0 when it got to its end).
Only check_update.py uses the network, and only after a yes to the first
question or with -Download. A folder that is a git clone (.git beside this
script) is never updated from GitHub's ZIP nor taken back by -Back: use git
there.

.PARAMETER From
The new copy: a .zip file or a folder. Without it (and without -Download) the
script asks, offering the newest taslation*.zip in your Downloads folder.

.PARAMETER Yes
For unattended runs and checks (with -From or -Download): no question, and
install.ps1 runs with -Yes too.

.PARAMETER DryRun
For checks: print what would be copied, deleted and run; change nothing, run
nothing and ask GitHub nothing.

.PARAMETER Download
Look on GitHub for the newest version (or take -Version), show what changed,
ask, download that version's ZIP and update from it. Only a version newer than
this one.

.PARAMETER Version
With -Download: the version to download, as X.Y.Z, without asking GitHub which
is the newest. The ZIP must hold that version.

.PARAMETER WaitFor
The process number of a TASlation that is closing for this update: the update
waits up to 60 seconds for it to end, else it says so and stops.

.PARAMETER Restart
Start TASlation again, as its Start-menu shortcut does, when the installation
got to its end.

.PARAMETER Confirmed
The update was agreed to already (TASlation's Update now, after it showed both
versions): it is not asked again. install.ps1's own questions still are.

.PARAMETER Back
Go back to the version kept in .previous by the last update: its files are put
back and the files that update added are deleted. What the installation added
to .venv stays.
#>
[CmdletBinding()]
param(
    [string]$From = '',
    [switch]$Yes,
    [switch]$DryRun,
    [switch]$Download,
    [string]$Version = '',
    [int]$WaitFor = 0,
    [switch]$Restart,
    [switch]$Confirmed,
    [switch]$Back
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$Root = $PSScriptRoot
$Venv = Join-Path $Root '.venv'
$VenvPy = Join-Path $Venv 'Scripts\python.exe'
$VenvPyw = Join-Path $Venv 'Scripts\pythonw.exe'
$CheckScript = Join-Path $Root 'check_update.py'
$Interactive = (-not [Console]::IsInputRedirected) -and [Environment]::UserInteractive
# Never copied over (at the top of the folder): the person's settings, what install.ps1 made, the clone's own history
# and the repository's checks (.github: GitHub's ZIP leaves it out, a clone has it), the earlier version kept.
$KeptNames = @('taslation.toml', '.venv', 'models', '.git', '.github', '.kv-cache-by-install', '.cache-ram-by-install',
               '.ollama-by-install', '.ollama-autostart-by-install', '.previous')
# The files an update replaces or deletes, kept for -Back (one earlier version), and the note of that version.
$Previous = Join-Path $Root '.previous'
$PreviousFiles = Join-Path $Previous 'files'
$PreviousNote = Join-Path $Previous 'previous-version.txt'
$IsClone = Test-Path -LiteralPath (Join-Path $Root '.git')
$WaitForS = 60  # how long -WaitFor waits for TASlation to close
$StartWatchS = 10  # how long a TASlation started again is watched for an end at once
$Downloads = Join-Path $env:USERPROFILE 'Downloads'
$script:Temp = $null
$script:DownloadDir = $null
$script:KeepDownload = $false

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
    if ($script:DownloadDir -and -not $script:KeepDownload -and (Test-Path -LiteralPath $script:DownloadDir)) {
        Remove-Item -LiteralPath $script:DownloadDir -Recurse -Force -ErrorAction SilentlyContinue
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

# The version line of the pyproject.toml in *Folder*, as it is written ('' when there is none).
function Get-VersionText([string]$Folder) {
    $project = Join-Path $Folder 'pyproject.toml'
    if (-not (Test-Path -LiteralPath $project)) { return '' }
    foreach ($line in Get-Content -LiteralPath $project -Encoding UTF8) {
        if ($line -match '^\s*version\s*=\s*"([^"]+)"') { return $Matches[1] }
    }
    return ''
}

# A version written X.Y.Z (digits only) as a number to compare, else $null.
function ConvertTo-Version([string]$Text) {
    if ("$Text" -notmatch '^[0-9]+\.[0-9]+\.[0-9]+$') { return $null }
    try { return [version]$Text } catch { return $null }
}

# The version, and the date of the newest program file (as Help > About shows it).
function Get-VersionLine([string]$Folder) {
    $version = Get-VersionText $Folder
    if (-not $version) { $version = '?' }
    $newest = Get-ChildItem -LiteralPath (Join-Path $Folder 'taslation') -Filter '*.py' -File -Recurse -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime | Select-Object -Last 1
    if ($newest) { return [pscustomobject]@{ Text = ('{0}, files dated {1}' -f $version, $newest.LastWriteTime.ToString('yyyy-MM-dd')); Date = $newest.LastWriteTime; Version = $version } }
    return [pscustomobject]@{ Text = $version; Date = $null; Version = $version }
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
        Write-Info 'Give the new copy with -From <the ZIP or folder>, or -Download for the newest version on GitHub, or run update.cmd and answer its questions.'
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

# The processes running from the program files (the window, a batch): they run the old files.
function Get-Running {
    try {
        $prefix = (Get-FullPath $Venv) + '\'
        return @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
            try { $_.Path -and $_.Path.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) } catch { $false }
        })
    } catch { return @() }
}

# A TASlation that closes for this update (-WaitFor): its end waited for, at most $WaitForS seconds.
function Wait-ForTaslation([int]$Id) {
    $p = Get-Process -Id $Id -ErrorAction SilentlyContinue
    if ($null -eq $p) { return }
    Write-Info "Waiting for TASlation (process $Id) to close ..."
    $done = $true
    try { $done = $p.WaitForExit($WaitForS * 1000) } catch { $done = $true }
    if (-not $done) { Stop-Update "TASlation (process $Id) did not close within $WaitForS seconds. Close it and run update.cmd again." }
}

# Whether the program files' Python runs: check_update.py needs it.
function Test-VenvPython {
    if (-not (Test-Path -LiteralPath $VenvPy)) { return $false }
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $ok = $false
    try {
        $out = @(& $VenvPy -I -c 'print(6 * 7)' 2>$null)
        $ok = ($LASTEXITCODE -eq 0) -and ((($out | ForEach-Object { "$_" }) -join '').Trim() -eq '42')
    } catch {
        $ok = $false
    } finally {
        $ErrorActionPreference = $old
    }
    return $ok
}

# What check_update.py says of the newest version on GitHub (its one line of JSON); $null when it gave none.
function Invoke-Check {
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = @(& $VenvPy -I $CheckScript check 2>$null)
    } catch {
        $out = @()
    } finally {
        $ErrorActionPreference = $old
    }
    $line = @($out | ForEach-Object { "$_".Trim() } | Where-Object { $_.StartsWith('{') }) | Select-Object -Last 1
    if (-not $line) { return $null }
    try { return ($line | ConvertFrom-Json) } catch { return $null }
}

# The ZIP of *Target* downloaded by check_update.py into a temporary folder of its own (its progress on the console);
# $null when it did not come.
function Invoke-Download([string]$Target) {
    $script:DownloadDir = Join-Path ([IO.Path]::GetTempPath()) ('taslation-download-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
    $null = New-Item -ItemType Directory -Path $script:DownloadDir -Force
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $code = -1
    try {
        $null = & $VenvPy -I $CheckScript download --version $Target --to $script:DownloadDir
        $code = $LASTEXITCODE
    } catch {
        Write-Info "check_update.py did not run: $($_.Exception.Message)"
    } finally {
        $ErrorActionPreference = $old
    }
    $zip = Join-Path $script:DownloadDir "taslation-$Target.zip"
    if ($code -ne 0 -or -not (Test-Path -LiteralPath $zip -PathType Leaf)) { return $null }
    return $zip
}

# The newest version on GitHub (or -Version), agreed to and downloaded: the ZIP's path. $script:Announced is the
# version it must hold.
function Get-FromGitHub {
    if ($IsClone) { Stop-Update 'this folder is a git clone: update it with git (git pull), not from GitHub''s ZIP.' }
    $nowText = Get-VersionText $Root
    $now = ConvertTo-Version $nowText
    if ($null -eq $now) { Stop-Update "the version of this TASlation could not be read from pyproject.toml ($nowText)." }
    if ($DryRun) {
        if ($Version) {
            Write-Plan "take version $Version, without asking GitHub which is the newest (only if it is newer than $nowText)"
        } else {
            Write-Plan "ask GitHub for the newest version: .venv\Scripts\python.exe -I check_update.py check (one small file, CHANGELOG.md)"
            Write-Plan 'show both versions and what changed'
        }
        if (-not $Confirmed) { Write-Plan "ask: Update this TASlation from $nowText to <that version>?" }
        Write-Plan 'download its ZIP into a temporary folder: .venv\Scripts\python.exe -I check_update.py download --version <that version> --to <that folder>'
        Write-Plan 'check that the ZIP holds that version, then update from it as with -From:'
        Write-Plan 'keep the files the update replaces or deletes in .previous, with a note of this version (update.cmd -Back)'
        Write-Plan 'copy the new files over these and run install.ps1'
        if ($Restart) { Write-Plan "start TASlation again when the installation got to its end: .venv\Scripts\pythonw.exe -m taslation gui" }
        Write-Host ''
        Write-Host 'Dry run finished; nothing was changed.' -ForegroundColor Cyan
        Exit-Update 0
    }
    if (-not (Test-Path -LiteralPath $CheckScript)) { Stop-Update 'check_update.py is not in this folder. Download the ZIP yourself and give it to update.cmd.' }
    if (-not (Test-VenvPython)) { Stop-Update 'looking on GitHub needs the program files'' Python (.venv\Scripts\python.exe), which does not run here. Download the ZIP yourself and give it to update.cmd.' }
    $target = $Version
    $asked = $false
    if (-not $target) {
        Write-Info 'Asking GitHub for the newest version (one small file) ...'
        $answer = Invoke-Check
        if ($null -eq $answer) { Stop-Update 'check_update.py gave no answer. Download the ZIP yourself and give it to update.cmd.' }
        if ("$($answer.result)" -eq 'could not ask') {
            Stop-Update "GitHub could not be asked: $($answer.reason) Download the ZIP yourself and give it to update.cmd."
        }
        Write-Info "this one:   $nowText"
        Write-Info "the newest: $($answer.newest), of $($answer.date)"
        if ("$($answer.result)" -ne 'newer') {
            Write-Host ''
            Write-Host 'This TASlation is the newest version. Nothing was changed.' -ForegroundColor Cyan
            Exit-Update 0
        }
        Write-Info 'What changed since this one:'
        foreach ($line in ("$($answer.changes)" -split "`n")) { Write-Host "    $line" }
        $target = "$($answer.newest)"
        if (-not $Confirmed -and -not (Confirm-Choice "Update this TASlation from $nowText to ${target}?" $true)) {
            Write-Host ''
            Write-Host 'Nothing was changed.'
            Exit-Update 1
        }
        $asked = $true
    }
    $next = ConvertTo-Version $target
    if ($null -eq $next) { Stop-Update "$target is no version number (X.Y.Z)." }
    if ($next -le $now) { Stop-Update "TASlation $target is not newer than this one ($nowText): there is nothing to update." }
    if (-not $asked -and -not $Confirmed -and -not (Confirm-Choice "Update this TASlation from $nowText to ${target}?" $true)) {
        Write-Host ''
        Write-Host 'Nothing was changed.'
        Exit-Update 1
    }
    Write-Step "Downloading TASlation $target from GitHub"
    $zip = Invoke-Download $target
    if (-not $zip) { Stop-Update 'the ZIP did not download (what went wrong is said above). Download it yourself and give it to update.cmd.' }
    Write-Ok 'downloaded'
    $script:Announced = $target
    return $zip
}

# A path the note of .previous names: inside this folder, never one of the kept names.
function Test-SafePath([string]$Rel) {
    if (-not $Rel -or [IO.Path]::IsPathRooted($Rel) -or $Rel.Contains('/') -or $Rel.Contains(':')) { return $false }
    $parts = $Rel -split '\\'
    if ($parts -contains '..' -or $parts -contains '.' -or $parts -contains '') { return $false }
    return -not ($KeptNames -contains $parts[0])
}

# The files the update replaces or deletes (*Replaced*) kept in .previous, with a note of this version and of the
# files it adds (*Added*), so that -Back can put this version back. One earlier version only: the last one goes.
function Save-Previous([string[]]$Replaced, [string[]]$Added, $Now, [string]$NextVersion) {
    if (Test-Path -LiteralPath $Previous) { Remove-Item -LiteralPath $Previous -Recurse -Force }
    $null = New-Item -ItemType Directory -Path $PreviousFiles -Force
    foreach ($rel in $Replaced) {
        $target = Join-Path $PreviousFiles $rel
        $folder = Split-Path -Parent $target
        if (-not (Test-Path -LiteralPath $folder)) { $null = New-Item -ItemType Directory -Path $folder -Force }
        Copy-Item -LiteralPath (Join-Path $Root $rel) -Destination $target -Force
    }
    $when = Get-Date -Format 'yyyy-MM-dd HH:mm'
    $lines = @("TASlation $($Now.Text), kept on $when before the update to $NextVersion.",
               'update.cmd -Back puts these files back and deletes the files that update added.',
               "version: $($Now.Version)", "kept: $when", "to: $NextVersion")
    foreach ($rel in $Added) { $lines += "added: $rel" }
    Set-Content -LiteralPath $PreviousNote -Value $lines -Encoding UTF8
}

# The note of .previous: the version kept, when, before which update, the files that update added; $null for none.
function Read-PreviousNote {
    if (-not (Test-Path -LiteralPath $PreviousNote -PathType Leaf) -or -not (Test-Path -LiteralPath $PreviousFiles)) { return $null }
    $note = [pscustomobject]@{ Version = ''; Kept = ''; To = ''; Added = @() }
    foreach ($line in Get-Content -LiteralPath $PreviousNote -Encoding UTF8) {
        if ($line -notmatch '^(version|kept|to|added): (.+)$') { continue }
        $key = $Matches[1]
        $value = $Matches[2].Trim()
        if ($key -eq 'version') { $note.Version = $value }
        elseif ($key -eq 'kept') { $note.Kept = $value }
        elseif ($key -eq 'to') { $note.To = $value }
        elseif (Test-SafePath $value) { $note.Added += $value }
    }
    if (-not $note.Version) { return $null }
    return $note
}

# How to go back, after an update that did not get to its end or a TASlation that does not start after it.
function Write-GoBack {
    $note = Read-PreviousNote
    if ($null -eq $note) { return }
    Write-Host ''
    Write-Host "To go back to TASlation $($note.Version), close this window and run this in a Command Prompt:"
    Write-Host "  `"$(Join-Path $Root 'update.cmd')`" -Back"
    Write-Host 'It puts back the program files kept in the folder .previous.'
}

# Folders that held only files now deleted (and Python's cache of them) removed, up to this folder.
function Remove-EmptyFolders([string[]]$Rels) {
    $folders = @($Rels | ForEach-Object { Split-Path -Parent $_ } | Where-Object { $_ } | Sort-Object -Unique |
        Sort-Object -Property Length -Descending)
    foreach ($rel in $folders) {
        $parts = @($rel -split '\\')
        for ($n = $parts.Count; $n -ge 1; $n--) {
            $dir = Join-Path $Root ($parts[0..($n - 1)] -join '\')
            if (-not (Test-Path -LiteralPath $dir -PathType Container)) { continue }
            $left = @(Get-ChildItem -LiteralPath $dir -Force | Where-Object { $_.Name -ne '__pycache__' })
            if ($left.Count -gt 0) { break }
            Remove-Item -LiteralPath $dir -Recurse -Force
        }
    }
}

# TASlation started as its Start-menu shortcut starts it; whether it did not end at once with an error.
function Start-Taslation {
    Write-Step 'Starting TASlation again'
    if ($DryRun) { Write-Plan '.venv\Scripts\pythonw.exe -m taslation gui, in this folder'; return $true }
    if (-not (Test-Path -LiteralPath $VenvPyw)) {
        Write-Host '  TASlation could not be started: .venv\Scripts\pythonw.exe is not there.' -ForegroundColor Red
        return $false
    }
    try {
        $p = Start-Process -FilePath $VenvPyw -ArgumentList '-m taslation gui' -WorkingDirectory $Root -PassThru
        $null = $p.Handle
    } catch {
        Write-Host "  TASlation could not be started: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
    if ($p.WaitForExit($StartWatchS * 1000) -and $p.ExitCode -ne 0) {
        Write-Host "  TASlation did not start: it ended at once (exit code $($p.ExitCode))." -ForegroundColor Red
        return $false
    }
    Write-Ok 'TASlation started'
    return $true
}

# -Back: the version kept in .previous put back.
function Invoke-Back {
    Write-Step 'Going back to the earlier version'
    if ($IsClone) { Stop-Update 'this folder is a git clone: go back to an earlier version with git (git checkout), not with -Back.' }
    $note = Read-PreviousNote
    if ($null -eq $note) { Stop-Update 'no earlier version is kept here (no .previous folder from an update): there is nothing to go back to.' }
    $kept = Get-Files $PreviousFiles
    $added = @($note.Added | Where-Object { Test-Path -LiteralPath (Join-Path $Root $_) -PathType Leaf } | Sort-Object)
    $now = Get-VersionLine $Root
    Write-Info "this one: $($now.Text)"
    Write-Info "kept:     $($note.Version), kept on $($note.Kept) before the update to $($note.To)"
    Write-Info ("{0} files to put back; {1} files that update added to delete." -f $kept.Count, $added.Count)
    Write-Info 'Kept as they are: taslation.toml, .venv (what the newer version installed into it stays), models and your data folder.'
    if (-not $Confirmed -and -not (Confirm-Choice "Go back to TASlation $($note.Version)?" $true)) {
        Write-Host ''
        Write-Host 'Nothing was changed.'
        Exit-Update 1
    }
    if ($DryRun) {
        foreach ($rel in ($kept.Keys | Sort-Object)) { Write-Plan "put back $rel" }
        foreach ($rel in $added) { Write-Plan "delete $rel" }
        Write-Plan 'remove the folder .previous'
        if ($Restart) { Write-Plan 'start TASlation again: .venv\Scripts\pythonw.exe -m taslation gui' }
        Write-Host ''
        Write-Host 'Dry run finished; nothing was changed.' -ForegroundColor Cyan
        Exit-Update 0
    }
    $done = 0
    try {
        foreach ($rel in ($kept.Keys | Sort-Object)) {
            $target = Join-Path $Root $rel
            $folder = Split-Path -Parent $target
            if (-not (Test-Path -LiteralPath $folder)) { $null = New-Item -ItemType Directory -Path $folder -Force }
            Copy-Item -LiteralPath $kept[$rel] -Destination $target -Force
            $done++
        }
        foreach ($rel in $added) { Remove-Item -LiteralPath (Join-Path $Root $rel) -Force }
        Remove-EmptyFolders $added
    } catch {
        Write-Host "  error: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "  $done files were put back before it stopped; .previous is kept. Close what uses this folder and run update.cmd -Back again." -ForegroundColor Red
        Exit-Update 1
    }
    Remove-Item -LiteralPath $Previous -Recurse -Force -ErrorAction SilentlyContinue
    Write-Ok "$done files put back, $($added.Count) deleted; .previous removed"
    Write-Host ''
    Write-Host "TASlation is back at $($note.Version)." -ForegroundColor Cyan
    Write-Info 'What the newer version''s installation added to .venv stays. If TASlation does not start, run install.cmd.'
    if ($Restart -and -not (Start-Taslation)) { Exit-Update 1 }
    Exit-Update 0
}

# ---------------------------------------------------------------- start
Write-Host 'TASlation update' -ForegroundColor Cyan
Push-Location -LiteralPath $Root
Write-Host "  folder: $Root"
if ($DryRun) { Write-Host '  DRY RUN: nothing is copied, deleted, run or asked of GitHub.' -ForegroundColor DarkYellow }
if (-not (Test-Copy $Root)) { Stop-Update 'this folder holds no TASlation to update. Run update.cmd in the TASlation folder.' }
$ways = 0
foreach ($way in @([bool]$From, [bool]$Download, [bool]$Back)) { if ($way) { $ways++ } }
if ($ways -gt 1) { Stop-Update 'give one of -From, -Download and -Back.' }
if ($Version -and -not $Download) { Stop-Update '-Version goes with -Download.' }
if ($Version -and $null -eq (ConvertTo-Version $Version)) { Stop-Update "-Version must be written X.Y.Z (digits only), not $Version." }
$script:Announced = ''

# Python running from the environment (the window, a batch) runs the old files: it is closed first. A TASlation that
# closes for this update (-WaitFor) is waited for; the launcher of its Python ends a moment after it.
if ($WaitFor -gt 0) {
    if ($DryRun) { Write-Plan "wait up to $WaitForS seconds for TASlation (process $WaitFor) to close" } else { Wait-ForTaslation $WaitFor }
}
$running = @(Get-Running)
if ($WaitFor -gt 0 -and -not $DryRun) {
    for ($i = 0; $i -lt 10 -and $running.Count -gt 0; $i++) { Start-Sleep -Milliseconds 500; $running = @(Get-Running) }
}
if ($running.Count -gt 0 -and -not $DryRun) {
    $list = ($running | ForEach-Object { "$($_.ProcessName) (pid $($_.Id))" }) -join ', '
    Stop-Update "TASlation is running from this folder: $list. Close it (and any batch) and run update.cmd again."
}

if ($Back) { Invoke-Back }

Write-Step 'The new copy'
$fromGitHub = [bool]$Download
if (-not $Download -and -not $From -and $Interactive -and -not $Yes -and -not $DryRun) {
    if ($IsClone) {
        Write-Info 'This folder is a git clone: update it with git (git pull), or give a copy you downloaded yourself.'
    } elseif (-not (Test-Path -LiteralPath $CheckScript) -or -not (Test-VenvPython)) {
        Write-Info 'Looking on GitHub needs the program files'' Python (.venv), which does not run here: give a copy you downloaded yourself.'
    } else {
        $fromGitHub = Confirm-Choice 'Look on GitHub for the newest version and download it?'
    }
}
if ($fromGitHub) { $source = Get-FromGitHub } else { $source = Get-Source }
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
if ($script:Announced -and $next.Version -ne $script:Announced) {
    Stop-Update "the ZIP from GitHub holds version $($next.Version), not $($script:Announced) as GitHub said."
}
$older = ($null -ne $now.Date) -and ($null -ne $next.Date) -and ($next.Date.Date -lt $now.Date.Date)
if ($older) { Write-Info 'The new copy is OLDER than this one.' }

$newFiles = Get-Files $new
$oldFiles = @{}
foreach ($pair in (Get-Files $Root).GetEnumerator()) {
    if ($pair.Key -like 'taslation\*') { $oldFiles[$pair.Key] = $pair.Value }
}
$gone = @($oldFiles.Keys | Where-Object { -not $newFiles.ContainsKey($_) } | Sort-Object)
$replaced = @(@($newFiles.Keys | Where-Object { Test-Path -LiteralPath (Join-Path $Root $_) -PathType Leaf }) + $gone | Sort-Object)
$added = @($newFiles.Keys | Where-Object { -not (Test-Path -LiteralPath (Join-Path $Root $_)) } | Sort-Object)
# The same version again (an update that stopped, run again): the earlier version kept stays the one to go back to.
$keepPrevious = ($now.Version -ne $next.Version)
Write-Info ("{0} files to copy over these; {1} program files the new version no longer has to delete." -f $newFiles.Count, $gone.Count)
Write-Info 'Kept as they are: taslation.toml, .venv, models and your data folder.'
if ($keepPrevious) {
    Write-Info ("The {0} files it replaces or deletes are kept in the folder .previous first (update.cmd -Back goes back to {1})." -f $replaced.Count, $now.Version)
} else {
    Write-Info 'The new copy is the same version as this one: the earlier version kept in .previous, if any, stays as it is.'
}
if (-not $fromGitHub -and -not $Confirmed -and -not (Confirm-Choice "Update this TASlation to $($next.Text)?" (-not $older))) {
    Write-Host ''
    Write-Host 'Nothing was changed.'
    Exit-Update 1
}

Write-Step 'Copying'
if ($DryRun) {
    if ($keepPrevious) {
        Write-Plan ("keep the {0} files it replaces or deletes in .previous, with a note of {1} and of the {2} files it adds (the .previous of an earlier update goes)" -f $replaced.Count, $now.Version, $added.Count)
    }
    foreach ($rel in ($newFiles.Keys | Sort-Object)) { Write-Plan "copy $rel" }
    foreach ($rel in $gone) { Write-Plan "delete $rel" }
    Write-Plan 'run install.ps1'
    if ($Restart) { Write-Plan 'start TASlation again when the installation got to its end: .venv\Scripts\pythonw.exe -m taslation gui' }
    Write-Host ''
    Write-Host 'Dry run finished; nothing was changed.' -ForegroundColor Cyan
    Exit-Update 0
}
if ($keepPrevious) {
    try {
        Save-Previous $replaced $added $now $next.Version
    } catch {
        $why = $_.Exception.Message
        Remove-Item -LiteralPath $Previous -Recurse -Force -ErrorAction SilentlyContinue
        Stop-Update "the files of this version could not be kept in .previous: $why"
    }
    Write-Ok "$($replaced.Count) files of $($now.Version) kept in .previous"
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
    if ($fromGitHub) { $script:KeepDownload = $true; Write-Host "  The ZIP downloaded from GitHub is kept for it: $source" }
    Write-GoBack
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
if ($code -ne 0) {
    if ($fromGitHub) {
        $script:KeepDownload = $true
        Write-Host ''
        Write-Host "The ZIP downloaded from GitHub is kept for that: $source"
    }
    if ($Restart) { Write-Host 'TASlation is not started again: the installation did not get to its end.' }
    Write-GoBack
    Exit-Update $code
}
if ($Restart -and -not (Start-Taslation)) {
    Write-GoBack
    Exit-Update 1
}
Exit-Update 0
