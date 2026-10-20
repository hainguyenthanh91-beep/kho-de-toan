@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Chua co Python. Hay cai Python 3.11 tro len tu https://www.python.org/downloads/
  echo Khi cai, nho tick o "Add python.exe to PATH".
  pause
  exit /b
)
if not exist ".venv" (
  echo Lan dau chay: dang cai thu vien, mat khoang 1-2 phut...
  python -m venv .venv
  .venv\Scripts\python -m pip install -q -r requirements.txt
)
.venv\Scripts\python run.py
pause
