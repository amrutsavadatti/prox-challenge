@echo off
setlocal

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" cmd
if errorlevel 1 exit /b %errorlevel%

endlocal
