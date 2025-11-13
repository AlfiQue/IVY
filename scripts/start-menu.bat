@echo off
setlocal EnableExtensions EnableDelayedExpansion

pushd "%~dp0.."
if errorlevel 1 (
    echo Impossible d'acceder au dossier du projet.
    exit /b 1
)

:menu
cls
echo ================== IVY Launcher ==================
echo  [ 1] Creer / mettre a jour config.json (CORS par defaut)
echo  [ 2] Installer / mettre a jour les dependances Python
echo  [ 3] Demarrer le serveur API (FastAPI)
echo  [ 4] UI dev : installer deps et lancer Vite (5173)
echo  [ 5] Construire l'UI (Vite build)
echo  [ 6] Servir l'UI construite en statique (5174)
echo  [ 7] Reinitialiser le mot de passe admin
echo  [ 8] Ouvrir la documentation API dans le navigateur
echo  [ 9] Quitter
echo  [10] Construire l'UI puis demarrer l'API (serveur unique)
echo  [11] Demarrer l'API en mode debug (uvicorn --reload)
echo  [12] Arreter le serveur API (port 8000)
echo.
set "choice="
set /p "choice=Choisissez une option [1-12] > "
if not defined choice goto menu

rem Rejeter les entrees non numeriques
for /f "delims=0123456789" %%A in ("%choice%") do (
    echo Option invalide : %choice%
    timeout /t 2 >nul
    goto menu
)

if "%choice%"=="9" goto end
if "%choice%"=="10" goto ui_build_and_start
if "%choice%"=="11" goto serve_debug
if "%choice%"=="12" goto stop_server
if "%choice%"=="1" goto cfg
if "%choice%"=="2" goto deps
if "%choice%"=="3" goto serve
if "%choice%"=="4" goto ui_dev
if "%choice%"=="5" goto ui_build
if "%choice%"=="6" goto ui_static
if "%choice%"=="7" goto reset_admin
if "%choice%"=="8" goto docs

echo Option invalide : %choice%
timeout /t 2 >nul
goto menu

:ensure_venv
if exist .venv\Scripts\python.exe goto activate_venv
echo Creation de l'environnement virtuel (.venv)...
py -3.11 -m venv .venv >nul 2>&1
if errorlevel 1 (
    echo Python 3.11 introuvable via 'py'. Tentative avec python par defaut...
    python -m venv .venv >nul 2>&1
)
if not exist .venv\Scripts\python.exe (
    echo Impossible de creer .venv. Installez Python 3.11 puis relancez.
    pause
    exit /b 1
)

:activate_venv
call .\.venv\Scripts\activate.bat
set "VENV_PY=.venv\Scripts\python.exe"
exit /b 0

:ensure_port_free
set "CHECK_PORT=%~1"
if "%CHECK_PORT%"=="" exit /b 0
set "PORT_PID="
for /f "usebackq tokens=1" %%P in (`powershell -NoProfile -Command "$c = Get-NetTCPConnection -State Listen -LocalPort %CHECK_PORT% -ErrorAction SilentlyContinue; if ($c) { $c[0].OwningProcess }"`) do (
    set "PORT_PID=%%P"
)
if not defined PORT_PID exit /b 0
echo Le port %CHECK_PORT% est deja utilise (PID !PORT_PID!).
echo Fermez le processus ou changez de port avant de relancer.
pause
exit /b 1

:deps
call :ensure_venv
if errorlevel 1 goto menu
echo Mise a jour de pip...
"%VENV_PY%" -m pip install --upgrade pip
echo Installation du projet (mode developpeur)...
"%VENV_PY%" -m pip install --no-cache-dir -e .[dev]
"%VENV_PY%" -m pip install --no-cache-dir --force-reinstall "bcrypt==4.0.1" "passlib[bcrypt]==1.7.4"
if errorlevel 1 (
    echo Installation complete avec erreurs, tentative de repli minimale...
    "%VENV_PY%" -m pip install -r scripts\requirements-dev-no-llama.txt
)
echo Installation de llama-cpp-python (definir CUDA_PATH/CMAKE_ARGS avant pour CUDA)...
"%VENV_PY%" -m pip install llama-cpp-python
pause
goto menu

:serve
call :ensure_venv
if errorlevel 1 goto menu
call :ensure_port_free 8000
if errorlevel 1 goto menu
echo Demarrage du serveur IVY sur http://127.0.0.1:8000 ...
"%VENV_PY%" -c "from app.core.security import maybe_reset_admin; temp = maybe_reset_admin(); import sys; temp and sys.stdout.write('[RESET-ADMIN] Nouveau mot de passe genere: ' + temp + '\n')"
"%VENV_PY%" -m app.cli serve
goto menu

