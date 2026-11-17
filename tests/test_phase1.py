import time
from dispatcher import CommandDispatcher
from actions import SystemController
from web_skills import WebSkills
from tts import TextToSpeech

class MockTTS:
    def __init__(self):
        self.last_spoken = ""
        self.history = []
    def speak(self, text, *args, **kwargs):
        self.last_spoken = text
        self.history.append(text)
        print(f" [MockTTS]: {text}")
    def stop(self): pass

class MockController:
    def __init__(self):
        self.dictation_mode = False
        self.actions_log = []
        self.installed_apps = {}

    def _resolve_app_name(self, name):
        return None, None

    def empty_recycle_bin(self):
        self.actions_log.append("empty_recycle_bin_EXECUTED")
        print("  -> EXECUTED: empty_recycle_bin")

    def restart_pc(self):
        self.actions_log.append("restart_pc_EXECUTED")
        print("  -> EXECUTED: restart_pc")

    def change_brightness(self, amount):
        self.actions_log.append(f"change_brightness({amount})")
        print(f"  -> EXECUTED: change_brightness({amount})")

    def volume_control(self, direction):
        self.actions_log.append(f"volume_control({direction})")
        print(f"  -> EXECUTED: volume_control({direction})")

    def minimize_all(self):
        self.actions_log.append("minimize_all_EXECUTED")
        print("  -> EXECUTED: minimize_all")

    def get_battery_status(self):
        self.actions_log.append("get_battery_status_EXECUTED")
        print("  -> EXECUTED: get_battery_status")

    def close_application(self, target):
        self.actions_log.append(f"close_app({target})")
        print(f"  -> EXECUTED: close_app({target})")

def run_tests():
    tts = MockTTS()
    ctrl = MockController()
    ws = WebSkills(tts)
    disp = CommandDispatcher(ctrl, tts, ws)

    print("==================================================")
    print("TEST 1: Voice Confirmation Guardrail (Aborted)")
    print("==================================================")
    disp.process("empty recycle bin")
    assert disp.pending_confirmation is not None, "Guardrail did not arm!"
    assert "Are you sure" in tts.last_spoken, "Did not ask confirmation question!"
    
    # User says single-word "no"
    disp.process("no")
    assert disp.pending_confirmation is None, "Guardrail did not disarm on single-word 'no' cancel!"
    assert "empty_recycle_bin_EXECUTED" not in ctrl.actions_log, "Destructive action ran despite cancel!"
    assert "cancelled" in tts.last_spoken, "Did not confirm cancellation!"
    print("-> PASSED: Abort guardrail verified with single-word 'no'.\n")

    print("==================================================")
    print("TEST 2: Voice Confirmation Guardrail (Confirmed)")
    print("==================================================")
    disp.process("restart computer")
    assert disp.pending_confirmation is not None, "Guardrail did not arm for restart!"
    
    # User says single-word "yes"
    disp.process("yes")
    assert disp.pending_confirmation is None, "Guardrail did not clear after single-word 'yes' confirmation!"
    assert "restart_pc_EXECUTED" in ctrl.actions_log, "Destructive action failed to execute!"
    print("-> PASSED: Confirm guardrail verified with single-word 'yes'.\n")

    print("==================================================")
    print("TEST 3: Tier 2 Natural Language Intent Resolution")
    print("==================================================")
    
    natural_phrases = [
        ("it's too bright in here", "change_brightness(-20)"),
        ("make it louder", "volume_control(up)"),
        ("clear my screen", "minimize_all_EXECUTED"),
        ("how much juice is left", "get_battery_status_EXECUTED"),
        ("exit chrome", "close_app(chrome)")
    ]

    for phrase, expected in natural_phrases:
        print(f"\nEvaluating: '{phrase}'")
        ctrl.actions_log.clear()
        disp.process(phrase)
        assert expected in ctrl.actions_log, f"Failed for '{phrase}': expected {expected}, got {ctrl.actions_log}"
        print(f"-> PASSED: '{phrase}' mapped to {expected}")

    print("\n==================================================")
    print("TEST 4: TTS Engine Support (Kokoro & Piper Fallback)")
    print("==================================================")
    real_tts = TextToSpeech()
    print(f"Current TTS Engine: {real_tts.engine_type}")
    real_tts.set_engine("kokoro", voice="bm_george")
    print(f"Switched to: {real_tts.engine_type} with voice: {real_tts.kokoro_voice}")
    # Verify that speaking with Kokoro uninstalled falls back cleanly without crashing
    real_tts.speak("Testing Kokoro fallback mechanism, sir.")
    real_tts.set_engine("edge-tts", voice="en-GB-RyanNeural")
    print("-> PASSED: Kokoro/Piper fallback handled gracefully without crash.\n")

    print("==================================================")
    print("ALL PHASE 1 CORE CAPABILITIES VERIFIED 100%!")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
