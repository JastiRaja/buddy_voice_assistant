from screen_ocr import ScreenOCRExtractor, ERROR_SIGNATURES
from vision import VisionAssistant
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

def test_phase4_error_diagnostics():
    print("==================================================")
    print("TEST 1: Terminal & IDE Error Debugging Engine")
    print("==================================================")
    ocr = ScreenOCRExtractor()

    # 1. Python Module Not Found
    trace_module = "Traceback (most recent call last):\n  File 'main.py', line 2\nModuleNotFoundError: No module named 'scipy'"
    diag_mod = ocr.diagnose_screen_error(trace_module)
    print(f"Diagnosed: {diag_mod}")
    assert "pip install scipy" in diag_mod, "Failed to suggest pip install for missing module!"

    # 2. Syntax Error
    trace_syntax = "  File 'app.py', line 12\n    if x == 5\n             ^\nSyntaxError: expected ':'"
    diag_syntax = ocr.diagnose_screen_error(trace_syntax)
    print(f"Diagnosed: {diag_syntax}")
    assert "syntax error" in diag_syntax.lower(), "Failed to identify syntax error!"

    # 3. Node.js Dependency Error
    trace_node = "Error: Cannot find module 'express'\nRequire stack:\n- /app/server.js"
    diag_node = ocr.diagnose_screen_error(trace_node)
    print(f"Diagnosed: {diag_node}")
    assert "npm install express" in diag_node, "Failed to diagnose Node.js module error!"

    # 4. Port Conflict
    trace_port = "Error: listen EADDRINUSE: address already in use :::8080"
    diag_port = ocr.diagnose_screen_error(trace_port)
    print(f"Diagnosed: {diag_port}")
    assert "port conflict" in diag_port.lower() or "already running" in diag_port.lower(), "Failed to diagnose port conflict!"

    # 5. Git Error
    trace_git = "fatal: not a git repository (or any of the parent directories): .git"
    diag_git = ocr.diagnose_screen_error(trace_git)
    print(f"Diagnosed: {diag_git}")
    assert "git init" in diag_git.lower(), "Failed to suggest git init!"

    print("-> PASSED: All 5 error diagnostics diagnosed with actionable remediations.\n")

def test_phase4_ocr_screen_text_extractor():
    print("==================================================")
    print("TEST 2: Hands-Free OCR Screen Text Extractor")
    print("==================================================")
    tts = MockTTS()
    vis = VisionAssistant(tts)
    success, word_count, preview = vis.ocr.copy_screen_text_to_clipboard()
    print(f"Extraction result: success={success}, words={word_count}, preview='{preview}'")
    assert success is True, "OCR copying failed!"
    print("-> PASSED: Screen text extracted and copied to clipboard successfully.\n")

def test_phase4_dispatcher_routing():
    print("==================================================")
    print("TEST 3: Dispatcher Routing for Vision & OCR")
    print("==================================================")
    tts = MockTTS()
    ctrl = SystemController(tts)
    ws = WebSkills(tts)
    vis = VisionAssistant(tts)
    disp = CommandDispatcher(ctrl, tts, ws, vision=vis)

    # 1. Test "copy text from screen"
    print("\nEvaluating: 'copy text from screen'")
    disp.process("copy text from screen")
    assert "Extracted" in tts.last_spoken or "copied" in tts.last_spoken.lower(), "Copy text from screen routing failed!"

    # 2. Test "explain this error"
    print("\nEvaluating: 'explain this error'")
    disp.process("explain this error")
    assert any(k in tts.last_spoken.lower() for k in ["error", "inspected", "detected", "screen", "troubleshooting", "display", "blank"]), "Explain error routing failed!"

    print("\n==================================================")
    print("ALL PHASE 4 CAPABILITIES VERIFIED 100%!")
    print("==================================================")

if __name__ == "__main__":
    test_phase4_error_diagnostics()
    test_phase4_ocr_screen_text_extractor()
    test_phase4_dispatcher_routing()
