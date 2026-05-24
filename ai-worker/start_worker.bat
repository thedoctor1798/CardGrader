@echo off
setlocal

cd /d %~dp0

if not exist ".venv\Scripts\python.exe" (
    echo Creating AI worker virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo Installing/updating AI worker requirements...
python -m pip install -r requirements.txt

echo.
echo CardGrader AI Worker starting...
echo Health: http://127.0.0.1:8765/health
echo.

python main.py

pause
