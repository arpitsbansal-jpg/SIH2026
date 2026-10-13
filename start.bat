@echo off
cd /d "%~dp0"
echo Starting RETINOVA...
if exist "backend\venv\Scripts\python.exe" (
    backend\venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
) else (
    echo ERROR: backend\venv\Scripts\python.exe was not found.
    echo Please run the backend using your existing virtual environment.
    pause
)
