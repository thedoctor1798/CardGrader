@echo off
echo Stopping any process listening on port 8710
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8710 ^| findstr LISTENING') do taskkill /F /PID %%a
echo Done.
