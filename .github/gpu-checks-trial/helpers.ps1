<#
Helpers of the trial of the GPU computer's checks on GitHub's runners (.github/workflows/gpu-checks-trial.yml),
dot-sourced by its steps (PowerShell 7).

What a job's summary gives besides the tools' own reports (the machine, the screen, the times of the run, the sizes of
the caches) goes to facts.json in the trial folder (RUNNER_TEMP\gpu-checks-trial), which goes into the job's artifact:
the runner's own figures, nothing of a person and nothing of the dataset. Ollama comes from its own release on GitHub,
as winget installs it for install.ps1 (OllamaSetup.exe, checked against the release's sha256sum.txt where it has one).
#>
Set-StrictMode -Version 3.0

$TrialDir = Join-Path $env:RUNNER_TEMP 'gpu-checks-trial'
$null = New-Item -ItemType Directory -Force -Path $TrialDir
$FactsFile = Join-Path $TrialDir 'facts.json'
$OllamaHome = Join-Path $env:LOCALAPPDATA 'Programs\Ollama'  # where Ollama's installer puts it (TASlation looks there)
$OllamaReleases = 'https://github.com/ollama/ollama/releases/download'
$OllamaLatest = 'https://api.github.com/repos/ollama/ollama/releases/latest'
$ProgressPreference = 'SilentlyContinue'  # (Invoke-WebRequest's progress bar slows a large download down)
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

function Get-Facts {
    if (-not (Test-Path -LiteralPath $FactsFile)) { return [ordered]@{} }
    $facts = Get-Content -LiteralPath $FactsFile -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
    if ($null -eq $facts) { return [ordered]@{} }
    return $facts
}

function Set-Fact([string]$Name, $Value) {
    $facts = Get-Facts
    $facts[$Name] = $Value
    Set-Content -LiteralPath $FactsFile -Value ($facts | ConvertTo-Json -Depth 8) -Encoding utf8
}

# The size of a folder or a file in GB; $null when there is none.
function Get-FolderGB([string]$Path) {
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return $null }
    $item = Get-Item -LiteralPath $Path -Force
    if (-not $item.PSIsContainer) { return [math]::Round($item.Length / 1GB, 2) }
    $sum = (Get-ChildItem -LiteralPath $Path -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
    if ($null -eq $sum) { $sum = 0 }
    return [math]::Round($sum / 1GB, 2)
}

# The screen: its size as Windows has it now, and the sizes the display offers, through user32 (no window is looked at).
if (-not ('GpuChecksTrial.Display' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace GpuChecksTrial {
    public static class Display {
        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        struct DEVMODE {
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string dmDeviceName;
            public short dmSpecVersion, dmDriverVersion, dmSize, dmDriverExtra;
            public int dmFields;
            public int dmPositionX, dmPositionY, dmDisplayOrientation, dmDisplayFixedOutput;
            public short dmColor, dmDuplex, dmYResolution, dmTTOption, dmCollate;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string dmFormName;
            public short dmLogPixels;
            public int dmBitsPerPel, dmPelsWidth, dmPelsHeight, dmDisplayFlags, dmDisplayFrequency;
            public int dmICMMethod, dmICMIntent, dmMediaType, dmDitherType, dmReserved1, dmReserved2;
            public int dmPanningWidth, dmPanningHeight;
        }

        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        static extern bool EnumDisplaySettingsW(string device, int mode, ref DEVMODE dm);

        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        static extern int ChangeDisplaySettingsW(ref DEVMODE dm, int flags);

        const int CurrentSettings = -1;
        const int PelsWidth = 0x80000, PelsHeight = 0x100000;

        static DEVMODE Blank() {
            DEVMODE dm = new DEVMODE();
            dm.dmSize = (short)Marshal.SizeOf(typeof(DEVMODE));
            return dm;
        }

        // "WIDTHxHEIGHT at BITS bit, HZ Hz", or "" when Windows says nothing
        public static string Current() {
            DEVMODE dm = Blank();
            if (!EnumDisplaySettingsW(null, CurrentSettings, ref dm)) return "";
            return dm.dmPelsWidth + "x" + dm.dmPelsHeight + " at " + dm.dmBitsPerPel + " bit, " + dm.dmDisplayFrequency + " Hz";
        }

        // the sizes the primary display offers, "WIDTHxHEIGHT", each once
        public static string[] Modes() {
            List<string> seen = new List<string>();
            DEVMODE dm = Blank();
            for (int i = 0; EnumDisplaySettingsW(null, i, ref dm); i++) {
                string size = dm.dmPelsWidth + "x" + dm.dmPelsHeight;
                if (!seen.Contains(size)) seen.Add(size);
                dm = Blank();
            }
            return seen.ToArray();
        }

        // the primary display set to width x height for this session (not written to the registry): Windows' answer,
        // 0 when it was changed (DISP_CHANGE_SUCCESSFUL), -99 when the current settings could not be read
        public static int Change(int width, int height) {
            DEVMODE dm = Blank();
            if (!EnumDisplaySettingsW(null, CurrentSettings, ref dm)) return -99;
            dm.dmPelsWidth = width;
            dm.dmPelsHeight = height;
            dm.dmFields = PelsWidth | PelsHeight;
            return ChangeDisplaySettingsW(ref dm, 0);
        }
    }
}
'@
}

function Get-Screen {
    try { return [GpuChecksTrial.Display]::Current() } catch { return "unknown ($($_.Exception.GetType().Name))" }
}

# The screen set to *Size* ("WIDTHxHEIGHT", or "as-is"), when the display offers that size; never fails the step (the
# run then says on which screen it ran). The runner is deleted after the job, and the change is not kept even there.
function Set-Screen([string]$Size) {
    $before = Get-Screen
    $result = [ordered]@{ asked = $Size; before = $before; after = $before; offered = @(); answer = $null }
    if ($Size -eq 'as-is') { return $result }
    if ($Size -notmatch '^(\d{3,4})x(\d{3,4})$') { $result.answer = 'not WIDTHxHEIGHT'; return $result }
    $width = [int]$Matches[1]
    $height = [int]$Matches[2]
    try {
        $result.offered = @([GpuChecksTrial.Display]::Modes())
        if ($result.offered -notcontains "${width}x${height}") {
            $result.answer = 'not offered by the display'
        } else {
            $result.answer = [GpuChecksTrial.Display]::Change($width, $height)
        }
    } catch {
        $result.answer = "failed ($($_.Exception.GetType().Name))"
    }
    $result.after = Get-Screen
    return $result
}

function Get-MachineFacts {
    $os = Get-CimInstance -ClassName Win32_OperatingSystem
    $cpu = @(Get-CimInstance -ClassName Win32_Processor)
    return [ordered]@{
        os = "$($os.Caption) $($os.Version)"
        cpu = $cpu[0].Name.Trim()
        cores = ($cpu | Measure-Object -Property NumberOfCores -Sum).Sum
        logical_processors = ($cpu | Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum
        ram_gb = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)  # (the size is in KB)
        gpus = @(Get-CimInstance -ClassName Win32_VideoController | ForEach-Object { $_.Name })
        session = (Get-Process -Id $PID).SessionId
        interactive = [Environment]::UserInteractive
        screen = Get-Screen
    }
}

# The release of Ollama to install: *Asked* as it is when it is a tag (v1.2.3), else ("latest", or empty) the latest
# release on GitHub, the one winget's package and ollama.com's download follow.
function Resolve-OllamaTag([string]$Asked) {
    if ($Asked -and $Asked -ne 'latest') {
        if ($Asked -notmatch '^v\d+\.\d+\.\d+$') { throw "ollama_version is 'latest' or a tag such as v0.40.16, not '$Asked'" }
        return $Asked
    }
    $headers = @{ Accept = 'application/vnd.github+json' }
    if ($env:GH_TOKEN) { $headers.Authorization = "Bearer $env:GH_TOKEN" }
    $tag = "$((Invoke-RestMethod -Uri $OllamaLatest -Headers $headers -TimeoutSec 60).tag_name)"
    if ($tag -notmatch '^v\d+\.\d+\.\d+$') { throw "the latest release of Ollama has the tag '$tag'" }
    return $tag
}

# OllamaSetup.exe of release *Tag* downloaded into *Dir*, checked against the release's sha256sum.txt when it has one.
function Save-OllamaSetup([string]$Tag, [string]$Dir) {
    $null = New-Item -ItemType Directory -Force -Path $Dir
    $file = Join-Path $Dir 'OllamaSetup.exe'
    $clock = [Diagnostics.Stopwatch]::StartNew()
    Invoke-WebRequest -Uri "$OllamaReleases/$Tag/OllamaSetup.exe" -OutFile $file -TimeoutSec 1800
    $hash = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
    $checked = 'no sha256sum.txt in the release'
    $sums = $null
    try { $sums = "$((Invoke-WebRequest -Uri "$OllamaReleases/$Tag/sha256sum.txt" -TimeoutSec 60).Content)" } catch { $sums = $null }
    if ($sums) {
        $line = @($sums -split "`r?`n" | Where-Object { $_ -match '^\s*[0-9a-fA-F]{64}\s+\*?(\S*/)?OllamaSetup\.exe\s*$' }) | Select-Object -First 1
        if (-not $line) {
            $checked = 'OllamaSetup.exe not listed in sha256sum.txt'
        } elseif (($line.Trim() -split '\s+')[0].ToLowerInvariant() -ne $hash) {
            Remove-Item -LiteralPath $file -Force
            throw "OllamaSetup.exe of $Tag does not match the release's sha256sum.txt"
        } else {
            $checked = 'matches the release''s sha256sum.txt'
        }
    }
    return [ordered]@{ tag = $Tag; sha256 = $hash; checked = $checked; gb = Get-FolderGB $file
                       seconds = [math]::Round($clock.Elapsed.TotalSeconds, 1) }
}

# The running processes of Ollama's program folder: its app, its server, the model's (llama-server, in lib\ollama).
function Get-OllamaProcesses {
    $prefix = $OllamaHome.TrimEnd('\') + '\'
    return @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
        try { $_.Path -and $_.Path.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) } catch { $false }
    })
}

