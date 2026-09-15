@echo off
setlocal
cd /d "%~dp0"
title El Amana Immo - Mettre a jour
echo.
echo ============================================================
echo  MISE A JOUR du logiciel (backend + frontend)
echo  Les saisies du PC comptable sont CONSERVEES.
echo  Une sauvegarde est faite automatiquement avant.
echo ============================================================
echo.
pause
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\update-on-comptable.ps1"
echo.
echo Ouvrir http://localhost puis Ctrl+F5
pause
