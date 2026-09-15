@echo off
setlocal
cd /d "%~dp0"
title El Amana Immo - Premiere installation
echo.
echo ============================================================
echo  PREMIERE INSTALLATION uniquement
echo  Si la plateforme existe deja avec des saisies, utilisez
echo  plutôt MettreAJour.cmd (pour ne pas ecraser les donnees).
echo ============================================================
echo.
pause
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-on-comptable.ps1"
echo.
pause
