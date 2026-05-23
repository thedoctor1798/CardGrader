@echo off
setlocal

cd /d %~dp0

if not exist "backend\.venv\Scripts\python.exe" (
    echo Creating backend virtual environment...
    python -m venv backend\.venv
)

call backend\.venv\Scripts\activate.bat

echo Installing/updating backend requirements...
python -m pip install -r backend\requirements.txt

echo.
echo Backend: http://127.0.0.1:8710
echo Health:  http://127.0.0.1:8710/api/health
echo.
echo Frontend dev server must be started separately:
echo cd frontend ^&^& npm run dev
echo.

cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8710 --reload

pause
