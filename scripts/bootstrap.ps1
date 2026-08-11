param(
    [switch]$SkipFrontend,
    [switch]$SkipSpeech
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvPython = Join-Path $RepoRoot "backend\.venv\Scripts\python.exe"
$VenvAwfSetup = Join-Path $RepoRoot "backend\.venv\Scripts\awf-setup.exe"
$VenvAwfSpeech = Join-Path $RepoRoot "backend\.venv\Scripts\awf-speech.exe"
$VenvAwf = Join-Path $RepoRoot "backend\.venv\Scripts\awf.exe"

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Body
    )
    Write-Host "==> $Name"
    & $Body
}

Set-Location $RepoRoot
New-Item -ItemType Directory -Force -Path (Join-Path $RepoRoot "cache\temp") | Out-Null

if (-not (Test-Path $VenvPython)) {
    Invoke-Step "Create backend venv" {
        py -m venv (Join-Path $RepoRoot "backend\.venv")
    }
}

Invoke-Step "Upgrade pip" {
    & $VenvPython -m pip install --upgrade pip
}

Invoke-Step "Install AWF base package" {
    & $VenvPython -m pip install -e ".[dev]"
}

Invoke-Step "Install hardware-selected backend dependencies" {
    & $VenvAwfSetup --install --verify
}

Invoke-Step "Bootstrap local state" {
    & $VenvAwfSetup
}

if (-not $SkipSpeech) {
    Invoke-Step "Acquire speech models" {
        & $VenvAwfSpeech models sync
    }
    Invoke-Step "Verify speech models" {
        & $VenvAwfSpeech models verify
    }
}

if (-not $SkipFrontend -and (Get-Command npm -ErrorAction SilentlyContinue)) {
    Invoke-Step "Install frontend dependencies" {
        npm --prefix frontend install
    }
}

Invoke-Step "Doctor" {
    & $VenvAwf doctor
}

Write-Host ""
Write-Host "Next command:"
Write-Host '.\backend\.venv\Scripts\awf run assistant-default@1.0.0 --objective "check the system"'
