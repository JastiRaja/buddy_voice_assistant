"""
J.A.R.V.I.S. / Buddy AI System Doctor & Pre-flight Validator
Verifies environment, system dependencies, hardware peripherals, and offline models.
Automatically repairs missing Python dependencies and guides system packages across OSes.
"""

import sys
import os
import platform
import subprocess
import shutil
import importlib
from pathlib import Path

# Required Python packages with display names
REQUIRED_PACKAGES = [
    ("faster_whisper", "faster-whisper"),
    ("sounddevice", "sounddevice"),
    ("numpy", "numpy"),
    ("pyautogui", "pyautogui"),
    ("psutil", "psutil"),
    ("pyttsx3", "pyttsx3"),
    ("pygame", "pygame"),
    ("customtkinter", "customtkinter"),
    ("pyperclip", "pyperclip"),
    ("PIL", "Pillow"),
]

def print_header(title: str):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)

def check_python_version() -> bool:
    print("[1/5] Checking Python Version...")
    v = sys.version_info
    print(f"      Detected: Python {v.major}.{v.minor}.{v.micro} on {platform.system()} ({platform.machine()})")
    if v.major != 3 or v.minor < 9 or v.minor > 13:
        print("      [WARNING] Recommended Python version is 3.10 - 3.12 for optimal AI wheel compatibility.")
        return False
    print("      -> Python version OK.")
    return True

def check_and_repair_pip_dependencies() -> bool:
    print("\n[2/5] Checking Python Packages & Libraries...")
    missing = []
    for mod_name, pkg_name in REQUIRED_PACKAGES:
        try:
            importlib.import_module(mod_name)
            print(f"      [OK] {pkg_name}")
        except ImportError:
            print(f"      [MISSING] {pkg_name}")
            missing.append(pkg_name)

    if missing:
        print(f"\n      Missing {len(missing)} Python packages. Attempting automatic installation...")
        try:
            req_file = os.path.join(os.path.dirname(__file__), "requirements.txt")
            if os.path.exists(req_file):
                cmd = [sys.executable, "-m", "pip", "install", "-r", req_file]
            else:
                cmd = [sys.executable, "-m", "pip", "install"] + missing
            
            res = subprocess.run(cmd, check=False)
            if res.returncode == 0:
                print("      -> All missing packages successfully installed!")
                return True
            else:
                print("      [ERROR] Automatic pip installation failed. Please run manually:")
                print(f"              {sys.executable} -m pip install -r requirements.txt")
                return False
        except Exception as e:
            print(f"      [ERROR] Could not run pip: {e}")
            return False
    else:
        print("      -> All required Python packages are installed.")
        return True

def check_os_system_dependencies() -> bool:
    print("\n[3/5] Checking OS System Libraries & Binaries...")
    sys_name = platform.system()
    all_ok = True

    if sys_name == "Linux":
        # Check PortAudio (needed by sounddevice)
        portaudio_found = False
        for p in ["/usr/lib", "/usr/local/lib", "/usr/lib/x86_64-linux-gnu", "/usr/lib/aarch64-linux-gnu"]:
            if os.path.exists(p):
                for f in os.listdir(p):
                    if "libportaudio" in f:
                        portaudio_found = True
                        break
        if not portaudio_found:
            print("      [NOTICE] libportaudio may be missing. If audio recording fails, install via:")
            print("               sudo apt-get install libportaudio2 libasound2-plugins")

        # Check espeak-ng for offline TTS fallback
        if not shutil.which("espeak") and not shutil.which("espeak-ng"):
            print("      [NOTICE] 'espeak' not found. For offline system TTS fallback, install:")
            print("               sudo apt-get install espeak-ng")

        # Check ffmpeg
        if not shutil.which("ffmpeg"):
            print("      [NOTICE] 'ffmpeg' not found in PATH (recommended for audio conversion).")
            print("               sudo apt-get install ffmpeg")

    elif sys_name == "Darwin":
        # macOS check
        if not shutil.which("ffmpeg"):
            print("      [NOTICE] 'ffmpeg' not found. Install via Homebrew if needed: brew install ffmpeg")
        print("      -> Ensure Terminal/Python has 'Accessibility', 'Microphone', and 'Screen Recording' permissions in:")
        print("         System Settings > Privacy & Security")

    elif sys_name == "Windows":
        # Check PowerShell and audio components
        if shutil.which("powershell.exe"):
            print("      [OK] Windows PowerShell available.")
        else:
            print("      [WARNING] powershell.exe not found in PATH.")

    print("      -> OS-level checks completed.")
    return all_ok

def check_audio_hardware() -> bool:
    print("\n[4/5] Testing Audio Hardware (Microphone & Speakers)...")
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        input_devs = [d for d in devices if d.get('max_input_channels', 0) > 0]
        output_devs = [d for d in devices if d.get('max_output_channels', 0) > 0]

        print(f"      Input Devices (Microphones): {len(input_devs)}")
        print(f"      Output Devices (Speakers):   {len(output_devs)}")

        if not input_devs:
            print("      [WARNING] No active microphone detected! Connect a microphone to speak to the assistant.")
            return False
        if not output_devs:
            print("      [WARNING] No active speaker detected! You will not be able to hear assistant replies.")
            return False

        default_in = sd.query_devices(kind='input')
        default_out = sd.query_devices(kind='output')
        print(f"      Default Mic: {default_in.get('name', 'Unknown')}")
        print(f"      Default Spk: {default_out.get('name', 'Unknown')}")
        print("      -> Audio peripherals verified.")
        return True
    except Exception as e:
        print(f"      [WARNING] Sounddevice device query error: {e}")
        return False

def check_offline_models() -> bool:
    print("\n[5/5] Verifying Local Offline Models...")
    models_dir = os.path.join(os.path.dirname(__file__), "models")
    os.makedirs(models_dir, exist_ok=True)
    
    found_models = []
    for item in os.listdir(models_dir):
        p = os.path.join(models_dir, item)
        if os.path.isdir(p) or item.endswith((".onnx", ".bin", ".gguf", ".zim")):
            found_models.append(item)

    print(f"      Local models directory: {models_dir}")
    print(f"      Found {len(found_models)} offline asset(s): {found_models if found_models else 'None (models will download or use system voice on first run)'}")
    print("      -> Model directory initialized.")
    return True

def run_doctor():
    print_header("J.A.R.V.I.S. PRE-FLIGHT ENVIRONMENT DOCTOR")
    c1 = check_python_version()
    c2 = check_and_repair_pip_dependencies()
    c3 = check_os_system_dependencies()
    c4 = check_audio_hardware()
    c5 = check_offline_models()

    print_header("DIAGNOSTIC SUMMARY")
    if c2 and c4:
        print("  🎉 SYSTEM HEALTHY: J.A.R.V.I.S. is ready to launch on this machine!")
        print("  To start the assistant, run:")
        if platform.system() == "Windows":
            print("      run.bat   or   python main.py")
        else:
            print("      ./run.sh  or   python3 main.py")
    else:
        print("  ⚠️ System requires attention on the items noted above before optimal execution.")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    run_doctor()
