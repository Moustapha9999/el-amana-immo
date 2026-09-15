@echo off
setlocal
cd /d "%~dp0"
title El Amana Immo - Sauvegarder
echo.
echo Sauvegarde PostgreSQL + documents...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\backup-local.ps1"
echo.
echo Les fichiers sont dans le dossier backups\
pause
