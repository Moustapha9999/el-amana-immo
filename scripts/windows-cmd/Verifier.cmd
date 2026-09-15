@echo off
setlocal
cd /d "%~dp0"
title El Amana Immo - Verifier
echo.
echo Verification de l'instance...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\check-local.ps1"
echo.
pause
