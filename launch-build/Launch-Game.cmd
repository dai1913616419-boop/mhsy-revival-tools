@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-servers.ps1"
if errorlevel 1 goto failed
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch-emulator.ps1"
if errorlevel 1 goto failed
exit /b 0
:failed
echo Game startup failed. Check C:\mhsy-local\server\logs and the message above.
pause
exit /b 1
