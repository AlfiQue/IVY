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
echo  [13] Telecharger le modele d'embeddings BAAI/bge-m3 (Hugging Face)
echo  [14] Installer / mettre a jour le client vocal (deps + ressources)
echo  [15] Installer PyTorch CUDA (cu121)
echo  [16] Optimiser le LLM (auto-tune complet)
echo  [17] Ouvrir la page "Taches & Programmation"
echo  [18] Packager le client vocal (PyInstaller)
echo.
set "choice="
set /p "choice=Choisissez une option [1-17] > "
if not defined choice goto menu

for /f "delims=0123456789" %%A in ("%choice%") do (
    echo Option invalide : %choice%
    timeout /t 2 >nul
    goto menu
)

if "%choice%"=="9" goto end
if "%choice%"=="10" goto ui_build_and_start
if "%choice%"=="11" goto serve_debug
if "%choice%"=="12" goto stop_server
if "%choice%"=="13" goto download_bge
if "%choice%"=="14" goto voice_setup
if "%choice%"=="15" goto install_torch_cuda
if "%choice%"=="16" goto tune_llm_full
if "%choice%"=="17" goto open_taskhub
if "%choice%"=="18" goto package_voice
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

:deps
call :ensure_venv
if errorlevel 1 goto menu
echo Installation / mise a jour des dependances Python...
"%VENV_PY%" -m pip install --upgrade pip setuptools wheel
"%VENV_PY%" -m pip install --no-cache-dir -e .[dev]
if errorlevel 1 (
    echo Echec de l'installation editable, tentative requirements-dev-no-llama...
    "%VENV_PY%" -m pip install -r scripts\requirements-dev-no-llama.txt
)
echo Installation de llama-cpp-python...
"%VENV_PY%" -m pip install llama-cpp-python
if exist llama_cpp (
  echo Suppression du stub local llama_cpp...
  rmdir /S /Q llama_cpp >nul 2>&1
)
pause
goto menu

:serve
call :ensure_venv
if errorlevel 1 goto menu
echo Demarrage du serveur IVY sur http://127.0.0.1:8000 ...
"%VENV_PY%" -m app.cli serve
set "SERV_EXIT=%ERRORLEVEL%"
if not "%SERV_EXIT%"=="0" (
    echo Serveur IVY termine avec le code %SERV_EXIT%.
    pause
)
goto menu

:serve_debug
call :ensure_venv
if errorlevel 1 goto menu
echo Demarrage du serveur IVY (debug --reload)...
set "PYTHONPATH=%CD%"
"%VENV_PY%" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
set "PYTHONPATH="
set "SERV_EXIT=%ERRORLEVEL%"
if not "%SERV_EXIT%"=="0" (
    echo Serveur debug termine avec le code %SERV_EXIT%.
    pause
)
goto menu

:stop_server
set "PID="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8000" ^| findstr LISTENING') do (
    set PID=%%P
)
if not defined PID (
    echo Aucun processus en ecoute sur le port 8000.
    timeout /t 2 >nul
    goto menu
)
echo Tentative d'arret du serveur (PID %PID%)...
taskkill /PID %PID% /F >nul 2>&1
if errorlevel 1 (
    echo Echec de l'arret du serveur. Essayez en tant qu'administrateur.
    timeout /t 2 >nul
    goto menu
)
echo Serveur API arrete (PID %PID%).
set "PID="
timeout /t 2 >nul
goto menu

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
if errorlevel 1 goto menu
echo Build UI termine.
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
call :ensure_venv
if errorlevel 1 goto menu
echo Build reussi. Lancement du serveur (CTRL+C pour arreter)...
"%VENV_PY%" -m app.cli serve
set "SERV_EXIT=%ERRORLEVEL%"
if not "%SERV_EXIT%"=="0" (
    echo Serveur IVY termine avec le code %SERV_EXIT%.
    pause
)
goto menu
:build_ui
call :install_webui_deps
if errorlevel 1 goto menu
call :ensure_venv
if errorlevel 1 goto menu
echo Generation des icones...
"%VENV_PY%" scripts\generate_icons.py
if errorlevel 1 (
    echo Echec de la generation des icones.
    pause
    exit /b 1
)
echo Construction de l'UI (npm run build)...
pushd webui >nul 2>&1
set "VITE_API_URL=http://127.0.0.1:8000"
echo Nettoyage du cache TypeScript...
call npx tsc --build --clean >nul 2>&1
if errorlevel 1 (
    echo Echec du nettoyage TypeScript.
    set "VITE_API_URL="
    popd >nul 2>&1
    pause
    exit /b 1
)
call npm run build
set "VITE_API_URL="
if errorlevel 1 (
    echo npm run build a echoue.
    popd >nul 2>&1
    pause
    exit /b 1
)
popd >nul 2>&1
exit /b 0

