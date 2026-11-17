@echo off
title Buddy AI (JARVIS Edition) - Setup and Installer
color 0b
echo ========================================================
echo        BUDDY AI / J.A.R.V.I.S. VOICE ASSISTANT
echo        Setting up and updating your desktop assistant...
echo ========================================================
echo.

cd /d "%~dp0"

:: 1. Terminate any previous running assistant instances
echo [*] Checking for previous running assistant instances...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*main.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

:: 2. Determine Python executable
set "PY_CMD="

if exist "venv\Scripts\python.exe" (
    set "PY_CMD=venv\Scripts\python.exe"
    echo [*] Found existing virtual environment: venv\Scripts\python.exe
    goto :FOUND_PY
)

python --version >nul 2>&1
if not errorlevel 1 (
    set "PY_CMD=python"
    goto :FOUND_PY
)

py -3 --version >nul 2>&1
if not errorlevel 1 (
    set "PY_CMD=py -3"
    goto :FOUND_PY
)

py -3.11 --version >nul 2>&1
if not errorlevel 1 (
    set "PY_CMD=py -3.11"
    goto :FOUND_PY
)

py -3.12 --version >nul 2>&1
if not errorlevel 1 (
    set "PY_CMD=py -3.12"
    goto :FOUND_PY
)

py -3.10 --version >nul 2>&1
if not errorlevel 1 (
    set "PY_CMD=py -3.10"
    goto :FOUND_PY
)

echo.
echo [ERROR] Python was not found on your system.
echo Please install Python 3.10, 3.11, or 3.12 from https://www.python.org/
echo Make sure to check the box: "Add Python to PATH" during installation.
echo.
pause
exit /b 1

:FOUND_PY
echo [*] Using Python executable: %PY_CMD%

:: 3. Create Virtual Environment if not exists
if not exist "venv\Scripts\python.exe" (
    echo [*] Creating isolated virtual environment - venv...
    %PY_CMD% -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

:: 4. Install & Update Dependencies
echo [*] Upgrading pip and installing dependencies from requirements.txt...
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt

:: 5. Generate Arc Reactor Icon
echo [*] Generating high-resolution application branding...
venv\Scripts\python.exe create_icon.py

:: 6. Ensure Local Offline Whisper Model is Available
echo [*] Checking and verifying persistent local Whisper model...
venv\Scripts\python.exe -c "from stt import ensure_whisper_model; ensure_whisper_model()"

:: 7. Create Desktop Shortcut via Python
echo [*] Creating Desktop Shortcut...
venv\Scripts\python.exe -c "import os, win32com.client; wsh = win32com.client.Dispatch('WScript.Shell'); desktop = wsh.SpecialFolders('Desktop'); shortcut = wsh.CreateShortcut(os.path.join(desktop, 'Buddy AI.lnk')); shortcut.TargetPath = os.path.join(os.getcwd(), 'Start_Buddy.vbs'); shortcut.WorkingDirectory = os.getcwd(); ico = os.path.join(os.getcwd(), 'assets', 'buddy_icon.ico'); shortcut.IconLocation = ico if os.path.exists(ico) else ''; shortcut.Description = 'Buddy AI / JARVIS Voice Assistant'; shortcut.Save(); print('[*] Desktop shortcut created successfully!')"

echo.
echo ========================================================
echo   SUCCESS! Buddy AI (JARVIS) has been updated and installed.
echo   - Desktop shortcut 'Buddy AI' is configured with the icon.
echo   - All latest offline voice features and dependencies are ready.
echo ========================================================
echo.
pause
