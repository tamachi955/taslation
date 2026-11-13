<#
Helpers of the install check (.github/workflows/install-check.yml), dot-sourced by each of its steps (PowerShell 7).

Every check a step makes is written down in results.jsonl in the check folder (RUNNER_TEMP\install-check), and what
the job summary gives besides (the machine, the times, the sizes) in facts.json there; the summary step makes the
summary from both, and the files go into the job's artifact. Nothing here installs or changes anything: it looks.
The folder TASlation is installed in is INSTALL_DIR, which the step that unpacks it sets for the steps after it.
#>
Set-StrictMode -Version 3.0

$CheckDir = Join-Path $env:RUNNER_TEMP 'install-check'
$null = New-Item -ItemType Directory -Force -Path $CheckDir
$ResultsFile = Join-Path $CheckDir 'results.jsonl'
$FactsFile = Join-Path $CheckDir 'facts.json'
$InstallDir = $env:INSTALL_DIR
$VenvPy = $null
$VenvPyw = $null
if ($InstallDir) {
    $VenvPy = Join-Path $InstallDir '.venv\Scripts\python.exe'
    $VenvPyw = Join-Path $InstallDir '.venv\Scripts\pythonw.exe'
}
$OllamaHome = Join-Path $env:LOCALAPPDATA 'Programs\Ollama'  # where Ollama's installer puts it (install.ps1 looks there)
$OllamaUrl = 'http://127.0.0.1:11434'
$OllamaLog = Join-Path $env:LOCALAPPDATA 'Ollama\server.log'  # the log of the server Ollama's own app starts
$TranslatorModel = 'taslation-plamo3-translate-2b'  # the translation model install.ps1 installs for English
# Output of programs is read as UTF-8 (install.ps1 and Python write it); there may be no console to set it on.
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

# A text for a workflow command (::error:: and the like), where %, CR and LF are markup, and in a property : and , too.
function ConvertTo-CommandText([string]$Text, [switch]$Property) {
    $t = $Text.Replace('%', '%25').Replace("`r", '%0D').Replace("`n", '%0A')
    if ($Property) { $t = $t.Replace(':', '%3A').Replace(',', '%2C') }
    return $t
}

# One check of step *Step*: *Ok* $true (passed), $false (failed: Complete-Step then fails the step) or $null (cannot be
# shown on this runner: said plainly, as a warning, and not counted as a failure).
function Add-Check([string]$Step, [string]$What, $Ok, [string]$Detail = '') {
    if ($null -ne $Ok) { $Ok = [bool]$Ok }
    $mark = 'ok'
    if ($Ok -eq $false) { $mark = 'FAILED' } elseif ($null -eq $Ok) { $mark = 'not shown' }
    $line = '{0,-10} {1}' -f $mark, $What
    if ($Detail) { $line += " ($Detail)" }
    Write-Host $line
    $message = $What
    if ($Detail) { $message += " ($Detail)" }
    if ($Ok -eq $false) {
        Write-Host ('::error title={0}::{1}' -f (ConvertTo-CommandText $Step -Property), (ConvertTo-CommandText $message))
    } elseif ($null -eq $Ok) {
        Write-Host ('::warning title={0}::{1}' -f (ConvertTo-CommandText $Step -Property), (ConvertTo-CommandText "not shown: $message"))
    }
    $record = [ordered]@{ step = $Step; what = $What; ok = $Ok; detail = $Detail }
    Add-Content -LiteralPath $ResultsFile -Value ($record | ConvertTo-Json -Compress) -Encoding utf8
}

function Get-Results {
    if (-not (Test-Path -LiteralPath $ResultsFile)) { return @() }
    return @(Get-Content -LiteralPath $ResultsFile -Encoding utf8 | Where-Object { $_ } | ForEach-Object { $_ | ConvertFrom-Json })
}

# The end of a step: exit code 1 when one of its checks failed, else 0 (whatever the last program's exit code was).
function Complete-Step([string]$Step) {
    $failed = @(Get-Results | Where-Object { $_.step -eq $Step -and $_.ok -eq $false })
    if ($failed.Count -gt 0) { exit 1 }
    exit 0
}

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

# The fixed drives, with their size and free space in GB.
function Get-Drives {
    return @(Get-CimInstance -ClassName Win32_LogicalDisk -Filter 'DriveType=3' | ForEach-Object {
        [ordered]@{ drive = $_.DeviceID; size_gb = [math]::Round($_.Size / 1GB, 1); free_gb = [math]::Round($_.FreeSpace / 1GB, 1) }
    })
}

# The bytes all network adapters have received since they started; $null when Windows does not say.
function Get-ReceivedBytes {
    try {
        return [long](@(Get-NetAdapterStatistics -ErrorAction Stop) | Measure-Object -Property ReceivedBytes -Sum).Sum
    } catch { return $null }
}

# The size of a folder and everything in it, in GB; $null when there is no such folder.
function Get-FolderGB([string]$Path) {
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return $null }
    $sum = (Get-ChildItem -LiteralPath $Path -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
    if ($null -eq $sum) { $sum = 0 }
    return [math]::Round($sum / 1GB, 2)
}

