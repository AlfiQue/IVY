@echo off
setlocal enabledelayedexpansion
REM Jump to repo root (one level up from scripts\)
pushd "%~dp0.."

if not exist .venv (
  python -m venv .venv
)
call .venv\Scripts\activate

REM Try using uv at repo root
pip install --upgrade uv >NUL 2>&1
uv --version >NUL 2>&1
if %errorlevel%==0 (
  echo Installing project with uv (editable)...
  uv pip install -e .
  if %errorlevel% neq 0 (
    echo uv install failed. Falling back to pip with minimal requirements (no llama-cpp).
    python -m pip install --upgrade pip
    pip install -r scripts\requirements-dev-no-llama.txt
  )
) else (
  echo uv not available. Using pip with minimal requirements (no llama-cpp).
  python -m pip install --upgrade pip
  pip install -r scripts\requirements-dev-no-llama.txt
)

echo Starting IVY server...
python -m app.cli serve

popd
endlocal
