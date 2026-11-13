<#
.SYNOPSIS
Installs TASlation in this folder: its program files, the OCR model and fonts,
and (when you agree) Python, Ollama and the translation model: PLaMo 3
Translate 2B (PLaMo Community License, which you are asked to agree to), or
Qwen3.5 4B for Portuguese (Brazil) and Turkish.
TASlation cannot read pages without the OCR model, whose licence you are asked
to agree to first: it is for non-commercial use only (CC BY-NC-SA 4.0).

.DESCRIPTION
Unpack the ZIP of the repository (a git clone works the same) and double-click
install.cmd, which runs this script; no administrator rights are needed. From a
PowerShell window:

    powershell -ExecutionPolicy Bypass -File install.ps1

Every question comes first: the language you translate into (it decides the
translation model), the licences, then what to install. The downloads follow
without another question, so you can leave it running. The questions are in
this PC's display language where installer-texts.json has it (Japanese for
now; more can be added there), else in English.

It can be run again at any time: what is already in place is checked and kept.
It writes into this folder (.venv and models) and makes one Start-menu shortcut,
plus what you agree to: Python and Ollama (installed by winget into your user
profile) and the translation model (into Ollama's model folder).
Two more changes have no question. Each is made only when its variable is not
set already (for your user or in this window), and Ollama then restarts once:
  * on every computer with Ollama it sets LLAMA_ARG_CACHE_RAM=0 for your user.
    Ollama otherwise keeps up to 8 GB of RAM as a cache of earlier requests. In
    TASlation's measurements that cache made translation no faster with a GPU,
    and about 8 % faster without one. It applies to the Ollama you run and to
    any other program of yours that reads llama.cpp's LLAMA_ARG_* variables. It
    leaves the file .cache-ram-by-install in this folder;
  * on an NVIDIA GPU of 6 GB or less it sets OLLAMA_KV_CACHE_TYPE=q8_0 for your
    user, and leaves the file .kv-cache-by-install in this folder.
uninstall.cmd then clears each variable if it still has that value. To undo one
by hand, delete it in "Edit environment variables for your account" (search
the Start menu for that) and restart Ollama.
Your data folder (~/.taslation) is created later by TASlation itself; only a
language you choose other than the one offered is written into its ui.json
first, for the window to start with.

What it downloads, and from where:
  * Python 3.13 with winget, about 30 MB, only when no Python 3.11 or newer is
    found and after your Y (which also accepts the terms winget shows for it);
  * Python packages from PyPI (pypi.org), and PyTorch from download.pytorch.org:
    on a computer with an NVIDIA GPU its GPU build (about 2.6 GB; about 2.0 GB
    for the newest GPUs), tried on the GPU once installed, with the CPU build
    instead when it does not work there; else its CPU build (about 0.13 GB);
  * the three OCR models from Hugging Face, about 700 MB, once you have agreed
    to their licence, and the OFL fonts from the google/fonts repository on GitHub (by setup_models.py);
  * the layout and inpainting models from Hugging Face (about 170 and 200 MB),
    after your yes: Enter is yes on a computer with an NVIDIA GPU, which the
    GPU build runs on, and no on one without;
  * Ollama with winget, only after your Y (which also accepts winget's terms);
  * the translation model for the language you translate into (the first
    question; taslation.toml decides it when it names one), only
    after your Y: PLaMo 3 Translate 2B from Hugging Face (one file, about
    1.8 GB, checked and imported into Ollama, then deleted) once you have
    agreed to its licence, or for Portuguese (Brazil) and Turkish Qwen3.5 4B
    with `ollama pull` (about 3.3 GB). Only one of the two is installed;
    TASlation offers the other when you change the language.
TASlation itself never uses the network after this.

The GPU is what nvidia-smi, which comes with NVIDIA's driver, says of it;
nothing is fetched to find it, and there is no question about it. AMD and
Intel GPUs count as none (PyTorch's GPU build runs only on NVIDIA's). A CUDA
build of PyTorch already installed is kept; a CPU build on a computer with an
NVIDIA GPU is replaced by the GPU build, except in the run after update.cmd,
which keeps it and says how to get the GPU build.

.PARAMETER Yes
For unattended runs and checks; install.cmd asks instead. Takes the language
offered and answers Y to the questions for Python, Ollama and the Qwen
translation model (a Y there accepts winget's agreements for Python and Ollama,
as a person's does). It never answers the question about the layout and
inpainting models, and never agrees to the OCR models'
licence nor to PLaMo's, which take a person: without the OCR models the run
stops, without PLaMo it goes on without a translation model. Too little disk
space also stops it.

.PARAMETER DryRun
For checks: look at everything and print what would be done, with the details
a normal run leaves out; change nothing.
#>
[CmdletBinding()]
param(
    [switch]$Yes,
    [switch]$DryRun
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

# A folder or user name outside the ANSI code page: Python prints paths into our pipes in that code page unless told
# otherwise, and fails on them. UTF-8 on both ends of the pipe; the console's own setting comes back in Exit-Install.
$env:PYTHONUTF8 = '1'
$script:ConsoleEncoding = $null
try {
    $script:ConsoleEncoding = [Console]::OutputEncoding
    [Console]::OutputEncoding = [Text.Encoding]::UTF8
} catch { $script:ConsoleEncoding = $null }

# ---------------------------------------------------------------- constants
$Root = $PSScriptRoot
$Venv = Join-Path $Root '.venv'
$VenvPy = Join-Path $Venv 'Scripts\python.exe'
$VenvPyw = Join-Path $Venv 'Scripts\pythonw.exe'
$Icon = Join-Path $Root 'taslation\ui\assets\taslation.ico'
$ShortcutPath = Join-Path ([Environment]::GetFolderPath('Programs')) 'TASlation.lnk'
$MinPython = [version]'3.11'
$PythonPage = 'https://www.python.org/downloads/windows/'
# --source winget: without it a first run asks to agree to the Microsoft Store's terms, which neither install needs.
# The agreements: the Y to the question accepts what winget would ask about (the question says so), so that winget
# asks nothing in the middle of the downloads, when nobody may be watching. Not tried on a fresh PC.
$WingetAgreements = @('--accept-source-agreements', '--accept-package-agreements')
$PythonWingetArgs = @('install', '--id', 'Python.Python.3.13', '--exact', '--source', 'winget', '--scope', 'user') + $WingetAgreements
$OllamaWingetArgs = @('install', '--id', 'Ollama.Ollama', '--exact', '--source', 'winget') + $WingetAgreements
# winget does not refresh this process's PATH, so the folder it installs into is looked at directly.
$PythonUserExe = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'
$OllamaPage = 'https://ollama.com/download'
$OllamaUrl = 'http://127.0.0.1:11434'
$TorchCpuIndex = 'https://download.pytorch.org/whl/cpu'
# The GPU builds of PyTorch, from the same index (NVIDIA's CUDA libraries come inside the wheel), by the compute
# capability a GPU reaches (nvidia-smi's compute_cap): cu126 runs on every NVIDIA GPU from Maxwell (5.0) to Hopper and
# Ada with a driver of the CUDA 12 generation (528.33 or newer: CUDA's minor version compatibility), and torch 2.14 is
# its last release; Blackwell (10.0 and up) has kernels only in the CUDA 12.8 and newer builds: cu130, whose driver
# must be of the 580 branch or newer (CUDA 13). Measured on the index for torch 2.14.1, Python 3.13 (the CPU build is
# 2.15.0): download and unpacked, cu126 2.60 / 4.19 GB, cu130 1.99 / 3.02 GB, CPU 0.13 / 0.48 GB.
$TorchCudaBuilds = @(
    [pscustomobject]@{ Index = 'https://download.pytorch.org/whl/cu126'; FromCompute = [version]'5.0'; MinDriver = '528.33';
                       DownloadGB = 2.6; UnpackedGB = 4.2 },
    [pscustomobject]@{ Index = 'https://download.pytorch.org/whl/cu130'; FromCompute = [version]'10.0'; MinDriver = '580.00';
                       DownloadGB = 2.0; UnpackedGB = 3.0 })
$TorchCpuDownloadGB = 0.13
$TorchCpuUnpackedGB = 0.48
# Run by update.ps1: an update keeps the program files' PyTorch as it is, a CPU build on a computer with an NVIDIA GPU
# too (install.cmd replaces that), so that an update never starts the GPU build's download unasked. update.ps1 says so
# in TASLATION_UPDATING; the update.cmd of the versions before it sets only TASLATION_UPDATE_PAUSE, and nothing else
# sets either.
$FromUpdate = [bool]($env:TASLATION_UPDATING -or $env:TASLATION_UPDATE_PAUSE)
# Sizes measured on the development machine, in GB.
$SizePython = 0.2
$SizeVenvCpu = 1.3
$SizeModels = 1.2
$SizeOllama = 3.0
$SizeLlm = 3.3
$SizePlamo = 1.8
# The translator models (taslation/translate/models.py): PLaMo for every language but these (spelt as
# QWEN_LANGUAGES spells them, lower case), which take Qwen ...
$PlamoName = 'taslation-plamo3-translate-2b'
$QwenName = 'qwen3.5:4b'
$QwenLanguages = @('brazilian portuguese', 'portuguese', 'portuguese (brazil)', 'portuguese (brazilian)', 'pt', 'pt-br', 'tr', 'turkish')
# ... and the ones PLaMo writes (its codes too); a language in neither list goes to Qwen, as in models.py.
$PlamoLanguages = @(
    'ar', 'arabic', 'armenian', 'az', 'azerbaijani', 'basque', 'be', 'belarusian', 'bengali', 'bg', 'bn',
    'bulgarian', 'burmese', 'ca', 'catalan', 'ceb', 'cebuano', 'chinese', 'chinese (simplified)',
    'chinese (traditional)', 'croatian', 'de', 'dutch', 'en', 'english', 'es', 'estonian', 'et', 'eu', 'fa', 'fr',
    'french', 'georgian', 'german', 'gu', 'gujarati', 'he', 'hebrew', 'hi', 'hindi', 'hr', 'hu', 'hungarian', 'hy',
    'id', 'indonesian', 'it', 'italian', 'ja', 'japanese', 'javanese', 'jv', 'ka', 'kazakh', 'khmer', 'kk', 'km',
    'ko', 'korean', 'latvian', 'lithuanian', 'lt', 'lv', 'malay', 'malayalam', 'marathi', 'ml', 'mr', 'ms', 'my',
    'ne', 'nepali', 'nl', 'pa', 'persian', 'pl', 'polish', 'punjabi', 'ru', 'russian', 'serbian', 'si',
    'simplified chinese', 'sinhala', 'sk', 'sl', 'slovak', 'slovenian', 'spanish', 'sr', 'sw', 'swahili', 'ta',
    'tagalog', 'tamil', 'te', 'telugu', 'th', 'thai', 'tl', 'traditional chinese', 'ur', 'urdu', 'uz', 'uzbek',
    'vi', 'vietnamese', 'zh-hans', 'zh-hant')
# The window's target languages (taslation/ui/constants.py LANGUAGES), offered by number in the first question.
$WindowLanguages = @('English', 'Spanish', 'Portuguese (Brazil)', 'French', 'German', 'Italian', 'Russian', 'Polish',
    'Dutch', 'Turkish', 'Indonesian', 'Vietnamese', 'Thai', 'Chinese (Simplified)', 'Chinese (Traditional)', 'Korean',
    'Arabic', 'Hebrew', 'Hindi', 'Bengali')
# The questions in this PC's language: the English text, then its translation by TASlation's language code (T).
$TextsFile = Join-Path $Root 'installer-texts.json'
$script:Texts = $null
$script:TextLanguage = ''
$PlamoLicenceUrls = @('https://plamo.preferredai.jp/info/plamo-community-license-en',
                      'https://plamo.preferredai.jp/info/plamo-community-license-ja')
$Interactive = (-not [Console]::IsInputRedirected) -and [Environment]::UserInteractive
# The longest file in .venv has 154 characters (a licence file in torch 2.15.0's CPU build; 151 in 2.14.1's GPU
# builds), and without long paths enabled Windows opens no path of 260 characters or more. Four are kept spare, as
# the licence folders of a later torch may be deeper.
$MaxRootLength = 100
# Say that this install set OLLAMA_KV_CACHE_TYPE and LLAMA_ARG_CACHE_RAM: uninstall.ps1 clears only what the install
# set (update.ps1 never copies them over).
$KvMarker = Join-Path $Root '.kv-cache-by-install'
$CacheRamMarker = Join-Path $Root '.cache-ram-by-install'
$StepCount = 7
$script:StepNo = 0
$script:Warnings = New-Object System.Collections.Generic.List[string]
$script:LastCommand = $null

# ---------------------------------------------------------------- helpers
function Write-Step([string]$Text) {
    $script:StepNo++
    Write-Host ''
    Write-Host ('[{0}/{1}] {2}' -f $script:StepNo, $StepCount, $Text) -ForegroundColor Cyan
}
function Write-Ok([string]$Text) { Write-Host "  ok: $Text" -ForegroundColor Green }
function Write-Info([string]$Text) { Write-Host "  $Text" }
function Write-Warn([string]$Text) {
    $script:Warnings.Add($Text)
    Write-Host "  warning: $Text" -ForegroundColor Yellow
}
function Write-Plan([string]$Text) { Write-Host "  dry run, would: $Text" -ForegroundColor DarkYellow }
# A text of the questions in this PC's language (Read-InstallerTexts), else as it is. Always called in parentheses, with
# the English text itself: the tests check installer-texts.json against these calls.
function T([string]$Text) {
    try {
        $value = $script:Texts.PSObject.Properties[$Text].Value.PSObject.Properties[$script:TextLanguage].Value
        if ($value) { return [string]$value }
    } catch { }
    return $Text
}
# What a reader need not see; a dry run shows it. A failure shows the command that failed (Stop-Install).
function Write-Detail([string]$Text) { if ($DryRun) { Write-Host "  detail: $Text" -ForegroundColor DarkGray } }
function Exit-Install([int]$Code) {
    if ($script:ConsoleEncoding) { try { [Console]::OutputEncoding = $script:ConsoleEncoding } catch { } }
    Pop-Location
    exit $Code
}
function Stop-Install([string]$Text) {
    Write-Host "  error: $Text" -ForegroundColor Red
    if ($script:LastCommand) { Write-Host "  last command: $($script:LastCommand)" }
    Write-Host ''
    Write-Host 'Installation stopped. Fix the above and run install.cmd again; what is done is kept.'
    Exit-Install 1
}

# Asks a yes/no question; -Yes, a dry run and a run without a console answer it without a prompt.
# With -DefaultYes a plain Enter means yes and a dry run counts a yes; without a console it is still no: nobody agreed.
function Confirm-Choice([string]$Question, [bool]$DefaultYes = $false) {
    $hint = '[y/N]'
    $counted = 'n'
    if ($DefaultYes) { $hint = '[Y/n]'; $counted = 'y' }
    if ($Yes) { Write-Info "$Question $hint y (-Yes)"; return $true }
    if ($DryRun) { Write-Info "$Question $hint (dry run: would ask; counted as $counted)"; return $DefaultYes }
    if (-not $Interactive) { Write-Info "$Question $hint n (no console to ask)"; return $false }
    $answer = Read-Host "  $Question $hint"
    # also what a Japanese input method gives: full-width y and yes, hai
    $words = 'y|yes|\uFF59|\uFF59\uFF45\uFF53|\u306F\u3044'
    if ($DefaultYes) { return ($answer -match "^\s*($words)?\s*$") }
    return ($answer -match "^\s*($words)\s*$")
}

# Runs a program and returns its exit code and output lines (stderr included) without stopping on stderr.
function Invoke-Captured([string]$Exe, [string[]]$Arguments) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = & $Exe @Arguments 2>&1 | ForEach-Object { "$_" }
        $code = $LASTEXITCODE
    } catch {
        $out = @("$_")
        $code = -1
    } finally {
        $ErrorActionPreference = $old
    }
    if ($null -eq $code) { $code = 0 }
    return [pscustomobject]@{ Code = $code; Out = @($out) }
}

# One command line: Start-Process joins its arguments with spaces and quotes nothing.
function Join-Arguments([string[]]$Arguments) {
    $quoted = foreach ($a in $Arguments) {
        if ($a -and $a -notmatch '[\s"]') { $a }
        else { '"' + (($a -replace '(\\*)"', '$1$1\"') -replace '(\\+)$', '$1$1') + '"' }
    }
    return ($quoted -join ' ')
}

# Runs a program straight on the console, so that a prompt or a progress bar is seen as it comes. Returns the exit code.
# Start-Process -Wait would not do: Windows PowerShell 5.1 then waits for every descendant too, and Ollama's installer
# leaves the tray app running. The handle has to be taken for ExitCode to be there after the wait.
function Invoke-Console([string]$Exe, [string[]]$Arguments) {
    $script:LastCommand = (Split-Path $Exe -Leaf) + ' ' + ($Arguments -join ' ')
    try {
        # a name on the PATH may be a .cmd, which the process start does not look for
        $found = @(Get-Command -Name $Exe -CommandType Application -ErrorAction SilentlyContinue)
        if ($found.Count -gt 0) { $Exe = $found[0].Source }
        $p = Start-Process -FilePath $Exe -ArgumentList (Join-Arguments $Arguments) -NoNewWindow -PassThru
        $null = $p.Handle
        $p.WaitForExit()
        return $p.ExitCode
    } catch {
        Write-Info "could not run $Exe`: $_"
        return -1
    }
}

function Get-PythonInfo([string[]]$Command) {
    $exe = $Command[0]
    $rest = @($Command | Select-Object -Skip 1)
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { return $null }
    $r = Invoke-Captured $exe ($rest + @('-c', "import sys; print('%d.%d.%d' % sys.version_info[:3]); print(sys.executable)"))
    if ($r.Code -ne 0 -or $r.Out.Count -lt 2) { return $null }
    try { $v = [version]$r.Out[0].Trim() } catch { return $null }
    return [pscustomobject]@{ Command = $Command; Version = $v; Exe = $r.Out[1].Trim() }
}

# The first Python new enough among `py -3`, `python` and the folder winget installs into; $null when there is none.
function Find-BasePython {
    foreach ($candidate in @(@('py', '-3'), @('python'), @($PythonUserExe))) {
        $info = Get-PythonInfo $candidate
        if ($null -eq $info) { continue }
        if ($info.Version -lt $MinPython) {
            Write-Info "found Python $($info.Version), too old"
            continue
        }
        return $info
    }
    return $null
}

function Get-TomlValue([string]$Key) {
    $toml = Join-Path $Root 'taslation.toml'
    if (-not (Test-Path -LiteralPath $toml)) { return $null }
    foreach ($line in Get-Content -LiteralPath $toml -Encoding UTF8) {
        if ($line -match ('^\s*' + $Key + '\s*=\s*["'']([^"'']+)["'']')) { return $Matches[1] }
    }
    return $null
}

function Get-StateDir {
    foreach ($name in @('TASLATION_STATE_DIR', 'SELFTRANS_STATE_DIR')) {
        $v = [Environment]::GetEnvironmentVariable($name)
        if ($v) { return $v }
    }
    $configured = Get-TomlValue 'state_dir'
    if ($configured) { return $configured }
    return (Join-Path $env:USERPROFILE '.taslation')
}

# This PC's display language, as 'pt-BR': the window's first start takes the target language from it.
function Get-UiCulture { try { return (Get-UICulture).Name } catch { return '' } }

# A display language such as 'ja-JP' or 'zh-Hant-TW' as TASlation's language code: 'ja', 'zh-tw'.
function Get-LanguageCode([string]$Culture) {
    $c = "$Culture".Trim().ToLowerInvariant()
    if (-not $c) { return '' }
    if ($c -match '^zh-(tw|hk|mo|hant)') { return 'zh-tw' }
    return ($c -split '-')[0]
}

# The target language the window starts with in this display language (taslation/ui/constants.py WINDOW_TARGETS);
# $null for one that has none (Japanese among them).
function Get-WindowTarget([string]$Culture) {
    $targets = @{
        'en' = 'English'; 'es' = 'Spanish'; 'pt' = 'Portuguese (Brazil)'; 'fr' = 'French'; 'de' = 'German';
        'it' = 'Italian'; 'ru' = 'Russian'; 'pl' = 'Polish'; 'nl' = 'Dutch'; 'tr' = 'Turkish'; 'id' = 'Indonesian';
        'vi' = 'Vietnamese'; 'th' = 'Thai'; 'zh' = 'Chinese (Simplified)'; 'zh-tw' = 'Chinese (Traditional)'; 'ko' = 'Korean' }
    $code = Get-LanguageCode $Culture
    if ($code -and $targets.ContainsKey($code)) { return $targets[$code] }
    return $null
}

# The questions' texts in this PC's display language, from installer-texts.json; English without it.
function Read-InstallerTexts {
    $script:TextLanguage = Get-LanguageCode (Get-UiCulture)
    $script:Texts = $null
    if (-not $script:TextLanguage -or $script:TextLanguage -eq 'en' -or -not (Test-Path -LiteralPath $TextsFile)) { return }
    try { $script:Texts = Get-Content -LiteralPath $TextsFile -Raw -Encoding UTF8 | ConvertFrom-Json } catch { $script:Texts = $null }
}

# The language offered for translating into: taslation.toml's, else the one last chosen in the window (ui.json),
# else the one the window starts with in this PC's language, else English.
function Get-TargetLanguage {
    $configured = Get-TomlValue 'target_language'
    if ($configured) { return [pscustomobject]@{ Name = $configured; Source = 'taslation.toml' } }
    $ui = Join-Path (Get-StateDir) 'ui.json'
    if (Test-Path -LiteralPath $ui) {
        try {
            $saved = (Get-Content -LiteralPath $ui -Raw -Encoding UTF8 | ConvertFrom-Json).translation.language
            if ($saved) { return [pscustomobject]@{ Name = [string]$saved; Source = 'the window' } }
        } catch { }
    }
    $pc = Get-WindowTarget (Get-UiCulture)
    if ($pc) { return [pscustomobject]@{ Name = $pc; Source = 'this PC' } }
    return [pscustomobject]@{ Name = 'English'; Source = 'built-in' }
}

# A language typed as an answer, as the window keeps it: a name of its list in that spelling, else a name another
# list here knows (not a code), else $null.
function Find-LanguageName([string]$Typed) {
    $key = (("$Typed" -split '\s+') | Where-Object { $_ }) -join ' '
    foreach ($name in $WindowLanguages) { if ($name -ieq $key) { return $name } }
    $known = @($PlamoLanguages + $QwenLanguages | Where-Object { $_.Length -gt 3 -and $_ -notmatch '-' })
    if ($known -contains $key.ToLowerInvariant()) { return (Get-Culture).TextInfo.ToTitleCase($key.ToLowerInvariant()) }
    return $null
}

# The first question: the language translated into, which decides the translation model (Get-Translator). The
# window's list by number, or a name; Enter takes the one offered. taslation.toml's is not asked about: the file
# decides. -Yes, a dry run and a run without a console take the one offered.
function Select-TargetLanguage($Offered) {
    if ($Offered.Source -eq 'taslation.toml') {
        Write-Info ((T 'Translating into {0} (set in taslation.toml).') -f $Offered.Name)
        return $Offered
    }
    $question = (T 'Translate into which language? A number or a name; Enter: {0}') -f $Offered.Name
    if ($Yes -or $DryRun -or -not $Interactive) {
        $why = 'no console to ask'
        if ($Yes) { $why = '-Yes' } elseif ($DryRun) { $why = 'dry run: would ask' }
        Write-Info "$question -> $($Offered.Name) ($why)"
        return $Offered
    }
    Write-Host ''
    Write-Info (T 'The language you translate into decides the translation model. The window lists these:')
    $half = [math]::Ceiling($WindowLanguages.Count / 2)
    for ($i = 0; $i -lt $half; $i++) {
        $line = ('    {0,2}. {1}' -f ($i + 1), $WindowLanguages[$i]).PadRight(34)
        if ($i + $half -lt $WindowLanguages.Count) { $line += '{0,2}. {1}' -f ($i + $half + 1), $WindowLanguages[$i + $half] }
        Write-Host $line
    }
    for ($try = 0; $try -lt 3; $try++) {
        $answer = Read-Host "  $question"
        $answer = "$answer".Trim()
        if (-not $answer) { return $Offered }
        $n = 0
        if ([int]::TryParse($answer, [ref]$n) -and $n -ge 1 -and $n -le $WindowLanguages.Count) {
            return [pscustomobject]@{ Name = $WindowLanguages[$n - 1]; Source = 'your answer' }
        }
        $named = Find-LanguageName $answer
        if ($named) { return [pscustomobject]@{ Name = $named; Source = 'your answer' } }
        Write-Info ((T '"{0}" is not a language TASlation knows. Type its number or its English name.') -f $answer)
    }
    Write-Info ((T 'Going on with {0}; the window can change it later.') -f $Offered.Name)
    return $Offered
}

# The language chosen kept for the window as its "To:" box keeps it (ui.json, by TASlation's own code), so that the
# window starts with the language whose model was installed. Whether it was kept.
function Save-TargetLanguage([string]$StateDir, [string]$Language) {
    if ($StateDir -match '[\\/]$' -and $StateDir -notmatch '^[A-Za-z]:\\$') { $StateDir = $StateDir.TrimEnd([char[]]'\/') }
    $code = 'import sys; from taslation.i18n import save_ui_entry; save_ui_entry(sys.argv[1], ''translation'', ''language'', sys.argv[2])'
    $r = Invoke-Captured $VenvPy @('-c', $code, $StateDir, $Language)
    return ($r.Code -eq 0)
}

# The translator model a language needs (as taslation.translate.models.model_for_language decides).
function Get-Translator([string]$Language) {
    $key = (($Language -split '\s+') | Where-Object { $_ }) -join ' '
    if (($QwenLanguages -contains $key) -or -not ($PlamoLanguages -contains $key)) {
        return [pscustomobject]@{ Kind = 'qwen'; Name = $QwenName; Shown = 'Qwen3.5 4B'; GB = $SizeLlm }
    }
    return [pscustomobject]@{ Kind = 'plamo'; Name = $PlamoName; Shown = 'PLaMo 3 Translate 2B'; GB = $SizePlamo }
}

function Get-ModelsDir {
    foreach ($name in @('TASLATION_MODELS_DIR', 'SELFTRANS_MODELS_DIR')) {
        $v = [Environment]::GetEnvironmentVariable($name)
        if ($v) { return [pscustomobject]@{ Path = $v; Source = $name } }
    }
    $configured = Get-TomlValue 'models_dir'
    if ($configured) { return [pscustomobject]@{ Path = $configured; Source = 'taslation.toml' } }
    return [pscustomobject]@{ Path = (Join-Path $Root 'models'); Source = 'this folder' }
}

function Test-Files([string]$Dir, [string[]]$Names) {
    foreach ($f in $Names) {
        if (-not (Test-Path -LiteralPath (Join-Path $Dir $f))) { return $false }
    }
    return $true
}

# The model that reads alone: an install from before the three has only this one.
function Test-FirstOcrModel([string]$ModelsDir) {
    return Test-Files (Join-Path $ModelsDir 'manga-ocr-charspot-small') @('model.safetensors', 'vocab.json', 'config.json')
}

# The layout and inpainting models: TASlation works without them, as it did before them.
function Test-PageModels([string]$ModelsDir) {
    return ((Test-Files (Join-Path $ModelsDir 'comic-text-and-bubble-detector') @('model.safetensors', 'config.json')) -and
            (Test-Files (Join-Path $ModelsDir 'lama-manga') @('lama-manga.safetensors')))
}

function Test-OcrModel([string]$ModelsDir) {
    if (-not (Test-FirstOcrModel $ModelsDir)) { return $false }
    foreach ($name in @('manga-ocr-nar-small', 'manga-ocr-base-CPT-flex')) {
        if (-not (Test-Files (Join-Path $ModelsDir $name) @('model.safetensors', 'nar_vocabulary_6817.json', 'config.json'))) { return $false }
    }
    return $true
}

# 'none', 'cpu' or 'cuda' (with the version) for the torch in the virtual environment.
function Get-TorchBuild {
    if (-not (Test-Path -LiteralPath $VenvPy)) { return [pscustomobject]@{ Kind = 'none'; Version = '' } }
    $r = Invoke-Captured $VenvPy @('-c', "import torch; print(torch.__version__); print(torch.version.cuda or '')")
    if ($r.Code -ne 0 -or $r.Out.Count -lt 1) { return [pscustomobject]@{ Kind = 'none'; Version = '' } }
    $cuda = ''
    if ($r.Out.Count -ge 2) { $cuda = $r.Out[1].Trim() }
    $kind = 'cpu'
    if ($cuda) { $kind = 'cuda' }
    return [pscustomobject]@{ Kind = $kind; Version = $r.Out[0].Trim() }
}

# nvidia-smi's line for a GPU ("NVIDIA GeForce GTX 1660 Ti, 6144 MiB, 610.88, 7.5": the name, the video memory, the
# driver's version, the compute capability) as Name, MemoryMb, Driver (a version, with DriverText as written) and
# Compute; $null (0 for the memory) for a field it lacks or does not give as a number; $null for a line without a name.
function ConvertTo-NvidiaGpu([string]$Line) {
    $parts = @("$Line" -split ',' | ForEach-Object { $_.Trim() })
    if (-not $parts[0]) { return $null }
    $memory = 0
    if ($parts.Count -ge 2 -and $parts[1] -match '^(\d+)\s*MiB$') { $memory = [int]$Matches[1] }
    $driver = $null
    $driverText = ''
    $compute = $null
    $v = $null
    if ($parts.Count -ge 3 -and [version]::TryParse($parts[2], [ref]$v)) { $driver = $v; $driverText = $parts[2] }
    $v = $null
    if ($parts.Count -ge 4 -and [version]::TryParse($parts[3], [ref]$v)) { $compute = $v }
    return [pscustomobject]@{ Name = $parts[0]; MemoryMb = $memory; Driver = $driver; DriverText = $driverText; Compute = $compute }
}

# nvidia-smi, which every NVIDIA display driver installs (into System32 since the DCH drivers, into NVSMI before
# them); $null when there is none.
function Find-NvidiaSmi {
    $found = @(Get-Command nvidia-smi -CommandType Application -ErrorAction SilentlyContinue)
    if ($found.Count -gt 0) { return $found[0].Source }
    if ($env:ProgramFiles) {
        $old = Join-Path $env:ProgramFiles 'NVIDIA Corporation\NVSMI\nvidia-smi.exe'
        if (Test-Path -LiteralPath $old) { return $old }
    }
    return $null
}

# The first NVIDIA GPU as nvidia-smi answers for it (ConvertTo-NvidiaGpu); $null when there is no nvidia-smi or it
# does not answer: no NVIDIA GPU, or a driver that does not work, which a GPU build of PyTorch could not use either.
# An AMD or Intel GPU has no nvidia-smi: PyTorch's CUDA cannot use them. nvidia-smi rather than NVIDIA's library (NVML,
# which `devices.nvml_name` asks in the window): it is NVML's own front end, so the answer is the same; it runs before
# there is any Python, with nothing to compile; and it also says the driver's version and the compute capability,
# which choose the GPU build. A driver too old to know compute_cap is asked again without it. No network.
function Get-NvidiaGpu {
    $smi = Find-NvidiaSmi
    if (-not $smi) { return $null }
    foreach ($fields in @('name,memory.total,driver_version,compute_cap', 'name,memory.total,driver_version')) {
        $r = Invoke-Captured $smi @("--query-gpu=$fields", '--format=csv,noheader')
        if ($r.Code -ne 0) { continue }
        $line = @($r.Out | Where-Object { "$_".Trim() }) | Select-Object -First 1
        $gpu = ConvertTo-NvidiaGpu $line
        if ($gpu) { return $gpu }
    }
    return $null
}

# The GPU build of PyTorch for *Gpu* (Get-NvidiaGpu): the last of $TorchCudaBuilds whose compute capability it reaches,
# the first when nvidia-smi does not say, as Build with Why ''; else Build $null and Why 'none' (no NVIDIA GPU), 'gpu'
# (older than any build has kernels for) or 'driver' (a driver older than the build needs). Need: the driver the build
# needs. A version nvidia-smi does not say is not held against the GPU: the check after the install decides then.
function Get-CudaBuild($Gpu) {
    if ($null -eq $Gpu) { return [pscustomobject]@{ Build = $null; Why = 'none'; Need = '' } }
    $build = $TorchCudaBuilds[0]
    if ($Gpu.Compute) {
        if ($Gpu.Compute -lt $TorchCudaBuilds[0].FromCompute) { return [pscustomobject]@{ Build = $null; Why = 'gpu'; Need = '' } }
        foreach ($b in $TorchCudaBuilds) { if ($Gpu.Compute -ge $b.FromCompute) { $build = $b } }
    }
    if ($Gpu.Driver -and $Gpu.Driver -lt [version]$build.MinDriver) {
        return [pscustomobject]@{ Build = $null; Why = 'driver'; Need = $build.MinDriver }
    }
    return [pscustomobject]@{ Build = $build; Why = ''; Need = $build.MinDriver }
}

# What the program files' PyTorch is to be, from what is there (Get-TorchBuild's *Torch*) and the GPU (*Gpu*): Build
# 'cuda' or 'cpu'; Action 'keep' (what is there stays), 'install' (nothing there) or 'replace' (the CPU build there
# makes way for the GPU build); Cuda, the GPU build for this GPU (Get-CudaBuild; $null when none runs on it); UsesGpu,
# whether TASlation will run on this GPU, which makes yes the default of the page models' question; Note, what the
# person is told besides: 'driver', 'gpu' (why the CPU build) or 'update' (a CPU build an update keeps). A CUDA build
# there is kept; a CPU build is replaced where a GPU build runs, unless *FromUpdate*.
function Get-TorchPlan($Torch, $Gpu, [bool]$FromUpdate) {
    $cuda = Get-CudaBuild $Gpu
    $usable = $null -ne $cuda.Build
    $note = ''
    if ($cuda.Why -eq 'driver' -or $cuda.Why -eq 'gpu') { $note = $cuda.Why }
    $plan = [pscustomobject]@{ Build = 'cpu'; Action = 'install'; Cuda = $cuda.Build; Need = $cuda.Need; UsesGpu = $false; Note = $note }
    if ($Torch.Kind -eq 'cuda') {
        $plan.Build = 'cuda'; $plan.Action = 'keep'; $plan.UsesGpu = $usable; $plan.Note = ''
    } elseif ($Torch.Kind -eq 'cpu') {
        $plan.Action = 'keep'
        if ($usable -and $FromUpdate) { $plan.Note = 'update' }
        elseif ($usable) { $plan.Build = 'cuda'; $plan.Action = 'replace'; $plan.UsesGpu = $true }
    } elseif ($usable) {
        $plan.Build = 'cuda'; $plan.UsesGpu = $true
    }
    return $plan
}

# What the person reads of *Plan* among the questions, before anything is downloaded: the GPU build and its download.
function Show-TorchPlan($Plan, $Gpu) {
    if ($Plan.Action -eq 'install' -and $Plan.Build -eq 'cuda') {
        Write-Info ((T 'This computer has an NVIDIA GPU, so the program files come in their GPU build: about {0:N1} GB more to download.') -f ($Plan.Cuda.DownloadGB - $TorchCpuDownloadGB))
    } elseif ($Plan.Action -eq 'replace') {
        Write-Info ((T 'This computer has an NVIDIA GPU: the CPU build of the program files here is replaced by their GPU build (about {0:N1} GB to download).') -f $Plan.Cuda.DownloadGB)
    } elseif ($Plan.Note -eq 'update') {
        Write-Info (T 'This computer has an NVIDIA GPU, but the program files here are their CPU build, which an update keeps.')
        Write-Info ((T 'To use the GPU, run install.cmd: it fetches their GPU build (about {0:N1} GB).') -f $Plan.Cuda.DownloadGB)
    } elseif ($Plan.Note -eq 'driver') {
        Write-Info ((T 'The GPU build needs an NVIDIA driver of version {0} or newer, and this one is {1}: the program files use their CPU build.') -f $Plan.Need, $Gpu.DriverText)
        Write-Info (T 'To use the GPU, update the driver and run install.cmd again.')
    } elseif ($Plan.Note -eq 'gpu') {
        Write-Info (T 'This NVIDIA GPU is older than the GPU build supports: the program files use their CPU build.')
    }
}

# Whether the torch in the virtual environment runs on the GPU: torch.cuda.is_available(), and one sum computed there
# (a GPU the build has no kernels for passes is_available and fails on its first kernel).
function Test-TorchCuda {
    $code = "import torch; ok = torch.cuda.is_available() and (torch.ones(2, device='cuda') + 1).sum().item() == 4; print('cuda ok' if ok else 'no cuda')"
    $r = Invoke-Captured $VenvPy @('-c', $code)
    return ($r.Code -eq 0 -and (@($r.Out | ForEach-Object { "$_".Trim() }) -contains 'cuda ok'))
}

# PyTorch into the virtual environment as *Plan* says (Get-TorchPlan; not for 'keep'), with pip's own progress on the
# console. The GPU build comes without pip's cache (it would keep a second copy of 2.6 GB) and is then tried on the GPU
# (Test-TorchCuda); when it does not download, install or run there, the CPU build takes its place and one line says
# so: the GPU step never leaves the install broken. Only the CPU build not coming stops the install (the network or
# the disk), as it always did. Returns the build installed: 'cuda' or 'cpu'.
function Install-Torch($Plan) {
    if ($Plan.Build -eq 'cpu') {
        $code = Invoke-Console $VenvPy @('-m', 'pip', 'install', '--disable-pip-version-check', 'torch', '--index-url', $TorchCpuIndex)
        if ($code -ne 0) { Stop-Install "the program files did not download (exit code $code). Check the network and the disk space." }
        return 'cpu'
    }
    Write-Info ((T 'Downloading the GPU build of the program files (about {0:N1} GB).') -f $Plan.Cuda.DownloadGB)
    $cudaArgs = @('-m', 'pip', 'install', '--disable-pip-version-check', '--no-cache-dir')
    # A CPU build of the same version or a newer one counts as torch already there unless reinstalled; torch alone
    # (its dependencies are there, and the next step's pip install puts in what it lacks).
    if ($Plan.Action -eq 'replace') { $cudaArgs += @('--force-reinstall', '--no-deps') }
    $code = Invoke-Console $VenvPy ($cudaArgs + @('torch', '--index-url', $Plan.Cuda.Index))
    if ($code -eq 0 -and (Test-TorchCuda)) { return 'cuda' }
    Write-Detail "the GPU build: pip's exit code $code, or no CUDA after it"
    Write-Warn (T 'The GPU build did not work on this computer, so the program files come in their CPU build instead.')
    $there = (Get-TorchBuild).Kind
    if ($there -eq 'cpu') { return 'cpu' }  # a replace that did not download: the CPU build is still there
    $listed = Clear-HalfInstalledTorch
    $cpuArgs = @('-m', 'pip', 'install', '--disable-pip-version-check')
    # A torch pip still sees (the GPU build that does not run here, or one that does not import) counts as torch
    # already there unless reinstalled: torch alone again. With none there, pip brings what torch needs as always.
    if ($there -eq 'cuda' -or $listed) { $cpuArgs += @('--force-reinstall', '--no-deps') }
    $code = Invoke-Console $VenvPy ($cpuArgs + @('torch', '--index-url', $TorchCpuIndex))
    if ($code -ne 0) { Stop-Install "the program files did not download (exit code $code). Check the network and the disk space." }
    return 'cpu'
}

# Whether pip still sees a torch in the virtual environment after the GPU build failed, with what is left of a GPU
# build whose unpacking stopped half way (the disk full) taken out first: that one has no RECORD file, from which pip
# would uninstall it, and pip refuses to put anything over it, so its folders are removed here as pip's uninstall
# would remove them. A torch with its RECORD is left to pip.
function Clear-HalfInstalledTorch {
    $site = Join-Path (Split-Path -Parent (Split-Path -Parent $VenvPy)) 'Lib\site-packages'
    $infos = @(Get-ChildItem -LiteralPath $site -Directory -Filter 'torch-*.dist-info' -ErrorAction SilentlyContinue)
    if ($infos.Count -eq 0) { return $false }
    if (@($infos | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'RECORD') }).Count -gt 0) { return $true }
    Write-Detail 'the GPU build was left half unpacked: its folders are removed'
    try {
        foreach ($name in @('torch', 'functorch', 'torchgen')) {
            $path = Join-Path $site $name
            if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction Stop }
        }
        foreach ($info in $infos) { Remove-Item -LiteralPath $info.FullName -Recurse -Force -ErrorAction Stop }
    } catch {
        Write-Detail "could not remove them: $($_.Exception.Message)"
        return $true  # pip then says why it cannot install over them
    }
    return $false
}

