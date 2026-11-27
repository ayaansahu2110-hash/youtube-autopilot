@echo off
title Next Toppers Trio Automated Clipper & Uploader
echo Starting ClipForge Local Studio API on 127.0.0.1:4820...
start "ClipForge API" /min cmd /c "cd /d C:\Users\ayaan\Desktop\clone && node src\cli.js serve"
timeout /t 4 /nobreak >nul
echo Starting Next Toppers Trio Daily Scheduler (10:00 AM & 06:00 PM IST)...
cd /d E:\youtube-autopilot
set PYTHONPATH=src
.\.venv\Scripts\python.exe -m autopilot.cli schedule-trio --count 2 --upload
pause
