@echo off
setlocal
cd /d "F:\youtube-autopilot"
echo Starting YouTube Autopilot dual-channel scheduler daemon...
echo Active slots: 12:00 PM IST and 18:00 PM IST daily
".venv\Scripts\python.exe" -m autopilot.cli schedule-all
pause