# Where the Start-menu shortcut points; $null when there is none (or it cannot be read).
function Get-ShortcutTarget {
    if (-not (Test-Path -LiteralPath $ShortcutPath)) { return $null }
    try { return (New-Object -ComObject WScript.Shell).CreateShortcut($ShortcutPath).TargetPath } catch { return $null }
}

function Find-OllamaExe {
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $user = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
    if (Test-Path -LiteralPath $user) { return $user }
    return $null
}

function Test-OllamaServer {
    try {
        $null = Invoke-RestMethod -Uri "$OllamaUrl/api/version" -TimeoutSec 3 -UseBasicParsing
        return $true
    } catch { return $false }
}

# $null when the server does not answer, else the installed model names.
function Get-OllamaModels {
    try {
        $tags = Invoke-RestMethod -Uri "$OllamaUrl/api/tags" -TimeoutSec 5 -UseBasicParsing
        return @($tags.models | ForEach-Object { $_.name })
    } catch { return $null }
}

function Test-HasModel([object[]]$Installed, [string]$Name) {
    foreach ($m in $Installed) {
        if ($m -eq $Name -or $m -eq "${Name}:latest") { return $true }
    }
    return $false
}

function Get-UserEnv([string]$Name) { return [Environment]::GetEnvironmentVariable($Name, 'User') }
function Set-UserEnv([string]$Name, [string]$Value) { [Environment]::SetEnvironmentVariable($Name, $Value, 'User') }

