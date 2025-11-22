[CmdletBinding()]
param(
  [switch]$Coverage,
  [switch]$NoInstall,
  [string]$K = ""
)

$ErrorActionPreference = "Stop"

function Has-Cmd($name) {
  try { Get-Command $name -ErrorAction Stop | Out-Null; return $true } catch { return $false }
}

$useUv = Has-Cmd "uv"

if (-not $NoInstall) {
  $editableOk = $true
  if ($useUv) {
    Write-Host "Installing dev dependencies with uv..."
    uv pip install -e .[dev]
    if ($LASTEXITCODE -ne 0) { $editableOk = $false }
  } elseif (Has-Cmd "python") {
    Write-Host "Installing dev dependencies with pip..."
    python -m pip install --upgrade pip
    python -m pip install -e .[dev]
    if ($LASTEXITCODE -ne 0) { $editableOk = $false }
  } else {
    Write-Error "Neither 'uv' nor 'python' found. Install uv (recommended) or Python 3.11+."
    exit 1
  }
  # Verify essential modules; if missing or editable failed, install minimal deps
  $tmpCheck = Join-Path $env:TEMP ("check_deps." + [System.Guid]::NewGuid().ToString("N") + ".py")
  @"
import sys
mods = [
    'fastapi','httpx','pydantic_settings','itsdangerous','jose','passlib','typer','apscheduler','aiosqlite','prometheus_client','psutil','pytest','pytest_asyncio'
]
missing = []
for name in mods:
    try:
        __import__(name)
    except Exception:
        missing.append(name)
if missing:
    print('MISSING:' + ','.join(missing))
    sys.exit(1)
print('OK')
"@ | Out-File -FilePath $tmpCheck -Encoding ascii
  python $tmpCheck
  $depsOk = $LASTEXITCODE -eq 0
  Remove-Item -ErrorAction SilentlyContinue $tmpCheck
  if (-not $depsOk -or -not $editableOk) {
    Write-Warning "Installing minimal runtime test dependencies..."
    $pkgs = @(
      'pytest','pytest-asyncio',
      'fastapi','httpx','pydantic','pydantic-settings','python-multipart',
      'apscheduler','aiosqlite','prometheus-client','psutil','tzdata','python-dotenv',
      'python-jose[cryptography]','passlib[bcrypt]','itsdangerous','typer[all]','watchdog',
      'pillow','pdf2image','pyzipper','openpyxl','python-pptx','python-docx','click>=8.1.7'
    )
    python -m pip install $pkgs
  }
}

# Build temp pytest config to avoid coverage options if plugins missing
$tmpIni = Join-Path $env:TEMP ("pytest." + [System.Guid]::NewGuid().ToString("N") + ".ini")
@"
[pytest]
addopts = -q
asyncio_mode = auto
testpaths = tests
"@ | Out-File -FilePath $tmpIni -Encoding ascii

$pytestArgs = @("-c", "$tmpIni")
if ($K -and $K.Trim().Length -gt 0) { $pytestArgs += @("-k", $K) }

if ($useUv) { $cmd = @("uv", "run", "pytest") + $pytestArgs }
elseif (Has-Cmd "python") { $cmd = @("python", "-m", "pytest") + $pytestArgs }
else { Write-Error "Neither 'uv' nor 'python' found."; exit 1 }

Write-Host "Running:" ($cmd -join " ")
# Avoid faiss native crashes on some Windows by disabling it for tests
$env:IVY_DISABLE_FAISS = "1"
& $cmd[0] @($cmd[1..($cmd.Length-1)])
$code = $LASTEXITCODE
Remove-Item -ErrorAction SilentlyContinue $tmpIni
exit $code
