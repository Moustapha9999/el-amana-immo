@echo off
setlocal
cd /d "%~dp0"
title El Amana Immo - Arreter
echo.
echo Arret des conteneurs (donnees conservees)...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-local.ps1"
echo.
pause
