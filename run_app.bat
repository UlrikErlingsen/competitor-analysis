@echo off
setlocal
cd /d "%~dp0"
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if errorlevel 1 (
  echo Rival Signal needs Python 3.10 or newer.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Creating Rival Signal's private Python environment...
  py -m venv .venv
)
".venv\Scripts\python.exe" -c "import streamlit, plotly, jsonschema" >nul 2>&1
if errorlevel 1 (
  echo Installing Rival Signal's open-source packages...
  ".venv\Scripts\python.exe" -m pip --disable-pip-version-check install --prefer-binary -r requirements.txt
  if errorlevel 1 (
    pause
    exit /b 1
  )
)
if "%RIVALSIGNAL_PORT%"=="" set RIVALSIGNAL_PORT=8598
if "%RIVALSIGNAL_MAX_UPLOAD_MB%"=="" set RIVALSIGNAL_MAX_UPLOAD_MB=10000
echo Starting Rival Signal at http://127.0.0.1:%RIVALSIGNAL_PORT% ...
".venv\Scripts\python.exe" -m streamlit run app.py --server.headless=true --server.address=127.0.0.1 --server.port=%RIVALSIGNAL_PORT% --server.maxUploadSize=%RIVALSIGNAL_MAX_UPLOAD_MB% --server.fileWatcherType=none --browser.gatherUsageStats=false
if errorlevel 1 pause
