@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-runtime-bundle.ps1" %*
exit /b %ERRORLEVEL%
