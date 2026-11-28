@echo off
title NextToppers Roast Automated Pipeline (3 Shorts/Day + 4-Day Long)
echo Starting ClipForge Local Studio API from E:\ClipForge on 127.0.0.1:4820...
set CLIPFORGE_HOME=E:\ClipForge
set CLIPFORGE_DATA_DIR=E:\ClipForgeData
start "ClipForge API" /min cmd /c "cd /d E:\ClipForge && node src\cli.js serve"
timeout /t 4 /nobreak >nul
echo Starting NextToppers Roast Scheduler (3 Shorts/day + 1 Long video every 4 days)...
cd /d E:\youtube-autopilot
set PYTHONPATH=src
.\.venv\Scripts\python.exe -m autopilot.cli schedule-trio --morning-count 1 --evening-count 2 --long-every-days 4 --upload
pause
