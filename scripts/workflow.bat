@echo off
setlocal EnableExtensions EnableDelayedExpansion

:: Demande le nom de branche si non fourni
if "%~1"=="" (
  set /p "NAME=Nom de la branche (ex: llm-spec): "
) else (
  set "NAME=%~1"
)

if "%NAME%"=="" (
  echo Aucun nom fourni. Abandon.
  exit /b 1
)

set "BRANCH=feature/%NAME%"

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
  echo Pas de depot git detecte.
  exit /b 1
)

:: Creation/bascule branche
git show-ref --verify --quiet refs/heads/%BRANCH%
if errorlevel 1 (
  echo Creation de la branche %BRANCH% ...
  git checkout -b "%BRANCH%" || exit /b 1
) else (
  echo Bascule sur la branche existante %BRANCH% ...
  git checkout "%BRANCH%" || exit /b 1
)

git status --short
echo Branche active: %BRANCH%
echo.
echo Saisis le message de commit (laisser vide pour annuler le push).
set "MSG="
set /p "MSG=Message de commit: "
if "%MSG%"=="" (
  echo Aucun commit/push effectue.
  exit /b 0
)

git add -A || exit /b 1
git commit -m "%MSG%" || exit /b 1
git push || exit /b 1

echo Push termine sur %BRANCH%.
endlocal
