import collections
import os
import queue
import re
import sys
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from config import (
    WHISPER_MODEL_SIZE,
    WHISPER_BEAM_SIZE,
    WHISPER_DEVICE,
    WHISPER_COMPUTE_TYPE,
    CPU_THREADS,
    INITIAL_PROMPT,
    SAMPLE_RATE,
    SILENCE_THRESHOLD,
    SPEECH_END_SILENCE,
    MAX_SPEECH_DURATION,
    WHISPER_MODEL_DIR,
    BUNDLED_MODELS_DIR,
    load_user_settings
)

def is_hallucination(text: str, pending_confirmation: bool = False) -> bool:
    """Detects common Whisper silence/noise hallucination artifacts and loop patterns."""
    if not text:
        return True
    
    clean = text.lower().strip()
    words = [w for w in re.findall(r'\b[a-zA-Z\']+\b', clean)]
    if not words:
        return True

    # If user is responding to a confirmation prompt or speaking a valid single-word command
    valid_short_commands = {
        "yes", "yeah", "yep", "sure", "no", "nope", "cancel", "abort", "confirm", "proceed", "stop"
    }
    if clean in valid_short_commands:
        if pending_confirmation:
            return False
        # Even without pending confirmation, "stop" is an emergency command
        if clean == "stop":
            return False

    # 1. Known Whisper background noise / outro hallucination phrases
    known_hallucinations = [
        "thank you for watching", "thanks for watching", "subtitles by",
        "subscribe to my channel", "see you in the next", "watching and see",
        "i'm glad you're watching", "we've got a stage here", "thank you. thank you",
        "bye. bye. bye", "okay. okay. thank you", "thanks so much. bye",
        "amara.org", "english subtitles", "like and subscribe", "please subscribe",
        "thank you very much", "thank you so much", "see you next time",
        "thanks for listening", "copyright", "all rights reserved",
        "translated by", "transcription by", "silence", "you you you",
        "so, so, so", "watching"
    ]
    for phrase in known_hallucinations:
        if phrase in clean:
            return True

    # Single-word mic pop / breath artifacts from silence
    single_artifacts = {
        "you", "you.", "so", "the", "a", "an", "oh",
        "um", "uh", "subtitles", "mbc", "amara", "the end",
        "hello?", "hi?", "okay?", "ok?"
    }
    if clean in single_artifacts or (len(words) == 1 and words[0] in single_artifacts):
        return True

    # 2. High repetition loops (e.g. repeated words/phrases)
    if len(words) >= 4:
        unique_words = set(words)
        ratio = len(unique_words) / len(words)
        # If less than 45% of words are unique in a sentence >= 4 words
        if ratio < 0.45:
            return True
        
        # Check if single word makes up > 35% of a sentence
        word_counts = collections.Counter(words)
        most_common_word, most_common_count = word_counts.most_common(1)[0]
        if most_common_count >= 3 and (most_common_count / len(words)) > 0.35:
            return True

        # Check for repeating bigrams
        if len(words) >= 6:
            bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words)-1)]
            bigram_counts = collections.Counter(bigrams)
            if bigram_counts.most_common(1)[0][1] >= 2:
                return True

    return False

def deduplicate_speech(text: str) -> str:
    """Collapses repetitive spoken phrases/stutters and standardizes wake words."""
    if not text:
        return text
    clean = text.strip()
    # Normalize J.A.R.V.I.S. abbreviation variations to Jarvis
    clean = re.sub(r'\b[jJ]\.?\s*[aA]\.?\s*[rR]\.?\s*[vV]\.?\s*[iI]\.?\s*[sS]\.?\b[\.\,]*', 'Jarvis', clean)

    # 1. Comma / period separated identical repetitions: "open chrome. open chrome" -> "open chrome"
    parts = [p.strip() for p in re.split(r'[,;\.\?!]+', clean) if p.strip()]
    if len(parts) >= 2:
        if all(p.lower() == parts[0].lower() for p in parts):
            clean = parts[0]
        elif len(parts) == 2 and (parts[0].lower() in parts[1].lower() or parts[1].lower() in parts[0].lower()):
            clean = max(parts, key=len)

    # 2. Complete phrase duplicate: "open chrome open chrome" -> "open chrome"
    clean_words = clean.split()
    n = len(clean_words)
    if n >= 4 and n % 2 == 0:
        half = n // 2
        if [w.lower() for w in clean_words[:half]] == [w.lower() for w in clean_words[half:]]:
            clean = " ".join(clean_words[:half])

    return clean

