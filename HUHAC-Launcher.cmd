@echo off
setlocal
for %%I in ("%~dp0.") do set "PROJECT_ROOT=%%~fI"
set "PYTHONW=%PROJECT_ROOT%\.venv\Scripts\pythonw.exe"

if not exist "%PYTHONW%" (
  echo HUHAC Launcher: chybi projektovy interpreter:
  echo %PYTHONW%
  pause
  exit /b 2
)

start "HUHAC Launcher" /D "%PROJECT_ROOT%" "%PYTHONW%" -m huhac_launcher --project-root "%PROJECT_ROOT%"
if errorlevel 1 (
  echo HUHAC Launcher se nepodarilo spustit.
  pause
  exit /b 1
)

endlocal