# This Ollama's own processes stopped; whether there were any.
function Stop-OllamaProcesses([string]$Folder) {
    $running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and (Split-Path -Parent $_.Path) -eq $Folder })
    if ($running.Count -eq 0) { return $false }
    $running | Stop-Process -Force -ErrorAction SilentlyContinue
    return $true
}

# The two settings below are made for this user (Set-UserEnv) and in this process, whose environment the Ollama that
# Restart-Ollama starts inherits; an Ollama started later (the tray app at sign-in, ollama serve from a new window)
# inherits the user's. Each leaves its marker first, so that an uninstall clears only what an install set.
function Set-KvCache {
    Write-Info 'This GPU has 6 GB or less, so Ollama is set to use less of its memory, and Ollama restarts.'
    try { Set-Content -LiteralPath $KvMarker -Value 'q8_0' -Encoding Ascii } catch { Write-Detail "no marker: $_" }
    Set-UserEnv 'OLLAMA_KV_CACHE_TYPE' 'q8_0'
    $env:OLLAMA_KV_CACHE_TYPE = 'q8_0'
}

# Ollama 0.40 runs a model in llama.cpp's server, which keeps a cache of earlier prompts in RAM, up to 8 GiB unless
# told otherwise (--cache-ram; LLAMA_ARG_CACHE_RAM when the command line does not say, and Ollama's does not). In a
# whole-book run of 100 pages on the development machine (GPU) the translator's server grew to 9.8 GB working set
# (11.9 GB committed) with it, and stayed at 1.7 GB (3.8 GB) with 0, no cache; a line took 0.37 s both ways. Without
# the GPU (16 pages) the server peaked at 7.4 GB with it and 4.0 GB without, and a line took 1.51 s with it and 1.63 s
# without: one request found an earlier prompt in the cache. The installer trades those 8 % for 3.3 GB of RAM
# (docs/OFFLINE_VERIFICATION.md, "Ollama's prompt cache in RAM").
function Set-CacheRam {
    Write-Info (T 'Ollama is set to keep no cache of earlier requests in RAM (LLAMA_ARG_CACHE_RAM=0 for this Windows user), and Ollama restarts.')
    Write-Info (T 'Otherwise Ollama keeps up to 8 GB of RAM for that cache. In TASlation''s measurements it made translation no faster with a GPU, and about 8 % faster without one.')
    Write-Info (T 'It applies to the Ollama this user runs, and to any other program of this user that reads llama.cpp''s LLAMA_ARG_* settings.')
    Write-Info (T 'To undo it: uninstall.cmd clears it, or delete LLAMA_ARG_CACHE_RAM in "Edit environment variables for your account" (search the Start menu for that).')
    try { Set-Content -LiteralPath $CacheRamMarker -Value '0' -Encoding Ascii } catch { Write-Detail "no marker: $_" }
    Set-UserEnv 'LLAMA_ARG_CACHE_RAM' '0'
    $env:LLAMA_ARG_CACHE_RAM = '0'
}

