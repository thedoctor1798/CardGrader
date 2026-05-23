@echo off
setlocal

cd /d %~dp0frontend

if not exist "node_modules" (
    echo Installing frontend dependencies...
    npm install
)

echo.
echo Frontend expected at http://127.0.0.1:5173
echo.

netstat -ano | findstr ":5173" >nul
if %ERRORLEVEL% EQU 0 (
    echo Port 5173 is already in use. Close the existing frontend terminal or run: taskkill /IM node.exe /F
    echo.
)

npm run dev

pause
