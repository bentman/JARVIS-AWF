param(
    [switch]$SkipFrontend,
    [switch]$SkipSpeech
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvPython = Join-Path $RepoRoot "backend\.venv\Scripts\python.exe"
$VenvRoot = Join-Path $RepoRoot "backend\.venv"
$VenvAwfSpeech = Join-Path $RepoRoot "backend\.venv\Scripts\awf-speech.exe"
$VenvAwf = Join-Path $RepoRoot "backend\.venv\Scripts\awf.exe"
$ReportsDir = Join-Path $RepoRoot "reports\diagnostics"
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$ReportPath = Join-Path $ReportsDir "$Timestamp-bootstrap.txt"

New-Item -ItemType Directory -Force -Path $ReportsDir | Out-Null
Set-Content -LiteralPath $ReportPath -Value @(
    "AWF bootstrap report"
    "started_at=$((Get-Date).ToString('o'))"
    "repo_root=$RepoRoot"
    "report_path=$ReportPath"
    ""
)

try {

function Write-Log {
    param([string]$Message)
    Write-Host $Message
    Add-Content -LiteralPath $ReportPath -Value $Message
}

Write-Log "Bootstrap report: $ReportPath"

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Body
    )
    Write-Log "==> $Name"
    & $Body
}

function Invoke-Native {
    param(
        [Parameter(Mandatory=$true, Position=0)]
        [string]$Command,
        [Parameter(ValueFromRemainingArguments=$true, Position=1)]
        [string[]]$Arguments
    )
    Write-Log "command: $Command $($Arguments -join ' ')"
    & $Command @Arguments 2>&1 | Tee-Object -FilePath $ReportPath -Append
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "Command failed ($exitCode): $Command $($Arguments -join ' ')"
    }
}

Set-Location $RepoRoot
New-Item -ItemType Directory -Force -Path (Join-Path $RepoRoot "cache\temp") | Out-Null

$PyVenvCfg = Join-Path $VenvRoot "pyvenv.cfg"
if ((Test-Path $PyVenvCfg) -and (Test-Path (Join-Path $VenvRoot "bin\python"))) {
    $Cfg = Get-Content -LiteralPath $PyVenvCfg -Raw
    if ($Cfg -match "/mnt/" -or $Cfg -match "home = /") {
        throw "backend\.venv was created by Linux/WSL. Remove backend\.venv and rerun scripts\bootstrap.ps1 from Windows PowerShell."
    }
}

function Resolve-HostPythonCommand {
    $Candidates = @(
        @("py"),
        @("py", "-3.14"),
        @("py", "-3.13"),
        @("py", "-3.12"),
        @("python"),
        @("python3"),
        @("python3.14"),
        @("python3.13"),
        @("python3.12")
    )
    foreach ($Cmd in $Candidates) {
        $Exe = $Cmd[0]
        $Args = if ($Cmd.Length -gt 1) { $Cmd[1..($Cmd.Length-1)] } else { @() }
        if (Get-Command $Exe -ErrorAction SilentlyContinue) {
            try {
                $VersionOutput = & $Exe @Args -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
                if ($LASTEXITCODE -eq 0 -and $VersionOutput) {
                    $Parts = $VersionOutput.Trim().Split('.')
                    if ($Parts.Length -ge 2) {
                        $Major = [int]$Parts[0]
                        $Minor = [int]$Parts[1]
                        if ($Major -eq 3 -and $Minor -ge 12 -and $Minor -lt 15) {
                            return ,$Cmd
                        }
                    }
                }
            } catch {
                # Continue trying next candidate
            }
        }
    }
    throw "No compatible Python executable (>=3.12,<3.15) found. Install Python 3.12, 3.13, or 3.14 (ARM64 native from python.org on ARM64 hosts)."
}

if (-not (Test-Path $VenvPython)) {
    $HostPythonCmd = Resolve-HostPythonCommand
    $HostExe = $HostPythonCmd[0]
    $HostArgs = if ($HostPythonCmd.Length -gt 1) { $HostPythonCmd[1..($HostPythonCmd.Length-1)] } else { @() }
    Invoke-Step "Create backend venv using $($HostPythonCmd -join ' ')" {
        Invoke-Native $HostExe ($HostArgs + @("-m", "venv", (Join-Path $RepoRoot "backend\.venv")))
    }
}

Invoke-Step "Upgrade pip" {
    Invoke-Native $VenvPython @("-m", "pip", "install", "--upgrade", "pip")
}

Invoke-Step "Install AWF base package" {
    Invoke-Native $VenvPython @("-m", "pip", "install", "-e", ".[dev]")
}

Invoke-Step "Provision hardware-selected backend dependencies" {
    Invoke-Native $VenvPython @("-m", "awf.setup", "--provision")
}

Invoke-Step "Install hardware-selected backend dependencies" {
    Invoke-Native $VenvPython @("-m", "awf.setup", "--install", "--verify")
}

Invoke-Step "Profile hardware readiness" {
    Invoke-Native $VenvPython @("scripts\validate_backend.py", "profile")
}

Invoke-Step "Bootstrap local state" {
    Invoke-Native $VenvPython @("-m", "awf.setup")
}

if (-not $SkipSpeech) {
    Invoke-Step "Acquire speech models" {
        Invoke-Native $VenvAwfSpeech @("models", "sync")
    }
    Invoke-Step "Verify speech models" {
        Invoke-Native $VenvAwfSpeech @("models", "verify")
    }
} else {
    Write-Host "==> Skip speech setup"
    Write-Host "    Speech is part of the normal operator path; use -SkipSpeech only for dependency outage triage."
}

if (-not $SkipFrontend -and (Get-Command npm -ErrorAction SilentlyContinue)) {
    Invoke-Step "Install frontend dependencies" {
        Invoke-Native "npm" @("--prefix", "frontend", "install")
    }
}

Invoke-Step "Doctor" {
    Invoke-Native $VenvAwf @("doctor")
}

Write-Log ""
Write-Log "Next commands:"
Write-Log '. .\scripts\use-awf.ps1'
Write-Log 'awf run assistant-default@1.0.0 --objective "check the system"'

} finally {
    Write-Log ""
    Write-Log "Bootstrap report: $ReportPath"
}