# Every process of Ollama stopped, also one its installer starts a moment after it ends (its app, which would start
# a server of its own): TASlation starts the server it needs itself. How many were stopped.
function Stop-OllamaProcesses([int]$WatchSeconds = 10) {
    $stopped = 0
    $clock = [Diagnostics.Stopwatch]::StartNew()
    do {
        foreach ($p in @(Get-OllamaProcesses)) {
            try { $p.Kill($true); $stopped++ } catch { }
        }
        Start-Sleep -Milliseconds 500
    } while ($clock.Elapsed.TotalSeconds -lt $WatchSeconds)
    return $stopped
}

# Ollama installed for this user from *Setup* (OllamaSetup.exe) without a question, as winget installs it, and then
# nothing of it left running.
function Install-Ollama([string]$Setup) {
    $clock = [Diagnostics.Stopwatch]::StartNew()
    $p = Start-Process -FilePath $Setup -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-' -PassThru
    $p.WaitForExit()
    $stopped = Stop-OllamaProcesses
    $exe = Join-Path $OllamaHome 'ollama.exe'
    if (-not (Test-Path -LiteralPath $exe)) { throw "Ollama's installer ended with exit code $($p.ExitCode) and left no $exe" }
    # (from the file: the ollama command itself could start Ollama's app when no server answers)
    $version = "$((Get-Item -LiteralPath $exe).VersionInfo.ProductVersion)".Trim()
    return [ordered]@{ exit_code = $p.ExitCode; seconds = [math]::Round($clock.Elapsed.TotalSeconds, 1)
                       stopped_after_it = $stopped; version = $version; program_gb = Get-FolderGB $OllamaHome }
}