# Ollama stopped and started again, once for both settings, so that its server reads them; nothing when it is not
# running: it reads them when it starts.
function Restart-Ollama([string]$OllamaPath) {
    if (Stop-OllamaProcesses (Split-Path -Parent $OllamaPath)) {
        Start-Sleep -Seconds 1
        [void](Start-OllamaServer $OllamaPath)
    }
}

function Start-OllamaServer([string]$Exe) {
    if (Test-OllamaServer) { return $true }
    $app = Join-Path (Split-Path $Exe -Parent) 'ollama app.exe'
    if (Test-Path -LiteralPath $app) {
        Write-Info 'Starting Ollama.'
        Start-Process -FilePath $app | Out-Null
    } else {
        Write-Info 'Starting Ollama.'
        Start-Process -FilePath $Exe -ArgumentList 'serve' -WindowStyle Hidden | Out-Null
    }
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        if (Test-OllamaServer) { return $true }
    }
    return $false
}

function Get-FreeGB([string]$Path) {
    try {
        $rootPath = [IO.Path]::GetPathRoot([IO.Path]::GetFullPath($Path))
        $drive = New-Object System.IO.DriveInfo($rootPath)
        return [math]::Round($drive.AvailableFreeSpace / 1GB, 1)
    } catch { return $null }
}

