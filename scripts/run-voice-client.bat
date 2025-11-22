@echo off
setlocal

set "ROOT=%~dp0.."
pushd "%ROOT%"
if errorlevel 1 (
    echo Impossible d'acceder au dossier du projet.
    exit /b 1
)


if not exist ".venv\Scripts\python.exe" goto missing_venv

".venv\Scripts\python.exe" run_voice_client.py
goto end

:missing_venv
echo Environnement virtuel (.venv) introuvable. Lancez d'abord le menu start (option 2 ou 14).
popd
exit /b 1

:end
popd
endlocal
