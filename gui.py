import math
import os
import random
import threading
import time
import json
import psutil
import sounddevice as sd
import pyperclip
from PIL import Image
import customtkinter as ctk
from screeninfo import get_monitors
from config import (
    AVAILABLE_EDGE_VOICES,
    AVAILABLE_KOKORO_VOICES,
    AVAILABLE_SAPI_VOICES,
    TTS_ENGINE,
    EDGE_VOICE,
    GEMINI_API_KEY,
    STRICT_OFFLINE_MODE,
    AUDIO_DEVICE_INDEX,
    AUDIO_OUTPUT_DEVICE_INDEX,
    AUDIO_OUTPUT_DEVICE_NAME,
    load_user_settings,
    save_user_settings
)

ctk.set_appearance_mode("dark")

class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent, hud):
        super().__init__(parent)
        self.hud = hud
        self.title("J.A.R.V.I.S. Core Configuration")
        self.geometry("480x640")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.configure(fg_color="#030712")
        self.bind("<Escape>", lambda e: self.destroy())

        self.settings = load_user_settings()

        # Title
        title_lbl = ctk.CTkLabel(
            self,
            text="⚡ J.A.R.V.I.S. SETTINGS & HARDWARE",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color="#00f2fe"
        )
        title_lbl.pack(pady=(16, 12))

        # Main Scrollable Form Frame
        form_frame = ctk.CTkScrollableFrame(self, fg_color="#090e17", corner_radius=12)
        form_frame.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        # 1. TTS Engine & Voice
        ctk.CTkLabel(form_frame, text="Neural Voice Synthesis:", font=ctk.CTkFont(weight="bold"), text_color="#38bdf8").pack(anchor="w", pady=(8, 2))
        
        current_engine = self.settings.get("tts_engine", "edge-tts")
        self.engine_var = ctk.StringVar(value=current_engine)
        engine_menu = ctk.CTkOptionMenu(
            form_frame,
            values=["edge-tts", "kokoro", "piper", "pyttsx3"],
            variable=self.engine_var,
            command=self._on_engine_change,
            fg_color="#0f172a",
            button_color="#0284c7"
        )
        engine_menu.pack(fill="x", pady=(0, 8))

        self.voice_label = ctk.CTkLabel(
            form_frame,
            text=f"Voice Personality ({'Kokoro ONNX' if current_engine == 'kokoro' else 'Edge-TTS'}):",
            font=ctk.CTkFont(weight="bold"),
            text_color="#38bdf8"
        )
        self.voice_label.pack(anchor="w", pady=(4, 2))
        
        if current_engine == "kokoro":
            voice_names = list(AVAILABLE_KOKORO_VOICES.keys())
            current_voice_id = self.settings.get("kokoro_voice", "bm_george")
            current_label = voice_names[0]
            for name, vid in AVAILABLE_KOKORO_VOICES.items():
                if vid == current_voice_id:
                    current_label = name
                    break
        elif current_engine == "pyttsx3":
            voice_names = list(AVAILABLE_SAPI_VOICES.keys())
            current_voice_id = self.settings.get("sapi_voice", "TTS_MS_EN-US_DAVID_11.0")
            current_label = voice_names[0]
            for name, vid in AVAILABLE_SAPI_VOICES.items():
                if vid == current_voice_id:
                    current_label = name
                    break
        else:
            voice_names = list(AVAILABLE_EDGE_VOICES.keys())
            current_voice_id = self.settings.get("edge_voice", "en-GB-RyanNeural")
            current_label = voice_names[0]
            for name, vid in AVAILABLE_EDGE_VOICES.items():
                if vid == current_voice_id:
                    current_label = name
                    break

        self.voice_var = ctk.StringVar(value=current_label)
        self.voice_menu = ctk.CTkOptionMenu(
            form_frame,
            values=voice_names,
            variable=self.voice_var,
            fg_color="#0f172a",
            button_color="#0284c7"
        )
        self.voice_menu.pack(fill="x", pady=(0, 4))

        # Voice preview test row
        voice_test_row = ctk.CTkFrame(form_frame, fg_color="transparent")
        voice_test_row.pack(fill="x", pady=(0, 10))
        self.voice_status_lbl = ctk.CTkLabel(
            voice_test_row,
            text="Click Preview to test voice output",
            font=ctk.CTkFont(size=10),
            text_color="#94a3b8"
        )
        self.voice_status_lbl.pack(side="left")
        ctk.CTkButton(
            voice_test_row,
            text="🔊 Preview Voice",
            width=100,
            height=22,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#1e293b",
            hover_color="#0284c7",
            command=self._preview_voice
        ).pack(side="right")

        # Determine system defaults
        default_mic_name = "System Default"
        default_spk_name = "System Default"
        def_in_idx, def_out_idx = None, None
        devices = []
        apis = []
        try:
            def_in_idx, def_out_idx = sd.default.device
            devices = sd.query_devices()
            apis = sd.query_hostapis()
            if def_in_idx is not None and def_in_idx < len(devices):
                default_mic_name = devices[def_in_idx]['name']
            if def_out_idx is not None and def_out_idx < len(devices):
                default_spk_name = devices[def_out_idx]['name']
        except Exception:
            pass

        # 2. Microphone Audio Device Picker
        ctk.CTkLabel(form_frame, text="Microphone Input Device:", font=ctk.CTkFont(weight="bold"), text_color="#38bdf8").pack(anchor="w", pady=(4, 2))
        
        self.device_options = [f"System Default ({default_mic_name[:28]})"]
        self.device_indices = [None]
        for idx, dev in enumerate(devices):
            if dev.get('max_input_channels', 0) > 0:
                api_name = apis[dev['hostapi']]['name'] if dev.get('hostapi', 0) < len(apis) else ""
                tag = " [Default]" if idx == def_in_idx else ""
                name = f"[{idx}] {dev['name']} ({api_name}){tag}"
                self.device_options.append(name)
                self.device_indices.append(idx)

        saved_idx = self.settings.get("audio_device_index", None)
        selected_dev_label = self.device_options[0]
        if saved_idx is not None and saved_idx in self.device_indices:
            pos = self.device_indices.index(saved_idx)
            selected_dev_label = self.device_options[pos]

        self.device_var = ctk.StringVar(value=selected_dev_label)
        self.device_menu = ctk.CTkOptionMenu(
            form_frame,
            values=self.device_options,
            variable=self.device_var,
            fg_color="#0f172a",
            button_color="#0284c7"
        )
        self.device_menu.pack(fill="x", pady=(0, 4))

        # Mic Test Row
        mic_test_row = ctk.CTkFrame(form_frame, fg_color="transparent")
        mic_test_row.pack(fill="x", pady=(0, 10))
        self.mic_status_lbl = ctk.CTkLabel(
            mic_test_row,
            text=f"Active: {default_mic_name[:26]}",
            font=ctk.CTkFont(size=10),
            text_color="#94a3b8"
        )
        self.mic_status_lbl.pack(side="left")
        ctk.CTkButton(
            mic_test_row,
            text="🎙️ Test Mic",
            width=80,
            height=22,
            font=ctk.CTkFont(size=10),
            fg_color="#1e293b",
            hover_color="#0284c7",
            command=self._test_microphone
        ).pack(side="right")

        # 2.1 Speaker Audio Output Device Picker
        ctk.CTkLabel(form_frame, text="Speaker Output Device (Voice Playback):", font=ctk.CTkFont(weight="bold"), text_color="#38bdf8").pack(anchor="w", pady=(4, 2))
        
        self.output_options = [f"System Default ({default_spk_name[:28]})"]
        self.output_indices = [None]
        self.output_names = [None]
        for idx, dev in enumerate(devices):
            if dev.get('max_output_channels', 0) > 0:
                api_name = apis[dev['hostapi']]['name'] if dev.get('hostapi', 0) < len(apis) else ""
                tag = " [Default]" if idx == def_out_idx else ""
                name = f"[{idx}] {dev['name']} ({api_name}){tag}"
                self.output_options.append(name)
                self.output_indices.append(idx)
                self.output_names.append(dev['name'])

        saved_out_idx = self.settings.get("audio_output_device_index", None)
        saved_out_name = self.settings.get("audio_output_device_name", None)
        selected_out_label = self.output_options[0]
        if saved_out_idx is not None and saved_out_idx in self.output_indices:
            pos = self.output_indices.index(saved_out_idx)
            selected_out_label = self.output_options[pos]
        elif saved_out_name is not None and saved_out_name in self.output_names:
            pos = self.output_names.index(saved_out_name)
            selected_out_label = self.output_options[pos]

        self.output_var = ctk.StringVar(value=selected_out_label)
        self.output_menu = ctk.CTkOptionMenu(
            form_frame,
            values=self.output_options,
            variable=self.output_var,
            fg_color="#0f172a",
            button_color="#0284c7"
        )
        self.output_menu.pack(fill="x", pady=(0, 4))

        # Speaker Test Row
        spk_test_row = ctk.CTkFrame(form_frame, fg_color="transparent")
        spk_test_row.pack(fill="x", pady=(0, 10))
        self.spk_status_lbl = ctk.CTkLabel(
            spk_test_row,
            text=f"Active: {default_spk_name[:26]}",
            font=ctk.CTkFont(size=10),
            text_color="#94a3b8"
        )
        self.spk_status_lbl.pack(side="left")
        ctk.CTkButton(
            spk_test_row,
            text="🔊 Test Sound",
            width=80,
            height=22,
            font=ctk.CTkFont(size=10),
            fg_color="#1e293b",
            hover_color="#0284c7",
            command=self._test_speaker
        ).pack(side="right")

        # 3. Speech Recognition Model Selection
        ctk.CTkLabel(form_frame, text="Speech Recognition Model:", font=ctk.CTkFont(weight="bold"), text_color="#38bdf8").pack(anchor="w", pady=(4, 2))
        self.stt_models = {
            "Whisper Small (High Accuracy, ~460MB)": "small.en",
            "Whisper Base (Fast, 39MB)": "base.en"
        }
        current_model = self.settings.get("whisper_model_size", "small.en")
        current_stt_label = "Whisper Small (High Accuracy, ~460MB)"
        for k, v in self.stt_models.items():
            if v == current_model:
                current_stt_label = k
                break
        self.stt_model_var = ctk.StringVar(value=current_stt_label)
        self.stt_menu = ctk.CTkOptionMenu(
            form_frame,
            values=list(self.stt_models.keys()),
            variable=self.stt_model_var,
            fg_color="#0f172a",
            button_color="#0284c7"
        )
        self.stt_menu.pack(fill="x", pady=(0, 12))

        # 4. Multimodal & General AI (Gemini API Key)
        ctk.CTkLabel(form_frame, text="Gemini AI API Key (Smart Q&A & Multimodal Screen Vision):", font=ctk.CTkFont(weight="bold"), text_color="#38bdf8").pack(anchor="w", pady=(4, 2))
        self.api_key_entry = ctk.CTkEntry(
            form_frame,
            placeholder_text="Enter Gemini API Key (e.g. AIzaSy...)",
            show="*",
            fg_color="#0f172a",
            border_color="#1e293b",
            text_color="#f8fafc"
        )
        saved_key = self.settings.get("gemini_api_key", "")
        if saved_key:
            self.api_key_entry.insert(0, saved_key)
        self.api_key_entry.pack(fill="x", pady=(0, 12))

        # 5. Screen Vision Mode (Hybrid: Gemini Multimodal + Local Telemetry)
        ctk.CTkLabel(form_frame, text="Screen Vision Intelligence Mode:", font=ctk.CTkFont(weight="bold"), text_color="#38bdf8").pack(anchor="w", pady=(4, 2))
        vision_desc = "🟢 Gemini 1.5 Flash Multimodal Vision Enabled" if saved_key else "🟢 100% On-Device Local Telemetry (Private & Air-Gapped)"
        mode_badge = ctk.CTkLabel(
            form_frame,
            text=vision_desc,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#22c55e",
            anchor="w"
        )
        mode_badge.pack(fill="x", pady=(0, 8))

        # 6. Strict Offline Mode Toggle
        self.offline_var = ctk.BooleanVar(value=self.settings.get("strict_offline_mode", False))
        self.offline_chk = ctk.CTkCheckBox(
            form_frame,
            text="Air-Gapped Offline Mode (Block external AI & web)",
            variable=self.offline_var,
            command=self._on_offline_toggle,
            text_color="#e2e8f0",
            fg_color="#0284c7"
        )
        self.offline_chk.pack(anchor="w", pady=(4, 6))

        # 7. Require Wake Word Toggle (Eliminates stray/noise activations)
        self.wake_word_var = ctk.BooleanVar(value=self.settings.get("require_wake_word", True))
        self.wake_word_chk = ctk.CTkCheckBox(
            form_frame,
            text="Require Wake Word ('Jarvis' or Ctrl+Space)",
            variable=self.wake_word_var,
            text_color="#e2e8f0",
            fg_color="#0284c7"
        )
        self.wake_word_chk.pack(anchor="w", pady=(2, 12))

        # Save and Close Button
        save_btn = ctk.CTkButton(
            self,
            text="💾 Save Configuration",
            font=ctk.CTkFont(weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            command=self._save_and_close
        )
        save_btn.pack(fill="x", padx=16, pady=(0, 16))

    def _preview_voice(self):
        chosen_engine = self.engine_var.get()
        chosen_voice_name = self.voice_var.get()
        is_offline = self.offline_var.get()

        if chosen_engine == "kokoro":
            chosen_voice_id = AVAILABLE_KOKORO_VOICES.get(chosen_voice_name, "bm_george")
        elif chosen_engine == "pyttsx3":
            chosen_voice_id = AVAILABLE_SAPI_VOICES.get(chosen_voice_name, "TTS_MS_EN-US_DAVID_11.0")
        else:
            chosen_voice_id = AVAILABLE_EDGE_VOICES.get(chosen_voice_name, "en-GB-RyanNeural")

        if self.hud.tts:
            self.hud.tts.set_engine(chosen_engine, chosen_voice_id, strict_offline=is_offline)
            clean_name = chosen_voice_name.split(" (")[0]
            preview_phrase = f"Hello sir, I am {clean_name}. Voice synthesis is operational."
            self.voice_status_lbl.configure(text=f"▶ Speaking: {clean_name}", text_color="#38bdf8")
            self.hud.tts.speak(preview_phrase, async_mode=True)

    def _on_offline_toggle(self):
        is_offline = self.offline_var.get()
        if is_offline:
            # Switch to local SAPI5 voices for true offline operation
            self.engine_var.set("pyttsx3")
            self._on_engine_change("pyttsx3")
            self.voice_status_lbl.configure(text="🔒 Air-Gapped enabled: Local SAPI5 voices active", text_color="#f59e0b")
        else:
            # Switch back to Edge-TTS studio neural voices
            self.engine_var.set("edge-tts")
            self._on_engine_change("edge-tts")
            self.voice_status_lbl.configure(text="🌐 Online enabled: Studio Neural voices active", text_color="#22c55e")

    def _on_engine_change(self, engine_val: str):
        if engine_val == "kokoro":
            v_names = list(AVAILABLE_KOKORO_VOICES.keys())
            self.voice_label.configure(text="Voice Personality (Kokoro ONNX):")
            self.voice_menu.configure(values=v_names)
            curr_kokoro = self.settings.get("kokoro_voice", "bm_george")
            match = next((name for name, vid in AVAILABLE_KOKORO_VOICES.items() if vid == curr_kokoro), v_names[0])
            self.voice_var.set(match)
        elif engine_val == "edge-tts":
            v_names = list(AVAILABLE_EDGE_VOICES.keys())
            self.voice_label.configure(text="Voice Personality (Edge-TTS):")
            self.voice_menu.configure(values=v_names)
            curr_edge = self.settings.get("edge_voice", "en-GB-RyanNeural")
            match = next((name for name, vid in AVAILABLE_EDGE_VOICES.items() if vid == curr_edge), v_names[0])
            self.voice_var.set(match)
        elif engine_val == "pyttsx3":
            v_names = list(AVAILABLE_SAPI_VOICES.keys())
            self.voice_label.configure(text="Voice Personality (System SAPI5):")
            self.voice_menu.configure(values=v_names)
            curr_sapi = self.settings.get("sapi_voice", "TTS_MS_EN-US_DAVID_11.0")
            match = next((name for name, vid in AVAILABLE_SAPI_VOICES.items() if vid == curr_sapi), v_names[0])
            self.voice_var.set(match)
        else:
            self.voice_label.configure(text="Voice Personality (System Standard):")
            self.voice_menu.configure(values=["Default System Voice"])
            self.voice_var.set("Default System Voice")

    def _save_and_close(self):
        chosen_engine = self.engine_var.get()
        chosen_voice_name = self.voice_var.get()

        if chosen_engine == "kokoro":
            chosen_voice_id = AVAILABLE_KOKORO_VOICES.get(chosen_voice_name, "bm_george")
            self.settings["kokoro_voice"] = chosen_voice_id
            if any(w in chosen_voice_id.lower() for w in ["emma", "heart", "nicole", "female"]):
                self.settings["edge_voice"] = "en-GB-SoniaNeural"
                self.settings["sapi_voice"] = "TTS_MS_EN-US_ZIRA_11.0"
            else:
                self.settings["edge_voice"] = "en-GB-RyanNeural"
                self.settings["sapi_voice"] = "TTS_MS_EN-US_DAVID_11.0"
        elif chosen_engine == "pyttsx3":
            chosen_voice_id = AVAILABLE_SAPI_VOICES.get(chosen_voice_name, "TTS_MS_EN-US_DAVID_11.0")
            self.settings["sapi_voice"] = chosen_voice_id
            if any(w in chosen_voice_id.lower() for w in ["zira", "heera", "female"]):
                self.settings["edge_voice"] = "en-IN-NeerjaNeural" if "heera" in chosen_voice_id.lower() else "en-GB-SoniaNeural"
                self.settings["kokoro_voice"] = "bf_emma"
            else:
                if "ravi" in chosen_voice_id.lower():
                    self.settings["edge_voice"] = "en-IN-PrabhatNeural"
                elif "mark" in chosen_voice_id.lower():
                    self.settings["edge_voice"] = "en-US-ChristopherNeural"
                else:
                    self.settings["edge_voice"] = "en-GB-RyanNeural"
                self.settings["kokoro_voice"] = "bm_george"
        else:
            chosen_voice_id = AVAILABLE_EDGE_VOICES.get(chosen_voice_name, "en-GB-RyanNeural")
            self.settings["edge_voice"] = chosen_voice_id
            if any(w in chosen_voice_id.lower() for w in ["sonia", "jenny", "ava", "neerja", "female"]):
                self.settings["sapi_voice"] = "MSTTS_V110_enIN_HeeraM" if "neerja" in chosen_voice_id.lower() else "TTS_MS_EN-US_ZIRA_11.0"
                self.settings["kokoro_voice"] = "bf_emma"
            else:
                if "prabhat" in chosen_voice_id.lower():
                    self.settings["sapi_voice"] = "MSTTS_V110_enIN_RaviM"
                elif "christopher" in chosen_voice_id.lower():
                    self.settings["sapi_voice"] = "MSTTS_V110_enUS_MarkM"
                else:
                    self.settings["sapi_voice"] = "TTS_MS_EN-US_DAVID_11.0"
                self.settings["kokoro_voice"] = "bm_george"

        self.settings["tts_engine"] = chosen_engine

        # Microphone Input Device
        chosen_dev_str = self.device_var.get()
        dev_idx = None
        if chosen_dev_str in self.device_options:
            pos = self.device_options.index(chosen_dev_str)
            dev_idx = self.device_indices[pos]

        # Speaker Output Device
        chosen_out_str = self.output_var.get()
        out_idx = None
        out_name = None
        if chosen_out_str in self.output_options:
            pos = self.output_options.index(chosen_out_str)
            out_idx = self.output_indices[pos]
            out_name = self.output_names[pos]

        chosen_stt_label = self.stt_model_var.get()
        chosen_stt_model = self.stt_models.get(chosen_stt_label, "base.en")

        self.settings["audio_device_index"] = dev_idx
        self.settings["audio_output_device_index"] = out_idx
        self.settings["audio_output_device_name"] = out_name
        self.settings["whisper_model_size"] = chosen_stt_model
        self.settings["gemini_api_key"] = self.api_key_entry.get().strip()
        self.settings["strict_offline_mode"] = self.offline_var.get()
        self.settings["require_wake_word"] = self.wake_word_var.get()

        save_user_settings(self.settings)

        if self.hud.tts:
            self.hud.tts.set_output_device(out_name, out_idx)
            self.hud.tts.set_engine(
                chosen_engine,
                chosen_voice_id,
                strict_offline=self.settings["strict_offline_mode"]
            )
            self.hud.tts.speak(f"Configuration updated, sir.", async_mode=True)
        
        self.hud.set_state("idle", "Settings Saved", f"Voice set to {chosen_voice_name}")
        self.destroy()

    def _test_microphone(self):
        chosen_str = self.device_var.get()
        dev_idx = None
        if chosen_str in self.device_options:
            pos = self.device_options.index(chosen_str)
            dev_idx = self.device_indices[pos]

        def _bg_test():
            try:
                import numpy as np
                self.after(0, lambda: self.mic_status_lbl.configure(text="Listening... speak now!", text_color="#38bdf8"))
                rec = sd.rec(int(1.2 * 16000), samplerate=16000, channels=1, device=dev_idx, blocking=True)
                rms = float(np.sqrt(np.mean(rec ** 2)))
                level_pct = min(100, int(rms * 2500))
                if level_pct > 1:
                    self.after(0, lambda: self.mic_status_lbl.configure(text=f"✅ Signal OK ({level_pct}%)", text_color="#22c55e"))
                else:
                    self.after(0, lambda: self.mic_status_lbl.configure(text=f"⚠️ Low signal ({level_pct}%)", text_color="#f59e0b"))
            except Exception as e:
                err_msg = str(e)[:22]
                self.after(0, lambda: self.mic_status_lbl.configure(text=f"❌ Error: {err_msg}", text_color="#ef4444"))

        threading.Thread(target=_bg_test, daemon=True).start()

    def _test_speaker(self):
        chosen_str = self.output_var.get()
        out_idx = None
        out_name = None
        if chosen_str in self.output_options:
            pos = self.output_options.index(chosen_str)
            out_idx = self.output_indices[pos]
            out_name = self.output_names[pos]

        if self.hud.tts:
            self.hud.tts.set_output_device(out_name, out_idx)
            chosen_engine = self.engine_var.get()
            chosen_voice_name = self.voice_var.get()
            if chosen_engine == "kokoro":
                vid = AVAILABLE_KOKORO_VOICES.get(chosen_voice_name, "bm_george")
            elif chosen_engine == "pyttsx3":
                vid = AVAILABLE_SAPI_VOICES.get(chosen_voice_name, "TTS_MS_EN-US_DAVID_11.0")
            else:
                vid = AVAILABLE_EDGE_VOICES.get(chosen_voice_name, "en-GB-RyanNeural")
            self.hud.tts.set_engine(chosen_engine, vid, strict_offline=self.offline_var.get())
            self.hud.tts.speak("Audio output test. Voice playback operational, sir.", async_mode=True)
            self.spk_status_lbl.configure(text="✅ Playing test audio...", text_color="#22c55e")


class CommandsCatalogDialog(ctk.CTkToplevel):
    """
    Futuristic HUD Modal displaying the full catalog of voice commands and actions
    supported by J.A.R.V.I.S., organized by category with live search filter.
    """
    COMMANDS_DATA = [
        {
            "category": "📁 Files & Folder Management",
            "commands": [
                ("Open folder [name]", "Opens any library or subfolder (e.g. 'Open folder camera roll', 'Open folder screenshots')"),
                ("How many folders in [name] folder?", "Counts and lists subfolders (e.g. 'How many folders are there in pictures folder?')"),
                ("How many files in [name] folder?", "Counts and previews files in directory (e.g. 'How many files in downloads?')"),
                ("How many items in [name] folder?", "Reports total count of folders and files combined in requested directory"),
                ("Open [library]", "Opens standard folders: 'Open pictures', 'Open downloads', 'Open documents', 'Open desktop'"),
                ("List files / Show files", "Lists recent files in the current or specified folder"),
                ("Open latest file / download", "Finds and opens the most recently saved or downloaded file"),
                ("Clean up / Organize downloads", "Automatically sorts files into categorized subfolders (Images, Docs, Installers, etc.)"),
                ("Open [letter] drive", "Opens any mounted volume (e.g. 'Open C drive', 'Open D drive')"),
                ("Open This PC / My Computer", "Opens File Explorer system drives overview")
            ]
        },
        {
            "category": "📬 Gmail & Google Apps",
            "commands": [
                ("Read my emails / Read Gmail", "Inspects open inbox on screen with Gemini Vision, or opens Gmail in browser"),
                ("Open Gmail", "Opens https://mail.google.com in default browser"),
                ("Open Google Docs / Docs", "Opens Google Docs document editor"),
                ("Open Google Sheets / Sheets", "Opens Google Sheets spreadsheet editor"),
                ("Open Google Drive / Drive", "Opens Google Drive cloud storage overview"),
                ("Open Google Calendar / Calendar", "Opens Google Calendar schedule"),
                ("Open Google Meet / Meet", "Opens Google Meet video conferencing"),
                ("Open Google Slides / Slides", "Opens Google Slides presentation builder"),
                ("Open Google Photos / Photos", "Opens your cloud Google Photos library"),
                ("Open Google Keep / Keep", "Opens your Google Keep cloud notes"),
                ("Open Google Maps / Maps", "Opens Google Maps navigation"),
                ("Open YouTube Music", "Opens YouTube Music web player")
            ]
        },
        {
            "category": "👁️ Vision & Multimodal Screen Intelligence",
            "commands": [
                ("What's on my screen? / Read screen", "Multimodal AI visual inspection of active window, emails, documents, or code (auto-hides HUD overlay)"),
                ("What do you see? / Inspect screen", "Real-time visual description of open display powered by Gemini AI"),
                ("Explain this error / Debug screen", "Inspects on-screen error dialogs or terminal stack traces with actionable remedies"),
                ("Copy text from screen / OCR", "Extracts visible on-screen text directly into your clipboard")
            ]
        },
        {
            "category": "🚀 Apps & Window Management",
            "commands": [
                ("Open / Launch [app]", "Opens any installed program (e.g. 'Open Chrome', 'Open Notepad', 'Open Spotify')"),
                ("Close [app] / Close window", "Safely closes focused window or specific running application"),
                ("List installed apps", "Voice summary of dynamically discovered applications on your computer"),
                ("Read app notes", "Reads dynamic knowledge base summary from SYSTEM_APPS_NOTES.md"),
                ("Snap left / Snap right", "Snaps active window to left or right half of the screen"),
                ("Maximize / Minimize window", "Expands or minimizes focused window"),
                ("Minimize all / Show desktop", "Minimizes all open windows to reveal desktop")
            ]
        },
        {
            "category": "⚡ Hardware & System Controls",
            "commands": [
                ("System status / Diagnostics", "Reports real-time CPU, RAM, battery level, and power state"),
                ("Volume [up / down / mute / 50%]", "Controls master system audio level, mute, or specific percentage"),
                ("Brightness [up / down / 80%]", "Adjusts monitor display brightness level"),
                ("Lock PC / Sleep / Restart", "Locks workstation, enters sleep mode, or restarts system"),
                ("Empty recycle bin", "Cleans Windows Recycle Bin with voice confirmation guardrail")
            ]
        },
        {
            "category": "✍️ Smart Writing & Document RAG",
            "commands": [
                ("Search my documents for [query]", "Semantic search through local documents (PDF, DOCX, TXT) via local RAG vector indexing"),
                ("Make professional", "Polishes selected text or clipboard into workplace-ready professional tone"),
                ("Make concise", "Shortens and tightens highlighted text"),
                ("Fix grammar", "Corrects typos, grammar, and punctuation in highlighted text"),
                ("Read clipboard history", "Reads aloud recent items from your clipboard history")
            ]
        },
        {
            "category": "🌐 Web, Q&A & Intelligence",
            "commands": [
                ("Search YouTube for [topic]", "Searches and plays requested topic or music directly on YouTube"),
                ("Google search [query]", "Launches Google search in default browser"),
                ("Weather in [city]", "Speaks live weather condition and temperature"),
                ("Latest news / Headlines", "Fetches and reads top current news headlines"),
                ("Calculate [math expression]", "Solves arithmetic, square roots, percentages, and unit conversions"),
                ("Ask any question...", "General knowledge answered via Gemini AI or offline knowledge base")
            ]
        },
        {
            "category": "⏱️ Timers, Notes & Macros",
            "commands": [
                ("Set timer for [X] minutes", "Sets background voice countdown timer with completion alert"),
                ("Take note: [content]", "Appends note with timestamp to Buddy_Notes.txt"),
                ("Read my notes", "Speaks recorded notes back to you"),
                ("Start dictation / Stop dictation", "Hands-free continuous typing anywhere cursor is placed"),
                ("Morning briefing", "Speaks current time, date, hardware metrics, and agenda"),
                ("Activate stealth mode", "Executes multi-step voice macro routine"),
                ("Stop listening / Standby", "Pauses assistant into passive listening mode")
            ]
        }
    ]

    def __init__(self, parent, hud):
        super().__init__(parent)
        self.hud = hud
        self.title("J.A.R.V.I.S. Command Catalog")
        self.geometry("540x660")
        self.resizable(False, False)
        self.configure(fg_color="#030712")
        self.transient(parent)
        self.grab_set()

        # Header
        hdr = ctk.CTkFrame(self, fg_color="#0a101f", corner_radius=12, border_width=1, border_color="#00f2fe")
        hdr.pack(fill="x", padx=14, pady=(12, 8))
        ctk.CTkLabel(hdr, text="📜 J.A.R.V.I.S. VOICE COMMANDS CATALOG", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color="#00f2fe").pack(anchor="w", padx=12, pady=(8, 2))
        ctk.CTkLabel(hdr, text="Say any command below aloud or type in search filter to find capabilities.", font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#94a3b8").pack(anchor="w", padx=12, pady=(0, 8))

        # Search Bar
        search_frame = ctk.CTkFrame(self, fg_color="transparent")
        search_frame.pack(fill="x", padx=14, pady=(0, 8))
        self.search_entry = ctk.CTkEntry(
            search_frame,
            placeholder_text="🔍 Type to filter commands (e.g. camera roll, vision, volume, timer)...",
            fg_color="#0f172a",
            border_color="#1e293b",
            text_color="#f8fafc",
            height=32
        )
        self.search_entry.pack(fill="x")
        self.search_entry.bind("<KeyRelease>", self._filter_commands)

        # Scrollable Commands Container
        self.scroll_frame = ctk.CTkScrollableFrame(self, fg_color="#070c18", corner_radius=12, border_width=1, border_color="#1e293b")
        self.scroll_frame.pack(fill="both", expand=True, padx=14, pady=(0, 12))

        self._render_commands("")

    def _filter_commands(self, event=None):
        query = self.search_entry.get().strip().lower()
        self._render_commands(query)

    def _render_commands(self, query: str):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        match_count = 0
        for section in self.COMMANDS_DATA:
            cat_title = section["category"]
            matching_cmds = []
            for cmd_phrase, cmd_desc in section["commands"]:
                if not query or query in cmd_phrase.lower() or query in cmd_desc.lower() or query in cat_title.lower():
                    matching_cmds.append((cmd_phrase, cmd_desc))

            if matching_cmds:
                match_count += len(matching_cmds)
                cat_hdr = ctk.CTkLabel(
                    self.scroll_frame,
                    text=cat_title,
                    font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                    text_color="#38bdf8",
                    anchor="w"
                )
                cat_hdr.pack(fill="x", pady=(8, 4), padx=4)

                for cmd_phrase, cmd_desc in matching_cmds:
                    card = ctk.CTkFrame(self.scroll_frame, fg_color="#0f172a", corner_radius=8, border_width=1, border_color="#1e293b")
                    card.pack(fill="x", pady=2, padx=2)

                    ctk.CTkLabel(
                        card,
                        text=f"🗣️  \"{cmd_phrase}\"",
                        font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
                        text_color="#00ffcc",
                        anchor="w"
                    ).pack(fill="x", padx=8, pady=(4, 1))

                    ctk.CTkLabel(
                        card,
                        text=cmd_desc,
                        font=ctk.CTkFont(family="Segoe UI", size=9),
                        text_color="#cbd5e1",
                        anchor="w",
                        wraplength=470,
                        justify="left"
                    ).pack(fill="x", padx=8, pady=(0, 4))

        if match_count == 0:
            ctk.CTkLabel(
                self.scroll_frame,
                text=f"No commands found matching '{query}'.\nYou can still ask J.A.R.V.I.S. in natural speech!",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color="#64748b"
            ).pack(pady=40)


class ScreenVisualizerDialog(ctk.CTkToplevel):
    """
    Futuristic Cybernetic Holographic Dialog for visualizing screen content,
    screenshot layout, active window bounding box, and extracted UI elements.
    """
    def __init__(self, parent, hud, telemetry: dict, thumbnail_img: Image.Image = None):
        super().__init__(parent)
        self.hud = hud
        self.telemetry = telemetry
        self.thumbnail_img = thumbnail_img

        self.title("J.A.R.V.I.S. Screen Content Visualizer")
        self.geometry("560x680")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.configure(fg_color="#030712")
        self.bind("<Escape>", lambda e: self.destroy())

        self._build_ui()

    def _build_ui(self):
        # 1. Header Bar
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(14, 6))

        title_badge = ctk.CTkFrame(header, fg_color="#0a192f", corner_radius=8, border_width=1, border_color="#00b4d8")
        title_badge.pack(side="left")

        title_lbl = ctk.CTkLabel(
            title_badge,
            text=" 👁️ J.A.R.V.I.S. VISUAL SCREEN INSPECTOR ",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#00f2fe"
        )
        title_lbl.pack(padx=8, pady=3)

        mode_badge = ctk.CTkLabel(
            header,
            text="● LOCAL VISUAL ENGINE",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color="#22c55e"
        )
        mode_badge.pack(side="left", padx=8)

        close_btn = ctk.CTkButton(
            header,
            text="✕",
            width=24,
            height=24,
            corner_radius=6,
            fg_color="#0f172a",
            hover_color="#ef4444",
            text_color="#94a3b8",
            command=self.destroy
        )
        close_btn.pack(side="right")

        # 2. Main Scrollable Container
        content_scroll = ctk.CTkScrollableFrame(self, fg_color="#090e17", corner_radius=14, border_width=1, border_color="#1e3a5f")
        content_scroll.pack(fill="both", expand=True, padx=14, pady=(2, 10))

        # 3. Screenshot Visualizer Preview Card
        preview_card = ctk.CTkFrame(content_scroll, fg_color="#030712", corner_radius=10, border_width=1, border_color="#00f2fe")
        preview_card.pack(fill="x", padx=8, pady=(8, 10))

        if self.thumbnail_img:
            try:
                tw, th = self.thumbnail_img.size
                # Constrain display size
                disp_w = 460
                disp_h = int(th * (disp_w / float(tw))) if tw else 260
                self.thumb_ctk = ctk.CTkImage(light_image=self.thumbnail_img, dark_image=self.thumbnail_img, size=(disp_w, disp_h))
                self.img_lbl = ctk.CTkLabel(preview_card, text="", image=self.thumb_ctk, corner_radius=8)
                self.img_lbl.pack(padx=6, pady=6)
            except Exception as e:
                print(f"[Visualizer Image Error] {e}")
                ctk.CTkLabel(preview_card, text="[Screenshot Capture Ready]", text_color="#38bdf8").pack(pady=20)
        else:
            ctk.CTkLabel(preview_card, text="[Screen Captured]", text_color="#38bdf8").pack(pady=20)

        # 4. Telemetry Pills Row
        pills_row = ctk.CTkFrame(content_scroll, fg_color="transparent")
        pills_row.pack(fill="x", padx=8, pady=(0, 8))

        proc = self.telemetry.get("process_name", "Explorer").replace(".exe", "").title()
        res = self.telemetry.get("resolution", "1920x1080")
        cat = self.telemetry.get("category", "Application")

        for icon, text_val in [("🖥️", f"Disp: {res}"), ("⚡", f"App: {proc}"), ("🏷️", cat)]:
            p = ctk.CTkFrame(pills_row, fg_color="#0f172a", corner_radius=8, border_width=1, border_color="#1e293b")
            p.pack(side="left", padx=(0, 6))
            ctk.CTkLabel(p, text=f"{icon} {text_val}", font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"), text_color="#38bdf8").pack(padx=6, pady=2)

        # 5. Visual Speech Synthesis Card
        summary_card = ctk.CTkFrame(content_scroll, fg_color="#041226", corner_radius=10, border_width=1, border_color="#0284c7")
        summary_card.pack(fill="x", padx=8, pady=(0, 10))

        ctk.CTkLabel(
            summary_card,
            text="💡 J.A.R.V.I.S. Screen Content Assessment:",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#00f2fe"
        ).pack(anchor="w", padx=10, pady=(6, 2))

        speech_text = self.telemetry.get("summary", "Screen content inspected.")
        self.summary_lbl = ctk.CTkLabel(
            summary_card,
            text=speech_text,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#e2e8f0",
            wraplength=480,
            justify="left",
            anchor="w"
        )
        self.summary_lbl.pack(fill="x", padx=10, pady=(0, 8))

        # 6. Active Window & Extracted Controls Breakdown
        details_card = ctk.CTkFrame(content_scroll, fg_color="#0a101d", corner_radius=10, border_width=1, border_color="#1e293b")
        details_card.pack(fill="x", padx=8, pady=(0, 10))

        ctk.CTkLabel(
            details_card,
            text="🎯 Active Window & UI Elements:",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#38bdf8"
        ).pack(anchor="w", padx=10, pady=(6, 4))

        title_str = self.telemetry.get("active_title", "Desktop")
        rect = self.telemetry.get("rect", (0, 0, 1920, 1080))
        w = rect[2] - rect[0]
        h = rect[3] - rect[1]

        ctk.CTkLabel(
            details_card,
            text=f"• Focused Title: {title_str}\n• Bounds: (x:{rect[0]}, y:{rect[1]}, w:{w}, h:{h})",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color="#cbd5e1",
            justify="left",
            anchor="w"
        ).pack(fill="x", padx=12, pady=(0, 4))

        controls = self.telemetry.get("child_controls", [])
        if controls:
            ctrl_str = ", ".join(f"[{c}]" for c in controls[:8])
            ctk.CTkLabel(
                details_card,
                text=f"• Detected Controls: {ctrl_str}",
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color="#94a3b8",
                wraplength=470,
                justify="left",
                anchor="w"
            ).pack(fill="x", padx=12, pady=(0, 6))

        # 7. Background Applications
        other_apps = self.telemetry.get("visible_windows", [])
        if other_apps:
            apps_card = ctk.CTkFrame(content_scroll, fg_color="#0a101d", corner_radius=10, border_width=1, border_color="#1e293b")
            apps_card.pack(fill="x", padx=8, pady=(0, 10))

            ctk.CTkLabel(
                apps_card,
                text="🗂️ Open Companion Applications:",
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color="#38bdf8"
            ).pack(anchor="w", padx=10, pady=(6, 2))

            ctk.CTkLabel(
                apps_card,
                text=" • " + "   • ".join(other_apps),
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color="#94a3b8",
                wraplength=470,
                justify="left",
                anchor="w"
            ).pack(fill="x", padx=12, pady=(0, 6))

        # 8. Action Buttons Bar
        action_bar = ctk.CTkFrame(self, fg_color="transparent")
        action_bar.pack(fill="x", padx=16, pady=(0, 12))

        speak_btn = ctk.CTkButton(
            action_bar,
            text="🔊 Read Aloud",
            font=ctk.CTkFont(weight="bold", size=11),
            fg_color="#0284c7",
            hover_color="#0369a1",
            width=110,
            command=self._speak_summary
        )
        speak_btn.pack(side="left", padx=(0, 6))

        copy_btn = ctk.CTkButton(
            action_bar,
            text="📋 Copy Details",
            font=ctk.CTkFont(weight="bold", size=11),
            fg_color="#0f172a",
            hover_color="#1e293b",
            width=110,
            command=self._copy_details
        )
        copy_btn.pack(side="left", padx=(0, 6))

        rescan_btn = ctk.CTkButton(
            action_bar,
            text="🔄 Re-Scan",
            font=ctk.CTkFont(weight="bold", size=11),
            fg_color="#0f172a",
            hover_color="#1e293b",
            width=90,
            command=self._rescan_screen
        )
        rescan_btn.pack(side="left", padx=(0, 6))

        dismiss_btn = ctk.CTkButton(
            action_bar,
            text="✕ Dismiss",
            font=ctk.CTkFont(weight="bold", size=11),
            fg_color="#1e293b",
            hover_color="#334155",
            width=80,
            command=self.destroy
        )
        dismiss_btn.pack(side="right")

    def _speak_summary(self):
        if self.hud and self.hud.tts:
            summary = self.telemetry.get("summary", "")
            if summary:
                threading.Thread(target=self.hud.tts.speak, args=(summary,), daemon=True).start()

    def _copy_details(self):
        try:
            report = (
                f"--- J.A.R.V.I.S. Screen Content Report ---\n"
                f"Timestamp: {self.telemetry.get('timestamp')}\n"
                f"Active Application: {self.telemetry.get('process_name')}\n"
                f"Window Title: {self.telemetry.get('active_title')}\n"
                f"Resolution: {self.telemetry.get('resolution')}\n"
                f"Category: {self.telemetry.get('category')}\n"
                f"Summary: {self.telemetry.get('summary')}\n"
                f"Child Controls: {', '.join(self.telemetry.get('child_controls', []))}\n"
                f"Open Apps: {', '.join(self.telemetry.get('visible_windows', []))}\n"
            )
            pyperclip.copy(report)
            if self.hud:
                self.hud.set_state("idle", "Report Copied to Clipboard")
        except Exception as e:
            print(f"[Copy Error] {e}")

    def _rescan_screen(self):
        if self.hud and self.hud.vision:
            threading.Thread(target=self.hud.vision.analyze_screen, daemon=True).start()

    def update_data(self, telemetry: dict, thumbnail_img: Image.Image = None):
        """Refreshes visualizer contents in-place."""
        self.telemetry = telemetry
        self.thumbnail_img = thumbnail_img
        for widget in self.winfo_children():
            widget.destroy()
        self._build_ui()


class AssistantHUD:
    def __init__(self, tts=None, controller=None, vision=None):
        self.root = None
        self.tts = tts
        self.controller = controller
        self.vision = vision
        self.dispatcher = None
        self.status_var = None
        self.subtitle_var = None
        self.cpu_var = None
        self.ram_var = None
        self.pwr_var = None
        self.visualizer_canvas = None
        self.current_state = "idle"  # idle, listening, transcribing, speaking
        self.anim_phase = 0.0
        self.rotation_angle = 0.0
        self.is_running = True
        self.is_shutting_down = False
        self.is_muted = False
        self.settings_dialog = None
        self.screen_visualizer = None
        self.commands_dialog = None

    def start(self):
        """Launches the Hyper-Modern J.A.R.V.I.S. Holographic Island HUD."""
        self.root = ctk.CTk()
        self.root.title("J.A.R.V.I.S. Core Interface")
        
        # Frameless, Always on Top, Frosted Glass Aesthetic
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.96)

        # Position at bottom-right above taskbar
        try:
            monitor = get_monitors()[0]
            sw, sh = monitor.width, monitor.height
        except Exception:
            sw, sh = 1920, 1080

        w, h = 475, 320
        x = sw - w - 24
        y = sh - h - 60
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        # Dragging capability
        self.root.bind("<ButtonPress-1>", self._start_move)
        self.root.bind("<B1-Motion>", self._do_move)
        self.root.bind("<Escape>", lambda e: self._manual_stop())

        # Outer Glow Container
        outer_container = ctk.CTkFrame(
            self.root,
            corner_radius=22,
            fg_color="#030712",
            border_width=2,
            border_color="#00f2fe"
        )
        outer_container.pack(fill="both", expand=True, padx=3, pady=3)

        # 1. Header Bar: Branding + Status Badge + Window Actions
        header = ctk.CTkFrame(outer_container, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(10, 4))

        brand_badge = ctk.CTkFrame(header, fg_color="#0a192f", corner_radius=8, border_width=1, border_color="#00b4d8")
        brand_badge.pack(side="left")

        brand_lbl = ctk.CTkLabel(
            brand_badge,
            text=" ◈ J.A.R.V.I.S. v5.0 ",
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
            text_color="#00f2fe"
        )
        brand_lbl.pack(padx=6, pady=2)

        status_pill = ctk.CTkFrame(header, fg_color="#0b132b", corner_radius=8)
        status_pill.pack(side="left", padx=8)

        self.protocol_lbl = ctk.CTkLabel(
            status_pill,
            text="● NEURAL CORE ACTIVE",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color="#00ffcc"
        )
        self.protocol_lbl.pack(padx=6, pady=2)

        # Window Action Buttons: Minimize & Power Down
        header_actions = ctk.CTkFrame(header, fg_color="transparent")
        header_actions.pack(side="right")

        min_btn = ctk.CTkButton(
            header_actions,
            text="—",
            width=22,
            height=22,
            corner_radius=6,
            fg_color="transparent",
            hover_color="#1e293b",
            text_color="#94a3b8",
            command=self._minimize_hud
        )
        min_btn.pack(side="left", padx=(0, 2))

        power_btn = ctk.CTkButton(
            header_actions,
            text="⏻",
            width=22,
            height=22,
            corner_radius=6,
            fg_color="transparent",
            hover_color="#ef4444",
            text_color="#ef4444",
            command=self._manual_power_down
        )
        power_btn.pack(side="left")

        # 2. Telemetry Hardware Pills Row (CPU / RAM / Battery)
        telemetry_row = ctk.CTkFrame(outer_container, fg_color="transparent")
        telemetry_row.pack(fill="x", padx=16, pady=(2, 4))

        self.cpu_var = ctk.StringVar(value="CPU 0%")
        self.ram_var = ctk.StringVar(value="RAM 0%")
        self.pwr_var = ctk.StringVar(value="PWR 100%")

        for label_var, icon in [(self.cpu_var, "⚡"), (self.ram_var, "🧠"), (self.pwr_var, "🔋")]:
            pill = ctk.CTkFrame(telemetry_row, fg_color="#0f172a", corner_radius=10, border_width=1, border_color="#1e293b")
            pill.pack(side="left", padx=(0, 6))
            lbl = ctk.CTkLabel(
                pill,
                textvariable=label_var,
                font=ctk.CTkFont(family="Consolas", size=9),
                text_color="#38bdf8"
            )
            lbl.pack(padx=8, pady=1)

        # 2.1 Audio Peripherals Hardware Bar (Microphone & Speaker)
        audio_bar = ctk.CTkFrame(outer_container, fg_color="#090f1d", corner_radius=8, border_width=1, border_color="#1e293b")
        audio_bar.pack(fill="x", padx=16, pady=(1, 3))

        self.audio_status_var = ctk.StringVar(value="🎙️ Mic: Detecting...  |  🔊 Spk: Detecting...")
        audio_lbl = ctk.CTkLabel(
            audio_bar,
            textvariable=self.audio_status_var,
            font=ctk.CTkFont(family="Segoe UI", size=9),
            text_color="#94a3b8"
        )
        audio_lbl.pack(side="left", padx=8, pady=2)

        audio_config_btn = ctk.CTkButton(
            audio_bar,
            text="Change",
            width=48,
            height=18,
            font=ctk.CTkFont(size=9),
            fg_color="#1e293b",
            hover_color="#0284c7",
            command=self._open_settings
        )
        audio_config_btn.pack(side="right", padx=6, pady=2)

        # 3. Interactive Core Canvas: Arc Reactor + Live Harmonic Soundwave
        self.visualizer_canvas = ctk.CTkCanvas(
            outer_container,
            height=65,
            bg="#030712",
            highlightthickness=0
        )
        self.visualizer_canvas.pack(fill="x", padx=16, pady=(2, 2))

        # 4. State & Live Transcript Box (Glassmorphic Card)
        self.transcript_frame = ctk.CTkFrame(
            outer_container,
            fg_color="#090e17",
            corner_radius=14,
            border_width=1,
            border_color="#1e3a5f"
        )
        self.transcript_frame.pack(fill="both", expand=True, padx=14, pady=(2, 6))

        self.status_var = ctk.StringVar(value="Awaiting voice command...")
        self.status_lbl = ctk.CTkLabel(
            self.transcript_frame,
            textvariable=self.status_var,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#00f2fe",
            anchor="w"
        )
        self.status_lbl.pack(fill="x", padx=12, pady=(4, 0))

        self.subtitle_var = ctk.StringVar(value="J.A.R.V.I.S.: At your service, sir.")
        self.sub_label = ctk.CTkLabel(
            self.transcript_frame,
            textvariable=self.subtitle_var,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#e2e8f0",
            wraplength=420,
            justify="left",
            anchor="w"
        )
        self.sub_label.pack(fill="both", expand=True, padx=12, pady=(2, 4))

        # 5. Bottom Action Pills (Interactive Shortcuts)
        action_bar = ctk.CTkFrame(outer_container, fg_color="transparent")
        action_bar.pack(fill="x", padx=14, pady=(0, 8))

        btn_style = {
            "height": 22,
            "corner_radius": 8,
            "font": ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            "fg_color": "#0f172a",
            "hover_color": "#1e293b",
            "text_color": "#94a3b8"
        }

        # Settings Button
        settings_btn = ctk.CTkButton(
            action_bar,
            text="⚙️ Settings",
            width=65,
            command=self._open_settings,
            **btn_style
        )
        settings_btn.pack(side="left", padx=(0, 4))

        # Screen Vision / Visualizer Button
        vision_btn = ctk.CTkButton(
            action_bar,
            text="👁️ Vision",
            width=60,
            command=self._trigger_vision,
            **btn_style
        )
        vision_btn.pack(side="left", padx=(0, 4))

        # Diagnostics Button
        diag_btn = ctk.CTkButton(
            action_bar,
            text="⚡ Status",
            width=58,
            command=self._trigger_diagnostics,
            **btn_style
        )
        diag_btn.pack(side="left", padx=(0, 4))

        # Timer Button
        timer_btn = ctk.CTkButton(
            action_bar,
            text="⏱️ Timers",
            width=58,
            command=self._trigger_timers,
            **btn_style
        )
        timer_btn.pack(side="left", padx=(0, 4))

        # Commands Catalog Button
        cmds_btn = ctk.CTkButton(
            action_bar,
            text="📜 Commands",
            width=68,
            command=self._open_commands,
            **btn_style
        )
        cmds_btn.pack(side="left", padx=(0, 4))

        # Mute / Active Button (Rightmost)
        self.mute_btn = ctk.CTkButton(
            action_bar,
            text="🎙️ Active",
            width=65,
            fg_color="#0369a1",
            hover_color="#0284c7",
            text_color="#ffffff",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            height=22,
            corner_radius=8,
            command=self._toggle_mute
        )
        self.mute_btn.pack(side="right")

        # Dedicated Stop Button (Red Accent)
        self.stop_btn = ctk.CTkButton(
            action_bar,
            text="🛑 Stop",
            width=65,
            fg_color="#dc2626",
            hover_color="#ef4444",
            text_color="#ffffff",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            height=22,
            corner_radius=8,
            command=self._manual_stop
        )
        self.stop_btn.pack(side="right", padx=(0, 6))

        self.is_running = True
        self._update_telemetry_loop()
        self._animate_visualizer()
        self.root.mainloop()

    def set_state(self, state: str, message: str = None, subtitle: str = None):
        """Thread-safe state update."""
        if not self.root or not self.is_running:
            return

        def _update():
            self.current_state = state
            if message and self.status_var:
                self.status_var.set(message)
            if subtitle and self.subtitle_var:
                self.subtitle_var.set(subtitle)

        try:
            self.root.after(0, _update)
        except Exception:
            pass

    def show_screen_visualizer(self, telemetry: dict, thumbnail_img: Image.Image = None):
        """Displays the interactive screen visualizer inspection window."""
        if not self.root or not self.is_running:
            return

        def _open():
            try:
                if self.screen_visualizer is not None and self.screen_visualizer.winfo_exists():
                    self.screen_visualizer.update_data(telemetry, thumbnail_img)
                    self.screen_visualizer.deiconify()
                    self.screen_visualizer.lift()
                    self.screen_visualizer.attributes("-topmost", True)
                else:
                    self.screen_visualizer = ScreenVisualizerDialog(self.root, self, telemetry, thumbnail_img)
            except Exception as e:
                print(f"[HUD Visualizer Error] {e}")

        try:
            self.root.after(0, _open)
        except Exception:
            pass

    def _animate_visualizer(self):
        """Draws the dynamic holographic Arc Reactor and smooth animated audio spectrum."""
        if not self.visualizer_canvas:
            return

        self.anim_phase += 0.14
        self.rotation_angle += 0.06
        self.visualizer_canvas.delete("all")

        w = self.visualizer_canvas.winfo_width() or 430
        h = 65
        cx, cy = 35, 32

        palettes = {
            "idle": {"primary": "#00f2fe", "secondary": "#4facfe", "wave": "#00b4d8"},
            "listening": {"primary": "#ff007f", "secondary": "#9b5de5", "wave": "#d500f9"},
            "transcribing": {"primary": "#ffd600", "secondary": "#ff9100", "wave": "#ffab00"},
            "speaking": {"primary": "#00ffcc", "secondary": "#00e5ff", "wave": "#38bdf8"}
        }
        palette = palettes.get(self.current_state, palettes["idle"])

        pulse = math.sin(self.anim_phase) * 3

        # 1. Left: Arc Reactor Core
        r_outer = 20 + (pulse * 0.4)
        self.visualizer_canvas.create_oval(cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer, outline=palette["secondary"], width=1)

        # Rotating Arc segments
        for i in range(6):
            ang = self.rotation_angle + (i * (math.pi / 3))
            x1 = cx + math.cos(ang) * 14
            y1 = cy + math.sin(ang) * 14
            x2 = cx + math.cos(ang) * 20
            y2 = cy + math.sin(ang) * 20
            self.visualizer_canvas.create_line(x1, y1, x2, y2, fill=palette["primary"], width=2)

        # Center core glow
        r_core = 7 + (pulse * 0.3)
        self.visualizer_canvas.create_oval(cx - r_core, cy - r_core, cx + r_core, cy + r_core, fill=palette["primary"], outline="#ffffff", width=1)

        # 2. Right: Smooth Live Harmonic Soundwave Visualizer
        wave_start_x = 80
        wave_width = w - wave_start_x - 10
        num_bars = 30
        bar_spacing = wave_width / num_bars

        for i in range(num_bars):
            freq = 0.45
            if self.current_state == "speaking":
                amp = math.sin(self.anim_phase * 2 + i * freq) * 16 + math.cos(self.anim_phase + i * 0.2) * 8
            elif self.current_state == "listening":
                amp = math.sin(self.anim_phase * 3 + i * 0.6) * 12 + random.uniform(-3, 3)
            elif self.current_state == "transcribing":
                amp = math.sin(self.anim_phase * 4 + i * 0.8) * 8
            else:
                amp = math.sin(self.anim_phase + i * 0.3) * 3

            bar_h = max(3, abs(amp))
            bx = wave_start_x + (i * bar_spacing)
            by1 = cy - bar_h
            by2 = cy + bar_h

            color = palette["wave"] if i % 2 == 0 else palette["primary"]
            self.visualizer_canvas.create_line(bx, by1, bx, by2, fill=color, width=3, capstyle="round")

        try:
            if self.is_running and self.root and self.visualizer_canvas.winfo_exists():
                self.root.after(35, self._animate_visualizer)
        except Exception:
            pass

    def _get_active_audio_summary(self):
        """Returns concise active microphone and speaker names for the HUD bar."""
        import sounddevice as sd
        from config import load_user_settings
        settings = load_user_settings()
        mic_str = "Mic: Default"
        spk_str = "Spk: Default"
        try:
            devs = sd.query_devices()
            def_in, def_out = sd.default.device

            saved_in = settings.get("audio_device_index")
            if saved_in is not None and saved_in < len(devs):
                raw_mic = devs[saved_in]['name']
            elif def_in is not None and def_in < len(devs):
                raw_mic = devs[def_in]['name']
            else:
                raw_mic = "Default Mic"

            saved_out_name = settings.get("audio_output_device_name")
            saved_out_idx = settings.get("audio_output_device_index")
            if saved_out_name:
                raw_spk = saved_out_name
            elif saved_out_idx is not None and saved_out_idx < len(devs):
                raw_spk = devs[saved_out_idx]['name']
            elif def_out is not None and def_out < len(devs):
                raw_spk = devs[def_out]['name']
            else:
                raw_spk = "Default Spk"

            mic_clean = raw_mic.split('(')[0].strip() if '(' in raw_mic and len(raw_mic) > 18 else raw_mic
            spk_clean = raw_spk.split('(')[0].strip() if '(' in raw_spk and len(raw_spk) > 18 else raw_spk
            if len(mic_clean) > 15:
                mic_clean = mic_clean[:13] + ".."
            if len(spk_clean) > 15:
                spk_clean = spk_clean[:13] + ".."
            mic_str = f"Mic: {mic_clean}"
            spk_str = f"Spk: {spk_clean}"
        except Exception:
            pass
        return mic_str, spk_str

    def _update_telemetry_loop(self):
        """Updates live CPU, RAM, Battery pills, and audio peripheral status."""
        if not self.is_running:
            return

        try:
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            self.cpu_var.set(f"CPU {round(cpu)}%")
            self.ram_var.set(f"RAM {round(ram)}%")
            
            bat = psutil.sensors_battery()
            if bat:
                self.pwr_var.set(f"PWR {round(bat.percent)}%")
                
            if hasattr(self, 'audio_status_var') and self.audio_status_var:
                mic_desc, spk_desc = self._get_active_audio_summary()
                self.audio_status_var.set(f"🎙️ {mic_desc}   🔊 {spk_desc}")
        except Exception:
            pass

        if self.is_running:
            self.root.after(2000, self._update_telemetry_loop)

    def _toggle_mute(self):
        self.is_muted = not self.is_muted
        if self.is_muted:
            self.mute_btn.configure(text="🔇 Muted", fg_color="#dc2626", hover_color="#b91c1c")
            self.set_state("idle", "Microphone Muted", "Jarvis is standing by (Muted)")
        else:
            self.mute_btn.configure(text="🎙️ Active", fg_color="#0369a1", hover_color="#0284c7")
            self.set_state("idle", "Listening for 'Jarvis'...")

    def _manual_stop(self):
        """
        Manually interrupts any ongoing speech, cancels dictation mode,
        resets the wake-word session, and sets assistant to standby.
        """
        print("[HUD Manual Stop] Stopping speech and active session...")
        if self.tts:
            self.tts.stop()
        if self.controller:
            self.controller.dictation_mode = False
        if self.dispatcher:
            self.dispatcher.active_until = 0.0
        self.set_state("idle", "Halted // Standing by", "Assistant stopped. Say 'Jarvis' or press Ctrl+Space to activate.")

    def _manual_power_down(self):
        """Cleanly shuts down all assistant processes and closes the interface."""
        print("[HUD Power Down] Exiting assistant on user request...")
        self.is_running = False
        self.is_shutting_down = True
        if self.tts:
            self.tts.stop()
        self.set_state("idle", "Powering Down...", "Terminating J.A.R.V.I.S. systems, sir.")
        try:
            if self.tts:
                self.tts.speak("Powering down systems, sir. Goodbye.")
        except Exception:
            pass
        self.root.after(700, self._exit_app)

    def _exit_app(self):
        import sys
        self.is_running = False
        self.is_shutting_down = True
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass
        sys.exit(0)

    def _open_settings(self):
        if self.settings_dialog is None or not self.settings_dialog.winfo_exists():
            self.settings_dialog = SettingsDialog(self.root, self)
        else:
            self.settings_dialog.focus()

    def _open_commands(self):
        if self.commands_dialog is None or not self.commands_dialog.winfo_exists():
            self.commands_dialog = CommandsCatalogDialog(self.root, self)
        else:
            self.commands_dialog.focus()

    def _trigger_vision(self):
        if self.vision:
            threading.Thread(target=self.vision.analyze_screen, daemon=True).start()

    def _trigger_timers(self):
        if self.controller:
            self.controller.list_active_timers()

    def _trigger_diagnostics(self):
        if self.controller:
            self.controller.run_diagnostics()

    def _minimize_hud(self):
        try:
            self.root.withdraw()
        except Exception:
            pass

    def show(self):
        """Restores and brings HUD to foreground."""
        if not self.root or not self.is_running:
            return
        def _do_show():
            try:
                self.root.deiconify()
                self.root.lift()
                self.root.attributes("-topmost", True)
            except Exception:
                pass
        try:
            self.root.after(0, _do_show)
        except Exception:
            pass

    def _start_move(self, event):
        self._x = event.x
        self._y = event.y

    def _do_move(self, event):
        deltax = event.x - self._x
        deltay = event.y - self._y
        x = self.root.winfo_x() + deltax
        y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{x}+{y}")
