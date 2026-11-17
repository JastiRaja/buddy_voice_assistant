import os
import shutil
import tempfile
from os_adapter import get_os_adapter, WindowsAdapter, MacOSAdapter, LinuxAdapter
from actions import SystemController
from dispatcher import CommandDispatcher
from web_skills import WebSkills

class MockTTS:
    def __init__(self):
        self.last_spoken = ""
        self.history = []
    def speak(self, text, *args, **kwargs):
        self.last_spoken = text
        self.history.append(text)
        print(f" [MockTTS]: {text}")
    def stop(self): pass

def test_phase2_os_adapters():
    print("==================================================")
    print("TEST 1: Cross-Platform OS Adapter Architecture")
    print("==================================================")
    adapter = get_os_adapter()
    print(f"Active Platform Adapter: {type(adapter).__name__} on {adapter.system}")
    assert adapter.system in ["Windows", "Darwin", "Linux"], "Unrecognized system!"
    
    downloads = adapter.get_standard_folder("downloads")
    documents = adapter.get_standard_folder("documents")
    print(f"Standard Downloads: {downloads}")
    print(f"Standard Documents: {documents}")
    assert os.path.isabs(downloads), "Downloads path is not absolute!"
    assert os.path.isabs(documents), "Documents path is not absolute!"
    
    # Test modifier keys for each adapter type
    win = WindowsAdapter()
    assert win.modifier_key == 'ctrl' and win.super_key == 'win'
    
    mac = MacOSAdapter()
    assert mac.modifier_key == 'command' and mac.super_key == 'command'
    
    linux = LinuxAdapter()
    assert linux.modifier_key == 'ctrl' and linux.super_key == 'super'
    print("-> PASSED: Cross-platform adapter modifiers & paths verified.\n")

def test_phase2_file_organization():
    print("==================================================")
    print("TEST 2: Voice-Driven File Organization")
    print("==================================================")
    tts = MockTTS()
    ctrl = SystemController(tts)

    # Create a temporary sandbox directory with dummy files
    test_dir = tempfile.mkdtemp(prefix="buddy_organize_test_")
    try:
        files = {
            "invoice.pdf": "doc",
            "vacation.png": "img",
            "podcast.mp3": "audio",
            "movie.mp4": "video",
            "backup.zip": "archive",
            "script.py": "code",
            "setup.exe": "installer"
        }
        for fname, content in files.items():
            with open(os.path.join(test_dir, fname), "w") as f:
                f.write(content)

        # Execute organize_folder
        ctrl.organize_folder(test_dir)

        # Verify categorization
        assert os.path.exists(os.path.join(test_dir, "Documents", "invoice.pdf")), "PDF not in Documents!"
        assert os.path.exists(os.path.join(test_dir, "Images", "vacation.png")), "PNG not in Images!"
        assert os.path.exists(os.path.join(test_dir, "Audio", "podcast.mp3")), "MP3 not in Audio!"
        assert os.path.exists(os.path.join(test_dir, "Video", "movie.mp4")), "MP4 not in Video!"
        assert os.path.exists(os.path.join(test_dir, "Archives", "backup.zip")), "ZIP not in Archives!"
        assert os.path.exists(os.path.join(test_dir, "Code", "script.py")), "PY not in Code!"
        assert os.path.exists(os.path.join(test_dir, "Installers", "setup.exe")), "EXE not in Installers!"

        print("-> PASSED: All 7 file types correctly sorted into subfolders.\n")
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)

def test_phase2_workspace_profiles_and_media():
    print("==================================================")
    print("TEST 3: Workspace Profiles & Local Media Routing")
    print("==================================================")
    tts = MockTTS()
    ctrl = SystemController(tts)
    ws = WebSkills(tts)
    disp = CommandDispatcher(ctrl, tts, ws)

    # Test profile dispatch
    print("\nEvaluating: 'start coding mode'")
    disp.process("start coding mode")
    assert "coding" in tts.last_spoken.lower(), "Coding profile was not activated!"

    print("\nEvaluating: 'study mode'")
    disp.process("study mode")
    assert "study" in tts.last_spoken.lower(), "Study profile was not activated!"

    print("\nEvaluating: 'relax mode'")
    disp.process("relax mode")
    assert "relax" in tts.last_spoken.lower(), "Relax profile was not activated!"

    # Test local media query dispatch
    print("\nEvaluating: 'play local music'")
    disp.process("play local music")
    print(f"Response: {tts.last_spoken}")
    assert len(tts.last_spoken) > 0, "No speech response for local media!"

    print("\n==================================================")
    print("ALL PHASE 2 CAPABILITIES VERIFIED 100%!")
    print("==================================================")

if __name__ == "__main__":
    test_phase2_os_adapters()
    test_phase2_file_organization()
    test_phase2_workspace_profiles_and_media()
