@echo off
cd /d "%~dp0"
echo ============================================================
echo           Starting J.A.R.V.I.S. Voice Assistant             
echo ============================================================

:: 1. If virtual environment exists, launch directly
if exist "venv\Scripts\python.exe" (
    echo [*] Starting J.A.R.V.I.S. from virtual environment...
    venv\Scripts\python.exe main.py
    if errorlevel 1 (
        echo.
        echo [!] J.A.R.V.I.S. encountered an issue. Running diagnostics...
        venv\Scripts\python.exe doctor.py
        pause
    )
    exit /b %errorlevel%
)

:: 2. Find system Python to provision environment
set "PY_CMD="
python --version >nul 2>&1
if not errorlevel 1 (
    set "PY_CMD=python"
    goto :CREATE_ENV
)

py -3 --version >nul 2>&1
if not errorlevel 1 (
    set "PY_CMD=py -3"
    goto :CREATE_ENV
)

py -3.11 --version >nul 2>&1
if not errorlevel 1 (
    set "PY_CMD=py -3.11"
    goto :CREATE_ENV
)

py -3.12 --version >nul 2>&1
if not errorlevel 1 (
    set "PY_CMD=py -3.12"
    goto :CREATE_ENV
)

echo.
echo [ERROR] Python was not found in your system PATH.
echo         Please install Python 3.10, 3.11, or 3.12 from python.org
echo         and make sure to check "Add Python to PATH".
echo.
pause
exit /b 1

:CREATE_ENV
echo [*] Creating isolated virtual environment in .\venv...
%PY_CMD% -m venv venv
if errorlevel 1 (
    echo [ERROR] Failed creating virtual environment.
    pause
    exit /b 1
)

echo [*] Installing required dependencies...
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt

echo [*] Verifying environment with doctor.py...
venv\Scripts\python.exe doctor.py

echo [*] Launching J.A.R.V.I.S. runtime...
venv\Scripts\python.exe main.py
if errorlevel 1 (
    pause
)