function Get-DriveName([string]$Path) {
    try { return [IO.Path]::GetPathRoot([IO.Path]::GetFullPath($Path)).TrimEnd('\') } catch { return '?' }
}

function Test-LongPathsEnabled {
    try {
        $key = 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem'
        return ((Get-ItemProperty -LiteralPath $key -Name LongPathsEnabled -ErrorAction Stop).LongPathsEnabled -eq 1)
    } catch { return $false }
}

# Folders right inside this one that hold a whole other copy: what an update copied in one level too deep.
function Find-NestedCopies {
    return @(Get-ChildItem -LiteralPath $Root -Directory -Force -ErrorAction SilentlyContinue | Where-Object {
        (Test-Path -LiteralPath (Join-Path $_.FullName 'install.ps1')) -and (Test-Path -LiteralPath (Join-Path $_.FullName 'pyproject.toml'))
    } | ForEach-Object { $_.Name })
}

# The version, and the date of the program files, which tells an update that took from one that did not: the newest
# file of the whole package, as Help > About and update.ps1 give it.
function Get-VersionLine {
    $version = '?'
    foreach ($line in Get-Content -LiteralPath (Join-Path $Root 'pyproject.toml') -Encoding UTF8) {
        if ($line -match '^\s*version\s*=\s*"([^"]+)"') { $version = $Matches[1]; break }
    }
    $newest = Get-ChildItem -LiteralPath (Join-Path $Root 'taslation') -Filter '*.py' -File -Recurse -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime | Select-Object -Last 1
    if ($newest) { return ('{0}, files dated {1}' -f $version, $newest.LastWriteTime.ToString('yyyy-MM-dd')) }
    return $version
}

function Show-PythonWay {
    Write-Info ((T 'Install it from {0}') -f $PythonPage)
    Write-Info (T '(the 64-bit Windows installer; tick ''Add python.exe to PATH''), then run install.cmd again.')
}

function New-Venv {
    $cmd = $script:basePython.Command
    $code = Invoke-Console $cmd[0] (@($cmd | Select-Object -Skip 1) + @('-m', 'venv', $Venv))
    if ($code -ne 0 -or -not (Test-Path -LiteralPath $VenvPy)) { Stop-Install "could not create the program folder (exit code $code)." }
}

# Closing the window while .venv is being made leaves it without pip, and every later run would blame the network.
function Repair-Pip {
    if ((Invoke-Captured $VenvPy @('-m', 'pip', '--version')).Code -eq 0) { return }
    Write-Info 'The program files were left unfinished. Repairing them.'
    $null = Invoke-Captured $VenvPy @('-m', 'ensurepip', '--default-pip')
    if ((Invoke-Captured $VenvPy @('-m', 'pip', '--version')).Code -eq 0) { return }
    $script:basePython = Find-BasePython
    if ($null -eq $script:basePython) { Show-PythonWay; Stop-Install 'Python is missing.' }
    Remove-Item -LiteralPath $Venv -Recurse -Force
    New-Venv
    $script:torch = Get-TorchBuild
}

# ---------------------------------------------------------------- start
Write-Host 'TASlation installer' -ForegroundColor Cyan
# Python puts the current folder first on its path and TASlation reads taslation.toml from it: work in this folder.
Push-Location -LiteralPath $Root
Read-InstallerTexts
Write-Host "  folder: $Root"
if ($DryRun) { Write-Host '  DRY RUN: nothing is installed, downloaded or changed.' -ForegroundColor DarkYellow }
Write-Host ('  ' + (T 'The questions come first. After them you can leave it running.'))

# 1. this computer and the questions: nothing is downloaded before the last answer ---------------------------------
Write-Step (T 'This computer')
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    Stop-Install 'TASlation runs on Windows 10 or 11 (window capture and page turning use Win32).'
}
if (-not [Environment]::Is64BitOperatingSystem) { Stop-Install 'a 64-bit Windows is needed (PyTorch has no 32-bit build).' }
Write-Ok ('Windows ' + [Environment]::OSVersion.Version.ToString() + ', 64-bit')
if (-not (Test-Path -LiteralPath (Join-Path $Root 'pyproject.toml'))) {
    Stop-Install "pyproject.toml is not next to this script; unpack the whole ZIP of TASlation and run install.cmd in that folder."
}
if ($Root.Length -gt $MaxRootLength -and -not (Test-Path -LiteralPath $VenvPy) -and -not (Test-LongPathsEnabled)) {
    Stop-Install "this folder's path is too long ($($Root.Length) characters; $MaxRootLength fit). Move the folder somewhere shorter, such as C:\TASlation."
}
foreach ($name in (Find-NestedCopies)) {
    Write-Warn "The folder $name inside this one holds another copy of TASlation, which is not the one installed. To update from it: run update.cmd and give it the folder $name (or copy the files inside $name over this folder, choose Replace and run install.cmd), then delete $name."
}

# The first question: the language decides the translation model, and so which licence is asked about further on.
$offeredLanguage = Get-TargetLanguage
$language = Select-TargetLanguage $offeredLanguage

# The OCR models' licence comes before anything is installed: without them TASlation cannot read pages, so a no ends
# the run here with nothing done. An install from before the three keeps reading with the one it has, so there a no
# only leaves the other two out. -Yes does not agree: a licence takes a person.
$models = Get-ModelsDir
$ocrReady = Test-OcrModel $models.Path
if (-not $ocrReady) {
    Write-Host ''
    Write-Info (T 'TASlation reads pages with three OCR models (about 700 MB in all):')
    Write-Info '  manga-ocr-charspot-small, manga-ocr-nar-small, manga-ocr-base-CPT-flex'
    Write-Info (T 'All three are free for NON-COMMERCIAL use only. Their licence is CC BY-NC-SA 4.0:')
    Write-Info '  https://creativecommons.org/licenses/by-nc-sa/4.0/'
    Write-Info (T 'TASlation itself is MIT, but it cannot read pages without these models.')
    $licenceQuestion = (T 'Do you agree to the terms of the OCR models?')
    if ($DryRun) {
        Write-Info "$licenceQuestion [y/N] (dry run: would ask; counted as y)"
    } elseif ($Yes -or -not (Confirm-Choice $licenceQuestion)) {
        if ($Yes) { Write-Info "$licenceQuestion [y/N] (-Yes does not agree to a licence; run install.cmd and answer it yourself)" }
        if (Test-FirstOcrModel $models.Path) {
            Write-Info (T 'TASlation goes on reading with the one model it has. To agree later, run install.cmd again.')
            $ocrReady = $true
        } else {
            Write-Host ''
            Write-Host (T 'Installation stopped: TASlation cannot read pages without the OCR models.') -ForegroundColor Yellow
            Write-Host (T 'Nothing was installed. To agree later, run install.cmd again.')
            Exit-Install 1
        }
    }
}

# The GPU, and the PyTorch the program files get for it (Get-TorchPlan): no question, but said before any download.
$gpu = Get-NvidiaGpu
$gpuMemoryMb = 0
if ($gpu) {
    $gpuMemoryMb = $gpu.MemoryMb
    $shown = $gpu.Name
    if ($gpu.MemoryMb) { $shown += ", $($gpu.MemoryMb) MiB" }
    if ($gpu.DriverText) { $shown += ", driver $($gpu.DriverText)" }
    Write-Ok "NVIDIA GPU: $shown"
}
$torch = Get-TorchBuild
$torchPlan = Get-TorchPlan $torch $gpu $FromUpdate
Show-TorchPlan $torchPlan $gpu

# The layout and inpainting models are a person's choice too, and a no leaves TASlation as it was before them. Where
# TASlation will run on this GPU it uses the inpainting model by default (art_erase "auto"), so Enter means yes there;
# elsewhere it means no. Without a console it is no all the same, and -Yes does not answer it: nobody agreed.
$pageReady = Test-PageModels $models.Path
if (-not $pageReady) {
    $pageDefault = [bool]$torchPlan.UsesGpu
    $pageHint = '[y/N]'
    if ($pageDefault) { $pageHint = '[Y/n]' }
    Write-Host ''
    Write-Info (T 'Two more models find lettering on the drawing and take it out (about 360 MB in all):')
    Write-Info (T '  comic-text-and-bubble-detector is tagged Apache-2.0, the inpainting model LaMa MIT.')
    Write-Info (T 'Neither says where its training images come from. TASlation works without them, as it did before them.')
    if ($pageDefault) { Write-Info (T 'With this computer''s GPU TASlation uses the inpainting model by default, so Enter here means yes.') }
    $pageQuestion = (T 'Download these two models?')
    if ($DryRun) {
        Write-Info "$pageQuestion $pageHint (dry run: would ask; counted as y)"
    } elseif ($Yes -or -not (Confirm-Choice $pageQuestion $pageDefault)) {
        if ($Yes) { Write-Info "$pageQuestion $pageHint (-Yes does not answer this; run install.cmd and answer it yourself)" }
        Write-Info (T 'They are left out. To add them later, run install.cmd again.')
        $pageReady = $true
    }
}

$winget = Get-Command winget -ErrorAction SilentlyContinue
$basePython = $null
$wantPython = $false
$venvInfo = $null
if (Test-Path -LiteralPath $VenvPy) {
    $venvInfo = Get-PythonInfo @($VenvPy)
    if ($null -eq $venvInfo) {
        Stop-Install ".venv exists but its Python does not run. Delete the folder $Venv (or run uninstall.cmd) and run install.cmd again."
    }
    if ($venvInfo.Version -lt $MinPython) {
        Stop-Install ".venv was made with Python $($venvInfo.Version); TASlation needs $MinPython or newer. Delete $Venv and run install.cmd again."
    }
    Write-Ok "program files found (Python $($venvInfo.Version))"
} else {
    $basePython = Find-BasePython
    if ($null -eq $basePython) {
        Write-Info ((T 'Python {0} or newer was not found.') -f $MinPython)
        Write-Detail "tried 'py -3', 'python' and $PythonUserExe"
        if ($winget) { Write-Info (T 'It is installed with winget, the package manager of Windows: a Y also accepts the terms winget shows for it.') }
        $wantPython = $winget -and (Confirm-Choice (T 'Install Python 3.13 now (about 30 MB to download; it stays after an uninstall)?') $true)
        if (-not $wantPython) { Show-PythonWay; Stop-Install 'Python is missing.' }
        $basePython = [pscustomobject]@{ Command = @($PythonUserExe); Version = [version]'3.13'; Exe = $PythonUserExe }
    } else {
        Write-Ok "Python $($basePython.Version) found"
        Write-Detail "$($basePython.Command -join ' '): $($basePython.Exe)"
    }
}

# what is already there
$ollamaExe = Find-OllamaExe
$model = Get-Translator $language.Name
$installedModels = $null
if ($ollamaExe) { $installedModels = Get-OllamaModels }
$modelPresent = ($null -ne $installedModels) -and (Test-HasModel $installedModels $model.Name)

$wantOllama = $false
$wantModel = $false
if (-not $ollamaExe) {
    Write-Info (T 'Ollama runs the translation model on this computer. TASlation needs it to translate.')
    if (-not $winget) {
        Write-Info ((T 'Ollama cannot be installed from here. Install it from {0} and run install.cmd again.') -f $OllamaPage)
    } else {
        Write-Info (T 'It is installed with winget, the package manager of Windows: a Y also accepts the terms winget shows for it.')
        $wantOllama = Confirm-Choice (T 'Install Ollama now (about 3 GB)?') $true
    }
}
if (($ollamaExe -or $wantOllama) -and -not $modelPresent -and $model.Kind -eq 'qwen') {
    $wantModel = Confirm-Choice ((T 'Download the translation model {0} for {1} now (about 3.3 GB)?') -f $model.Name, $language.Name) $true
} elseif (($ollamaExe -or $wantOllama) -and -not $modelPresent) {
    # PLaMo's licence takes a person, as the OCR models' does; a no leaves TASlation without a translator for now.
    Write-Host ''
    Write-Info ((T 'TASlation translates into {0} with PLaMo 3 Translate 2B by Preferred Networks (about 1.8 GB).') -f $language.Name)
    Write-Info (T 'Its licence is the PLaMo Community License:')
    Write-Info (T '  - personal and other non-commercial use is free, with no registration;')
    Write-Info (T '    commercial use needs registering with Preferred Networks first;')
    Write-Info (T '  - you must be 18 or older (or of age where you live), or have a parent''s or guardian''s consent;')
    Write-Info (T '  - a translation made with it may be published only with a clear note that it is PLaMo''s output')
    Write-Info (T '    (article 5); TASlation asks you not to publish translations at all;')
    Write-Info (T '  - the model comes as is, without any warranty.')
    Write-Info (T 'The full licence, in English and in Japanese:')
    foreach ($u in $PlamoLicenceUrls) { Write-Info "  $u" }
    $plamoQuestion = (T 'Do you agree to the PLaMo Community License (PLaMo is then downloaded)?')
    if ($DryRun) {
        Write-Info "$plamoQuestion [y/N] (dry run: would ask; counted as y)"
        $wantModel = $true
    } elseif ($Yes) {
        Write-Info "$plamoQuestion [y/N] (-Yes does not agree to a licence; run install.cmd and answer it yourself)"
    } else {
        $wantModel = Confirm-Choice $plamoQuestion
    }
    if (-not $wantModel -and -not $DryRun) {
        Write-Info (T 'PLaMo is left out, and TASlation cannot translate without it. To agree later, run install.cmd again.')
    }
}

# 2. disk ------------------------------------------------------------------
Write-Step (T 'Disk space')
$ollamaModelsDir = $env:OLLAMA_MODELS
if (-not $ollamaModelsDir) { $ollamaModelsDir = Join-Path $env:USERPROFILE '.ollama\models' }
# the GPU build in place of the CPU build's torch; pip keeps its download in the temporary folder while it installs
$venvGB = $SizeVenvCpu
$venvWhat = 'program files'
$gpuDownload = ($torchPlan.Build -eq 'cuda') -and ($torchPlan.Action -ne 'keep')
if ($gpuDownload) {
    $venvGB = [math]::Round($SizeVenvCpu - $TorchCpuUnpackedGB + $torchPlan.Cuda.UnpackedGB, 1)
    $venvWhat = 'program files, GPU build'
}
$parts = @(
    [pscustomobject]@{ What = $venvWhat; GB = $venvGB; Where = $Venv; Present = ($torch.Kind -ne 'none' -and -not $gpuDownload); Wanted = $true },
    [pscustomobject]@{ What = 'reading model and fonts'; GB = $SizeModels; Where = $models.Path; Present = $ocrReady; Wanted = $true },
    [pscustomobject]@{ What = 'Ollama'; GB = $SizeOllama; Where = (Join-Path $env:LOCALAPPDATA 'Programs\Ollama'); Present = [bool]$ollamaExe; Wanted = $wantOllama },
    [pscustomobject]@{ What = "translation model $($model.Shown)"; GB = $model.GB; Where = $ollamaModelsDir; Present = $modelPresent; Wanted = $wantModel }
)
if ($wantPython) {
    $parts += [pscustomobject]@{ What = 'Python 3.13'; GB = $SizePython; Where = (Split-Path $PythonUserExe -Parent); Present = $false; Wanted = $true }
}
$total = ($parts | Measure-Object -Property GB -Sum).Sum
Write-Info ("TASlation takes about {0:N1} GB in all:" -f $total)
$need = @{}
$downloadGB = 0.0
foreach ($p in $parts) {
    $state = 'to download'
    if ($p.Present) { $state = 'already there' }
    elseif (-not $p.Wanted) { $state = 'not now' }
    Write-Info ("  {0,4:N1} GB  {1} ({2})" -f $p.GB, $p.What, $state)
    Write-Detail "$($p.What) goes to $($p.Where)"
    if ($p.Wanted -and -not $p.Present) {
        $downloadGB += $p.GB
        $d = Get-DriveName $p.Where
        if (-not $need.ContainsKey($d)) { $need[$d] = [pscustomobject]@{ GB = 0.0; Path = $p.Where } }
        $need[$d].GB += $p.GB
    }
}
if ($wantModel -and -not $modelPresent -and $model.Kind -eq 'plamo') {
    # its download waits in the models folder until Ollama has its copy
    $d = Get-DriveName $models.Path
    if (-not $need.ContainsKey($d)) { $need[$d] = [pscustomobject]@{ GB = 0.0; Path = $models.Path } }
    $need[$d].GB += $SizePlamo
}
if ($gpuDownload) {
    $temp = [IO.Path]::GetTempPath()
    $d = Get-DriveName $temp
    if (-not $need.ContainsKey($d)) { $need[$d] = [pscustomobject]@{ GB = 0.0; Path = $temp } }
    $need[$d].GB += $torchPlan.Cuda.DownloadGB
    Write-Detail "the GPU build's download waits in $temp while pip installs it"
}
$tooFull = @()
if ($need.Count -eq 0) {
    Write-Ok 'nothing new to store'
} else {
    foreach ($d in $need.Keys) {
        $free = Get-FreeGB $need[$d].Path
        if ($null -eq $free) {
            Write-Info ("{0} about {1:N1} GB needed; free space unknown" -f $d, $need[$d].GB)
        } elseif ($free -lt $need[$d].GB) {
            $tooFull += ((T '{0} has {1:N1} GB free, and this needs about {2:N1} GB there') -f $d, $free, $need[$d].GB)
        } else {
            Write-Ok ("{0} about {1:N1} GB needed, {2:N1} GB free" -f $d, $need[$d].GB, $free)
        }
    }
}
if ($tooFull.Count -gt 0) {
    if ($DryRun) {
        foreach ($t in $tooFull) { Write-Plan "stop here unless a person goes on: $t" }
    } else {
        foreach ($t in $tooFull) { Write-Host "  $t" -ForegroundColor Yellow }
        # -Yes is no answer here: a run nobody watches should not fill the disk
        if ($Yes -or -not (Confirm-Choice (T 'There is too little disk space. Go on anyway?'))) {
            Stop-Install 'too little disk space. Free some space.'
        }
    }
}

$timeText = (T 'a few minutes')
if ($downloadGB -ge 3) { $timeText = (T 'about 15 to 60 minutes') }
elseif ($downloadGB -ge 0.5) { $timeText = (T 'about 5 to 20 minutes') }
Write-Host ''
Write-Host ((T 'No more questions. The rest takes {0}, depending on your connection.') -f $timeText) -ForegroundColor Cyan
Write-Host (T 'You can leave it running.') -ForegroundColor Cyan

# 3. the program files: Python when it was agreed to, the environment, PyTorch --------------------------------------
Write-Step (T 'Program files')
if ($wantPython) {
    $wingetArgs = $PythonWingetArgs
    if ($DryRun) {
        Write-Plan ('winget ' + ($wingetArgs -join ' '))
    } else {
        Write-Info 'Installing Python 3.13.'
        $code = Invoke-Console $winget.Source $wingetArgs
        $basePython = Find-BasePython
        if ($null -eq $basePython) {
            Write-Info "Python was not found after its install (exit code $code)."
            Show-PythonWay
            Stop-Install 'Python is missing.'
        }
        Write-Ok "Python $($basePython.Version) installed"
    }
}
if ($venvInfo) {
    if (-not $DryRun) { Repair-Pip }
} elseif ($DryRun) {
    Write-Plan "create $Venv with $($basePython.Command -join ' ') -m venv"
} else {
    New-Venv
}
$torchPlan = Get-TorchPlan $torch $gpu $FromUpdate  # (again: Repair-Pip may have made the folder anew)
if ($torchPlan.Action -eq 'keep') {
    if ($torch.Kind -eq 'cuda') {
        Write-Detail "CUDA build already installed (torch $($torch.Version)); kept (it also runs on the CPU)"
    } else {
        Write-Detail "CPU build already installed (torch $($torch.Version)); kept"
    }
    Write-Ok 'already there; kept'
} elseif ($DryRun -and $torchPlan.Build -eq 'cpu') {
    Write-Plan ('python -m pip install --disable-pip-version-check torch --index-url ' + $TorchCpuIndex)
} elseif ($DryRun) {
    $force = ''
    if ($torchPlan.Action -eq 'replace') { $force = ' --force-reinstall --no-deps' }
    Write-Plan ("python -m pip install --disable-pip-version-check --no-cache-dir$force torch --index-url $($torchPlan.Cuda.Index)" +
                " (driver $($torchPlan.Need) or newer), check torch.cuda on the GPU, and when it fails: python -m pip install" +
                " --disable-pip-version-check --force-reinstall --no-deps torch --index-url $TorchCpuIndex")
} else {
    $built = Install-Torch $torchPlan
    $torch = Get-TorchBuild
    if ($built -eq 'cuda') { Write-Ok (T 'program files ready, GPU build') } else { Write-Ok 'program files ready' }
}

# 4. TASlation -------------------------------------------------------------
Write-Step (T 'TASlation and its parts')
$spec = '{0}[backup]' -f $Root
if ($DryRun) {
    Write-Plan "python -m pip install -e `"$spec`""
} else {
    # An older install has the headless OpenCV. windows-capture brings the other build, and the two share one cv2
    # folder: the old one goes first, so that nothing is left half overwritten.
    $r = Invoke-Captured $VenvPy @('-m', 'pip', 'show', '--disable-pip-version-check', 'opencv-python-headless')
    if ($r.Code -eq 0) { $null = Invoke-Console $VenvPy @('-m', 'pip', 'uninstall', '-y', 'opencv-python-headless') }
    $code = Invoke-Console $VenvPy @('-m', 'pip', 'install', '--disable-pip-version-check', '-e', $spec)
    if ($code -ne 0) { Stop-Install "TASlation did not install (exit code $code). Check the network and the disk space." }
    $r = Invoke-Captured $VenvPy @('-c', 'import taslation, os; print(os.path.dirname(taslation.__file__))')
    if ($r.Code -ne 0) { Stop-Install ('TASlation does not import after the install: ' + ($r.Out -join ' ')) }
    Write-Ok 'installed'
}
# a language chosen other than the one offered: the window starts with it (the one whose model is installed)
if ($language.Name -ne $offeredLanguage.Name) {
    if ($DryRun) {
        Write-Plan "keep $($language.Name) as the window's target language (ui.json)"
    } elseif (Save-TargetLanguage (Get-StateDir) $language.Name) {
        Write-Ok "the window will translate into $($language.Name)"
    } else {
        Write-Warn "The window could not be told the language $($language.Name): choose it in its To: box."
    }
}

# 5. OCR model and fonts ---------------------------------------------------
Write-Step (T 'Reading model and fonts')
$setup = Join-Path $Root 'setup_models.py'
$setupArgs = @('-u', $setup, '--agreed', '--brief', '--font', '--fonts')
if ($ocrReady) { $setupArgs += '--skip-ocr' }
if ($pageReady) { $setupArgs += '--skip-page-models' }
if ($DryRun) {
    Write-Plan ('python ' + ($setupArgs -join ' '))
} else {
    $code = Invoke-Console $VenvPy $setupArgs
    if ($code -ne 0) { Stop-Install "the reading model or the fonts did not download (exit code $code). Check the network and the disk space." }
    Write-Ok 'reading model and fonts ready'
}

# 6. Ollama ----------------------------------------------------------------
Write-Step (T 'Ollama and the translation model')
if ($wantOllama) {
    $wingetArgs = $OllamaWingetArgs
    if ($DryRun) {
        Write-Plan ('winget ' + ($wingetArgs -join ' '))
    } else {
        Write-Info 'Installing Ollama.'
        $code = Invoke-Console $winget.Source $wingetArgs
        $ollamaExe = Find-OllamaExe
        if ($ollamaExe) { Write-Ok 'Ollama installed' }
        else { Write-Warn "Ollama was not installed (exit code $code): run install.cmd again." }
    }
} elseif ($ollamaExe) {
    Write-Ok 'Ollama found'
    Write-Detail $ollamaExe
} else {
    Write-Info (T 'Ollama is not installed. To add it, run install.cmd again.')
}
# setup_models.py installs it and writes down that TASlation did (so that only it is ever removed again)
$translatorArgs = @('-u', $setup, '--translator-for', $language.Name, '--brief')
if ($model.Kind -eq 'plamo') { $translatorArgs += @('--plamo-agreed', 'install') }
if ($modelPresent) {
    Write-Ok "$($model.Shown) is already there"
} elseif ($wantModel -and $DryRun) {
    Write-Plan ('start Ollama if it is not running, then: python ' + ($translatorArgs -join ' ') + ' --ollama-exe OLLAMA')
} elseif ($wantModel -and $ollamaExe) {
    if (-not (Start-OllamaServer $ollamaExe)) {
        Write-Warn 'Ollama did not start: run install.cmd again.'
    } else {
        $installedModels = Get-OllamaModels
        if ($null -ne $installedModels -and (Test-HasModel $installedModels $model.Name)) {
            Write-Ok "$($model.Shown) is already there"
        } else {
            $code = Invoke-Console $VenvPy ($translatorArgs + @('--ollama-exe', $ollamaExe))
            if ($code -eq 0) { Write-Ok "$($model.Shown) installed" }
            else { Write-Warn "The translation model was not installed (exit code $code): run install.cmd again." }
        }
    }
} elseif ($ollamaExe -and -not $wantModel) {
    Write-Info (T 'The translation model was not downloaded. To add it, run install.cmd again.')
}
Write-Detail "translation model $($model.Name) for $($language.Name) (the language from $($language.Source))"
# Ollama's two settings, each only where its variable is set neither for this user nor in this process (a value there
# is the person's, and stays without a word), then one restart for both. A dry run counts an Ollama it would install.
$ollamaThere = $ollamaExe -or ($DryRun -and $wantOllama)
$ollamaSet = New-Object System.Collections.Generic.List[string]
# a GPU of 6 GB or less holds the model's whole context only with a quantized KV cache (about 4 times the speed)
if ($ollamaThere -and $gpuMemoryMb -gt 0 -and $gpuMemoryMb -le 6144 -and -not $env:OLLAMA_KV_CACHE_TYPE -and -not (Get-UserEnv 'OLLAMA_KV_CACHE_TYPE')) {
    if ($DryRun) {
        Write-Plan "set OLLAMA_KV_CACHE_TYPE=q8_0 for this user (and write $KvMarker)"
    } else {
        Set-KvCache
    }
    $ollamaSet.Add('Ollama set up for this GPU')
}
# every computer: no prompt cache of up to 8 GiB in RAM (Set-CacheRam)
if ($ollamaThere -and -not $env:LLAMA_ARG_CACHE_RAM -and -not (Get-UserEnv 'LLAMA_ARG_CACHE_RAM')) {
    if ($DryRun) {
        Write-Plan "set LLAMA_ARG_CACHE_RAM=0 for this user (and write $CacheRamMarker)"
        Write-Detail 'so that Ollama keeps no cache of earlier requests in RAM, up to 8 GB otherwise; uninstall.cmd clears it'
    } else {
        Set-CacheRam
    }
    $ollamaSet.Add((T 'Ollama keeps no cache of earlier requests in RAM'))
} elseif ($ollamaThere) {
    $cacheRam = $env:LLAMA_ARG_CACHE_RAM
    if (-not $cacheRam) { $cacheRam = Get-UserEnv 'LLAMA_ARG_CACHE_RAM' }
    Write-Detail "LLAMA_ARG_CACHE_RAM is set already ($cacheRam); left as it is"
}
if ($ollamaSet.Count -gt 0) {
    if ($DryRun) {
        Write-Plan 'start Ollama again if it is running (once), so that it reads what was set'
    } else {
        Restart-Ollama $ollamaExe
        foreach ($done in $ollamaSet) { Write-Ok $done }
    }
}

# 7. check and shortcut ----------------------------------------------------
Write-Step (T 'Final check')
$canTranslate = $false
if ($DryRun) {
    Write-Plan 'run .venv\Scripts\python -m taslation doctor'
} else {
    $r = Invoke-Captured $VenvPy @('-m', 'taslation', 'doctor')
    $canTranslate = ($r.Code -eq 0)
    if ($canTranslate) {
        Write-Ok 'ready'
    } else {
        $missing = @($r.Out | Where-Object { $_ -cmatch 'MISSING|NOT INSTALLED|Ollama' -and $_ -cnotmatch 'Ollama: reachable' })
        if ($missing.Count -eq 0) { $missing = $r.Out }  # a crash: the details are all there is
        Write-Info (T 'Not ready yet:')
        foreach ($line in $missing) { Write-Info "  $($line.Trim())" }
    }
}
$hasShortcut = (Get-ShortcutTarget) -ieq $VenvPyw
if ($hasShortcut) {
    Write-Ok 'Start-menu shortcut already there'
} elseif ($DryRun) {
    Write-Plan "create the Start-menu shortcut $ShortcutPath"
    $hasShortcut = $true
} else {
    try {
        $shell = New-Object -ComObject WScript.Shell
        $lnk = $shell.CreateShortcut($ShortcutPath)
        $lnk.TargetPath = $VenvPyw
        $lnk.Arguments = '-m taslation gui'
        $lnk.WorkingDirectory = $Root
        $lnk.IconLocation = "$Icon,0"
        $lnk.Description = 'TASlation: offline manga translation for books you own'
        $lnk.Save()
        $hasShortcut = $true
        Write-Ok 'Start-menu shortcut made'
    } catch {
        Write-Warn "The Start-menu shortcut could not be made ($_): run install.cmd again."
    }
}

Write-Host ''
if ($DryRun) {
    Write-Host 'Dry run finished; nothing was changed.' -ForegroundColor Cyan
} elseif ($canTranslate) {
    Write-Host (T 'TASlation is installed.') -ForegroundColor Cyan
} else {
    Write-Host (T 'Translating is not ready yet: run install.cmd again.') -ForegroundColor Yellow
}
Write-Host "  Version: $(Get-VersionLine)"
if ($hasShortcut) { Write-Host ('  ' + (T 'To start it: open the Start menu and choose TASlation.')) }
Write-Host ('  ' + (T 'To remove it: run uninstall.cmd.'))
if ($script:Warnings.Count -gt 0) {
    Write-Host ''
    Write-Host "$($script:Warnings.Count) warning(s):" -ForegroundColor Yellow
    foreach ($w in $script:Warnings) { Write-Host "  - $w" -ForegroundColor Yellow }
}
Exit-Install 0
