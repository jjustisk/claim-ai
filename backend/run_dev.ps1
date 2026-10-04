# Dev API: reload only watches app/ (not scripts/) to avoid reload CancelledError tracebacks.
Set-Location $PSScriptRoot
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --reload-dir app --reload-delay 0.75
