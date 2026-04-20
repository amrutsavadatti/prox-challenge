$Shell = "powershell"
if ($args.Count -gt 0) {
    $Shell = $args[0].ToLowerInvariant()
}
if ($Shell -notin @("powershell", "cmd")) {
    throw "Unsupported shell mode '$Shell'. Use 'powershell' or 'cmd'."
}

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $ScriptDir ".."))
$PythonVersion = "3.12"
$NodeVersion = "20.19.0"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Ensure-UserPathEntry {
    param([string]$PathEntry)

    if (-not (Test-Path $PathEntry)) {
        return
    }

    $currentProcessPath = $env:PATH -split ';'
    if (-not ($currentProcessPath -contains $PathEntry)) {
        $env:PATH = "$PathEntry;$env:PATH"
    }

    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $userEntries = @()
    if ($userPath) {
        $userEntries = $userPath -split ';' | Where-Object { $_ }
    }

    if (-not ($userEntries -contains $PathEntry)) {
        $updated = @($PathEntry) + $userEntries
        [Environment]::SetEnvironmentVariable("Path", ($updated -join ';'), "User")
    }
}

function Resolve-VoltaExecutable {
    $command = Get-Command volta -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $candidates = @(
        (Join-Path $env:ProgramFiles "Volta\volta.exe"),
        (Join-Path $env:ProgramFiles "Volta\bin\volta.exe"),
        (Join-Path $env:LOCALAPPDATA "Volta\volta.exe"),
        (Join-Path $env:LOCALAPPDATA "Volta\bin\volta.exe")
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    return $null
}

function Refresh-Path {
    $knownPaths = @(
        "$env:USERPROFILE\.local\bin",
        "$env:ProgramFiles\Volta",
        "$env:ProgramFiles\Volta\bin",
        "$env:LOCALAPPDATA\Volta\bin"
    )

    foreach ($pathEntry in $knownPaths) {
        Ensure-UserPathEntry $pathEntry
    }
}

function Ensure-Uv {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        return
    }

    Write-Step "Installing uv"
    & ([ScriptBlock]::Create((Invoke-RestMethod "https://astral.sh/uv/install.ps1")))
    Refresh-Path

    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "uv was installed but is not on PATH. Add $env:USERPROFILE\.local\bin to PATH and rerun."
    }
}

function Ensure-Volta {
    $existingVolta = Resolve-VoltaExecutable
    if ($existingVolta) {
        return $existingVolta
    }

    Write-Step "Installing Volta"
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Volta installation on Windows requires winget. Install Microsoft's App Installer / winget and rerun the setup script."
    }

    winget install Volta.Volta --exact --accept-package-agreements --accept-source-agreements
    Refresh-Path

    $voltaExe = Resolve-VoltaExecutable
    if (-not $voltaExe) {
        throw "Volta appears to be installed, but this shell cannot find volta.exe yet. Close the terminal, open a new one, and rerun the setup script."
    }

    & $voltaExe setup | Out-Null
    Refresh-Path
    return $voltaExe
}

function Ensure-NodeShims {
    $shimPaths = @(
        "$env:LOCALAPPDATA\Volta\bin",
        "$env:ProgramFiles\Volta",
        "$env:ProgramFiles\Volta\bin"
    )

    foreach ($pathEntry in $shimPaths) {
        Ensure-UserPathEntry $pathEntry
    }
}

function Copy-EnvFile {
    $envPath = Join-Path $RepoRoot ".env"
    $examplePath = Join-Path $RepoRoot ".env.example"

    if (Test-Path $envPath) {
        Write-Step ".env already exists, leaving it untouched"
        return
    }

    if (-not (Test-Path $examplePath)) {
        throw ".env.example is missing from the repository root."
    }

    Write-Step "Creating .env from .env.example"
    Copy-Item $examplePath $envPath
}

Write-Step "Preparing toolchain"
Refresh-Path
Ensure-Uv
$voltaExe = Ensure-Volta

Write-Step "Installing Node.js $NodeVersion with Volta"
& $voltaExe install "node@$NodeVersion"
Ensure-NodeShims
Refresh-Path

Write-Step "Installing Python $PythonVersion with uv"
uv python install $PythonVersion

Copy-EnvFile

Write-Step "Installing backend dependencies"
Push-Location $RepoRoot
try {
    uv sync --python $PythonVersion
}
finally {
    Pop-Location
}

Write-Step "Installing frontend dependencies"
Push-Location (Join-Path $RepoRoot "frontend")
try {
    npm install
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Open $RepoRoot\.env"
Write-Host "2. Add your API keys"
Write-Host "3. Close this shell/terminal session completely"
Write-Host "4. Open a fresh terminal"
if ($Shell -eq "cmd") {
    Write-Host "5. Start the backend:"
    Write-Host '   set PYTHONPATH=src && uv run uvicorn prox_agent.api:app --port 8000 --reload'
    Write-Host "6. Start the frontend:"
    Write-Host '   cd frontend && npm run dev'
}
else {
    Write-Host "5. Start the backend:"
    Write-Host '   $env:PYTHONPATH = "src"; uv run uvicorn prox_agent.api:app --port 8000 --reload'
    Write-Host "6. Start the frontend:"
    Write-Host '   Set-Location frontend; npm run dev'
}
Write-Host ""
Write-Host "Installed versions:"
Write-Host "- Python $PythonVersion via uv"
Write-Host "- Node $NodeVersion via Volta"
Write-Host ""
Write-Host "PATH updates were written to your user environment so future terminals can find uv and Volta-managed Node."
Write-Host "Close this terminal before running the app so the new PATH entries are picked up cleanly."
