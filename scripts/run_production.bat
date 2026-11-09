@echo off
setlocal
cd /d "F:\youtube-autopilot"
if not exist "logs" mkdir "logs"
echo ======================================================== >> "logs\scheduler.log"
echo Production slot [%1] started at %DATE% %TIME% >> "logs\scheduler.log"
echo ======================================================== >> "logs\scheduler.log"
".venv\Scripts\python.exe" -m autopilot.cli run-all --slot %1 --live >> "logs\scheduler.log" 2>&1
echo Production slot [%1] finished at %DATE% %TIME% with exit code %ERRORLEVEL% >> "logs\scheduler.log"
echo. >> "logs\scheduler.log"
exit /b %ERRORLEVEL%