:install_webui_deps
if not exist webui (
    echo Dossier webui introuvable. Verifiez votre checkout.
    exit /b 1
)
if not exist webui\package.json (
    echo package.json introuvable dans webui.
    exit /b 1
)
pushd webui >nul 2>&1
echo Installation des dependances npm...
call npm install
if errorlevel 1 (
    echo npm install a echoue.
    popd >nul 2>&1
    pause
    exit /b 1
)
call npm pkg get devDependencies."@vitejs/plugin-react" >nul 2>&1
if errorlevel 1 (
    echo Ajout de @vitejs/plugin-react...
    call npm i -D @vitejs/plugin-react
    if errorlevel 1 (
        echo Impossible d'installer @vitejs/plugin-react.
        popd >nul 2>&1
        pause
        exit /b 1
    )
)
popd >nul 2>&1
exit /b 0

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

:download_bge
call :ensure_venv
if errorlevel 1 goto menu
echo Installation / mise a jour de huggingface_hub...
"%VENV_PY%" -m pip install --upgrade huggingface_hub
if errorlevel 1 (
    echo Echec de l'installation de huggingface_hub. Verifiez votre connexion.
    pause
    goto menu
)
set "TARGET_DIR=models/bge-m3"
if not exist models mkdir models
echo Telechargement du modele BAAI/bge-m3 dans %TARGET_DIR% ...
"%VENV_PY%" -c "from huggingface_hub import snapshot_download; snapshot_download('BAAI/bge-m3', local_dir='%TARGET_DIR%', repo_type='model')"
if errorlevel 1 (
    echo Telechargement impossible (connexion Hugging Face requise).
    pause
    goto menu
)
echo Modele telecharge. Configurez embedding_model_name sur "%TARGET_DIR%" dans config.json si necessaire.
pause
goto menu

:voice_setup
call :ensure_venv
if errorlevel 1 goto menu
echo Installation des dependances du client vocal...
"%VENV_PY%" -m pip install --no-cache-dir -e ".[voice]"
if errorlevel 1 (
    echo Echec de l'installation des dependances du client vocal.
    pause
    goto menu
)
echo Installation des ressources audio (ASR + TTS)...
set "OLD_PYTHONPATH=%PYTHONPATH%"
set "PYTHONPATH=%CD%"
"%VENV_PY%" scripts\install_voice_resources.py --all
set "PYTHONPATH=%OLD_PYTHONPATH%"
set "OLD_PYTHONPATH="
if errorlevel 1 (
    echo Impossible d'installer les ressources audio. Verifiez la connexion ou les droits.
    pause
    goto menu
)
echo Ressources audio installees.
pause
goto menu

:install_torch_cuda
call :ensure_venv
if errorlevel 1 goto menu
echo Desinstallation des versions existantes de torch...
"%VENV_PY%" -m pip uninstall -y torch torchvision torchaudio >nul 2>&1
echo Installation de PyTorch CUDA (cu121) pour l environnement .venv ...
"%VENV_PY%" -m pip install --index-url https://download.pytorch.org/whl/cu121 torch torchvision torchaudio
if errorlevel 1 (
    echo Echec de l installation CUDA. Aucune modification supplementaire.
    pause
    goto menu
)
echo Verification de torch.cuda.is_available() ...
"%VENV_PY%" -c "import torch; print('torch', torch.__version__, 'cuda dispo', torch.cuda.is_available())"
pause
goto menu

:tune_llm_full
call :ensure_venv
if errorlevel 1 goto menu
echo Lancement de l optimisation LLM (auto)...
"%VENV_PY%" scripts\auto_tune_llm_full.py
pause
goto menu

:open_taskhub
start "" http://127.0.0.1:5173/task-hub
goto menu

:package_voice
call :ensure_venv
if errorlevel 1 goto menu
echo Construction du client vocal (PyInstaller)...
set "OLD_PYTHONPATH=%PYTHONPATH%"
set "PYTHONPATH=%CD%"
"%VENV_PY%" scripts\package_voice_client.py
set "PYTHONPATH=%OLD_PYTHONPATH%"
set "OLD_PYTHONPATH="
if errorlevel 1 (
    echo Erreur pendant le packaging.
    pause
    goto menu
)
echo Client vocal empaquete. Consultez le dossier dist\voice_client\IVYVoice.
pause
goto menu

:end
popd
endlocal
exit /b 0

