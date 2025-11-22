@echo off
setlocal EnableExtensions EnableDelayedExpansion

:: Si un nom est passé en argument, on l'utilise, sinon on demande à l'utilisateur.
if "%~1"=="" (
  set /p "NAME=Nom de la branche (sans espace, ex: llm-spec): "
) else (
  set "NAME=%~1"
)

if "%NAME%"=="" (
  echo Aucun nom fourni. Abandon.
  exit /b 1
)

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
  echo Pas de depot git detecte.
  exit /b 1
)

set "BRANCH=feature/%NAME%"

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

endlocal
