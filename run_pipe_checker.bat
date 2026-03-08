@echo off
setlocal
cd /d %~dp0

echo Starting Pipe Checker...
where python >nul 2>nul
if errorlevel 1 (
  echo Python is not installed or not on PATH.
  echo Install Python 3.11+ from python.org, check "Add Python to PATH", then run this again.
  pause
  exit /b 1
)

python -m pip install --upgrade pip
if errorlevel 1 (
  echo Failed while upgrading pip.
  pause
  exit /b 1
)

python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Failed while installing requirements.
  pause
  exit /b 1
)

echo Opening Pipe Checker at http://127.0.0.1:8000
start http://127.0.0.1:8000
python app.py

echo Pipe Checker has stopped.
pause
