@echo off
chcp 65001 > nul
echo.
echo  ==========================================
echo   机器人巡检监控系统 - 一键启动
echo  ==========================================
echo.
powershell -ExecutionPolicy Bypass -File "%~dp0start.ps1"
pause
