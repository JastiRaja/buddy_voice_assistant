import os
import subprocess
import sys

def build_standalone():
    print("==================================================")
    print("   PACKAGING BUDDY AI AS STANDALONE APP (.EXE)")
    print("==================================================")

    # 1. Ensure icon is generated
    import create_icon
    create_icon.generate_buddy_icon()

    # 2. Run PyInstaller
    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name", "BuddyAI",
        "--icon", os.path.abspath("assets/buddy_icon.ico"),
        "--add-data", f"{os.path.abspath('assets')}{os.pathsep}assets",
    ]

    models_path = os.path.abspath("models")
    if os.path.exists(models_path):
        cmd.extend(["--add-data", f"{models_path}{os.pathsep}models"])

    cmd.extend([
        "--collect-all", "customtkinter",
        "--collect-all", "faster_whisper",
        "--collect-all", "ctranslate2",
        "--collect-all", "pyttsx3",
        "--collect-all", "screen_brightness_control",
        "--collect-all", "screeninfo",
        "main.py"
    ])

    print(f"[*] Running command: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    print("\n==================================================")
    print("   BUILD COMPLETE!")
    print(f"   Standalone App: {os.path.abspath('dist/BuddyAI/BuddyAI.exe')}")
    print("==================================================")

if __name__ == "__main__":
    build_standalone()
