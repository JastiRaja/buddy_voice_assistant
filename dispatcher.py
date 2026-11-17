import re
import time
from actions import SystemController
from tts import TextToSpeech
from web_skills import WebSkills
from vision import VisionAssistant
from intent_router import IntentRouter
from config import WAKE_WORDS, REQUIRE_WAKE_WORD, WAKE_TIMEOUT_SECONDS, ASSISTANT_NAME, APP_ALIASES

class CommandDispatcher:
    def __init__(self, controller: SystemController, tts: TextToSpeech, web_skills: WebSkills, vision: VisionAssistant = None, hud=None, require_wake_word: bool = None):
        self.controller = controller
        self.tts = tts
        self.web_skills = web_skills
        self.vision = vision
        self.hud = hud
        self.require_wake_word = require_wake_word
        self.active_until = 0.0
        self.pending_confirmation = None
        self.intent_router = IntentRouter()

    def process(self, text: str) -> bool:
        """
        Parses user speech and executes corresponding system actions, web skills,
        multimodal vision inspection, and automation with strict priority routing.
        """
        raw_text = text.strip()
        # 1. Preprocess & Normalize Wake Words and common phonetic misrecognitions
        clean_text = re.sub(r'\b[jJ]\.?\s*[aA]\.?\s*[rR]\.?\s*[vV]\.?\s*[iI]\.?\s*[sS]\.?\b[\.\,]*', 'jarvis', raw_text)
        clean_text = re.sub(r'\b(travis|javis|jarves|garvis|darvis|charvis|service|harvest)\b', 'jarvis', clean_text, flags=re.IGNORECASE)
        cmd = clean_text.lower().strip()
        print(f"\n[Voice Detected]: \"{raw_text}\"")

        # ---------------- 0. Voice Confirmation Guardrail Check ----------------
        if self.pending_confirmation:
            if time.time() > self.pending_confirmation.get("expires", 0):
                print("[Dispatcher Guardrail] Confirmation request expired.")
                self.pending_confirmation = None
            else:
                affirmative = any(re.search(r'\b' + re.escape(w) + r'\b', cmd) for w in [
                    "yes", "yeah", "confirm", "proceed", "do it", "sure", "affirmative",
                    "yes please", "go ahead", "continue", "yep", "do that"
                ])
                negative = any(re.search(r'\b' + re.escape(w) + r'\b', cmd) for w in [
                    "no", "cancel", "abort", "nevermind", "never mind", "stop",
                    "don't", "dont", "negative", "halt"
                ])
                if affirmative:
                    action_fn = self.pending_confirmation["action_fn"]
                    args = self.pending_confirmation.get("args", ())
                    kwargs = self.pending_confirmation.get("kwargs", {})
                    desc = self.pending_confirmation.get("description", "action")
                    self.pending_confirmation = None
                    self.tts.speak(f"Proceeding to {desc}, sir.")
                    action_fn(*args, **kwargs)
                    self.active_until = time.time() + WAKE_TIMEOUT_SECONDS
                    return True
                elif negative:
                    self.pending_confirmation = None
                    self.tts.speak("Action cancelled, sir.")
                    if self.hud:
                        self.hud.set_state("idle", "Standby // Awaiting Command...")
                    self.active_until = time.time() + WAKE_TIMEOUT_SECONDS
                    return True
                else:
                    desc = self.pending_confirmation.get("description", "action")
                    self.tts.speak(f"Please confirm: say 'Yes' to {desc}, or 'Cancel' to abort.")
                    return True

        # ---------------- 1. Dictation Mode Check ----------------
        if self.controller.dictation_mode:
            if any(stop_cmd in cmd for stop_cmd in ["stop dictation", "exit dictation", "end dictation", "stop typing"]):
                self.controller.dictation_mode = False
                self.tts.speak("Dictation mode deactivated, sir.")
                if self.hud:
                    self.hud.set_state("idle", "Standby // Awaiting Command...")
                return True
            else:
                self.controller.type_text(raw_text + " ")
                return True

        # ---------------- 2. Wake Word & Session Window ----------------
        is_wake_word_detected = False
        sorted_wake_words = sorted(WAKE_WORDS, key=len, reverse=True)
        wake_pattern = r'\b(' + '|'.join(re.escape(w) for w in sorted_wake_words) + r')\b'
        match = re.search(wake_pattern, cmd)

        if match:
            is_wake_word_detected = True
            cmd = re.sub(wake_pattern, '', cmd).strip()
            self.active_until = time.time() + WAKE_TIMEOUT_SECONDS

        is_currently_active = time.time() < self.active_until

        if self.require_wake_word is not None:
            require_wake = self.require_wake_word
        elif self.hud is not None:
            from config import load_user_settings
            require_wake = load_user_settings().get("require_wake_word", True)
        else:
            require_wake = False

        if require_wake and not is_wake_word_detected and not is_currently_active:
            print("[Dispatcher] Ignored: Wake word 'Jarvis' not present.")
            if self.hud:
                self.hud.set_state("idle", "Standby // Awaiting Command...", f"Heard: \"{raw_text}\"")
            return True

        # Strip polite conversational prefixes and punctuation
        cmd = re.sub(r'^(hey|hi|hello|ok|okay|yo|please|can you|could you|would you)\b[\s,]*', '', cmd).strip()
        cmd = re.sub(r'^[,\.\?!:\s]+|[,\.\?!:\s]+$', '', cmd).strip()
        cmd = re.sub(r'^(please|can you|could you|would you)\b[\s,]*', '', cmd).strip()
        cmd = re.sub(r'^[,\.\?!:\s]+|[,\.\?!:\s]+$', '', cmd).strip()

        # If user only called Jarvis/Buddy with no follow-up command
        if not cmd or cmd in ["hey", "hi", "hello", "ok", "okay", "yo", "there"]:
            msg = "At your service, sir. How may I assist you?"
            if self.hud:
                self.hud.set_state("speaking", "J.A.R.V.I.S. is speaking...", msg)
            self.tts.speak(msg)
            self.active_until = time.time() + WAKE_TIMEOUT_SECONDS
            if self.hud:
                self.hud.set_state("listening", "Listening for command...", "Listening for instructions, sir...")
            return True

        print(f"[Command to Execute]: \"{cmd}\"")
        if self.hud:
            self.hud.set_state("speaking", "Executing Command...", f"You: \"{cmd}\"")

        try:
            # Audit logging of every command processed
            if hasattr(self.controller, 'audit') and self.controller.audit:
                self.controller.audit.log(cmd)

            # ---------------- 2.5 Custom Voice Routine Macros ----------------
            if hasattr(self.controller, 'macros') and self.controller.macros and self.controller.macros.get_macro(cmd):
                self.controller.macros.execute_macro(cmd, self.controller, self.tts)
                self.active_until = time.time() + WAKE_TIMEOUT_SECONDS
                return True

            # ---------------- 3. Exit, Standby & Silence Controls ----------------
            if cmd in ["exit", "quit", "power down", "shut down assistant", "quit assistant", "close assistant", "stop assistant", "goodbye"]:
                self.tts.speak("Powering down systems, sir. Have a pleasant day.")
                self.active_until = 0.0
                if self.hud and hasattr(self.hud, 'root') and self.hud.root:
                    self.hud.root.after(1200, self.hud._exit_app)
                return False

            elif cmd in ["stop listening", "go to sleep", "standby", "cancel", "that will be all", "that is all", "nevermind", "never mind", "dismissed"]:
                self.tts.speak("Standing by, sir.")
                self.active_until = 0.0
                if self.hud:
                    self.hud.set_state("idle", "Standby // Awaiting Command...")
                return True

            elif cmd in ["stop", "pause", "halt"] or any(trigger in cmd for trigger in ["stop speaking", "stop reading", "be quiet", "shut up", "silence", "stop talking", "mute speech"]):
                self.tts.stop()
                if self.hud:
                    self.hud.set_state("idle", "Standby // Awaiting Command...")
                return True

            # ---------------- 4. Conversational Greetings, Status & Politeness ----------------
            elif any(trigger in cmd for trigger in ["are you there", "are you awake", "you there", "are you listening", "can you hear me"]):
                self.tts.speak("For you, sir, always. I am right here listening.")

            elif any(trigger in cmd for trigger in ["good morning", "morning jarvis", "morning buddy"]):
                self.tts.speak("Good morning, sir. I hope you have a productive day ahead. All systems are operational.")

            elif any(trigger in cmd for trigger in ["good afternoon"]):
                self.tts.speak("Good afternoon, sir. All neural subsystems operational and ready for your command.")

            elif any(trigger in cmd for trigger in ["good evening"]):
                self.tts.speak("Good evening, sir. I am at your service.")

            elif any(trigger in cmd for trigger in ["good night", "goodnight", "have a good night", "night jarvis", "night buddy"]):
                self.tts.speak("Good night, sir. Rest well. I will remain on standby.")

            elif any(trigger in cmd for trigger in ["have a good day", "have a nice day", "have a great day"]):
                self.tts.speak("Thank you, sir. Wishing you a wonderful and productive day as well.")

            elif any(trigger in cmd for trigger in ["how are you", "how are you doing", "how is it going", "how's it going", "how are things", "how do you do", "how's everything", "hows everything"]):
                self.tts.speak("All core systems and neural models are operating at peak efficiency, sir. How are you doing today?")

            elif any(trigger in cmd for trigger in ["what's up", "whats up", "what is up", "sup", "what's new", "whats new"]):
                self.tts.speak("All systems running smoothly, sir. Monitoring desktop status and ready for your instructions. What can I do for you?")

            elif any(trigger in cmd for trigger in ["greetings", "hello there", "hey there", "good to see you", "nice to meet you", "pleased to meet you"]):
                self.tts.speak("Greetings, sir. It is a pleasure to assist you today. How may I be of service?")

            elif any(trigger in cmd for trigger in ["i am back", "i'm back", "i have returned"]):
                self.tts.speak("Welcome back, sir. Ready when you are.")

            elif any(trigger in cmd for trigger in ["talk to you later", "see you later", "catch you later", "see ya", "talk later"]):
                self.tts.speak("Until next time, sir. Standing by whenever you need me.")

            elif any(trigger in cmd for trigger in ["who are you", "what is your name", "what are you", "tell me about yourself"]):
                self.tts.speak("I am J.A.R.V.I.S., your Just A Rather Very Intelligent System running 100 percent locally on your machine.")

            elif any(trigger in cmd for trigger in ["thank you", "thanks", "thanks a lot", "thank you so much", "appreciate it"]):
                self.tts.speak("My pleasure, sir. Always a privilege to assist.")

            elif re.search(r'\b(tell me a joke|tell a joke|say a joke|make me laugh)\b', cmd):
                jokes = [
                    "Why do programmers prefer dark mode? Because light attracts bugs, sir.",
                    "There are 10 types of people in the world: those who understand binary, and those who don't.",
                    "Why was the JavaScript developer sad? Because they didn't Node how to Express themselves."
                ]
                import random
                self.tts.speak(random.choice(jokes))

            # ---------------- 5. Settings Panel ----------------
            elif any(trigger in cmd for trigger in ["open settings", "show settings", "configure settings", "settings panel"]):
                if self.hud:
                    self.hud._open_settings()
                self.tts.speak("Opening configuration panel, sir.")

            # ---------------- 5.1 Voice Personality & Output Controls ----------------
            elif any(trigger in cmd for trigger in ["list voices", "what voices do you have", "show voices", "available voices", "voice options", "which voices do you have"]):
                self.controller.list_voices()

            elif (
                cmd.startswith(("change voice to ", "switch voice to ", "set voice to ", "change voice ", "switch voice ", "change the voice to ", "switch the voice to ")) or
                re.search(r'\b(switch|change|set)\s+(?:the\s+)?voice\s+(?:to\s+)?(.+)', cmd) or
                re.search(r'\b(switch|change|use)\s+(?:to\s+)?(?:a\s+)?(female|male|woman|man)\s+voice\b', cmd)
            ):
                voice_target = ""
                m = re.search(r'\b(?:switch|change|set)\s+(?:the\s+)?voice\s+(?:to\s+)?(.+)', cmd)
                if m:
                    voice_target = m.group(1).strip()
                elif "female" in cmd or "woman" in cmd:
                    voice_target = "female"
                elif "male" in cmd or "man" in cmd:
                    voice_target = "male"
                else:
                    voice_target = re.sub(r'^(change voice to|switch voice to|set voice to|change voice|switch voice|change the voice to|switch the voice to)\s*', '', cmd).strip()

                if voice_target:
                    self.controller.change_voice(voice_target)
                else:
                    self.controller.list_voices()

            # ---------------- 6. YouTube & Web Searches (Evaluated BEFORE media toggle & folders!) ----------------
            elif (
                re.search(r'^(?:play|search|find|open)\s+(.+?)\s+(?:on|in)\s+youtube$', cmd) or
                re.search(r'^(?:search\s+youtube\s+for|search\s+on\s+youtube\s+for|youtube\s+search\s+for)\s+(.+)$', cmd) or
                re.search(r'^youtube\s+(?:play\s+|search\s+)?(.+)$', cmd)
            ):
                yt_match = (
                    re.search(r'^(?:play|search|find|open)\s+(.+?)\s+(?:on|in)\s+youtube$', cmd) or
                    re.search(r'^(?:search\s+youtube\s+for|search\s+on\s+youtube\s+for|youtube\s+search\s+for)\s+(.+)$', cmd) or
                    re.search(r'^youtube\s+(?:play\s+|search\s+)?(.+)$', cmd)
                )
                query = yt_match.group(1).strip()
                query = re.sub(r'\b(video|song|track|clip)\b', '', query).strip()
                self.controller.search_youtube(query)

            # Direct "play <something>" when not a generic media toggle word
            elif cmd.startswith("play ") and not re.fullmatch(r'play(\s+(music|media|playback|song|video))?', cmd):
                song_query = re.sub(r'^play\s+', '', cmd).strip()
                if getattr(self.controller, 'strict_offline_mode', False) or "local" in cmd or "offline" in cmd:
                    self.controller.play_local_media(song_query)
                else:
                    self.controller.search_youtube(song_query)

            # Local Offline Media Player
            elif any(trigger in cmd for trigger in ["play local music", "play offline music", "play local song", "play local track", "offline music"]):
                query = re.sub(r'^(play local music|play offline music|play local song|play local track|offline music)\s*', '', cmd).strip()
                self.controller.play_local_media(query)

            elif cmd.startswith(("search google for ", "search the web for ", "search web for ", "search for ", "google ")):
                query = re.sub(r'^(search google for|search the web for|search web for|search for|google)\s+', '', cmd).strip()
                self.controller.search_web(query)

            elif cmd.startswith("search ") and not cmd.startswith("search file"):
                query = re.sub(r'^search\s+', '', cmd).strip()
                self.controller.search_web(query)

            # ---------------- 7. Media & Music Controls (Strict Word-Bounded) ----------------
            elif any(trigger in cmd for trigger in ["next song", "next track", "skip song", "skip track"]):
                self.controller.media_next()
            elif any(trigger in cmd for trigger in ["previous song", "previous track", "last song"]):
                self.controller.media_prev()
            elif re.fullmatch(r'(play|pause|resume)(\s+(music|media|playback|song|video))?', cmd) or cmd in [
                "play music", "pause music", "pause video", "resume video", "toggle music", "toggle playback", "stop music"
            ]:
                self.controller.media_toggle()

            # ---------------- 8. Volume, Mute, Screenshot & Brightness (Word-Bounded) ----------------
            elif re.search(r'\b(volume up|increase volume|turn it up|louder)\b', cmd):
                self.controller.volume_control("up")
            elif re.search(r'\b(volume down|decrease volume|turn it down|lower volume|softer)\b', cmd):
                self.controller.volume_control("down")
            elif re.search(r'\b(mute|unmute)\b', cmd):
                self.controller.volume_control("mute")
            elif re.search(r'\b(screenshot|capture screen|take a screenshot)\b', cmd):
                self.controller.take_screenshot()
            elif "brightness" in cmd:
                if "up" in cmd or "increase" in cmd or "higher" in cmd:
                    self.controller.change_brightness(15)
                elif "down" in cmd or "decrease" in cmd or "lower" in cmd:
                    self.controller.change_brightness(-15)
                else:
                    nums = re.findall(r'\d+', cmd)
                    if nums:
                        self.controller.set_brightness(int(nums[0]))
                    else:
                        self.controller.change_brightness(10)

            # ---------------- 9. Screen Vision & Telemetry ----------------
            elif any(trigger in cmd for trigger in ["clear screen", "clean screen", "hide all", "hide windows", "minimize windows"]):
                self.controller.minimize_all()
            elif any(trigger in cmd for trigger in ["share screen", "screen share"]):
                self.tts.speak("Screen visualizer active, sir.")
                if self.vision:
                    self.vision.analyze_screen()
            elif re.search(r'\b(what(\'s| is)?\s+(on|in)\s+(my\s+|the\s+)?(screen|display|monitor)|visualize screen|read\s+(my\s+|the\s+)?screen|describe\s+(my\s+|the\s+)?screen|analyze\s+(my\s+|the\s+)?screen|inspect\s+(my\s+|the\s+)?screen|explain this screen|what am i looking at|what do you see|what can you see|can you see my screen|look at (my\s+)?screen|look at this|reading screens?)\b', cmd):
                if self.vision:
                    self.vision.analyze_screen(cmd)
                else:
                    self.tts.speak("Vision module is initializing, sir.")
            elif re.search(r'\b(explain this error|what is this error|debug error|debug screen|check screen for errors)\b', cmd):
                if self.vision:
                    self.vision.explain_screen_error()
                else:
                    self.tts.speak("Vision module is initializing, sir.")
            elif any(trigger in cmd for trigger in ["copy text from screen", "extract text from screen", "ocr screen", "extract screen text", "grab text from screen"]):
                if self.vision:
                    self.vision.copy_screen_text()
                else:
                    self.tts.speak("Vision module is initializing, sir.")

            # ---------------- 9.5 Gmail & Email Voice Assistant ----------------
            elif re.search(r'\b(read|check|summarize)\s+(my\s+)?(emails?|gmail|inbox)\b', cmd) or \
                 cmd in ["read gmail", "check gmail", "check emails", "read emails", "check my email", "read my emails"]:
                telemetry = self.vision.get_screen_telemetry() if self.vision else {}
                title = telemetry.get("active_title", "").lower()
                if any(k in title for k in ["gmail", "inbox", "mail", "outlook"]):
                    self.tts.speak("Inspecting your open email inbox on screen, sir.")
                    if self.vision:
                        self.vision.analyze_screen("Inspect this email inbox or message on screen. Summarize unread emails, senders, and subjects concisely in 2 sentences.")
                else:
                    self.tts.speak("Opening Gmail for you now, sir. Once loaded, say 'read screen' and I will read your emails.")
                    self.controller.open_application("gmail")

            # ---------------- 10. Read Aloud & Text Selection ----------------
            elif any(trigger in cmd for trigger in [
                "read aloud", "read out loud", "read allowed", "reed aloud", "read a loud",
                "read selected text", "read selection", "read highlighted text", "read highlighted", "read the selection",
                "read this text", "read this out", "read this", "read what is selected", "read what's selected",
                "speak selected", "speak this text", "speak selection", "speak this",
                "read aloud this", "read aloud selected", "read aloud the selection", "read aloud the text",
                "read it out", "read it aloud", "read it", "speak it out", "read out"
            ]):
                self.controller.read_aloud(force_clipboard=False)

            # ---------------- 10.2. Clipboard History Manager ----------------
            elif any(trigger in cmd for trigger in ["read clipboard history", "clipboard history", "read last copied", "read copied items", "read my copied items"]):
                self.controller.read_clipboard_history(3)
            elif re.search(r'paste\s+(?:item\s+)?(?:number\s+)?(\d+)', cmd):
                num = int(re.search(r'paste\s+(?:item\s+)?(?:number\s+)?(\d+)', cmd).group(1))
                self.controller.paste_clipboard_history_item(num)
            elif "paste last copied" in cmd or "paste previous item" in cmd:
                self.controller.paste_clipboard_history_item(1)

            elif any(trigger in cmd for trigger in [
                "read clipboard", "read copied text", "read what i copied", "read what's copied",
                "read the clipboard", "read from clipboard", "speak clipboard"
            ]):
                self.controller.read_aloud(force_clipboard=True)

            # ---------------- 10.1. Smart Text Rewriting, Grammar & Summarization ----------------
            elif any(trigger in cmd for trigger in ["summarize this", "summarize selection", "summarize selected text", "summarize highlighted text"]):
                self.controller.summarize_selection()
            elif any(trigger in cmd for trigger in ["fix grammar", "fix spelling", "fix this grammar", "correct grammar", "fix punctuation"]):
                self.controller.fix_grammar_selection()
            elif any(trigger in cmd for trigger in ["make professional", "make this professional", "make formal", "make this formal", "professional tone", "rewrite professionally"]):
                self.controller.make_professional_selection()

            # ---------------- 10.3. Offline Document RAG ----------------
            elif any(trigger in cmd for trigger in ["summarize latest pdf", "summarize my latest pdf", "summarize pdf", "summarize document", "summarize my document"]):
                self.controller.summarize_document_rag("latest pdf")
            elif cmd.startswith(("search documents for ", "search document for ", "query documents ")):
                rag_q = re.sub(r'^(search documents for|search document for|query documents)\s+', '', cmd).strip()
                self.controller.summarize_document_rag(rag_q)

            # ---------------- 11. Time, Date & System Diagnostics ----------------
            elif any(trigger in cmd for trigger in ["morning briefing", "daily briefing", "what's on my schedule today", "what is on my schedule today", "today's briefing", "daily schedule", "today's schedule"]):
                self.controller.give_morning_briefing()

            # ---------------- 11.1. Network Kill-Switch & Audit Transparency ----------------
            elif any(trigger in cmd for trigger in ["enable network kill switch", "activate network kill switch", "turn on network kill switch", "block network", "enable kill switch", "activate kill switch"]):
                self.controller.toggle_network_killswitch(True)
            elif any(trigger in cmd for trigger in ["disable network kill switch", "deactivate network kill switch", "turn off network kill switch", "unblock network", "disable kill switch", "deactivate kill switch"]):
                self.controller.toggle_network_killswitch(False)
            elif any(trigger in cmd for trigger in ["network kill switch", "toggle network kill switch", "kill switch"]):
                self.controller.toggle_network_killswitch(None)
            elif any(trigger in cmd for trigger in ["read audit log", "audit log summary", "read audit", "audit log", "show audit log"]):
                self.controller.read_audit_log()

            elif re.search(r'\b(what(\'s|\s+is)?\s+(the\s+)?time|what\s+time|tell\s+(me\s+)?the\s+time|current\s+time|time\s+now)\b', cmd) or cmd in ["time", "the time"]:
                self.controller.tell_time()
            elif re.search(r'\b(what(\'s|\s+is)?\s+(the\s+|today\'s\s+)?(date|day)|what\s+(date|day)|tell\s+(me\s+)?the\s+(date|day)|today\'s\s+date|todays\s+date|current\s+date)\b', cmd) or cmd in ["date", "today's date", "todays date", "day", "today's day"]:
                self.controller.tell_date()
            elif re.search(r'\b(audio devices?|microphones?|speakers?|sound devices?|audio hardware)\b', cmd) or any(t in cmd for t in ["list audio", "show audio", "audio devices", "check microphone", "check speaker", "connected audio"]):
                self.controller.list_audio_devices()
            elif re.search(r'\b(system status|current status|pc status|diagnostics|status report)\b', cmd):
                self.controller.run_diagnostics()
            elif re.search(r'\b(battery|battery status|power level)\b', cmd):
                self.controller.get_battery_status()
            elif any(trigger in cmd for trigger in ["cpu usage", "ram usage", "memory usage", "system performance"]):
                self.controller.get_system_stats()
            elif re.search(r'\b(list|show|what|tell me|display|read)\b.*\b(apps|applications|software|programs|installed|app notes|app knowledge)\b', cmd) or cmd in ["app notes", "apps", "list apps"]:
                self.controller.list_installed_apps()

            # ---------------- 12. Explicit Folders & Drives Navigation ----------------
            elif cmd in ["open this pc", "this pc", "open my computer", "my computer"]:
                self.controller.open_this_pc()

            # Direct Drive requests (e.g. "open C drive", "open D drive")
            elif re.search(r'^(?:open|show|access)?\s*(?:the\s+)?([a-z]|see|sea|sito|dee)[-\s]*(?:drive|disk|drow|tray)$', cmd) or \
                 re.search(r'^(?:open|show|access)?\s*(?:drive|disk)\s*([a-z]|see|sea|sito|dee)$', cmd) or \
                 re.search(r'^(?:open\s+)?([a-z]):\\?$', cmd):
                drive_match = re.search(r'^(?:open|show|access)?\s*(?:the\s+)?([a-z]|see|sea|sito|dee)[-\s]*(?:drive|disk|drow|tray)$', cmd) or \
                              re.search(r'^(?:open|show|access)?\s*(?:drive|disk)\s*([a-z]|see|sea|sito|dee)$', cmd) or \
                              re.search(r'^(?:open\s+)?([a-z]):\\?$', cmd)
                if drive_match:
                    raw_letter = drive_match.group(1).upper()
                    letter = "C" if raw_letter in ["SEE", "SEA", "SITO", "C"] else ("D" if raw_letter in ["DEE", "D"] else raw_letter)
                    self.controller.open_drive(letter)

            # Specific folder requests requiring explicit intent verbs
            elif re.search(r'^(?:open|show|go to|navigate to|access|view)\s+(?:the\s+)?(downloads?|documents?|desktop|pictures?|photos?|videos?|music|projects?|users?)(?:\s+folder)?$', cmd) or \
                 cmd in ["open downloads", "open documents", "open desktop", "open pictures", "open videos", "open music"]:
                if cmd in ["show desktop", "minimize all", "minimize windows", "hide windows"]:
                    self.controller.minimize_all()
                else:
                    self.controller.open_folder(cmd)

            # Explicit folder and directory opening (e.g. "open folder camera roll", "open directory screenshots")
            elif cmd.startswith(("open folder ", "open directory ", "show folder ", "navigate to folder ", "go to folder ", "view folder ")):
                target_f = re.sub(r'^(open|show|navigate to|go to|view)\s+(?:the\s+)?(?:folder|directory)\s+', '', cmd).strip()
                self.controller.open_folder(target_f)

            # How many folders / files / items in directory query (e.g. "how many folders are there in pictures folder")
            elif re.search(r'\b(how many|count)\s+(folders?|subfolders?|directories|dirs|files?|images?|photos?|items?)\b', cmd) or \
                 re.search(r'\bwhat\s+(folders?|subfolders?|directories|dirs)\s+(are\s+)?(in|inside|on|there)\b', cmd):
                self.controller.count_folder_contents(cmd)

            # Latest Files & List Files
            elif any(trigger in cmd for trigger in ["open latest download", "open latest file", "open the latest file", "open newest file"]):
                self.controller.open_latest_file("downloads")
            elif any(trigger in cmd for trigger in [
                "what files", "list files", "list the files", "list to the files", "relish to the files",
                "show files", "files in", "items in", "files were this folder", "files in this folder",
                "files in here", "show contents", "list contents", "view files", "check files"
            ]) or re.search(r'\b(list|show|relish|what)\s+(?:all\s+)?(?:the\s+)?(?:to\s+the\s+)?(?:files|items|contents)\b', cmd):
                folder = "current"
                for f in ["c drive", "d drive", "c:", "d:", "documents", "desktop", "pictures", "videos", "projects", "music", "downloads"]:
                    if f in cmd:
                        folder = f.replace(" drive", "")
                        break
                self.controller.list_files_in_folder(folder)
            elif cmd.startswith(("find file ", "search file ", "open file ", "locate file ")):
                filename = re.sub(r'^(find file|search file|open file|locate file)\s+', '', cmd).strip()
                self.controller.find_and_open_file(filename)

            # Voice-Driven File Organization
            elif any(trigger in cmd for trigger in ["organize downloads", "clean up downloads", "organize my downloads", "organize folder", "clean folder", "sort downloads", "clean downloads"]):
                target_f = "downloads"
                for cand in ["documents", "desktop", "pictures", "projects"]:
                    if cand in cmd:
                        target_f = cand
                        break
                self.controller.organize_folder(target_f)

            # ---------------- 13. Window Management & Workspace Profiles ----------------
            elif any(trigger in cmd for trigger in ["coding mode", "study mode", "relax mode", "workspace profile", "coding profile", "study profile", "work mode", "work profile"]):
                self.controller.launch_workspace_profile(cmd)
            elif cmd.startswith(("switch to ", "bring up ")):
                target_app = re.sub(r'^(switch to|bring up)\s+', '', cmd).strip()
                self.controller.switch_to_window(target_app)
            elif "snap left" in cmd:
                self.controller.snap_window("left")
            elif "snap right" in cmd:
                self.controller.snap_window("right")
            elif "maximize" in cmd:
                self.controller.snap_window("maximize")
            elif "minimize" in cmd and not cmd.startswith("minimize all"):
                self.controller.snap_window("minimize")
            elif "close tab" in cmd:
                self.controller.close_tab()
            elif (
                cmd in [
                    "close window", "close this window", "close current window", "close the window",
                    "close open window", "close the open window", "close active window", "close this",
                    "close foreground window", "close the entire application", "close entire application"
                ] or
                re.search(r'\b(close|exit|shut)\s+(?:the\s+)?(?:open\s+|active\s+|current\s+|this\s+)?window\b', cmd) or
                re.search(r'\b(close|exit)\s+(?:the\s+)?entire\s+application\b', cmd)
            ):
                self.controller.close_window()
            elif "new tab" in cmd:
                self.controller.new_tab()
            elif "switch tab" in cmd:
                self.controller.switch_tab()
            elif "browser downloads" in cmd or "download history" in cmd:
                self.controller.browser_action("downloads")
            elif re.search(r'\b(refresh page|reload page|refresh tab)\b', cmd) or cmd == "refresh":
                self.controller.browser_action("refresh")

            # ---------------- 13.1. Keystroke Edit Controls (Strict/Bounded) ----------------
            elif re.fullmatch(r'(copy|paste|undo|select all|cut)(\s+(this|that|selection|text|all))?', cmd) or cmd in ["copy", "paste", "undo", "select all"]:
                act = "copy" if "copy" in cmd else ("paste" if "paste" in cmd else ("undo" if "undo" in cmd else "select_all"))
                self.controller.edit_action(act)
            elif "save file" in cmd:
                self.controller.edit_action("save")

            # ---------------- 13.2. Scrolling, Mouse & Keystrokes ----------------
            elif any(trigger in cmd for trigger in ["scroll to top", "scroll to the top", "scroll top", "go to top"]):
                self.controller.scroll_page("top")
            elif any(trigger in cmd for trigger in ["scroll to bottom", "scroll to the bottom", "scroll bottom", "go to bottom"]):
                self.controller.scroll_page("bottom")
            elif any(trigger in cmd for trigger in ["page down", "scroll down page"]):
                self.controller.scroll_page("page_down")
            elif any(trigger in cmd for trigger in ["page up", "scroll up page"]):
                self.controller.scroll_page("page_up")
            elif "scroll down" in cmd:
                nums = re.findall(r'\d+', cmd)
                mult = int(nums[0]) if nums else (3 if "more" in cmd or "fast" in cmd or "lot" in cmd else 1)
                self.controller.scroll_page("down", amount=mult)
            elif "scroll up" in cmd:
                nums = re.findall(r'\d+', cmd)
                mult = int(nums[0]) if nums else (3 if "more" in cmd or "fast" in cmd or "lot" in cmd else 1)
                self.controller.scroll_page("up", amount=mult)
            elif cmd in ["scroll", "scroll page"]:
                self.controller.scroll_page("down", amount=1)

            # Mouse Controls
            elif "click center" in cmd or "center click" in cmd:
                self.controller.mouse_click("center")
            elif "double click" in cmd:
                self.controller.mouse_click("double")
            elif "right click" in cmd:
                self.controller.mouse_click("right")
            elif any(trigger in cmd for trigger in ["left click", "single click", "click here", "mouse click"]) or cmd == "click":
                self.controller.mouse_click("left")
            elif cmd.startswith(("move mouse ", "move cursor ")):
                direction = "down"
                for d in ["up", "down", "left", "right"]:
                    if d in cmd:
                        direction = d
                        break
                self.controller.move_mouse(direction)

            # Keystrokes
            elif cmd.startswith(("press ", "hit ")):
                key_token = re.sub(r'^(press|hit)\s+', '', cmd).strip()
                self.controller.press_key(key_token)
            elif cmd.startswith("type "):
                text_to_type = re.sub(r'^type\s+', '', raw_text, flags=re.IGNORECASE).strip()
                self.controller.type_text(text_to_type)

            # ---------------- 14. Timers & Reminders ----------------
            elif "timer" in cmd:
                if any(trigger in cmd for trigger in ["cancel timer", "cancel timers", "stop timer"]):
                    self.controller.cancel_all_timers()
                elif any(trigger in cmd for trigger in ["list timer", "active timer", "check timer"]):
                    self.controller.list_active_timers()
                else:
                    mins, secs = 0, 0
                    min_match = re.search(r'(\d+)\s*(minute|min)', cmd)
                    sec_match = re.search(r'(\d+)\s*(second|sec)', cmd)
                    if min_match:
                        mins = int(min_match.group(1))
                    if sec_match:
                        secs = int(sec_match.group(1))
                    total_secs = (mins * 60) + secs
                    if total_secs == 0:
                        nums = re.findall(r'\d+', cmd)
                        if nums:
                            total_secs = int(nums[0]) * 60

                    label = "Timer"
                    for_match = re.search(r'(?:for|to)\s+([a-zA-Z\s]+)', cmd)
                    if for_match and not any(unit in for_match.group(1) for unit in ["min", "sec"]):
                        label = for_match.group(1).strip().title()

                    if total_secs > 0:
                        self.controller.set_timer(total_secs, label)
                    else:
                        self.tts.speak("How many minutes should I set the timer for, sir?")

            # ---------------- 15. Dictation & Notes ----------------
            elif any(trigger in cmd for trigger in ["start dictation", "dictation mode on", "enable dictation"]):
                self.controller.dictation_mode = True
                self.tts.speak("Dictation mode active. Everything you say will be typed into your focused window. Say 'stop dictation' when finished.")
                if self.hud:
                    self.hud.set_state("listening", "Dictation Mode Active", "Say 'stop dictation' to exit...")
            elif cmd.startswith(("take note", "save note", "write note")):
                note = re.sub(r'^(take note|save note|write note|note that|note)\s+', '', cmd).strip()
                self.controller.take_note(note)
            elif any(trigger in cmd for trigger in ["read notes", "read my notes", "what are my notes"]):
                self.controller.read_notes()

            # ---------------- 16. Power & Lock Controls ----------------
            elif any(trigger in cmd for trigger in ["lock pc", "lock computer", "lock screen"]):
                self.controller.lock_pc()
            elif "shut down in" in cmd or "shutdown in" in cmd:
                nums = re.findall(r'\d+', cmd)
                minutes = int(nums[0]) if nums else 10
                self.controller.schedule_shutdown(minutes)
            elif "cancel shutdown" in cmd or "abort shutdown" in cmd:
                self.controller.cancel_shutdown()
            elif any(trigger in cmd for trigger in ["restart pc", "restart computer", "reboot pc"]):
                self.request_confirmation("restart your computer", self.controller.restart_pc)
            elif any(trigger in cmd for trigger in ["sleep pc", "sleep computer"]):
                self.controller.sleep_pc()
            elif any(trigger in cmd for trigger in ["empty recycle bin", "clean recycle bin", "clear recycle bin"]):
                self.request_confirmation("empty the Windows Recycle Bin", self.controller.empty_recycle_bin)

            # ---------------- 17. Application Launch & Close ----------------
            elif cmd.startswith(("open ", "launch ", "start ", "go to ", "navigate to ", "access ")):
                target = re.sub(r'^(open|launch|start|go to|navigate to|access)\s+', '', cmd).strip()
                self.controller.open_application(target)
            elif cmd.startswith(("close ", "terminate ", "kill ", "quit ", "exit ")):
                app = re.sub(r'^(close|terminate|kill|quit|exit)\s+', '', cmd).strip()
                if app in ["the open window", "open window", "window", "this window", "the window", "active window", "current window", "entire application", "the entire application", "entire app"]:
                    self.controller.close_window()
                else:
                    self.controller.close_application(app)

            # ---------------- 18. Live Skills (Weather, News, Math) ----------------
            elif re.search(r'\b(weather|temperature|forecast)\b', cmd):
                city = re.sub(r'.*\b(in|for|at)\s+', '', cmd).strip()
                city = re.sub(r'(weather|forecast|temperature|what is the|tell me the|how is the)', '', city).strip()
                self.web_skills.get_weather(city)
            elif re.search(r'\b(news|headlines|latest news)\b', cmd):
                self.web_skills.get_news_headlines()
            elif (
                cmd.startswith(("calculate ", "convert ")) or
                re.search(r'^(what is|how much is|how many)\s+[\d\(\)\.\s\+\-\*\/x]+$', cmd) or
                re.search(r'^\d+\s*(plus|\+|\-|minus|times|\*|divided by|/|percent of|%)\s*\d+$', cmd) or
                re.search(r'^(square root of|sqrt of|log of|sine of|cosine of)\s+[\d\.]+', cmd) or
                re.search(r'\b(in|to|into)\s+(celsius|fahrenheit|kelvin|miles|km|kilometers|meters|feet|inches|pounds|kg|rupees|dollars|euros|gigabytes|megabytes)\b', cmd)
            ):
                self.web_skills.calculate(cmd)

            # ---------------- 19. Informational & Conversational Questions (AI / Q&A) ----------------
            elif re.search(r'^(who is|who was|what is|what was|why is|why are|why do|why does|how does|how do|how can|how to|where is|where are|tell me about|explain|can you explain)\b', cmd) or "wikipedia" in cmd:
                self.web_skills.answer_question(cmd)

            # ---------------- 20. Single-word / Clean App Aliases (Exact match only) ----------------
            elif cmd in APP_ALIASES or cmd in self.controller.installed_apps:
                self.controller.open_application(cmd)

            # ---------------- 21. Safe Fallback Intent (Tier 2 Local SLM & Semantic Router) ----------------
            else:
                # Do NOT run fuzzy search on full conversational sentences!
                # If command is 1-2 words, check if it was a standalone app request
                words = cmd.split()
                if len(words) <= 2:
                    resolved_kind, _ = self.controller._resolve_app_name(cmd)
                    if resolved_kind in ["app_file", "folder", "drive", "url"]:
                        self.controller.open_application(cmd)
                        self.active_until = time.time() + WAKE_TIMEOUT_SECONDS
                        return True

                # Two-Tier Local Intent Router
                intent_res = self.intent_router.resolve(cmd)
                if intent_res:
                    print(f"[Tier 2 Intent Resolved]: {intent_res}")
                    handled = self._execute_resolved_intent(intent_res)
                    if handled:
                        self.active_until = time.time() + WAKE_TIMEOUT_SECONDS
                        return True

                # Check if query is asking about screen or visual elements
                if any(w in cmd for w in ["screen", "display", "monitor", "what do you see", "can you see", "on my screen", "reading screen"]):
                    if self.vision:
                        self.vision.analyze_screen(cmd)
                        self.active_until = time.time() + WAKE_TIMEOUT_SECONDS
                        return True

                # If Gemini API key is configured and online, answer via Gemini AI!
                from config import load_user_settings
                settings = load_user_settings()
                api_key = settings.get("gemini_api_key", "").strip() or os.environ.get("GEMINI_API_KEY", "").strip() or os.environ.get("GOOGLE_API_KEY", "").strip()
                if api_key and not self.controller.strict_offline_mode:
                    print(f"[Dispatcher] Routing unhandled conversational query to Gemini AI: '{cmd}'")
                    self.web_skills.answer_question(cmd)
                    self.active_until = time.time() + WAKE_TIMEOUT_SECONDS
                    return True

                print(f"[Dispatcher] No specific rule matched for: '{cmd}'")
                if self.hud:
                    self.hud.set_state("idle", "Standby // Awaiting Command...", f"Unrecognized: \"{cmd}\"")
                # Offer a friendly conversational guidance response
                self.tts.speak(f"I am not sure how to assist with '{cmd}', sir.")

            # Extend active hands-free session on recognized commands
            self.active_until = time.time() + WAKE_TIMEOUT_SECONDS
            if self.hud and self.hud.current_state not in ["speaking"]:
                self.hud.set_state("idle", "Continuous Session Active", "Listening for your next command...")

        except Exception as e:
            print(f"[Dispatcher Execution Error] {e}")
            if self.hud:
                self.hud.set_state("idle", "Standby // Awaiting Command...", f"Error: {e}")

        return True

    def request_confirmation(self, description: str, action_fn, *args, **kwargs):
        """Arm multi-turn voice confirmation guardrail for destructive actions."""
        self.pending_confirmation = {
            "description": description,
            "action_fn": action_fn,
            "args": args,
            "kwargs": kwargs,
            "expires": time.time() + 20.0
        }
        msg = f"Are you sure you want to {description}, sir?"
        print(f"[Guardrail Triggered]: {msg}")
        if self.hud:
            self.hud.set_state("listening", "Confirmation Required", f"Say 'Yes' to {description}, or 'Cancel'")
        self.tts.speak(msg)

    def _execute_resolved_intent(self, intent_res: dict) -> bool:
        """Executes tool action resolved by Tier 2 Intent Router."""
        name = intent_res.get("name")
        params = intent_res.get("parameters", {})
        is_destructive = intent_res.get("is_destructive", False)
        desc = intent_res.get("description", "execute this action")

        if is_destructive:
            if name == "power_control":
                act = params.get("action")
                if act == "empty_recycle_bin":
                    self.request_confirmation("empty the Windows Recycle Bin", self.controller.empty_recycle_bin)
                    return True
                elif act == "restart":
                    self.request_confirmation("restart your computer", self.controller.restart_pc)
                    return True
                elif act == "shutdown":
                    delay = int(params.get("delay_minutes", 0))
                    self.request_confirmation("shut down your computer", self.controller.schedule_shutdown, delay)
                    return True

        # Non-destructive / Standard Actions
        if name == "close_app":
            target = params.get("target", "")
            if target in ["open", "window", "this window", "the window", "open window", "the open window", "active window", "current window", "entire application", "the entire application", "entire app"]:
                self.controller.close_window()
                return True
            if target:
                self.controller.close_application(target)
                return True
        elif name == "open_app":
            target = params.get("target", "")
            if target:
                self.controller.open_application(target)
                return True
        elif name == "switch_window":
            target = params.get("target", "")
            if target:
                self.controller.switch_to_window(target)
                return True
        elif name == "change_brightness":
            direction = params.get("direction", "set")
            amount = int(params.get("amount", 15))
            if direction == "down":
                self.controller.change_brightness(-amount)
            elif direction == "up":
                self.controller.change_brightness(amount)
            else:
                self.controller.set_brightness(amount)
            return True
        elif name == "volume_control":
            direction = params.get("direction", "up")
            self.controller.volume_control(direction)
            return True
        elif name == "media_control":
            action = params.get("action", "toggle")
            if action in ["play", "pause", "toggle"]:
                self.controller.media_toggle()
            elif action == "next":
                self.controller.media_next()
            elif action == "prev":
                self.controller.media_prev()
            return True
        elif name == "window_management":
            action = params.get("action", "minimize_all")
            if action == "minimize_all":
                self.controller.minimize_all()
            elif action in ["snap_left", "snap_right", "maximize", "minimize"]:
                self.controller.snap_window(action.replace("snap_", ""))
            elif action == "close_window":
                self.controller.close_window()
            return True
        elif name == "list_files":
            folder = params.get("folder", "current")
            self.controller.list_files_in_folder(folder)
            return True
        elif name == "count_folder_contents":
            query = params.get("query", "pictures")
            self.controller.count_folder_contents(query)
            return True
        elif name == "browser_action":
            action = params.get("action", "refresh")
            if action == "new_tab":
                self.controller.new_tab()
            elif action == "close_tab":
                self.controller.close_tab()
            elif action == "switch_tab":
                self.controller.switch_tab()
            else:
                self.controller.browser_action(action)
            return True
        elif name == "system_diagnostics":
            query = params.get("query", "status")
            if query == "battery":
                self.controller.get_battery_status()
            elif query == "status":
                self.controller.run_diagnostics()
            elif query in ["cpu", "ram"]:
                self.controller.get_system_stats()
            elif query in ["audio", "audio_devices", "microphones", "speakers", "sound"]:
                self.controller.list_audio_devices()
            return True
        elif name == "list_audio_devices":
            self.controller.list_audio_devices()
            return True
        elif name == "screen_vision":
            if self.vision:
                action = params.get("action", "analyze")
                if action == "explain_error":
                    self.vision.explain_screen_error()
                elif action == "copy_text":
                    self.vision.copy_screen_text()
                else:
                    self.vision.analyze_screen("Describe what is currently on my screen concisely.")
                return True
            else:
                self.tts.speak("Vision module is initializing, sir.")
                return True
        elif name == "read_aloud":
            source = params.get("source", "selection")
            self.controller.read_aloud(force_clipboard=(source == "clipboard"))
            return True
        elif name == "take_note":
            content = params.get("content", "")
            if content:
                self.controller.take_note(content)
                return True
        elif name == "read_notes":
            self.controller.read_notes()
            return True
        elif name == "set_timer":
            seconds = int(params.get("seconds", 60))
            label = params.get("label", "Timer")
            self.controller.set_timer(seconds, label)
            return True
        elif name == "cancel_timer":
            self.controller.cancel_all_timers()
            return True
        elif name == "power_control":
            action = params.get("action", "lock")
            if action == "lock":
                self.controller.lock_pc()
                return True
            elif action == "sleep":
                self.controller.sleep_pc()
                return True
        elif name == "weather_query":
            city = params.get("city", "")
            self.web_skills.get_weather(city)
            return True
        elif name == "news_query":
            self.web_skills.get_news_headlines()
            return True
        elif name == "calculate":
            expr = params.get("expression", "")
            self.web_skills.calculate(expr)
            return True
        elif name == "search_web":
            q = params.get("query", "")
            self.controller.search_web(q)
            return True
        elif name == "search_youtube":
            q = params.get("query", "")
            self.controller.search_youtube(q)
            return True
        elif name == "find_file":
            fn = params.get("filename", "")
            self.controller.find_and_open_file(fn)
            return True
        elif name == "open_folder":
            f = params.get("folder", "")
            self.controller.open_folder(f)
            return True
        elif name == "organize_folder":
            f = params.get("folder", "downloads")
            self.controller.organize_folder(f)
            return True
        elif name == "workspace_profile":
            p = params.get("profile", "coding")
            self.controller.launch_workspace_profile(p)
            return True
        elif name == "play_local_media":
            q = params.get("query", "")
            self.controller.play_local_media(q)
            return True
        elif name == "summarize_selection":
            self.controller.summarize_selection()
            return True
        elif name == "fix_grammar":
            self.controller.fix_grammar_selection()
            return True
        elif name == "make_professional":
            self.controller.make_professional_selection()
            return True
        elif name == "read_clipboard_history":
            self.controller.read_clipboard_history()
            return True
        elif name == "paste_clipboard_history":
            idx = int(params.get("index", 1))
            self.controller.paste_clipboard_history_item(idx)
            return True
        elif name == "document_rag":
            q = params.get("query", "")
            self.controller.summarize_document_rag(q)
            return True
        elif name == "morning_briefing":
            self.controller.give_morning_briefing()
            return True
        elif name == "execute_macro":
            macro_name = params.get("macro_name", "")
            if hasattr(self.controller, 'macros') and self.controller.macros:
                return self.controller.macros.execute_macro(macro_name, self.controller, self.tts)
            return False
        elif name == "toggle_network_killswitch":
            enable = params.get("enable", None)
            self.controller.toggle_network_killswitch(enable)
            return True
        elif name == "read_audit_log":
            self.controller.read_audit_log()
            return True
        elif name == "change_voice":
            v = params.get("voice_name", "")
            if v:
                self.controller.change_voice(v)
            else:
                self.controller.list_voices()
            return True
        elif name == "list_voices":
            self.controller.list_voices()
            return True

        return False
