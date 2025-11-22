@echo off
setlocal enabledelayedexpansion

rem Git auto-commit and push helper
set "MSG=%*"
if "%MSG%"=="" set "MSG=chore:auto-push"

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
  echo Not inside a git repository.
  exit /b 1
)

set "HAS_CHANGES="
for /f "delims=" %%i in ('git status --porcelain') do set "HAS_CHANGES=1"

if not defined HAS_CHANGES (
  echo No changes to commit. Nothing to push.
  exit /b 0
)

git status --short
git add -A || exit /b 1
git commit -m "%MSG%" || exit /b 1
git push || exit /b 1

echo Push completed.
endlocal