def is_valid_model_dir(dir_path: str) -> bool:
    """Verifies that a directory contains the required Whisper/CTranslate2 model weights."""
    if not dir_path or not os.path.isdir(dir_path):
        return False
    has_model = any(os.path.isfile(os.path.join(dir_path, f)) for f in ["model.bin", "model.safetensors"])
    has_config = os.path.isfile(os.path.join(dir_path, "config.json"))
    return has_model and has_config

def ensure_whisper_model(model_size: str = WHISPER_MODEL_SIZE, target_dir: str = WHISPER_MODEL_DIR) -> str:
    """
    Ensures that the Whisper speech recognition model is available locally.
    1. Checks persistent models directory (survives system cache clearing).
    2. Checks bundled models directory (for packaged frozen exe).
    3. Checks Hugging Face local cache if present.
    4. If not found anywhere, temporarily enables outgoing traffic and downloads the model
       into the persistent models directory, ensuring strict offline mode is restored after.
    """
    # 1. Check persistent target directory
    if is_valid_model_dir(target_dir):
        return target_dir

    # 2. Check bundled models directory (for packaged frozen exe)
    bundled_target = os.path.join(BUNDLED_MODELS_DIR, f"whisper-{model_size}")
    if is_valid_model_dir(bundled_target):
        return bundled_target

    # 3. Check Hugging Face hub local cache without initiating network traffic
    try:
        from faster_whisper.utils import download_model
        cached_path = download_model(model_size, local_files_only=True)
        if is_valid_model_dir(cached_path):
            return cached_path
    except Exception:
        pass

    # 4. Model is not cached locally (or cache was cleared). Download directly to persistent models directory.
    print(f"\n[*] Whisper model '{model_size}' not found in local cache.")
    print(f"[*] Downloading offline model files to persistent directory '{target_dir}' (~140MB one-time setup)...")

    # Temporarily allow network requests for downloading model weights
    old_hf_offline = os.environ.get("HF_HUB_OFFLINE")
    old_tf_offline = os.environ.get("TRANSFORMERS_OFFLINE")
    os.environ["HF_HUB_OFFLINE"] = "0"
    os.environ.pop("TRANSFORMERS_OFFLINE", None)

    old_const = None
    try:
        import huggingface_hub.constants
        old_const = getattr(huggingface_hub.constants, "HF_HUB_OFFLINE", None)
        huggingface_hub.constants.HF_HUB_OFFLINE = False
    except Exception:
        pass

    # Temporarily suspend process network kill-switch if active
    was_killswitch_active = False
    try:
        from audit_and_sandbox import NetworkKillSwitch
        was_killswitch_active = NetworkKillSwitch.is_active()
        if was_killswitch_active:
            NetworkKillSwitch.disable()
    except Exception:
        pass

    try:
        from faster_whisper.utils import download_model
        os.makedirs(target_dir, exist_ok=True)
        downloaded_path = download_model(model_size, output_dir=target_dir)
        print(f"[*] Successfully saved Whisper model to '{downloaded_path}'.")
        return downloaded_path
    except Exception as e:
        # Check if another valid Whisper model is already available locally to avoid crashing
        if os.path.isdir(MODELS_DIR):
            for entry in os.listdir(MODELS_DIR):
                candidate = os.path.join(MODELS_DIR, entry)
                if is_valid_model_dir(candidate):
                    print(f"\n[!] Warning: Could not download Whisper model '{model_size}' ({e}).")
                    print(f"[*] Seamlessly falling back to existing local offline model at '{candidate}'.")
                    return candidate

        error_msg = (
            f"Failed to load or download Whisper model '{model_size}' ({e}).\n"
            f"If system cache was cleared, an active internet connection is required once to download the model (~140MB).\n"
            f"Alternatively, copy model files into '{target_dir}'."
        )
        raise RuntimeError(error_msg) from e
    finally:
        # Restore network killswitch if it was active
        if was_killswitch_active:
            try:
                from audit_and_sandbox import NetworkKillSwitch
                NetworkKillSwitch.enable()
            except Exception:
                pass

        # Restore offline environment flags
        if old_hf_offline is not None:
            os.environ["HF_HUB_OFFLINE"] = old_hf_offline
        else:
            os.environ.pop("HF_HUB_OFFLINE", None)

        if old_tf_offline is not None:
            os.environ["TRANSFORMERS_OFFLINE"] = old_tf_offline
        else:
            os.environ.pop("TRANSFORMERS_OFFLINE", None)

        if old_const is not None:
            try:
                import huggingface_hub.constants
                huggingface_hub.constants.HF_HUB_OFFLINE = old_const
            except Exception:
                pass

