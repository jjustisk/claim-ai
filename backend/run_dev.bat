@echo off
REM Dev API: reload only watches app/ so scripts/ and data/ edits do not restart uvicorn
REM (avoids CancelledError noise from overlapping reloads on Windows).
cd /d "%~dp0"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --reload-dir app --reload-delay 0.75 --log-level info
