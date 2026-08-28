# Dot-source from the repository root:
# . .\scripts\use-awf.ps1

$AwfRepoRoot = (Resolve-Path (Join-Path "$PSScriptRoot" "..")).Path

function Invoke-AwfRepoCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [object[]]$Arguments = @()
    )

    $commandPath = Join-Path $AwfRepoRoot "backend\.venv\Scripts\$Name.exe"
    if (-not (Test-Path -LiteralPath $commandPath)) {
        Write-Error "AWF command '$Name' was not found at '$commandPath'. Run '.\scripts\bootstrap.ps1' from the repo root first."
        return
    }

    & $commandPath @Arguments
}

function awf { Invoke-AwfRepoCommand -Name "awf" -Arguments $args }

function awf-setup { Invoke-AwfRepoCommand -Name "awf-setup" -Arguments $args }

function awf-secret { Invoke-AwfRepoCommand -Name "awf-secret" -Arguments $args }

function awf-speech { Invoke-AwfRepoCommand -Name "awf-speech" -Arguments $args }

function awf-gui {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Write-Error "npm was not found. Install Node.js/npm, then rerun '.\scripts\bootstrap.ps1' if frontend dependencies are missing."
        return
    }

    Push-Location $AwfRepoRoot
    try { & npm --prefix frontend run dev @args }
    finally { Pop-Location }
}

function awf-cli {
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        Write-Error "node was not found. Install Node.js/npm, then rerun '.\scripts\bootstrap.ps1' if frontend dependencies are missing."
        return
    }

    $entryPoint = Join-Path $AwfRepoRoot "frontend\cli\dist\cli.js"
    if (-not (Test-Path -LiteralPath $entryPoint)) {
        Write-Error "The AWF terminal UI is not built. Run 'npm --prefix frontend run build' from the repo root first."
        return
    }

    Push-Location $AwfRepoRoot
    try { & node "frontend\cli\dist\cli.js" @args }
    finally { Pop-Location }
}

Write-Host "AWF commands loaded for this PowerShell session: awf, awf-setup, awf-secret, awf-speech, awf-gui, awf-cli"
