@echo off
cd /d %~dp0backend

if not exist ".venv\Scripts\python.exe" (
	echo Creating virtual environment...
	python -m venv .venv
)

call .venv\Scripts\activate.bat

echo Installing/updating requirements...
python -m pip install -r requirements.txt

echo Starting CardGrader on http://localhost:8710
python -m uvicorn app.main:app --host 127.0.0.1 --port 8710 --reload

pause