# Ollama's ollama.exe as install.ps1 finds it, else on the PATH as Windows keeps it now (a step's own PATH is the
# runner's, from before the install); $null when there is none.
function Find-OllamaExe {
    $user = Join-Path $OllamaHome 'ollama.exe'
    if (Test-Path -LiteralPath $user) { return $user }
    $found = @(Get-Command ollama -CommandType Application -ErrorAction SilentlyContinue)
    if ($found.Count -gt 0) { return $found[0].Source }
    $saved = [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + [Environment]::GetEnvironmentVariable('Path', 'Machine')
    foreach ($dir in ($saved -split ';')) {
        if (-not $dir) { continue }
        $exe = Join-Path $dir 'ollama.exe'
        if (Test-Path -LiteralPath $exe) { return $exe }
    }
    return $null
}

# Whether Ollama's server answers at its usual address (asking it starts nothing).
function Test-OllamaAnswers {
    try {
        $null = Invoke-RestMethod -Uri "$OllamaUrl/api/version" -TimeoutSec 5
        return $true
    } catch { return $false }
}

# The models Ollama's server has, by name; $null when it does not answer.
function Get-OllamaModels {
    try {
        return @((Invoke-RestMethod -Uri "$OllamaUrl/api/tags" -TimeoutSec 10).models | ForEach-Object { $_.name })
    } catch { return $null }
}

# A variable of the user as Windows keeps it (HKCU\Environment), which every process started later gets; $null when
# it is not there.
function Get-UserVariable([string]$Name) {
    try { return [string](Get-ItemPropertyValue -LiteralPath 'HKCU:\Environment' -Name $Name -ErrorAction Stop) } catch { return $null }
}

# Another process's environment, read from its environment block (where Windows keeps the variables a process was
# started with and has set since), as tools such as Process Explorer read it. For the 64-bit processes of this user,
# from a 64-bit PowerShell.
if (-not ('InstallCheck.ProcessEnvironment' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;

namespace InstallCheck {
    public static class ProcessEnvironment {
        [StructLayout(LayoutKind.Sequential)]
        struct BasicInformation {
            public IntPtr ExitStatus;
            public IntPtr PebBaseAddress;
            public IntPtr AffinityMask;
            public IntPtr BasePriority;
            public IntPtr UniqueProcessId;
            public IntPtr InheritedFromUniqueProcessId;
        }

        [DllImport("ntdll.dll")]
        static extern int NtQueryInformationProcess(IntPtr process, int infoClass, ref BasicInformation info, int size, out int returned);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern IntPtr OpenProcess(int access, bool inherit, int id);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool ReadProcessMemory(IntPtr process, IntPtr address, byte[] buffer, IntPtr size, out IntPtr read);
        [DllImport("kernel32.dll")]
        static extern bool CloseHandle(IntPtr handle);

        const int QueryInformation = 0x0400;
        const int VmRead = 0x0010;
        const int Page = 4096;

        static byte[] ReadBytes(IntPtr process, IntPtr address, int size) {
            byte[] buffer = new byte[size];
            IntPtr read;
            if (!ReadProcessMemory(process, address, buffer, new IntPtr(size), out read)) {
                throw new Win32Exception(Marshal.GetLastWin32Error());
            }
            return buffer;
        }

        static IntPtr ReadPointer(IntPtr process, IntPtr address) {
            return new IntPtr(BitConverter.ToInt64(ReadBytes(process, address, 8), 0));
        }

        // The NAME=value strings of process *id*. The 64-bit layout: PEB.ProcessParameters at 0x20, and in it
        // (RTL_USER_PROCESS_PARAMETERS) Environment at 0x80 and EnvironmentSize at 0x3F0; without a size, page by page
        // up to the empty string that ends the block.
        public static string[] Read(int id) {
            if (IntPtr.Size != 8) {
                throw new PlatformNotSupportedException("a 64-bit PowerShell is needed");
            }
            IntPtr process = OpenProcess(QueryInformation | VmRead, false, id);
            if (process == IntPtr.Zero) {
                throw new Win32Exception(Marshal.GetLastWin32Error());
            }
            try {
                BasicInformation info = new BasicInformation();
                int returned;
                int status = NtQueryInformationProcess(process, 0, ref info, Marshal.SizeOf(info), out returned);
                if (status != 0) {
                    throw new Win32Exception(string.Format("NtQueryInformationProcess said 0x{0:X8}", status));
                }
                IntPtr parameters = ReadPointer(process, IntPtr.Add(info.PebBaseAddress, 0x20));
                IntPtr environment = ReadPointer(process, IntPtr.Add(parameters, 0x80));
                long size = ReadPointer(process, IntPtr.Add(parameters, 0x3F0)).ToInt64();
                string block;
                if (size > 0 && size <= 0x100000) {
                    block = Encoding.Unicode.GetString(ReadBytes(process, environment, (int)size));
                } else {
                    StringBuilder text = new StringBuilder();
                    for (int offset = 0; offset < 0x100000; offset += Page) {
                        text.Append(Encoding.Unicode.GetString(ReadBytes(process, IntPtr.Add(environment, offset), Page)));
                        if (text.ToString().IndexOf("\0\0", StringComparison.Ordinal) >= 0) {
                            break;
                        }
                    }
                    block = text.ToString();
                }
                int end = block.IndexOf("\0\0", StringComparison.Ordinal);
                if (end >= 0) {
                    block = block.Substring(0, end);
                }
                return block.Split(new char[] { '\0' }, StringSplitOptions.RemoveEmptyEntries);
            } finally {
                CloseHandle(process);
            }
        }
    }
}
'@
}

# The variable *Name* in the environment of process *Id* as that process sees it: its value, '' for none; throws when
# the process's environment cannot be read.
function Get-ProcessVariable([int]$Id, [string]$Name) {
    foreach ($entry in [InstallCheck.ProcessEnvironment]::Read($Id)) {
        $i = $entry.IndexOf('=', 1)  # (from 1: Windows keeps entries such as =C:=C:\ that begin with one)
        if ($i -gt 0 -and [string]::Equals($entry.Substring(0, $i), $Name, [StringComparison]::OrdinalIgnoreCase)) {
            return $entry.Substring($i + 1)
        }
    }
    return ''
}
