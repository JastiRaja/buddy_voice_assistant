import os
import json

# Configuration Storage Path with fallback
PRIMARY_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".buddy_ai_config.json")
LOCAL_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".buddy_ai_config.json")

def get_config_path():
    try:
        if os.path.exists(PRIMARY_CONFIG_PATH):
            with open(PRIMARY_CONFIG_PATH, "r", encoding="utf-8") as f:
                pass
            return PRIMARY_CONFIG_PATH
        test_file = os.path.join(os.path.expanduser("~"), ".buddy_test_touch")
        with open(test_file, "w") as f:
            pass
        os.remove(test_file)
        return PRIMARY_CONFIG_PATH
    except Exception:
        return LOCAL_CONFIG_PATH

USER_CONFIG_PATH = get_config_path()

def load_user_settings():
    default_settings = {
        "strict_offline_mode": False,
        "tts_engine": "edge-tts",  # "edge-tts" or "pyttsx3"
        "edge_voice": "en-GB-RyanNeural",  # British Ryan (Jarvis style)
        "kokoro_voice": "bm_george",
        "sapi_voice": "TTS_MS_EN-US_DAVID_11.0",
        "voice_rate": 175,
        "voice_volume": 1.0,
        "audio_device_index": None,
        "audio_output_device_index": None,
        "audio_output_device_name": None,
        "silence_threshold": 0.0004,
        "whisper_model_size": "small.en",
        "whisper_beam_size": 5,
        "require_wake_word": True,
        "gemini_api_key": os.environ.get("GEMINI_API_KEY", ""),
        "assistant_name": "J.A.R.V.I.S.",
        "user_title": "sir"
    }
    if os.path.exists(USER_CONFIG_PATH):
        try:
            with open(USER_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                default_settings.update(data)
        except Exception as e:
            print(f"[Config Warning] Could not load user settings: {e}")
    return default_settings

def save_user_settings(settings):
    try:
        with open(USER_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4)
    except Exception as e:
        print(f"[Config Error] Could not save user settings: {e}")

_settings = load_user_settings()

# Strict Offline Mode
STRICT_OFFLINE_MODE = _settings.get("strict_offline_mode", False)
if STRICT_OFFLINE_MODE:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# Assistant Identity & Wake Word Settings
ASSISTANT_NAME = _settings.get("assistant_name", "J.A.R.V.I.S.")
USER_TITLE = _settings.get("user_title", "sir")
WAKE_WORDS = [
    "hey jarvis", "ok jarvis", "okay jarvis", "hi jarvis", "hello jarvis", "jarvis",
    "hey buddy", "ok buddy", "okay buddy", "hi buddy", "hello buddy", "buddy",
    "hey travis", "travis", "javis", "service", "garvis", "darvis", "harvest",
    "jarvis are you there", "are you awake"
]
REQUIRE_WAKE_WORD = _settings.get("require_wake_word", True)
WAKE_TIMEOUT_SECONDS = 20  # Keep continuous hands-free session active for 20s after wake word or command
HOTKEY_TRIGGER = "ctrl+space"  # Instant Push-to-Talk activation shortcut

# TTS Configuration
TTS_ENGINE = _settings.get("tts_engine", "edge-tts")  # "kokoro", "piper", "edge-tts", or "pyttsx3"
EDGE_VOICE = _settings.get("edge_voice", "en-GB-RyanNeural")
KOKORO_VOICE = _settings.get("kokoro_voice", "bm_george")  # British Male (Jarvis style)
SAPI_VOICE = _settings.get("sapi_voice", "TTS_MS_EN-US_DAVID_11.0")
VOICE_RATE = _settings.get("voice_rate", 175)
VOICE_VOLUME = _settings.get("voice_volume", 1.0)

AVAILABLE_TTS_ENGINES = {
    "Edge-TTS (Online Studio Neural)": "edge-tts",
    "System SAPI5 (Offline Standard)": "pyttsx3",
    "Kokoro ONNX (Offline Neural)": "kokoro",
    "Piper TTS (Offline Fast)": "piper"
}

AVAILABLE_KOKORO_VOICES = {
    "Jarvis (British Male - George)": "bm_george",
    "Sonia (British Female - Emma)": "bf_emma",
    "Adam (US Male)": "am_adam",
    "Heart (US Female)": "af_heart",
    "Nicole (US Expressive Female)": "af_nicole"
}

AVAILABLE_EDGE_VOICES = {
    "Jarvis (British Male)": "en-GB-RyanNeural",
    "Sonia (British Female)": "en-GB-SoniaNeural",
    "Guy (US Male)": "en-US-GuyNeural",
    "Christopher (US Deep Male)": "en-US-ChristopherNeural",
    "Ava (US Expressive Female)": "en-US-AvaNeural",
    "Jenny (US Natural Female)": "en-US-JennyNeural",
    "Prabhat (Indian English Male)": "en-IN-PrabhatNeural",
    "Neerja (Indian English Female)": "en-IN-NeerjaNeural",
}

AVAILABLE_SAPI_VOICES = {
    "David (US Male)": "TTS_MS_EN-US_DAVID_11.0",
    "Mark (US Deep Male)": "MSTTS_V110_enUS_MarkM",
    "Zira (US Female)": "TTS_MS_EN-US_ZIRA_11.0",
    "Ravi (Indian Male)": "MSTTS_V110_enIN_RaviM",
    "Heera (Indian Female)": "MSTTS_V110_enIN_HeeraM"
}

# STT Configuration (Uses local cached Whisper model)
WHISPER_MODEL_SIZE = _settings.get("whisper_model_size", "base.en")  # Runs locally from disk on CPU
WHISPER_BEAM_SIZE = int(_settings.get("whisper_beam_size", 5))       # Higher beam size = far better accuracy
WHISPER_DEVICE = "cpu"          # 'cpu' or 'cuda' (if NVIDIA GPU available)
WHISPER_COMPUTE_TYPE = "int8"   # 'int8' for CPU, 'float16' for CUDA
CPU_THREADS = 4                 # Parallel CPU threads for Whisper inference

# Persistent Models Directory (Immune to system ~/.cache clearing)
import sys
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    BUNDLED_MODELS_DIR = os.path.join(sys._MEIPASS, "models")
    APP_DIR = os.path.dirname(sys.executable)
else:
    BUNDLED_MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

MODELS_DIR = os.path.join(APP_DIR, "models")
WHISPER_MODEL_DIR = os.path.join(MODELS_DIR, f"whisper-{WHISPER_MODEL_SIZE}")
KOKORO_MODEL_DIR = os.path.join(MODELS_DIR, "kokoro")
KOKORO_MODEL_PATH = os.path.join(KOKORO_MODEL_DIR, "kokoro-v0_19.onnx")
KOKORO_VOICES_PATH = os.path.join(KOKORO_MODEL_DIR, "voices.json")
PIPER_MODEL_DIR = os.path.join(MODELS_DIR, "piper")
SLM_MODEL_DIR = MODELS_DIR

# Audio Stream & Dynamic Speech Detection Settings
SAMPLE_RATE = 16000
SILENCE_THRESHOLD = _settings.get("silence_threshold", 0.0004)
SPEECH_END_SILENCE = 1.2        # 1.2s end-of-speech silence detection allows natural pauses without cutting off
MAX_SPEECH_DURATION = 14.0      # Increased from 6.0 to 14.0s for natural sentences & queries
AUDIO_DEVICE_INDEX = _settings.get("audio_device_index", None)
AUDIO_OUTPUT_DEVICE_INDEX = _settings.get("audio_output_device_index", None)
AUDIO_OUTPUT_DEVICE_NAME = _settings.get("audio_output_device_name", None)

# Multimodal & Vision API Key
GEMINI_API_KEY = _settings.get("gemini_api_key", os.environ.get("GEMINI_API_KEY", ""))

# Whisper Vocabulary Priming Prompt (biases acoustic decoder towards exact desktop commands and wake words)
INITIAL_PROMPT = "Jarvis, hey Jarvis, Buddy, open application, close window, volume control, mute, brightness, terminal, summarize, clipboard, briefing, screen, notes, timer."

# Web Bookmarks & Online Service Aliases
# Note: All desktop applications are dynamically scanned, learned, and cataloged 
# by AppKnowledgeBase (recorded in SYSTEM_APPS_NOTES.md) without any hardcoding.
APP_ALIASES = {
    "facebook": "https://www.facebook.com",
    "facebook.com": "https://www.facebook.com",
    "youtube": "https://www.youtube.com",
    "youtube.com": "https://www.youtube.com",
    "google": "https://www.google.com",
    "google.com": "https://www.google.com",
    "chatgpt": "https://chatgpt.com",
    "chatgpt.com": "https://chatgpt.com",
    "github": "https://github.com",
    "github.com": "https://github.com",
    "gmail": "https://mail.google.com",
    "google mail": "https://mail.google.com",
    "email": "https://mail.google.com",
    "instagram": "https://www.instagram.com",
    "twitter": "https://twitter.com",
    "x": "https://x.com",
    "reddit": "https://www.reddit.com",
    "netflix": "https://www.netflix.com",
    "linkedin": "https://www.linkedin.com",
    "amazon": "https://www.amazon.com",
    "wikipedia": "https://www.wikipedia.org",
    "whatsapp": "https://web.whatsapp.com",
    "whatsapp web": "https://web.whatsapp.com",
    "web whatsapp": "https://web.whatsapp.com",
    "gemini": "https://gemini.google.com",
    "google gemini": "https://gemini.google.com",
    "maps": "https://maps.google.com",
    "google maps": "https://maps.google.com",
    "google drive": "https://drive.google.com",
    "drive": "https://drive.google.com",
    "calendar": "https://calendar.google.com",
    "google calendar": "https://calendar.google.com",
    "keep": "https://keep.google.com",
    "google keep": "https://keep.google.com",
    "docs": "https://docs.google.com",
    "google docs": "https://docs.google.com",
    "sheets": "https://sheets.google.com",
    "google sheets": "https://sheets.google.com",
    "slides": "https://slides.google.com",
    "google slides": "https://slides.google.com",
    "meet": "https://meet.google.com",
    "google meet": "https://meet.google.com",
    "google photos": "https://photos.google.com",
    "contacts": "https://contacts.google.com",
    "google contacts": "https://contacts.google.com",
    "translate": "https://translate.google.com",
    "google translate": "https://translate.google.com",
    "forms": "https://forms.google.com",
    "google forms": "https://forms.google.com",
    "news": "https://news.google.com",
    "google news": "https://news.google.com",
    "classroom": "https://classroom.google.com",
    "google classroom": "https://classroom.google.com",
    "youtube music": "https://music.youtube.com",
}

