@echo off
title Buddy AI (JARVIS Edition) - Setup & Installer
color 0b
echo ========================================================
echo        BUDDY AI / J.A.R.V.I.S. VOICE ASSISTANT
echo        Setting up & updating your desktop assistant...
echo ========================================================
echo.

cd /d "%~dp0"

:: 1. Terminate any previous background assistant instances to apply updates
echo [*] Checking for previous running assistant instances...
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*main.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

:: 2. Check Python
py -3.11 --version >nul 2>&1
if %errorlevel% neq 0 (
    python --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] Python is not found. Please install Python 3.10 or 3.11 from python.org.
        pause
        exit /b 1
    )
    set PY_CMD=python
) else (
    set PY_CMD=py -3.11
)

:: 3. Create Virtual Environment if not exists
if not exist "venv\Scripts\activate.bat" (
    echo [*] Creating isolated virtual environment (venv)...
    %PY_CMD% -m venv venv
)

:: 4. Install & Update Dependencies
echo [*] Upgrading dependencies from requirements.txt...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

:: 5. Generate Arc Reactor Icon
echo [*] Generating high-resolution application branding...
python create_icon.py

:: 6. Ensure Local Offline Whisper Model is Available (Survives cache clearing)
echo [*] Checking and verifying persistent local Whisper model...
python -c "from stt import ensure_whisper_model; ensure_whisper_model()"

:: 7. Create / Update Desktop Shortcuts
echo [*] Updating Desktop Shortcut...
powershell -Command "$WshShell = New-Object -ComObject WScript.Shell; $Desktop = [Environment]::GetFolderPath('Desktop'); $Shortcut = $WshShell.CreateShortcut($Desktop + '\Buddy AI.lnk'); $Shortcut.TargetPath = '%~dp0Start_Buddy.vbs'; $Shortcut.WorkingDirectory = '%~dp0'; $Shortcut.IconLocation = '%~dp0assets\buddy_icon.ico'; $Shortcut.Description = 'Buddy AI / JARVIS Voice Assistant'; $Shortcut.Save()"

echo.
echo ========================================================
echo   SUCCESS! Buddy AI (JARVIS) has been updated & installed.
echo   - Desktop shortcut 'Buddy AI' is configured with the new icon.
echo   - All latest offline voice features & dependencies are ready.
echo ========================================================
echo.
pause
