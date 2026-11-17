import os
import sys
import hashlib
import tempfile
import threading
import asyncio
import time
import pyttsx3
import pygame
from config import (
    TTS_ENGINE, EDGE_VOICE, KOKORO_VOICE, SAPI_VOICE, KOKORO_MODEL_PATH, KOKORO_VOICES_PATH,
    PIPER_MODEL_DIR, VOICE_RATE, VOICE_VOLUME, STRICT_OFFLINE_MODE,
    AUDIO_OUTPUT_DEVICE_INDEX, AUDIO_OUTPUT_DEVICE_NAME,
    AVAILABLE_EDGE_VOICES, AVAILABLE_KOKORO_VOICES, AVAILABLE_SAPI_VOICES
)

class TextToSpeech:
    def __init__(self):
        self.is_speaking = False
        self._speech_lock = threading.Lock()
        self.engine_type = TTS_ENGINE
        self.edge_voice = EDGE_VOICE
        self.kokoro_voice = KOKORO_VOICE
        self.sapi_voice = SAPI_VOICE
        self.rate = VOICE_RATE
        self.volume = VOICE_VOLUME
        self.strict_offline_mode = STRICT_OFFLINE_MODE
        self.output_device_index = AUDIO_OUTPUT_DEVICE_INDEX
        self.output_device_name = AUDIO_OUTPUT_DEVICE_NAME
        self._kokoro_instance = None
        self._piper_voice = None
        self.cache_dir = os.path.join(os.path.expanduser("~"), ".buddy_tts_cache")
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
        except Exception:
            pass
        
        # Initialize Pygame Mixer with 24kHz for native Edge-TTS MP3 compatibility
        self.mixer_ready = False
        self._init_mixer(self.output_device_name)
        self.offline_ready = True
        self.available = True

    def _init_mixer(self, devicename: str = None):
        try:
            if pygame.mixer.get_init():
                pygame.mixer.quit()
            pygame.mixer.pre_init(24000, -16, 2, 2048)
            if devicename:
                pygame.mixer.init(devicename=devicename)
            else:
                pygame.mixer.init()
            self.mixer_ready = True
        except Exception:
            try:
                pygame.mixer.init()
                self.mixer_ready = True
            except Exception as e:
                print(f"[TTS Audio Warning] Pygame mixer init failed: {e}")
                self.mixer_ready = False

    def set_output_device(self, devicename: str = None, device_index: int = None):
        """Sets the audio output speaker/headphone device."""
        self.output_device_name = devicename
        self.output_device_index = device_index
        self._init_mixer(devicename)
        from config import load_user_settings, save_user_settings
        try:
            settings = load_user_settings()
            settings["audio_output_device_name"] = devicename
            settings["audio_output_device_index"] = device_index
            save_user_settings(settings)
        except Exception as e:
            print(f"[TTS Output Device Save Error] {e}")

    def stop(self):
        """Stops any ongoing audio playback or speech synthesis."""
        self.is_speaking = False
        try:
            if self.mixer_ready:
                pygame.mixer.stop()
        except Exception:
            pass
        try:
            if hasattr(self, '_sapi_speaker') and self._sapi_speaker:
                # Flag 2 = SVSFPurgeBeforeSpeak purges all current and pending speech
                self._sapi_speaker.Speak("", 2)
        except Exception:
            pass

    def set_engine(self, engine: str, voice: str = None, strict_offline: bool = None):
        self.engine_type = engine
        if voice:
            if engine == "kokoro":
                self.kokoro_voice = voice
                if any(w in voice.lower() for w in ["emma", "heart", "nicole", "female"]):
                    self.edge_voice = "en-GB-SoniaNeural"
                    self.sapi_voice = "TTS_MS_EN-US_ZIRA_11.0"
                else:
                    self.edge_voice = "en-GB-RyanNeural"
                    self.sapi_voice = "TTS_MS_EN-US_DAVID_11.0"
            elif engine == "pyttsx3":
                self.sapi_voice = voice
                if any(w in voice.lower() for w in ["zira", "heera", "female"]):
                    self.edge_voice = "en-IN-NeerjaNeural" if "heera" in voice.lower() else "en-GB-SoniaNeural"
                    self.kokoro_voice = "bf_emma"
                else:
                    self.edge_voice = "en-IN-PrabhatNeural" if "ravi" in voice.lower() else "en-GB-RyanNeural"
                    self.kokoro_voice = "bm_george"
            else:
                self.edge_voice = voice
                if any(w in voice.lower() for w in ["sonia", "jenny", "ava", "neerja", "female"]):
                    self.sapi_voice = "MSTTS_V110_enIN_HeeraM" if "neerja" in voice.lower() else "TTS_MS_EN-US_ZIRA_11.0"
                    self.kokoro_voice = "bf_emma"
                else:
                    if "prabhat" in voice.lower():
                        self.sapi_voice = "MSTTS_V110_enIN_RaviM"
                    elif "christopher" in voice.lower():
                        self.sapi_voice = "MSTTS_V110_enUS_MarkM"
                    else:
                        self.sapi_voice = "TTS_MS_EN-US_DAVID_11.0"
                    self.kokoro_voice = "bm_george"
        if strict_offline is not None:
            self.strict_offline_mode = strict_offline

        from config import load_user_settings, save_user_settings
        try:
            settings = load_user_settings()
            settings["tts_engine"] = self.engine_type
            settings["edge_voice"] = self.edge_voice
            settings["kokoro_voice"] = self.kokoro_voice
            settings["sapi_voice"] = self.sapi_voice
            if strict_offline is not None:
                settings["strict_offline_mode"] = self.strict_offline_mode
            save_user_settings(settings)
        except Exception as e:
            print(f"[TTS Config Save Error] {e}")

    def get_available_voices(self) -> dict:
        """Returns the dictionary of available voices for the current engine."""
        from config import AVAILABLE_EDGE_VOICES, AVAILABLE_KOKORO_VOICES, AVAILABLE_SAPI_VOICES
        if self.engine_type == "kokoro":
            return dict(AVAILABLE_KOKORO_VOICES)
        elif self.engine_type == "pyttsx3":
            return dict(AVAILABLE_SAPI_VOICES)
        return dict(AVAILABLE_EDGE_VOICES)

    def is_female_voice(self) -> bool:
        """Determines if the currently configured voice identity is female."""
        female_keys = [
            "sonia", "emma", "zira", "heera", "jenny", "ava", "neerja", "nicole",
            "heart", "female", "woman", "girl", "lady", "bf_emma", "af_heart", "af_nicole"
        ]
        if self.engine_type == "kokoro":
            target = (self.kokoro_voice or "").lower()
        elif self.engine_type == "pyttsx3":
            target = (self.sapi_voice or "").lower()
        else:
            target = (self.edge_voice or "").lower()
        return any(k in target for k in female_keys)

    def _get_best_sapi_token_id(self, is_female: bool, prefer_indian: bool = False, prefer_deep: bool = False) -> str:
        """Discovers and returns the best matching Windows SAPI/OneCore voice token."""
        try:
            import winreg
            tokens = []
            paths = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Speech\Voices\Tokens"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens")
            ]
            for root, path in paths:
                try:
                    k = winreg.OpenKey(root, path)
                    i = 0
                    while True:
                        try:
                            sub = winreg.EnumKey(k, i)
                            sub_path = f"{path}\\{sub}"
                            sk = winreg.OpenKey(root, sub_path)
                            try:
                                desc, _ = winreg.QueryValueEx(sk, "")
                            except Exception:
                                desc = sub
                            gender = "unknown"
                            try:
                                ak = winreg.OpenKey(root, f"{sub_path}\\Attributes")
                                g_val, _ = winreg.QueryValueEx(ak, "Gender")
                                gender = str(g_val).lower().strip()
                            except Exception:
                                pass
                            tokens.append({
                                "id": f"HKEY_LOCAL_MACHINE\\{sub_path}",
                                "sub": sub.lower(),
                                "desc": desc,
                                "gender": gender
                            })
                            i += 1
                        except OSError:
                            break
                except Exception:
                    pass

            if not tokens:
                return None

            # If user explicitly configured a specific SAPI voice
            if hasattr(self, "sapi_voice") and self.sapi_voice:
                req = self.sapi_voice.lower()
                for t in tokens:
                    if req in t["id"].lower() or req in t["sub"]:
                        if self.engine_type == "pyttsx3":
                            return t["id"]
                        t_is_female = (t["gender"] == "female" or any(k in t["sub"] for k in ["zira", "heera"]))
                        if (is_female and t_is_female) or (not is_female and not t_is_female):
                            return t["id"]

            if is_female:
                if prefer_indian:
                    for t in tokens:
                        if "heera" in t["sub"] or (t["gender"] == "female" and "in" in t["sub"]):
                            return t["id"]
                for t in tokens:
                    if "zira" in t["sub"]:
                        return t["id"]
                for t in tokens:
                    if t["gender"] == "female":
                        return t["id"]
            else:
                if prefer_deep:
                    for t in tokens:
                        if "mark" in t["sub"] or "deep" in t["sub"]:
                            return t["id"]
                if prefer_indian:
                    for t in tokens:
                        if "ravi" in t["sub"] or (t["gender"] == "male" and "in" in t["sub"]):
                            return t["id"]
                for t in tokens:
                    if "david" in t["sub"]:
                        return t["id"]
                for t in tokens:
                    if t["gender"] == "male":
                        return t["id"]

            return tokens[0]["id"]
        except Exception as e:
            print(f"[SAPI Token Lookup Warning] {e}")
            return None

    def change_voice(self, query: str) -> bool:
        """
        Dynamically changes the voice personality across Edge-TTS, Kokoro, and Windows SAPI.
        Synchronizes all engines and fallbacks so the selected identity/gender is guaranteed.
        Supports specific names (Sonia, Christopher, Guy, Jarvis, Jenny, Prabhat, Neerja, George, Emma, Zira, etc.)
        as well as gender descriptors ('female', 'woman', 'male', 'man', 'deep').
        """
        clean = query.lower().strip()
        from config import (
            AVAILABLE_EDGE_VOICES, AVAILABLE_KOKORO_VOICES, AVAILABLE_SAPI_VOICES,
            load_user_settings, save_user_settings
        )

        is_female_req = any(w in clean for w in [
            "female", "woman", "girl", "lady", "sonia", "jenny", "ava",
            "neerja", "emma", "heart", "nicole", "zira", "heera"
        ])
        is_male_req = any(w in clean for w in [
            "male", "man", "boy", "gentleman", "deep", "guy", "jarvis",
            "ryan", "christopher", "prabhat", "george", "adam", "david", "ravi"
        ])

        target_display_name = None

        if is_female_req:
            # Universal synchronization across all 3 engines
            self.edge_voice = "en-GB-SoniaNeural"
            self.kokoro_voice = "bf_emma"
            self.sapi_voice = "TTS_MS_EN-US_ZIRA_11.0"
            target_display_name = "Sonia"

            if "jenny" in clean:
                self.edge_voice = "en-US-JennyNeural"
                target_display_name = "Jenny"
            elif "ava" in clean:
                self.edge_voice = "en-US-AvaNeural"
                target_display_name = "Ava"
            elif "neerja" in clean:
                self.edge_voice = "en-IN-NeerjaNeural"
                self.sapi_voice = "MSTTS_V110_enIN_HeeraM"
                target_display_name = "Neerja"
            elif "zira" in clean:
                self.sapi_voice = "TTS_MS_EN-US_ZIRA_11.0"
                self.edge_voice = "en-US-JennyNeural"
                target_display_name = "Zira"
            elif "heera" in clean:
                self.sapi_voice = "MSTTS_V110_enIN_HeeraM"
                self.edge_voice = "en-IN-NeerjaNeural"
                target_display_name = "Heera"

        elif is_male_req:
            # Universal synchronization across all 3 engines
            self.edge_voice = "en-GB-RyanNeural"
            self.kokoro_voice = "bm_george"
            self.sapi_voice = "TTS_MS_EN-US_DAVID_11.0"
            target_display_name = "Jarvis"

            if "guy" in clean:
                self.edge_voice = "en-US-GuyNeural"
                self.kokoro_voice = "am_adam"
                target_display_name = "Guy"
            elif "christopher" in clean:
                self.edge_voice = "en-US-ChristopherNeural"
                target_display_name = "Christopher"
            elif "prabhat" in clean or "ravi" in clean:
                self.edge_voice = "en-IN-PrabhatNeural"
                self.sapi_voice = "MSTTS_V110_enIN_RaviM"
                target_display_name = "Prabhat"
            elif "david" in clean:
                self.sapi_voice = "TTS_MS_EN-US_DAVID_11.0"
                self.edge_voice = "en-US-GuyNeural"
                target_display_name = "David"

        else:
            # Fuzzy match against current engine voice list
            voice_map = self.get_available_voices()
            for label, vid in voice_map.items():
                if clean in label.lower() or clean in vid.lower():
                    if self.engine_type == "kokoro":
                        self.kokoro_voice = vid
                    elif self.engine_type == "pyttsx3":
                        self.sapi_voice = vid
                    else:
                        self.edge_voice = vid
                    target_display_name = label.split(" (")[0]
                    break

            if not target_display_name:
                import difflib
                candidates = list(voice_map.keys())
                matches = difflib.get_close_matches(clean, [c.lower() for c in candidates], n=1, cutoff=0.35)
                if matches:
                    matched_label = next(c for c in candidates if c.lower() == matches[0])
                    vid = voice_map[matched_label]
                    if self.engine_type == "kokoro":
                        self.kokoro_voice = vid
                    elif self.engine_type == "pyttsx3":
                        self.sapi_voice = vid
                    else:
                        self.edge_voice = vid
                    target_display_name = matched_label.split(" (")[0]

        if target_display_name:
            # Synchronize all engine identities
            is_fem = self.is_female_voice()
            if is_fem:
                if not any(k in getattr(self, 'sapi_voice', '').lower() for k in ["zira", "heera"]):
                    self.sapi_voice = "TTS_MS_EN-US_ZIRA_11.0"
                if not any(k in self.edge_voice.lower() for k in ["sonia", "jenny", "ava", "neerja"]):
                    self.edge_voice = "en-GB-SoniaNeural"
                if not any(k in self.kokoro_voice.lower() for k in ["emma", "heart", "nicole"]):
                    self.kokoro_voice = "bf_emma"
            else:
                if not any(k in getattr(self, 'sapi_voice', '').lower() for k in ["david", "ravi"]):
                    self.sapi_voice = "TTS_MS_EN-US_DAVID_11.0"
                if not any(k in self.edge_voice.lower() for k in ["ryan", "guy", "christopher", "prabhat"]):
                    self.edge_voice = "en-GB-RyanNeural"
                if not any(k in self.kokoro_voice.lower() for k in ["george", "adam"]):
                    self.kokoro_voice = "bm_george"

            try:
                settings = load_user_settings()
                settings["edge_voice"] = self.edge_voice
                settings["kokoro_voice"] = self.kokoro_voice
                settings["sapi_voice"] = self.sapi_voice
                save_user_settings(settings)
            except Exception as e:
                print(f"[TTS Voice Save Error] {e}")

            msg = f"Voice output changed to {target_display_name}, sir. How does this sound?"
            print(f"[*] Voice output changed to: {target_display_name} (Edge: {self.edge_voice}, SAPI: {self.sapi_voice})")
            self.speak(msg)
            return True
        else:
            voice_map = self.get_available_voices()
            available_names = [k.split(" (")[0] for k in voice_map.keys()]
            err_msg = f"I could not find a voice matching '{query}', sir. Available options include: {', '.join(available_names)}."
            self.speak(err_msg)
            return False

    def speak(self, text: str, async_mode: bool = False):
        print(f" Assistant: {text}")
        if not text or not text.strip():
            return

        if async_mode:
            thread = threading.Thread(target=self._run_speech, args=(text.strip(),))
            thread.daemon = True
            thread.start()
        else:
            self._run_speech(text.strip())

    def _run_speech(self, text: str):
        with self._speech_lock:
            self.is_speaking = True
            try:
                # 1. Try Kokoro ONNX if selected
                if self.engine_type == "kokoro":
                    if self._speak_kokoro(text):
                        return
                    print("[TTS Notice] Kokoro ONNX unavailable; falling back to offline voice.")

                # 2. Try Piper TTS if selected
                elif self.engine_type == "piper":
                    if self._speak_piper(text):
                        return
                    print("[TTS Notice] Piper TTS unavailable; falling back to offline voice.")

                # 3. Try Neural Edge-TTS if online and selected
                elif self.engine_type == "edge-tts" and not self.strict_offline_mode and self.mixer_ready:
                    success = self._speak_edge_tts(text)
                    if success:
                        return

                # 4. Fallback to offline native Windows SAPI5 / pyttsx3 voice (thread-safe)
                self._speak_offline(text)
            except Exception as e:
                print(f"[TTS Error] {e}")
                self._speak_offline(text)
            finally:
                time.sleep(0.25)  # Acoustic cooldown buffer so speaker echo isn't picked up by mic
                self.is_speaking = False

    def _speak_kokoro(self, text: str) -> bool:
        """Synthesizes speech using local Kokoro-82M ONNX."""
        try:
            if not os.path.exists(KOKORO_MODEL_PATH):
                return False

            try:
                import kokoro_onnx
                if self._kokoro_instance is None:
                    self._kokoro_instance = kokoro_onnx.Kokoro(KOKORO_MODEL_PATH, KOKORO_VOICES_PATH)
                
                samples, sample_rate = self._kokoro_instance.create(
                    text, voice=self.kokoro_voice, speed=1.0, lang="en-us"
                )
                import sounddevice as sd
                sd.play(samples, sample_rate, device=self.output_device_index)
                while sd.get_stream() and sd.get_stream().active and self.is_speaking:
                    time.sleep(0.04)
                if not self.is_speaking:
                    sd.stop()
                return True
            except ImportError:
                return False
        except Exception as e:
            print(f"[Kokoro TTS Error] {e}")
            return False

    def _speak_piper(self, text: str) -> bool:
        """Synthesizes speech using local Piper TTS model."""
        try:
            if not os.path.exists(PIPER_MODEL_DIR):
                return False
            # Check for piper onnx models in PIPER_MODEL_DIR
            model_files = [f for f in os.listdir(PIPER_MODEL_DIR) if f.endswith(".onnx")]
            if not model_files:
                return False

            model_path = os.path.join(PIPER_MODEL_DIR, model_files[0])
            config_path = model_path + ".json"
            if not os.path.exists(config_path):
                return False

            try:
                from piper import PiperVoice
                import wave
                import io

                if self._piper_voice is None:
                    self._piper_voice = PiperVoice.load(model_path, config_path=config_path)

                fd, temp_wav = tempfile.mkstemp(suffix=".wav")
                os.close(fd)
                with wave.open(temp_wav, "wb") as wav_file:
                    self._piper_voice.synthesize(text, wav_file)

                if os.path.exists(temp_wav) and os.path.getsize(temp_wav) > 0:
                    sound = pygame.mixer.Sound(temp_wav)
                    sound.set_volume(self.volume)
                    channel = sound.play()
                    while channel and channel.get_busy() and self.is_speaking:
                        time.sleep(0.04)
                    if not self.is_speaking and channel:
                        channel.stop()
                    try:
                        os.remove(temp_wav)
                    except Exception:
                        pass
                    return True
            except ImportError:
                return False
        except Exception as e:
            print(f"[Piper TTS Error] {e}")
            return False

    def _speak_edge_tts(self, text: str) -> bool:
        try:
            import edge_tts
            
            # Check local response cache for instant (<10ms) zero-latency playback
            text_hash = hashlib.md5(f"{self.edge_voice}_{text}".encode("utf-8")).hexdigest()
            cached_audio = os.path.join(self.cache_dir, f"{text_hash}.mp3")

            if not (os.path.exists(cached_audio) and os.path.getsize(cached_audio) > 0):
                fd, temp_path = tempfile.mkstemp(suffix=".mp3")
                os.close(fd)

                # Prioritize configured voice, followed by neural fallback of identical gender
                voices_to_try = [self.edge_voice]
                if self.is_female_voice():
                    for f_alt in ["en-GB-SoniaNeural", "en-US-JennyNeural", "en-US-AriaNeural"]:
                        if f_alt not in voices_to_try:
                            voices_to_try.append(f_alt)
                else:
                    for m_alt in ["en-GB-RyanNeural", "en-US-GuyNeural", "en-US-ChristopherNeural"]:
                        if m_alt not in voices_to_try:
                            voices_to_try.append(m_alt)

                success = False
                for v in voices_to_try:
                    async def _generate(target_v):
                        communicate = edge_tts.Communicate(text, voice=target_v)
                        await communicate.save(temp_path)

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(_generate(v))
                        if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                            success = True
                            break
                    except Exception as ge:
                        print(f"[Edge-TTS Voice Notice] Voice '{v}' attempt failed: {ge}")
                    finally:
                        loop.close()

                if success and os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                    try:
                        import shutil
                        shutil.copyfile(temp_path, cached_audio)
                        os.remove(temp_path)
                    except Exception:
                        cached_audio = temp_path
                else:
                    try:
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                    except Exception:
                        pass
                    return False

            if os.path.exists(cached_audio) and os.path.getsize(cached_audio) > 0:
                import time
                sound = pygame.mixer.Sound(cached_audio)
                sound.set_volume(self.volume)
                sound_len = sound.get_length()
                channel = sound.play()
                t0 = time.time()
                while channel and channel.get_busy() and self.is_speaking and (time.time() - t0 < sound_len + 0.3):
                    time.sleep(0.04)
                if not self.is_speaking and channel:
                    channel.stop()
                return True
        except Exception as e:
            print(f"[Edge-TTS Fallback Notice] {e}")
        return False

    def _speak_offline(self, text: str):
        if sys.platform == "win32":
            try:
                import pythoncom
                import win32com.client
                pythoncom.CoInitialize()
                try:
                    speaker = win32com.client.Dispatch("SAPI.SpVoice")
                    self._sapi_speaker = speaker

                    # Select and bind voice token matching active identity/gender
                    is_female = self.is_female_voice()
                    prefer_indian = "neerja" in self.edge_voice.lower() or "prabhat" in self.edge_voice.lower() or "ravi" in getattr(self, "sapi_voice", "").lower() or "heera" in getattr(self, "sapi_voice", "").lower()
                    prefer_deep = "christopher" in self.edge_voice.lower() or "mark" in getattr(self, "sapi_voice", "").lower() or "deep" in self.edge_voice.lower()
                    token_id = self._get_best_sapi_token_id(is_female, prefer_indian=prefer_indian, prefer_deep=prefer_deep)
                    if token_id:
                        try:
                            token = win32com.client.Dispatch("SAPI.SpObjectToken")
                            token.SetId(token_id)
                            speaker.Voice = token
                        except Exception as te:
                            print(f"[SAPI Voice Token Notice] Failed binding token {token_id}: {te}")

                    speaker.Volume = int(max(0, min(100, self.volume * 100)))
                    rate_mod = 0
                    if any(k in self.edge_voice.lower() for k in ["guy", "ava", "jenny"]):
                        rate_mod = 1
                    elif any(k in self.edge_voice.lower() for k in ["christopher", "deep"]):
                        rate_mod = -1
                    speaker.Rate = max(-10, min(10, int((self.rate - 150) / 15) + rate_mod))
                    # SVSFlagsAsync = 1 allows checking self.is_speaking for immediate cancellation
                    speaker.Speak(text, 1)
                    while self.is_speaking:
                        if speaker.WaitUntilDone(50):
                            break
                    if not self.is_speaking:
                        speaker.Speak("", 2)  # SVSFPurgeBeforeSpeak halts speech immediately
                    return
                finally:
                    pythoncom.CoUninitialize()
            except Exception as e:
                print(f"[Offline SAPI Error] {e}")
        elif sys.platform == "darwin":
            try:
                import subprocess
                subprocess.run(["say", text], check=False)
                return
            except Exception:
                pass
        elif sys.platform.startswith("linux"):
            try:
                import subprocess
                import shutil
                for bin_name in ["espeak-ng", "espeak", "spd-say"]:
                    if shutil.which(bin_name):
                        subprocess.run([bin_name, text], check=False)
                        return
            except Exception:
                pass

        try:
            engine = pyttsx3.init()
            engine.setProperty('rate', self.rate)
            engine.setProperty('volume', self.volume)
            is_female = self.is_female_voice()
            try:
                voices = engine.getProperty('voices')
                applied = False
                if hasattr(self, "sapi_voice") and self.sapi_voice:
                    req = self.sapi_voice.lower()
                    for v in voices:
                        v_name = (getattr(v, 'name', '') or '').lower()
                        v_id = (getattr(v, 'id', '') or '').lower()
                        if req in v_id or req in v_name:
                            engine.setProperty('voice', v.id)
                            applied = True
                            break
                if not applied:
                    for v in voices:
                        v_name = (getattr(v, 'name', '') or '').lower()
                        v_id = (getattr(v, 'id', '') or '').lower()
                        if is_female and any(w in v_name or w in v_id for w in ['zira', 'heera', 'female']):
                            engine.setProperty('voice', v.id)
                            break
                        elif not is_female and any(w in v_name or w in v_id for w in ['david', 'ravi', 'male']):
                            engine.setProperty('voice', v.id)
                            break
            except Exception:
                pass
            engine.say(text)
            engine.runAndWait()
        except Exception as e2:
            print(f"[Pyttsx3 Fallback Error] {e2}")
