import os
import re
import json
import time
from typing import Optional, Dict, Any, Tuple

# Available Tool Schema for Tier 2 Function Calling
TOOL_DEFINITIONS = [
    {
        "name": "close_app",
        "description": "Close, terminate, exit, or quit an open application or window",
        "parameters": {"target": "name of application or window to close (e.g. 'chrome', 'notepad')"}
    },
    {
        "name": "open_app",
        "description": "Open, launch, or start an application, program, or website",
        "parameters": {"target": "name of application to open"}
    },
    {
        "name": "switch_window",
        "description": "Switch focus to or bring up a running application window",
        "parameters": {"target": "name of application to switch to"}
    },
    {
        "name": "change_brightness",
        "description": "Adjust screen brightness when user mentions it's too bright, too dim, or requests a level",
        "parameters": {"direction": "up, down, or set", "amount": "optional integer percentage"}
    },
    {
        "name": "volume_control",
        "description": "Adjust audio volume or mute/unmute system sound",
        "parameters": {"direction": "up, down, or mute"}
    },
    {
        "name": "media_control",
        "description": "Control playback of music, songs, or videos",
        "parameters": {"action": "play, pause, toggle, next, or prev"}
    },
    {
        "name": "window_management",
        "description": "Manage desktop windows layout, minimize, maximize, snap, or close windows",
        "parameters": {"action": "minimize_all, snap_left, snap_right, maximize, minimize, or close_window"}
    },
    {
        "name": "browser_action",
        "description": "Browser tab actions or navigation",
        "parameters": {"action": "new_tab, close_tab, switch_tab, refresh, or downloads"}
    },
    {
        "name": "list_files",
        "description": "List files, items, or directory contents in a specified folder, drive, or current directory",
        "parameters": {"folder": "folder or drive name, or 'current'"}
    },
    {
        "name": "count_folder_contents",
        "description": "Count or inspect how many folders, subfolders, or files exist in a directory (e.g. Pictures, Downloads, Documents)",
        "parameters": {"query": "the user query or target folder"}
    },
    {
        "name": "system_diagnostics",
        "description": "Check PC performance, health, CPU, RAM, or battery status",
        "parameters": {"query": "status, battery, cpu, or ram"}
    },
    {
        "name": "screen_vision",
        "description": "Inspect, describe screen content, or diagnose on-screen errors",
        "parameters": {"action": "analyze or explain_error"}
    },
    {
        "name": "read_aloud",
        "description": "Read highlighted text or clipboard aloud",
        "parameters": {"source": "selection or clipboard"}
    },
    {
        "name": "take_note",
        "description": "Record or save a note to notes file",
        "parameters": {"content": "text to save"}
    },
    {
        "name": "read_notes",
        "description": "Read saved notes back to user",
        "parameters": {}
    },
    {
        "name": "set_timer",
        "description": "Set a countdown timer with duration in seconds",
        "parameters": {"seconds": "number of seconds", "label": "label of timer"}
    },
    {
        "name": "cancel_timer",
        "description": "Cancel all active countdown timers",
        "parameters": {}
    },
    {
        "name": "power_control",
        "description": "PC power actions (locking, sleeping, restarting, shutting down, empty recycle bin)",
        "parameters": {"action": "lock, sleep, restart, shutdown, or empty_recycle_bin", "delay_minutes": "optional minutes"}
    },
    {
        "name": "weather_query",
        "description": "Inquire about weather or temperature for a city",
        "parameters": {"city": "name of city"}
    },
    {
        "name": "news_query",
        "description": "Read current world news headlines",
        "parameters": {}
    },
    {
        "name": "calculate",
        "description": "Calculate a math expression or percentage",
        "parameters": {"expression": "math expression to calculate"}
    },
    {
        "name": "search_web",
        "description": "Search the internet using a search engine",
        "parameters": {"query": "search query string"}
    },
    {
        "name": "search_youtube",
        "description": "Search or play a song, video, or topic on YouTube",
        "parameters": {"query": "video or song search query"}
    },
    {
        "name": "find_file",
        "description": "Locate and open a file on the local computer",
        "parameters": {"filename": "name of file to find"}
    },
    {
        "name": "open_folder",
        "description": "Open a user folder (Downloads, Documents, Desktop, etc.)",
        "parameters": {"folder": "folder name"}
    },
    {
        "name": "organize_folder",
        "description": "Automatically categorize and sort files in a folder by file type",
        "parameters": {"folder": "folder to organize (e.g. 'downloads')"}
    },
    {
        "name": "workspace_profile",
        "description": "Activate a multi-app workspace preset (coding, study, or relax)",
        "parameters": {"profile": "preset name (e.g. 'coding', 'study', 'relax')"}
    },
    {
        "name": "play_local_media",
        "description": "Play local offline audio files without internet access",
        "parameters": {"query": "optional track or artist search name"}
    },
    {
        "name": "summarize_selection",
        "description": "Summarize highlighted text or current clipboard",
        "parameters": {}
    },
    {
        "name": "fix_grammar",
        "description": "Fix grammar, spelling, punctuation, and capitalization of selected text",
        "parameters": {}
    },
    {
        "name": "make_professional",
        "description": "Rewrite selected text into formal executive/professional language",
        "parameters": {}
    },
    {
        "name": "read_clipboard_history",
        "description": "Read recent items from local clipboard history",
        "parameters": {"count": "number of items to read"}
    },
    {
        "name": "paste_clipboard_history",
        "description": "Paste a specific item number from clipboard history",
        "parameters": {"index": "1-based item number"}
    },
    {
        "name": "document_rag",
        "description": "Query or summarize local indexed PDF and Word documents",
        "parameters": {"query": "document name or query text"}
    },
    {
        "name": "morning_briefing",
        "description": "Give a daily schedule and morning briefing with calendar events, to-dos, and system telemetry",
        "parameters": {}
    },
    {
        "name": "execute_macro",
        "description": "Execute a custom voice macro routine (e.g. wrap up for the day, presentation mode, focus mode)",
        "parameters": {"macro_name": "name of macro to execute"}
    },
    {
        "name": "toggle_network_killswitch",
        "description": "Activate or deactivate the OS process network kill-switch to enforce strict air-gapped privacy",
        "parameters": {"enable": "true or false"}
    },
    {
        "name": "read_audit_log",
        "description": "Read back a summary of recent local assistant operations and air-gapped audit records",
        "parameters": {}
    },
    {
        "name": "change_voice",
        "description": "Change the assistant's voice personality or gender (e.g. Sonia, Christopher, Jarvis, Guy, female, male)",
        "parameters": {"voice_name": "name of voice or gender"}
    },
    {
        "name": "list_voices",
        "description": "List all available voice personalities",
        "parameters": {}
    }
]

