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

if (-not (Test-Path $VenvPython)) {
    Invoke-Step "Create backend venv" {
        Invoke-Native "py" @("-3.12", "-m", "venv", (Join-Path $RepoRoot "backend\.venv"))
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