class SpeechRecognizer:
    def __init__(self, tts=None, hud=None, controller=None, dispatcher=None):
        self.tts = tts
        self.hud = hud
        self.controller = controller
        self.dispatcher = dispatcher

        model_path = ensure_whisper_model(WHISPER_MODEL_SIZE, WHISPER_MODEL_DIR)
        print(f"[*] Initializing local Whisper model from '{model_path}' ({WHISPER_DEVICE}, {WHISPER_COMPUTE_TYPE}, {CPU_THREADS} threads)...")

        self.model = WhisperModel(
            model_path,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
            cpu_threads=CPU_THREADS
        )
        self.audio_queue = queue.Queue()
        print("[*] Local Speech Recognition Engine Ready (100% Offline).")

    def _get_device_index(self):
        settings = load_user_settings()
        return settings.get("audio_device_index", None)

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            print(f"[Audio Status] {status}", file=sys.stderr)
        # Drop audio if assistant is speaking or mic is muted in HUD
        if (self.tts and self.tts.is_speaking) or (self.hud and self.hud.is_muted):
            return
        self.audio_queue.put(indata.copy())

    def listen_loop(self, on_command_callback):
        """
        Listens dynamically to microphone stream with auto noise calibration,
        visual indicators, whisper AGC, and end-of-speech detection.
        """
        print("\n" + "="*50)
        print("  ◈ LISTENING FOR WAKE WORD: 'JARVIS' OR 'BUDDY'")
        print("  Press Ctrl+C or say 'Jarvis power down' to quit")
        print("="*50)

        block_size = int(SAMPLE_RATE * 0.1)  # 100ms audio blocks (1600 samples)
        pre_buffer_size = 6                  # 600ms pre-speech audio buffer so leading syllables are fully preserved
        pre_buffer = collections.deque(maxlen=pre_buffer_size)

        device_idx = self._get_device_index()
        dev_desc = "System Default"
        try:
            devs = sd.query_devices()
            if device_idx is not None and device_idx < len(devs):
                dev_desc = f"[{device_idx}] {devs[device_idx]['name']}"
            else:
                def_in = sd.default.device[0]
                if def_in is not None and def_in < len(devs):
                    dev_desc = f"Default: [{def_in}] {devs[def_in]['name']}"
        except Exception:
            pass
        print(f"[*] Audio input device: {dev_desc}")

        # 1. Auto-Calibration of Ambient Noise Floor (1.2s, median-based)
        print("\n[*] Calibrating microphone ambient noise level...")
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break

        calib_chunks = []
        try:
            with sd.InputStream(device=device_idx, samplerate=SAMPLE_RATE, channels=1, blocksize=block_size, callback=self._audio_callback):
                for _ in range(12):
                    try:
                        calib_chunks.append(self.audio_queue.get(timeout=1.0))
                    except queue.Empty:
                        break
        except Exception as e:
            print(f"[Audio Device Warning] Failed opening device #{device_idx}: {e}. Falling back to default.")
            device_idx = None
            with sd.InputStream(device=None, samplerate=SAMPLE_RATE, channels=1, blocksize=block_size, callback=self._audio_callback):
                for _ in range(12):
                    try:
                        calib_chunks.append(self.audio_queue.get(timeout=1.0))
                    except queue.Empty:
                        break
        
        rms_values = [np.sqrt(np.mean(c ** 2)) for c in calib_chunks] if calib_chunks else [0.0001]
        ambient_rms = float(np.median(rms_values))
        # Responsive dynamic threshold: safely above ambient room noise floor without deafening soft speech
        threshold = max(ambient_rms * 2.0, ambient_rms + 0.00006)
        threshold = min(threshold, 0.012)
        print(f"[*] Microphone calibrated! Ambient RMS: {ambient_rms:.6f} -> Sensitivity Threshold: {threshold:.6f}")
        print(f"[*] Whisper Decoder: Model='{WHISPER_MODEL_SIZE}', BeamSize={WHISPER_BEAM_SIZE}")
        print("[*] All systems ready! Say a command or 'Jarvis'...\n")

        # Flush queue and pre-buffer before starting active recognition loop
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break
        pre_buffer.clear()

        # 2. Main Recognition Loop with Adaptive Ambient Tracking
        with sd.InputStream(device=device_idx, samplerate=SAMPLE_RATE, channels=1, blocksize=block_size, callback=self._audio_callback):
            while True:
                chunk = self.audio_queue.get()
                rms = np.sqrt(np.mean(chunk ** 2))

                if rms < threshold:
                    # Slow adaptation of background noise floor during silence
                    ambient_rms = 0.995 * ambient_rms + 0.005 * rms
                    threshold = max(ambient_rms * 2.0, ambient_rms + 0.00006)
                    threshold = min(threshold, 0.012)
                    pre_buffer.append(chunk)
                    continue

                # Voice detected!
                if self.hud:
                    self.hud.set_state("listening", "Hearing voice...", "Listening to command...")
                sys.stdout.write(f"\r[● Hearing voice... RMS: {rms:.5f}]      ")
                sys.stdout.flush()

                speech_chunks = list(pre_buffer)
                speech_chunks.append(chunk)
                pre_buffer.clear()

                silence_chunks = 0
                max_silence_chunks = int(SPEECH_END_SILENCE / 0.1)
                max_speech_chunks = int(MAX_SPEECH_DURATION / 0.1)

                while len(speech_chunks) < max_speech_chunks:
                    try:
                        next_chunk = self.audio_queue.get(timeout=0.3)
                    except queue.Empty:
                        break

                    speech_chunks.append(next_chunk)
                    chunk_rms = np.sqrt(np.mean(next_chunk ** 2))

                    if chunk_rms < threshold:
                        silence_chunks += 1
                        if silence_chunks >= max_silence_chunks:
                            break
                    else:
                        silence_chunks = 0

                if not speech_chunks:
                    continue

                audio_data = np.concatenate(speech_chunks, axis=0).flatten().astype(np.float32)

                # 1. Skip short clicks/pops under 200ms (speech requires at least 200ms)
                if len(audio_data) < SAMPLE_RATE * 0.20:
                    if self.hud:
                        self.hud.set_state("idle", "Standby // Awaiting Command...")
                    sys.stdout.write("\r                                               \r")
                    sys.stdout.flush()
                    continue

                # 2. Check energy before normalizing - permissive enough to capture soft and whispered speech
                audio_rms = np.sqrt(np.mean(audio_data ** 2))
                peak = np.max(np.abs(audio_data))
                if peak < max(ambient_rms * 1.4, 0.001) or audio_rms < max(ambient_rms * 1.1, 0.0003):
                    if self.hud:
                        self.hud.set_state("idle", "Standby // Awaiting Command...")
                    sys.stdout.write("\r                                               \r")
                    sys.stdout.flush()
                    continue

                # 3. Controlled audio normalization using 99th percentile (resilient to breath pops / mic clicks)
                audio_data = audio_data - np.mean(audio_data)
                p99 = float(np.percentile(np.abs(audio_data), 99))
                if p99 > 0.0008:
                    gain = min(0.65 / p99, 10.0)
                    audio_data = audio_data * gain
                audio_data = np.clip(audio_data, -0.95, 0.95)

                if self.hud:
                    self.hud.set_state("transcribing", "Transcribing Audio...", "Processing speech...")
                sys.stdout.write("\r[⌛ Transcribing audio...]                     \r")
                sys.stdout.flush()

                try:
                    segments, _ = self.model.transcribe(
                        audio_data,
                        initial_prompt=INITIAL_PROMPT,
                        beam_size=WHISPER_BEAM_SIZE,
                        best_of=WHISPER_BEAM_SIZE,
                        language="en",
                        vad_filter=True,
                        vad_parameters=dict(
                            threshold=0.38,
                            min_speech_duration_ms=180,
                            max_speech_duration_s=float('inf'),
                            min_silence_duration_ms=450,
                            speech_pad_ms=250
                        ),
                        condition_on_previous_text=False,
                        compression_ratio_threshold=2.4,
                        no_speech_threshold=0.6,
                        log_prob_threshold=-1.0,
                        temperature=0.0
                    )
                    raw_text = " ".join([segment.text for segment in segments]).strip()
                    transcribed_text = deduplicate_speech(raw_text)
                except Exception as e:
                    print(f"\n[Transcribe Error] {e}")
                    transcribed_text = ""

                sys.stdout.write("\r                                               \r")
                sys.stdout.flush()

                if raw_text:
                    print(f"\n[STT Transcribed]: \"{raw_text}\" (Duration: {len(audio_data)/SAMPLE_RATE:.1f}s, Peak: {peak:.5f}, RMS: {audio_rms:.5f})")
                sys.stdout.flush()
                sys.stdout.flush()

                is_confirmation_pending = False
                if self.dispatcher and getattr(self.dispatcher, 'pending_confirmation', None):
                    is_confirmation_pending = True
                elif hasattr(on_command_callback, '__self__'):
                    disp = getattr(on_command_callback, '__self__', None)
                    if disp and getattr(disp, 'pending_confirmation', None):
                        is_confirmation_pending = True

                if transcribed_text and is_hallucination(transcribed_text, pending_confirmation=is_confirmation_pending):
                    print(f"[STT] Filtered hallucination/noise loop: \"{transcribed_text}\"")
                    transcribed_text = ""
                    if self.hud:
                        self.hud.set_state("idle", "Standby // Awaiting Command...")

                if transcribed_text:
                    should_continue = True
                    try:
                        should_continue = on_command_callback(transcribed_text)
                    except Exception as ex:
                        print(f"\n[Command Error] {ex}")
                        if self.tts:
                            self.tts.speak("I encountered an issue processing that command, sir.")
                    finally:
                        # Flush stale audio chunks accumulated during command execution/TTS
                        while not self.audio_queue.empty():
                            try:
                                self.audio_queue.get_nowait()
                            except queue.Empty:
                                break
                        pre_buffer.clear()
                        if self.hud:
                            self.hud.set_state("idle", "Standby // Awaiting Command...")

                    if not should_continue:
                        break
