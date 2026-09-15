@echo off
setlocal
cd /d "%~dp0"
title El Amana Immo - Demarrer
echo.
echo Demarrage de la plateforme...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-local.ps1"
echo.
echo Ouvrir : http://localhost
pause