:serve_debug
call :ensure_venv
if errorlevel 1 goto menu
call :ensure_port_free 8000
if errorlevel 1 goto menu
echo Demarrage du serveur IVY en mode debug (uvicorn --reload) sur http://127.0.0.1:8000 ...
"%VENV_PY%" -c "from app.core.security import maybe_reset_admin; temp = maybe_reset_admin(); import sys; temp and sys.stdout.write('[RESET-ADMIN] Nouveau mot de passe genere: ' + temp + '\n')"
"%VENV_PY%" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
goto menu

:stop_server
set "STOPPED_PID="
for /f "usebackq tokens=* delims=" %%P in (`powershell -NoProfile -Command "$conn = Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue; if($conn){$conn | Select-Object -First 1 -ExpandProperty OwningProcess}"`) do (
    set "STOPPED_PID=%%P"
)
if "%STOPPED_PID%"=="" (
    echo Aucun serveur n'ecoute sur le port 8000.
    timeout /t 2 >nul
    goto menu
)
taskkill /PID %STOPPED_PID% /F >nul 2>&1
if errorlevel 1 (
    echo Echec de l'arret du serveur. Essayez de lancer ce script en tant qu'administrateur.
) else (
    echo Serveur API arrete (PID %STOPPED_PID%).
)
timeout /t 2 >nul
goto menu
:install_webui_deps
if not exist webui (
    echo Dossier webui introuvable. Verifiez votre checkout.
    goto menu
)
if not exist webui\package.json (
    echo package.json introuvable dans webui.
    goto menu
)
pushd webui >nul 2>&1
echo Installation des dependances npm...
call npm install
if errorlevel 1 (
    echo npm install a echoue.
    popd >nul 2>&1
    pause
    goto menu
)
call npm pkg get devDependencies."@vitejs/plugin-react" >nul 2>&1
if errorlevel 1 (
    echo Ajout de @vitejs/plugin-react...
    call npm i -D @vitejs/plugin-react
    if errorlevel 1 (
        echo Impossible d'installer @vitejs/plugin-react.
        popd >nul 2>&1
        pause
        goto menu
    )
)
popd >nul 2>&1
exit /b 0

:build_ui
call :install_webui_deps
if errorlevel 1 goto menu
set "VITE_API_URL=http://127.0.0.1:8000"
call :ensure_venv
if errorlevel 1 (
    set "VITE_API_URL="
    goto menu
)
echo Generation des icones...
"%VENV_PY%" scripts\generate_icons.py
if errorlevel 1 (
    echo Echec de scripts\generate_icons.py.
    set "VITE_API_URL="
    pause
    goto menu
)
echo Construction de l'UI (npm run build)...
pushd webui >nul 2>&1
call npm run build
set "VITE_API_URL="
if errorlevel 1 (
    echo npm run build a echoue.
    popd >nul 2>&1
    pause
    goto menu
)
popd >nul 2>&1
exit /b 0

:ui_dev
call :install_webui_deps
if errorlevel 1 goto menu
pushd webui >nul 2>&1
set "VITE_API_URL=http://127.0.0.1:8000"
echo Lancement de Vite (CTRL+C pour arreter)...
call npm run dev
set "VITE_API_URL="
popd >nul 2>&1
goto menu

:ui_build
call :build_ui
if not errorlevel 1 echo Build UI reussi.
pause
goto menu

:ui_static
call :ensure_venv
if errorlevel 1 goto menu
echo Service de webui\dist sur http://127.0.0.1:5174 ...
"%VENV_PY%" -m app.cli ui --path webui\dist --port 5174
goto menu

:ui_build_and_start
call :build_ui
if errorlevel 1 (
    echo Build UI echoue, abandon du lancement de l'API.
    pause
    goto menu
)
goto serve

:cfg
set "JSON={\"host\":\"127.0.0.1\",\"port\":8000,\"cors_origins\":[\"http://127.0.0.1:5173\",\"http://localhost:5173\",\"http://127.0.0.1:5174\",\"http://localhost:5174\"]}"
echo %JSON%>config.json
echo Fichier config.json genere :
type config.json
pause
goto menu

:reset_admin
if not exist app\data mkdir app\data
type NUL > app\data\reset_admin.flag
echo Fichier app\data\reset_admin.flag cree. Redemarrez le serveur pour generer un mot de passe temporaire.
pause
goto menu

:docs
start "" http://127.0.0.1:8000/docs
goto menu

:end
popd
endlocal
exit /b 0



