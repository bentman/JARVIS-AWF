param(
    [switch]$SkipFrontend,
    [switch]$SkipSpeech
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvPython = Join-Path $RepoRoot "backend\.venv\Scripts\python.exe"
$VenvAwfSpeech = Join-Path $RepoRoot "backend\.venv\Scripts\awf-speech.exe"
$VenvAwf = Join-Path $RepoRoot "backend\.venv\Scripts\awf.exe"
$ReportsDir = Join-Path $RepoRoot "reports\diagnostics"
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$ReportPath = Join-Path $ReportsDir "$Timestamp-bootstrap.txt"

New-Item -ItemType Directory -Force -Path $ReportsDir | Out-Null
Start-Transcript -Path $ReportPath -Force | Out-Null

try {

Write-Host "Bootstrap report: $ReportPath"

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Body
    )
    Write-Host "==> $Name"
    & $Body
}

function Invoke-Native {
    param(
        [Parameter(Mandatory=$true, Position=0)]
        [string]$Command,
        [Parameter(ValueFromRemainingArguments=$true, Position=1)]
        [string[]]$Arguments
    )
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed ($LASTEXITCODE): $Command $($Arguments -join ' ')"
    }
}

Set-Location $RepoRoot
New-Item -ItemType Directory -Force -Path (Join-Path $RepoRoot "cache\temp") | Out-Null

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
    & $VenvAwf doctor
}

Write-Host ""
Write-Host "Next command:"
Write-Host '.\backend\.venv\Scripts\awf run assistant-default@1.0.0 --objective "check the system"'

} finally {
    Stop-Transcript | Out-Null
    Write-Host ""
    Write-Host "Bootstrap report: $ReportPath"
}
