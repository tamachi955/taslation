<#
Helpers of the GPU computer's checks on GitHub's runners (.github/workflows/gpu-checks.yml), dot-sourced by its steps
(PowerShell 7).

What a job's summary gives besides the tools' own reports (the machine, the screen, the times of the run, the sizes of
the caches) goes to facts.json in the checks' folder (RUNNER_TEMP\gpu-checks), which goes into the job's artifact: the
runner's own figures, nothing of a person and nothing of the dataset. Ollama comes from its own release on GitHub: the
release's standalone files (ollama-windows-amd64.zip: ollama.exe and its libraries, what its installer puts in the
same folder, without the tray app, which TASlation never starts), checked against the digests published for it and
unpacked where the installer puts them, %LOCALAPPDATA%\Programs\Ollama, where TASlation looks for ollama.exe.
#>
Set-StrictMode -Version 3.0

$ChecksDir = Join-Path $env:RUNNER_TEMP 'gpu-checks'
$null = New-Item -ItemType Directory -Force -Path $ChecksDir
$FactsFile = Join-Path $ChecksDir 'facts.json'
$OllamaHome = Join-Path $env:LOCALAPPDATA 'Programs\Ollama'  # where Ollama's installer puts it (TASlation looks there)
$OllamaZip = 'ollama-windows-amd64.zip'
$OllamaApi = 'https://api.github.com/repos/ollama/ollama/releases'
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
if (-not ('GpuChecks.Display' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace GpuChecks {
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
    try { return [GpuChecks.Display]::Current() } catch { return "unknown ($($_.Exception.GetType().Name))" }
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
        $result.offered = @([GpuChecks.Display]::Modes())
        if ($result.offered -notcontains "${width}x${height}") {
            $result.answer = 'not offered by the display'
        } else {
            $result.answer = [GpuChecks.Display]::Change($width, $height)
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

# Ollama's release *Asked* on GitHub ("latest", or a tag such as v0.40.17), read through GitHub's API (a lookup, nothing
# is sent): its tag, and the standalone zip's address, size and the SHA-256 GitHub gives for it ($null when it gives
# none).
function Resolve-OllamaRelease([string]$Asked) {
    if ($Asked -ne 'latest' -and $Asked -notmatch '^v\d+\.\d+\.\d+$') {
        throw "ollama_version is 'latest' or a tag such as v0.40.17, not '$Asked'"
    }
    $headers = @{ Accept = 'application/vnd.github+json' }
    if ($env:GH_TOKEN) { $headers.Authorization = "Bearer $env:GH_TOKEN" }
    $uri = $(if ($Asked -eq 'latest') { "$OllamaApi/latest" } else { "$OllamaApi/tags/$Asked" })
    $release = Invoke-RestMethod -Uri $uri -Headers $headers -TimeoutSec 60
    $tag = "$($release.tag_name)"
    if ($tag -notmatch '^v\d+\.\d+\.\d+$') { throw "Ollama's release has the tag '$tag'" }
    $asset = @($release.assets | Where-Object { $_.name -eq $OllamaZip }) | Select-Object -First 1
    if (-not $asset) { throw "Ollama's release $tag has no $OllamaZip" }
    $digest = $null
    if (($asset.PSObject.Properties.Name -contains 'digest') -and "$($asset.digest)" -match '^sha256:([0-9a-fA-F]{64})$') {
        $digest = $Matches[1].ToLowerInvariant()
    }
    $sums = @($release.assets | Where-Object { $_.name -eq 'sha256sum.txt' }) | Select-Object -First 1
    return [ordered]@{ tag = $tag; url = "$($asset.browser_download_url)"; size = [long]$asset.size; digest = $digest
                       sums_url = $(if ($sums) { "$($sums.browser_download_url)" } else { $null }) }
}

# Ollama's standalone files of *Release* (Resolve-OllamaRelease) downloaded and checked - against *Pinned* (the SHA-256
# the workflow fixes for its pinned release, when this is that release), the digest GitHub gives for the file, and the
# release's sha256sum.txt where it lists the file; one of them at least, else nothing is unpacked - and unpacked into
# Ollama's folder. Nothing of Ollama is started.
function Install-OllamaFiles($Release, [string]$Pinned) {
    $dir = Join-Path $env:RUNNER_TEMP 'ollama-download'
    $null = New-Item -ItemType Directory -Force -Path $dir
    $zip = Join-Path $dir $OllamaZip
    $clock = [Diagnostics.Stopwatch]::StartNew()
    Invoke-WebRequest -Uri $Release.url -OutFile $zip -TimeoutSec 1800
    $download_s = [math]::Round($clock.Elapsed.TotalSeconds, 1)
    $hash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
    $checked = @()
    $wanted = [ordered]@{ pinned = $Pinned; github = $Release.digest }
    if ($Release.sums_url) {
        $sums = "$((Invoke-WebRequest -Uri $Release.sums_url -TimeoutSec 60).Content)"
        $line = @($sums -split "`r?`n" | Where-Object { $_ -match ('^\s*[0-9a-fA-F]{64}\s+\*?(\S*/)?' + [regex]::Escape($OllamaZip) + '\s*$') }) | Select-Object -First 1
        if ($line) { $wanted['sha256sum.txt'] = ($line.Trim() -split '\s+')[0].ToLowerInvariant() }
    }
    foreach ($name in $wanted.Keys) {
        if (-not $wanted[$name]) { continue }
        if ($wanted[$name] -ne $hash) {
            Remove-Item -LiteralPath $zip -Force
            throw "$OllamaZip of $($Release.tag) does not match the SHA-256 of $name"
        }
        $checked += $name
    }
    if (-not $checked) {
        Remove-Item -LiteralPath $zip -Force
        throw "no SHA-256 to check $OllamaZip of $($Release.tag) against"
    }
    if ((Get-Item -LiteralPath $zip).Length -ne $Release.size) { throw "$OllamaZip is not the size the release gives" }
    $clock.Restart()
    if (Test-Path -LiteralPath $OllamaHome) { Remove-Item -LiteralPath $OllamaHome -Recurse -Force }
    $null = New-Item -ItemType Directory -Force -Path $OllamaHome
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($zip, $OllamaHome)
    $unpack_s = [math]::Round($clock.Elapsed.TotalSeconds, 1)
    $zip_gb = Get-FolderGB $zip
    Remove-Item -LiteralPath $zip -Force
    $exe = Join-Path $OllamaHome 'ollama.exe'
    if (-not (Test-Path -LiteralPath $exe)) { throw "$OllamaZip of $($Release.tag) holds no ollama.exe at its top" }
    return [ordered]@{ tag = $Release.tag; sha256 = $hash; checked_against = $checked; zip_gb = $zip_gb
                       download_s = $download_s; unpack_s = $unpack_s; program_gb = Get-FolderGB $OllamaHome }
}

# What Ollama is here: its program's version, from the file (the ollama command itself is not run), and its size.
function Get-OllamaFacts {
    $exe = Join-Path $OllamaHome 'ollama.exe'
    if (-not (Test-Path -LiteralPath $exe)) { throw "no $exe" }
    return [ordered]@{ version = "$((Get-Item -LiteralPath $exe).VersionInfo.ProductVersion)".Trim()
                       program_gb = Get-FolderGB $OllamaHome }
}

# The running processes of Ollama's program folder: its server and the model's (llama-server, in lib\ollama).
function Get-OllamaProcesses {
    $prefix = $OllamaHome.TrimEnd('\') + '\'
    return @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
        try { $_.Path -and $_.Path.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) } catch { $false }
    })
}

# Every process of Ollama's folder stopped (after the translation model's import, before its store is kept). How many.
function Stop-OllamaProcesses([int]$WatchSeconds = 3) {
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
