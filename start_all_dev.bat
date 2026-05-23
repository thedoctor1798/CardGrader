@echo off
setlocal

cd /d %~dp0

start "CardGrader Backend" cmd /k "%~dp0start_cardgrader.bat"
start "CardGrader Frontend" cmd /k "%~dp0start_frontend.bat"
