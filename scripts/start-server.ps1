[CmdletBinding()]
param(
  [switch]$NoInstall,
  [switch]$SkipChecks
)

$ErrorActionPreference = "Stop"

function Has-Cmd($name) {
  try { Get-Command $name -ErrorAction Stop | Out-Null; return $true } catch { return $false }
}

$useUv = Has-Cmd "uv"

if (-not $NoInstall) {
  if ($useUv) {
    Write-Host "Installing app with uv..."
    uv pip install -e .
  } elseif (Has-Cmd "python") {
    Write-Host "Installing app with pip..."
    python -m pip install --upgrade pip
    python -m pip install -e .
  } else {
    Write-Error "Neither 'uv' nor 'python' found."
    exit 1
  }
}

if (-not $SkipChecks) {
  if ($useUv) {
    uv run python scripts/check_env.py
  } else {
    python scripts/check_env.py
  }
}

Write-Host "Starting IVY server..."
if ($useUv) {
  uv run python -m app.cli serve
} else {
  python -m app.cli serve
}

