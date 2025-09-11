@echo off
setlocal EnableExtensions EnableDelayedExpansion
pushd "%~dp0.."

:menu
cls
echo ================= IVY Launcher =================
echo 1^) Create/Update config.json (CORS defaults)
echo 2^) Install/Update Python deps (uv or pip)
echo 3^) Start API server (FastAPI)
echo 4^) UI dev: install deps and run vite dev on 5173
echo 5^) UI build (vite)
echo 6^) Serve built UI statically on 5174
echo 7^) Reset admin password (create flag)
echo 8^) Open API docs in browser
echo 9^) Exit
set /p choice=Select option [1-9]: 

if "%choice%"=="1" goto cfg
if "%choice%"=="2" goto deps
if "%choice%"=="3" goto serve
if "%choice%"=="4" goto ui_dev
if "%choice%"=="5" goto ui_build
if "%choice%"=="6" goto ui_static
if "%choice%"=="7" goto reset_admin
if "%choice%"=="8" goto docs
if "%choice%"=="9" goto end
goto menu

:ensure_venv
if not exist .venv (
  py -3.11 -m venv .venv
)
call .venv\Scripts\activate
goto :eof

:deps
call :ensure_venv
where uv >NUL 2>&1
if %errorlevel%==0 (
  echo Installing project with uv (editable)...
  uv pip install -e .[dev]
) else (
  echo uv not found. Using pip...
  python -m pip install --upgrade pip
  pip install -e .[dev] || pip install -r scripts\requirements-dev-no-llama.txt
)
pause
goto menu

:serve
call :ensure_venv
echo Starting IVY server on http://127.0.0.1:8000 ...
python -m app.cli serve
goto menu

:ui_dev
pushd webui
call npm install
call npm pkg get devDependencies."@vitejs/plugin-react" >NUL 2>&1
if errorlevel 1 (
  echo Adding @vitejs/plugin-react...
  call npm i -D @vitejs/plugin-react
)
set "VITE_API_URL=http://127.0.0.1:8000"
echo Starting Vite dev server on http://127.0.0.1:5173 ...
call npm run dev
popd
goto menu

:ui_build
pushd webui
call npm install
call npm pkg get devDependencies."@vitejs/plugin-react" >NUL 2>&1
if errorlevel 1 call npm i -D @vitejs/plugin-react
set "VITE_API_URL=http://127.0.0.1:8000"
call npm run build
popd
pause
goto menu

:ui_static
call :ensure_venv
echo Serving webui\dist at http://127.0.0.1:5174 ...
python -m app.cli ui --path webui\dist --port 5174
goto menu

:cfg
set "JSON={\"host\":\"127.0.0.1\",\"port\":8000,\"cors_origins\":[\"http://127.0.0.1:5173\",\"http://localhost:5173\",\"http://127.0.0.1:5174\",\"http://localhost:5174\"]}"
echo %JSON%>config.json
echo Wrote config.json
type config.json
pause
goto menu

:reset_admin
if not exist app\data mkdir app\data
type NUL > app\data\reset_admin.flag
echo Created app\data\reset_admin.flag. Restart server to print temp password.
pause
goto menu

:docs
start "" http://127.0.0.1:8000/docs
goto menu

:end
popd
endlocal
exit /b 0

