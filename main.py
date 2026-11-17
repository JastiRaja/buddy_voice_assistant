import sys
import threading

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
from tts import TextToSpeech
from actions import SystemController
from web_skills import WebSkills
from vision import VisionAssistant
from dispatcher import CommandDispatcher
from stt import SpeechRecognizer
from gui import AssistantHUD

def voice_worker(dispatcher, tts, hud, controller):
    import time
    recognizer = None
    while True:
        if hud and getattr(hud, 'is_shutting_down', False):
            break
        try:
            if recognizer is None:
                recognizer = SpeechRecognizer(tts=tts, hud=hud, controller=controller, dispatcher=dispatcher)
            recognizer.listen_loop(dispatcher.process)
            break  # Exit gracefully if user said "exit" / "power down"
        except KeyboardInterrupt:
            print("\n[!] Exiting assistant on user interrupt...")
            tts.speak("Goodbye, sir.")
            break
        except Exception as e:
            if hud and getattr(hud, 'is_shutting_down', False):
                break
            print(f"\n[Voice Engine Error] {e}")
            if hud:
                hud.set_state("error", "Voice Engine Offline", "Retrying in 5s...")
            print("[*] Automatically retrying voice listener in 5s... (Press Ctrl+C to exit)")
            for _ in range(10):
                if hud and getattr(hud, 'is_shutting_down', False):
                    break
                time.sleep(0.5)

    # Ensure GUI closes cleanly when voice worker exits intentionally (e.g. voice command)
    if hud and hasattr(hud, '_exit_app') and not getattr(hud, 'is_shutting_down', False):
        hud.is_shutting_down = True
        if hasattr(hud, 'root') and hud.root:
            try:
                hud.root.after(0, hud._exit_app)
            except Exception:
                hud._exit_app()
        else:
            hud._exit_app()

def main():
    print("==================================================")
    print("   ◈ [J.A.R.V.I.S. v5.0] ADVANCED DESKTOP AI")
    print("   Neural Speech • Multimodal Vision • Automation")
    print("   Say 'Jarvis' or 'Hey Jarvis' before any command")
    print("==================================================")

    # 1. Initialize local & neural TTS
    tts = TextToSpeech()

    # 2. Initialize Controllers, Web Skills & Vision Assistant
    controller = SystemController(tts)
    web_skills = WebSkills(tts)
    vision = VisionAssistant(tts)

    # 3. Initialize Desktop HUD with controller & vision linkages
    hud = AssistantHUD(tts=tts, controller=controller, vision=vision)
    controller.hud = hud
    controller.vision = vision
    vision.hud = hud

    # 4. Initialize Command Dispatcher
    dispatcher = CommandDispatcher(controller, tts, web_skills, vision=vision, hud=hud)
    hud.dispatcher = dispatcher

    # 4.5 Discover & report connected audio peripherals
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        apis = sd.query_hostapis()
        def_in, def_out = sd.default.device
        from config import load_user_settings
        settings = load_user_settings()
        saved_in = settings.get("audio_device_index")
        saved_out_name = settings.get("audio_output_device_name")
        saved_out_idx = settings.get("audio_output_device_index")
        
        in_name = devices[saved_in]['name'] if saved_in is not None and saved_in < len(devices) else (devices[def_in]['name'] if def_in is not None and def_in < len(devices) else "Default Microphone")
        out_name = saved_out_name if saved_out_name else (devices[saved_out_idx]['name'] if saved_out_idx is not None and saved_out_idx < len(devices) else (devices[def_out]['name'] if def_out is not None and def_out < len(devices) else "Default Speakers"))
        
        in_count = sum(1 for d in devices if d.get('max_input_channels', 0) > 0)
        out_count = sum(1 for d in devices if d.get('max_output_channels', 0) > 0)
        print(f"[*] Audio Hardware: {in_count} Microphones, {out_count} Output Sinks connected.")
        print(f"    🎙️ Active Input (Mic):   {in_name}")
        print(f"    🔊 Active Output (Spk):  {out_name}")
    except Exception as e:
        print(f"[*] Audio Devices: {e}")

    # 5. Announce readiness
    tts.speak("All systems online and ready, sir.", async_mode=True)

    # 6. Global Hotkey Listeners (Ctrl + Space: Push-to-Talk | Ctrl + Alt + S: Emergency Stop)
    try:
        import keyboard
        import time
        from config import WAKE_TIMEOUT_SECONDS
        def on_hotkey():
            dispatcher.active_until = time.time() + WAKE_TIMEOUT_SECONDS
            if hud:
                hud.show()
                hud.set_state("listening", "Push-to-Talk Activated", "Listening, sir...")
            tts.speak("Yes, sir?", async_mode=True)
        keyboard.add_hotkey("ctrl+space", on_hotkey)
        print("[*] Push-to-Talk Hotkey Active: Press [Ctrl + Space] to speak directly.")

        def on_stop_hotkey():
            if hud:
                hud._manual_stop()
        keyboard.add_hotkey("ctrl+alt+s", on_stop_hotkey)
        print("[*] Emergency Stop Hotkey Active: Press [Ctrl + Alt + S] or click [🛑 Stop] to halt speech/actions.")
    except Exception as e:
        print(f"[*] Note: Global hotkey disabled: {e}")

    # 7. Start Voice Worker in background thread
    voice_thread = threading.Thread(target=voice_worker, args=(dispatcher, tts, hud, controller), daemon=True)
    voice_thread.start()

    # 8. Start GUI HUD in main thread
    try:
        hud.start()
    except KeyboardInterrupt:
        print("\n[!] Exiting assistant...")

if __name__ == "__main__":
    main()