DESTRUCTIVE_ACTIONS = {
    "empty_recycle_bin": "empty the Windows Recycle Bin",
    "restart": "restart your computer",
    "shutdown": "shut down your computer",
    "kill_all_apps": "close all open applications"
}


class IntentRouter:
    """
    Two-Tier Local Intent Router:
    - Tier 1: Instant deterministic extraction and normalization.
    - Tier 2: Local SLM / Local Semantic Intent Resolution for natural language phrasing.
    """
    def __init__(self, models_dir: str = None):
        self.models_dir = models_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
        self.llm = None
        self._init_local_llm()

    def _init_local_llm(self):
        """Attempts to load a local GGUF model via llama-cpp-python if present."""
        try:
            # Check for GGUF files in models_dir
            if os.path.exists(self.models_dir):
                for f in os.listdir(self.models_dir):
                    if f.endswith(".gguf") and ("qwen" in f.lower() or "llama" in f.lower() or "slm" in f.lower()):
                        model_path = os.path.join(self.models_dir, f)
                        try:
                            from llama_cpp import Llama
                            self.llm = Llama(
                                model_path=model_path,
                                n_ctx=2048,
                                n_threads=4,
                                verbose=False
                            )
                            print(f"[*] Local SLM Intent Engine loaded: {f}")
                            return
                        except ImportError:
                            print("[IntentRouter] llama-cpp-python not installed; falling back to local semantic matcher.")
                            break
                        except Exception as e:
                            print(f"[IntentRouter] Failed to load local SLM {f}: {e}")
                            break
        except Exception as e:
            print(f"[IntentRouter Init Notice] {e}")

    def resolve(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Resolves natural language queries that bypassed Tier 1 regex.
        Returns a dict: {"name": tool_name, "parameters": dict, "is_destructive": bool, "description": str} or None.
        """
        cmd = text.lower().strip()
        if not cmd:
            return None

        # 1. Built-in Local Semantic Intent Engine (Zero-Latency <0.5ms, 100% Offline)
        semantic_result = self._resolve_semantic(cmd)
        if semantic_result:
            return self._decorate_result(semantic_result)

        # 2. Try Local SLM if GGUF model is loaded in memory
        if self.llm:
            slm_result = self._resolve_with_slm(cmd)
            if slm_result:
                return self._decorate_result(slm_result)

        # 3. Try Local Ollama fallback if running on localhost
        ollama_result = self._try_local_ollama(cmd)
        if ollama_result:
            return self._decorate_result(ollama_result)

        return None

    def _decorate_result(self, res: Dict[str, Any]) -> Dict[str, Any]:
        """Tags if the action requires voice confirmation."""
        name = res.get("name", "")
        params = res.get("parameters", {})
        action_key = params.get("action", "") if name == "power_control" else name

        is_destructive = False
        desc = ""
        if action_key in DESTRUCTIVE_ACTIONS:
            is_destructive = True
            desc = DESTRUCTIVE_ACTIONS[action_key]
        elif name == "power_control" and params.get("action") in DESTRUCTIVE_ACTIONS:
            is_destructive = True
            desc = DESTRUCTIVE_ACTIONS[params.get("action")]

        res["is_destructive"] = is_destructive
        res["description"] = desc
        return res

    def _resolve_semantic(self, cmd: str) -> Optional[Dict[str, Any]]:
        """
        High-precision offline semantic matcher for natural phrasing variations
        that do not match strict regex keywords.
        """
        # --- App & Window Closing Phrasings ---
        # e.g. "close the open window", "close this window", "close window", "exit chrome", "quit notepad"
        if (
            re.search(r'\b(close|exit|shut|terminate)\s+(?:the\s+)?(?:open\s+|active\s+|current\s+|this\s+)?window\b', cmd) or
            re.search(r'\b(close|exit)\s+(?:the\s+)?entire\s+application\b', cmd) or
            cmd in ["close window", "close this window", "close the window", "close open window", "close the open window", "close active window", "close current window", "close this"]
        ):
            return {"name": "window_management", "parameters": {"action": "close_window"}}

        close_match = re.search(r'^(?:exit|quit|terminate|kill|close|shut\s+down)\s+(?:the\s+)?([a-zA-Z0-9_\-\s]+?)(?:\s+app|\s+application|\s+window)?$', cmd)
        if close_match:
            target = close_match.group(1).strip()
            if target in ["open", "window", "this window", "the window", "open window", "the open window", "active window", "current window", "entire application", "the entire application", "entire app"]:
                return {"name": "window_management", "parameters": {"action": "close_window"}}
            if target not in ["assistant", "jarvis", "buddy", "computer", "pc", "all"]:
                return {"name": "close_app", "parameters": {"target": target}}

        # --- Folder & File Counting Natural Phrasings ---
        # e.g. "how many folders are there in pictures folder", "how many files in downloads", "what folders are in pictures"
        if re.search(r'\b(how many|count)\s+(folders?|subfolders?|directories|dirs|files?|images?|photos?|items?)\b', cmd) or \
           re.search(r'\bwhat\s+(folders?|subfolders?|directories|dirs)\s+(are\s+)?(in|inside|on|there)\b', cmd):
            return {"name": "count_folder_contents", "parameters": {"query": cmd}}

        # --- File & Directory Listing Natural Phrasings ---
        # e.g. "what files are here", "list the files", "list to the files", "relish to the files", "i wish the files were this folder"
        if any(p in cmd for p in [
            "list files", "list the files", "list to the files", "relish to the files",
            "show files", "files in this folder", "files in here", "what files are in",
            "files were this folder", "i wish the files were this folder", "show directory contents"
        ]) or re.search(r'\b(list|show|relish|what)\s+(?:all\s+)?(?:the\s+)?(?:to\s+the\s+)?(?:files|items|contents)\b', cmd):
            folder = "current"
            for f in ["c drive", "d drive", "downloads", "documents", "desktop", "pictures", "projects", "music"]:
                if f in cmd:
                    folder = f
                    break
            return {"name": "list_files", "parameters": {"folder": folder}}

        # --- Direct Drive Requests ---
        # e.g. "open c drive", "open c-drow", "open d drive", "open c-drive"
        drive_m = re.search(r'^(?:open|show|access)?\s*(?:the\s+)?([a-z]|see|sea|sito|dee)[-\s]*(?:drive|disk|drow|tray)$', cmd) or \
                  re.search(r'^(?:open|show|access)?\s*(?:drive|disk)\s*([a-z]|see|sea|sito|dee)$', cmd)
        if drive_m:
            raw_letter = drive_m.group(1).upper()
            letter = "C" if raw_letter in ["SEE", "SEA", "SITO", "C"] else ("D" if raw_letter in ["DEE", "D"] else raw_letter)
            return {"name": "open_folder", "parameters": {"folder": f"{letter} drive"}}

        # --- Brightness Natural Phrasings ---
        # e.g. "it's too bright in here", "screen is too bright", "my eyes hurt", "it's too dark"
        if any(p in cmd for p in ["too bright", "screen is bright", "blinding", "hurts my eyes", "hurting my eyes"]):
            return {"name": "change_brightness", "parameters": {"direction": "down", "amount": 20}}
        if any(p in cmd for p in ["too dark", "too dim", "can't see the screen", "cant see the screen", "screen is dim"]):
            return {"name": "change_brightness", "parameters": {"direction": "up", "amount": 20}}

        # --- Volume Natural Phrasings ---
        # e.g. "it's too loud", "make it louder", "can't hear anything", "turn off the sound"
        if any(p in cmd for p in ["too loud", "it's loud", "turn that down", "softer please", "lower the audio"]):
            return {"name": "volume_control", "parameters": {"direction": "down"}}
        if any(p in cmd for p in ["too quiet", "make it louder", "can't hear", "cant hear", "boost audio", "crank it up"]):
            return {"name": "volume_control", "parameters": {"direction": "up"}}
        if any(p in cmd for p in ["silence audio", "cut the sound", "turn off the sound", "turn sound off", "shut up audio"]):
            return {"name": "volume_control", "parameters": {"direction": "mute"}}

        # --- Window & Desktop Natural Phrasings ---
        # e.g. "clear everything out of the way", "hide all my windows", "get to desktop", "clear the screen"
        if any(p in cmd for p in [
            "clear my screen", "clear out windows", "hide everything", "get to desktop",
            "show me my desktop", "clear away windows", "sweep windows", "clean my screen"
        ]):
            return {"name": "window_management", "parameters": {"action": "minimize_all"}}

        # --- Audio Devices Natural Phrasings ---
        if any(p in cmd for p in ["audio devices", "connected audio", "what microphone", "what speakers", "check microphone", "check speaker", "sound devices", "audio peripherals", "input devices", "output devices"]):
            return {"name": "system_diagnostics", "parameters": {"query": "audio"}}

        # --- Battery & Power Natural Phrasings ---
        # e.g. "how much juice is left", "how much battery do i have", "am i plugged in", "battery level"
        if any(p in cmd for p in ["how much juice", "juice left", "how much battery", "battery level", "power remaining", "is the battery low"]):
            return {"name": "system_diagnostics", "parameters": {"query": "battery"}}

        # --- CPU / RAM Natural Phrasings ---
        # e.g. "is my pc lagging", "how hard is the computer working", "what's eating memory", "memory check"
        if any(p in cmd for p in ["is my computer lagging", "is pc lagging", "how hard is the cpu working", "check memory", "check performance", "performance check"]):
            return {"name": "system_diagnostics", "parameters": {"query": "status"}}

        # --- Media Natural Phrasings ---
        # e.g. "skip this track", "don't like this song", "next song please"
        if any(p in cmd for p in ["skip this", "hate this song", "dont like this song", "different song", "next track please"]):
            return {"name": "media_control", "parameters": {"action": "next"}}

        # --- Vision Natural Phrasings ---
        # e.g. "what is displayed right now", "take a look at my screen", "see what i have open"
        if any(p in cmd for p in ["copy text from screen", "extract text from screen", "grab screen text", "ocr text on screen", "copy screen text"]):
            return {"name": "screen_vision", "parameters": {"action": "copy_text"}}

        if any(p in cmd for p in ["take a look at my screen", "look at my screen", "see what is on screen", "see what i'm looking at", "look here"]):
            return {"name": "screen_vision", "parameters": {"action": "analyze"}}

        # --- Advanced Workspace, Organization & Local Media ---
        if any(p in cmd for p in ["clean up my downloads", "organize my downloads", "sort my downloads", "organize my files", "tidy up downloads"]):
            return {"name": "organize_folder", "parameters": {"folder": "downloads"}}

        if any(p in cmd for p in ["start coding mode", "coding mode", "coding profile", "developer mode", "dev mode"]):
            return {"name": "workspace_profile", "parameters": {"profile": "coding"}}

        if any(p in cmd for p in ["start study mode", "study mode", "study profile", "research mode"]):
            return {"name": "workspace_profile", "parameters": {"profile": "study"}}

        if any(p in cmd for p in ["start relax mode", "relax mode", "chill mode"]):
            return {"name": "workspace_profile", "parameters": {"profile": "relax"}}

        if any(p in cmd for p in ["play offline music", "play local music", "play stored music", "play music offline"]):
            return {"name": "play_local_media", "parameters": {"query": ""}}

        # --- Smart Writing, Clipboard & Document RAG ---
        if any(p in cmd for p in ["summarize this", "summarize my selection", "summarize the text", "summarize selection", "give me a summary of this"]):
            return {"name": "summarize_selection", "parameters": {}}

        if any(p in cmd for p in ["fix my grammar", "fix grammar", "clean up this text", "correct my spelling", "fix punctuation"]):
            return {"name": "fix_grammar", "parameters": {}}

        if any(p in cmd for p in ["make this sound professional", "make professional", "professional tone", "sound more professional", "polish this"]):
            return {"name": "make_professional", "parameters": {}}

        if any(p in cmd for p in ["what did i copy", "read my clipboard", "clipboard history", "read copied history", "read recent clips"]):
            return {"name": "read_clipboard_history", "parameters": {"count": 3}}

        if any(p in cmd for p in ["summarize my latest pdf", "summarize latest pdf", "summarize recent document", "what's in my latest pdf"]):
            return {"name": "document_rag", "parameters": {"query": "latest pdf"}}

        # --- Morning Briefing, Macros & Audit Privacy ---
        if any(p in cmd for p in ["morning briefing", "daily briefing", "what's on my schedule", "whats on my schedule", "daily schedule", "today's briefing"]):
            return {"name": "morning_briefing", "parameters": {}}

        if any(p in cmd for p in ["wrap up for the day", "end of day", "presentation mode", "focus mode"]):
            return {"name": "execute_macro", "parameters": {"macro_name": cmd}}

        if any(p in cmd for p in ["turn on network kill switch", "enable network kill switch", "block network", "activate network kill switch", "air gap mode"]):
            return {"name": "toggle_network_killswitch", "parameters": {"enable": True}}

        if any(p in cmd for p in ["turn off network kill switch", "disable network kill switch", "unblock network", "deactivate network kill switch"]):
            return {"name": "toggle_network_killswitch", "parameters": {"enable": False}}

        if any(p in cmd for p in ["read audit log", "audit log summary", "what actions did you take", "show audit"]):
            return {"name": "read_audit_log", "parameters": {}}

        # --- Voice Output & Personality Phrasings ---
        if any(p in cmd for p in ["change voice", "switch voice", "change your voice", "switch your voice", "female voice", "male voice", "different voice"]):
            v = ""
            for name in ["sonia", "christopher", "guy", "ryan", "jarvis", "ava", "jenny", "neerja", "prabhat", "female", "male"]:
                if name in cmd:
                    v = name
                    break
            return {"name": "change_voice", "parameters": {"voice_name": v or "female"}}

        if any(p in cmd for p in ["list voices", "what voices", "available voices", "which voices"]):
            return {"name": "list_voices", "parameters": {}}

        # --- Destructive Actions Natural Phrasings ---
        # e.g. "wipe the trash", "clean out the recycle bin", "empty the trash can"
        if re.search(r'\b(empty|clean|clear|dump|wipe)\s+(?:out\s+)?(?:the\s+)?(trash|recycle\s+bin|rubbish|bin)\b', cmd):
            return {"name": "power_control", "parameters": {"action": "empty_recycle_bin"}}

        if re.search(r'\b(reboot|restart)\s+(?:my\s+)?(?:computer|pc|machine|system)\b', cmd):
            return {"name": "power_control", "parameters": {"action": "restart"}}

        if re.search(r'\b(shut\s*down|power\s*down|turn\s*off)\s+(?:my\s+)?(?:computer|pc|machine|system)\b', cmd):
            return {"name": "power_control", "parameters": {"action": "shutdown"}}

        return None

    def _resolve_with_slm(self, cmd: str) -> Optional[Dict[str, Any]]:
        """Invokes the local GGUF model with low temperature to produce strict JSON."""
        try:
            tools_summary = ", ".join([t["name"] for t in TOOL_DEFINITIONS])
            prompt = (
                f"<|im_start|>system\n"
                f"You are J.A.R.V.I.S. Intent Classifier. Map the user's speech to one tool from: [{tools_summary}].\n"
                f"Respond ONLY with a valid JSON object matching: {{\"name\": \"<tool_name>\", \"parameters\": {{...}}}} or {{\"name\": \"unknown\"}}.\n"
                f"<|im_end|>\n"
                f"<|im_start|>user\n{cmd}<|im_end|>\n"
                f"<|im_start|>assistant\n"
            )
            output = self.llm(
                prompt,
                max_tokens=64,
                temperature=0.1,
                stop=["<|im_end|>", "\n\n"]
            )
            text = output["choices"][0]["text"].strip()
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                if data.get("name") and data["name"] != "unknown":
                    return data
        except Exception as e:
            print(f"[IntentRouter SLM Error] {e}")
        return None

    def _try_local_ollama(self, cmd: str) -> Optional[Dict[str, Any]]:
        """Queries local Ollama instance on port 11434 if available (with quick health check)."""
        now = time.time()
        # Fast exit if Ollama was checked recently and found offline
        if hasattr(self, '_ollama_checked') and not getattr(self, '_ollama_available', False):
            if now - self._ollama_checked < 30.0:
                return None

        try:
            import urllib.request
            # Fast ping to localhost:11434
            self._ollama_checked = now
            tools_summary = ", ".join([t["name"] for t in TOOL_DEFINITIONS])
            prompt = (
                f"Map this speech to one tool from: [{tools_summary}]. "
                f"Output ONLY JSON: {{\"name\": \"<tool_name>\", \"parameters\": {{...}}}} or {{\"name\": \"unknown\"}}.\n"
                f"Speech: \"{cmd}\""
            )
            payload = json.dumps({
                "model": "qwen2.5:1.5b",
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1}
            }).encode("utf-8")

            req = urllib.request.Request(
                "http://127.0.0.1:11434/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=0.5) as response:
                self._ollama_available = True
                res_data = json.loads(response.read().decode("utf-8"))
                raw_resp = res_data.get("response", "").strip()
                match = re.search(r'\{.*\}', raw_resp, re.DOTALL)
                if match:
                    data = json.loads(match.group(0))
                    if data.get("name") and data["name"] != "unknown":
                        return data
        except Exception:
            self._ollama_available = False
        return None
