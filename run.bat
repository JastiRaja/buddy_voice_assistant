@echo off
cd /d "%~dp0"
echo ============================================================
echo           Starting J.A.R.V.I.S. Voice Assistant             
echo ============================================================

where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python was not found in your system PATH.
    echo         Please install Python 3.10+ from python.org and check "Add Python to PATH".
    pause
    exit /b 1
)

if not exist "venv\Scripts\activate.bat" (
    echo [*] Creating isolated virtual environment in .\venv...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo [*] Installing required dependencies...
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

python doctor.py
echo [*] Launching J.A.R.V.I.S. runtime...
python main.py
pause

