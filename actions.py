import os
import re
import time
import shutil
import subprocess
import threading
import psutil
import pyautogui
import urllib.parse
import webbrowser
import ctypes
import difflib
from datetime import datetime
from config import APP_ALIASES, STRICT_OFFLINE_MODE
from tts import TextToSpeech
from os_adapter import get_os_adapter
from app_knowledge import get_app_knowledge_base
from smart_writer import SmartWriter
from clipboard_history import ClipboardHistory
from local_rag import LocalDocumentRAG
from macro_manager import MacroManager
from calendar_briefing import CalendarBriefingManager
from audit_and_sandbox import NetworkKillSwitch, ActionAuditLogger

try:
    import screen_brightness_control as sbc
except Exception as _sbc_err:
    sbc = None

class SystemController:
    def __init__(self, tts: TextToSpeech, hud=None, vision=None):
        self.tts = tts
        self.hud = hud
        self.vision = vision
        self.adapter = get_os_adapter()
        self.strict_offline_mode = STRICT_OFFLINE_MODE
        self.writer = SmartWriter(self.tts)
        self.clipboard_history = ClipboardHistory()
        self.clipboard_history.start()
        self.rag = LocalDocumentRAG()
        self.macros = MacroManager()
        self.calendar_briefing = CalendarBriefingManager()
        self.audit = ActionAuditLogger()
        if self.strict_offline_mode:
            NetworkKillSwitch.enable()
        pyautogui.FAILSAFE = True
        self.notes_file = os.path.join(self.adapter.get_standard_folder("documents"), "Buddy_Notes.txt")
        self.active_timers = []
        self.dictation_mode = False
        self.last_opened_folder = None
        self.knowledge_base = get_app_knowledge_base()
        self.installed_apps = {}
        self.scan_installed_apps()

    def scan_installed_apps(self):
        """Discovers and indexes all applications installed across operating systems dynamically and makes notes of it."""
        self.installed_apps.clear()
        self.knowledge_base.scan_system()
        self.installed_apps.update(self.knowledge_base.get_installed_apps_map())
        print(f"[*] J.A.R.V.I.S. indexed {len(self.installed_apps)} dynamic app triggers ({self.adapter.system}). Notes saved at SYSTEM_APPS_NOTES.md.")

    def list_installed_apps(self):
        """Voice summary of installed apps from dynamic knowledge base."""
        count = len(self.knowledge_base.apps)
        if count == 0:
            self.scan_installed_apps()
            count = len(self.knowledge_base.apps)
        
        sample = [a['display_name'] for a in list(self.knowledge_base.apps.values())[:6]]
        sample_str = ", ".join(sample)
        self.tts.speak(f"I have scanned and made notes of {count} applications on your computer, sir. Including {sample_str}, and many more. Notes are recorded at SYSTEM_APPS_NOTES.md.")

    def read_app_notes(self):
        """Reads a summary of the dynamically scanned system application notes."""
        total = len(self.knowledge_base.apps)
        msg = f"I have scanned and recorded notes for {total} applications in SYSTEM_APPS_NOTES.md, sir."
        self.tts.speak(msg)
        return msg

    def _clean_app_query(self, name: str) -> str:
        """Strips leading and trailing conversational keywords, app names, punctuation, and filler words."""
        clean = name.strip().lower()
        clean = re.sub(r'[,;:\'\"`\?!]+', ' ', clean)
        clean = re.sub(r'\s+', ' ', clean).strip()

        action_verbs = r'^(enter|go to|navigate to|visit|open up|open|launch|start|access|load|run|show|bring up|switch to|please|can you|could you|would you)\s+'
        while re.search(action_verbs, clean):
            clean = re.sub(action_verbs, '', clean).strip()

        app_prefix_patterns = [
            r'^(the\s+|my\s+|our\s+|a\s+|an\s+)?(application|app|software|program|tool|browser|window|folder|directory)\s+(name\s+|named\s+|called\s+)',
            r'^(the\s+|my\s+|our\s+|a\s+|an\s+)?(name\s+|named\s+|called\s+)',
            r'^(the\s+|my\s+|our\s+|a\s+|an\s+)?(application|app|software|program|tool|browser|window|folder|directory)\s+',
            r'^(the\s+|my\s+|our\s+|a\s+|an\s+)'
        ]
        changed = True
        while changed:
            changed = False
            for pat in app_prefix_patterns:
                if re.search(pat, clean):
                    new_clean = re.sub(pat, '', clean).strip()
                    if new_clean:
                        clean = new_clean
                        changed = True

        clean = re.sub(r'\s+(application|app|software|program|tool|browser|website|site|window|folder|directory)$', '', clean).strip()
        clean = re.sub(r'\s+(please|now|for me|on my pc|on my computer)$', '', clean).strip()
        clean = re.sub(r'^[,\.\?!:\s]+|[,\.\?!:\s]+$', '', clean).strip()
        return clean

    def _resolve_app_name(self, name: str):
        clean = self._clean_app_query(name)
        if not clean:
            return ("unknown", name)

        # 1. Check if it's 'This PC' or 'My Computer'
        if clean in ["this pc", "my computer", "computer"]:
            return ("this_pc", "shell:MyComputerFolder")

        # 2. Check if it's an explicit Drive request
        drive_match = re.search(r'^(?:the\s+)?([a-z]|see|sea|sito|dee)[-\s]*(?:drive|disk|drow|tray)$', clean) or \
                      re.search(r'^(?:drive|disk)\s*([a-z]|see|sea|sito|dee)$', clean) or \
                      re.search(r'^([a-z]):\\?$', clean)
        if drive_match:
            raw_letter = drive_match.group(1).upper()
            if raw_letter in ["SEE", "SEA", "SITO", "C"]:
                letter = "C"
            elif raw_letter in ["DEE", "D"]:
                letter = "D"
            else:
                letter = raw_letter
            return ("drive", letter)

        # 3. Check if it's a standard User Folder (e.g. Documents, Downloads, Desktop)
        clean_folder = clean.replace(" folder", "").replace("my ", "").strip()
        folder_candidates = ["downloads", "documents", "desktop", "pictures", "photos", "videos", "music", "projects", "users", "user"]
        if clean in folder_candidates or clean_folder in folder_candidates or clean.endswith(" folder"):
            folder_target = self._get_folder_path(clean_folder)
            if folder_target and os.path.exists(folder_target):
                return ("folder", folder_target)

        # 3.5 Check if it's a known subfolder in standard user libraries (e.g. "Camera Roll", "Screenshots")
        sub_match = self._search_subfolders(clean)
        if sub_match and os.path.exists(sub_match):
            return ("folder", sub_match)

        # 4. Web URLs / Bookmarks from config
        if clean in APP_ALIASES:
            target = APP_ALIASES[clean]
            if target.startswith("http://") or target.startswith("https://"):
                return ("url", target)

        # 5. Dynamic AppKnowledgeBase resolution (learns & scans all system apps)
        resolved = self.knowledge_base.resolve_application(clean)
        if resolved:
            app_id, launch_path, proc_name = resolved
            if launch_path.startswith("http://") or launch_path.startswith("https://"):
                return ("url", launch_path)
            return ("app_file", launch_path)

        # 6. Direct match in self.installed_apps
        if clean in self.installed_apps:
            return ("app_file", self.installed_apps[clean])

        # 7. Normalized match (without spaces or dashes)
        clean_norm = re.sub(r'[\s\-_]+', '', clean)
        for app_key, app_path in self.installed_apps.items():
            if clean_norm == re.sub(r'[\s\-_]+', '', app_key):
                return ("app_file", app_path)

        # 8. Check if text contains a web domain
        domain_match = re.search(r'\b([a-zA-Z0-9-]+\.(com|org|net|io|in|co|ai|app|dev|gov|edu|me))\b', clean)
        if domain_match:
            return ("url", f"https://{domain_match.group(1)}")

        if clean.startswith("www."):
            return ("url", f"https://{clean}")

        # 9. Fuzzy match against dynamically scanned apps (cutoff 0.70)
        app_matches = difflib.get_close_matches(clean, self.installed_apps.keys(), n=1, cutoff=0.70)
        if app_matches:
            return ("app_file", self.installed_apps[app_matches[0]])

        # 10. Check if executable exists in system PATH
        cmd_path = shutil.which(clean) or shutil.which(clean + ".exe")
        if cmd_path:
            return ("cmd", clean)

        return ("unknown", clean)

    def open_application(self, app_name: str):
        clean_name = self._clean_app_query(app_name)
        if not clean_name:
            clean_name = app_name.strip()

        # Handle 'This PC'
        if clean_name in ["this pc", "my computer", "computer"]:
            self.open_this_pc()
            return

        # Handle explicit Drive requests
        drive_match = re.search(r'^(?:the\s+)?([a-z]|see|sea|dee)\s+(?:drive|disk)$', clean_name) or \
                      re.search(r'^(?:drive|disk)\s+([a-z]|see|sea|dee)$', clean_name) or \
                      re.search(r'^([a-z]):\\?$', clean_name)
        if drive_match:
            raw_letter = drive_match.group(1).upper()
            letter = "C" if raw_letter in ["SEE", "SEA", "C"] else ("D" if raw_letter in ["DEE", "D"] else raw_letter)
            self.open_drive(letter)
            return

        kind, target = self._resolve_app_name(clean_name)
        try:
            if kind == "this_pc":
                self.open_this_pc()
            elif kind == "drive":
                self.open_drive(target)
            elif kind == "folder":
                self.adapter.open_path(target)
                self.tts.speak(f"Opening {clean_name}, sir.")
            elif kind == "app_file":
                self.tts.speak(f"Launching {clean_name}, sir.")
                try:
                    self.adapter.open_path(target)
                except Exception as err:
                    print(f"[App Launch Notice] {err}")
            elif kind == "url":
                webbrowser.open(target)
                self.tts.speak(f"Opening {clean_name}, sir.")
            elif kind == "cmd":
                if self.adapter.system == "Windows":
                    subprocess.Popen(f'start "" "{target}"', shell=True)
                else:
                    subprocess.Popen([target], shell=True)
                self.tts.speak(f"Opening {clean_name}, sir.")
            else:
                # Fallback: search user folders & files for matching folder or file
                found = self._find_and_open_fallback(clean_name)
                if not found:
                    self.tts.speak(f"I could not locate an application, folder, or file named {clean_name}, sir.")
        except Exception as e:
            print(f"[Open Error] {e}")
            self.tts.speak(f"Unable to launch {clean_name}, sir.")

    def _search_subfolders(self, name: str):
        """Searches immediate subdirectories in standard user folders (Pictures, Documents, Downloads, etc.) for a matching folder."""
        clean_target = name.strip().lower()
        clean_target = re.sub(r'^(the|my|our)\s+', '', clean_target).strip()
        clean_target = re.sub(r'^(folder|directory)\s+', '', clean_target).strip()
        clean_target = re.sub(r'\s+(folder|directory)$', '', clean_target).strip()
        if not clean_target or len(clean_target) < 2:
            return None

        roots = []
        for std in ["pictures", "documents", "downloads", "desktop", "videos", "music", "projects"]:
            try:
                p = self.adapter.get_standard_folder(std)
                if p and os.path.exists(p) and p not in roots:
                    roots.append(p)
            except Exception:
                pass

        # Dynamically discover top-level folders on all mounted volumes (C:, D:, E:, etc.)
        for vol in self.adapter.list_volumes():
            try:
                for entry in os.scandir(vol):
                    if entry.is_dir() and not entry.name.startswith(('$', 'System Volume', 'Recovery', 'Windows', 'Program Files')):
                        if entry.path not in roots:
                            roots.append(entry.path)
            except Exception:
                pass

        for root in roots:
            try:
                for entry in os.scandir(root):
                    if entry.is_dir():
                        en_lower = entry.name.lower()
                        if clean_target == en_lower or clean_target in en_lower or en_lower in clean_target:
                            return entry.path
            except Exception:
                continue
        return None

    def _find_and_open_fallback(self, query: str) -> bool:
        """Searches user folders for matching directory or file if query was not an app."""
        clean = self._clean_app_query(query)
        if not clean or len(clean) < 2:
            return False

        # First check subfolders directly
        sub_folder = self._search_subfolders(clean)
        if sub_folder and os.path.exists(sub_folder):
            try:
                self.last_opened_folder = sub_folder
                self.adapter.open_path(sub_folder)
                self.tts.speak(f"Opening {os.path.basename(sub_folder)}, sir.")
                return True
            except Exception:
                pass

        search_roots = []
        for std in ["downloads", "documents", "desktop", "pictures", "videos", "music", "projects"]:
            try:
                p = self.adapter.get_standard_folder(std)
                if p and os.path.exists(p) and p not in search_roots:
                    search_roots.append(p)
            except Exception:
                pass

        # Dynamically discover top-level folders across all mounted drives (C:, D:, E:, etc.)
        for vol in self.adapter.list_volumes():
            try:
                for entry in os.scandir(vol):
                    if entry.is_dir() and not entry.name.startswith(('$', 'System Volume', 'Recovery', 'Windows', 'Program Files')):
                        if entry.path not in search_roots:
                            search_roots.append(entry.path)
            except Exception:
                pass

        clean_stripped = re.sub(r'^(the\s+|my\s+)?(folder|directory)\s+', '', clean).strip()
        clean_stripped = re.sub(r'\s+(folder|directory)$', '', clean_stripped).strip()

        # 1. Exact or clear folder match
        for root_dir in search_roots:
            if not os.path.exists(root_dir):
                continue
            
            base_name = os.path.basename(root_dir).lower()
            if base_name and len(base_name) >= 3 and (clean == base_name or clean == f"{base_name} folder" or clean_stripped == base_name):
                try:
                    self.last_opened_folder = root_dir
                    self.adapter.open_path(root_dir)
                    self.tts.speak(f"Opening {os.path.basename(root_dir)}, sir.")
                    return True
                except Exception:
                    pass

            # Check subdirectories and files
            try:
                for entry in os.scandir(root_dir):
                    entry_name_lower = entry.name.lower()
                    entry_base_lower = os.path.splitext(entry_name_lower)[0]
                    if entry.is_dir() and (clean == entry_name_lower or clean_stripped == entry_name_lower or (len(clean_stripped) >= 3 and (clean_stripped in entry_name_lower or entry_name_lower in clean_stripped))):
                        self.last_opened_folder = entry.path
                        self.adapter.open_path(entry.path)
                        self.tts.speak(f"Opening {entry.name}, sir.")
                        return True
                    elif entry.is_file() and (clean == entry_name_lower or clean == entry_base_lower or clean_stripped == entry_name_lower or clean_stripped == entry_base_lower or (len(clean_stripped) >= 4 and clean_stripped in entry_name_lower)):
                        self.adapter.open_path(entry.path)
                        self.tts.speak(f"Opening {entry.name}, sir.")
                        return True
            except Exception:
                continue

        return False

    def run_diagnostics(self):
        """Jarvis Full System Diagnostics Report."""
        cpu_pct = psutil.cpu_percent(interval=0.4)
        ram = psutil.virtual_memory()
        battery = psutil.sensors_battery()
        
        report = f"All systems nominal, sir. Central processor is running at {cpu_pct} percent. Memory utilization is at {ram.percent} percent with {round(ram.available / (1024**3), 1)} gigabytes available."
        
        if battery:
            pwr_state = "charging" if battery.power_plugged else "on battery power"
            report += f" Primary power cell is at {round(battery.percent)} percent, {pwr_state}."
        
        self.tts.speak(report)

    # ---------------- TIMERS & REMINDERS ----------------
    def set_timer(self, duration_seconds: int, label: str = "Timer"):
        """Sets an asynchronous voice timer with countdown and alert."""
        if duration_seconds <= 0:
            self.tts.speak("Please specify a positive duration for the timer, sir.")
            return

        end_time = time.time() + duration_seconds
        timer_info = {"end_time": end_time, "label": label, "cancelled": False}
        self.active_timers.append(timer_info)

        mins = duration_seconds // 60
        secs = duration_seconds % 60
        time_desc = f"{mins} minutes" if mins > 0 and secs == 0 else (f"{secs} seconds" if mins == 0 else f"{mins} minutes and {secs} seconds")

        self.tts.speak(f"Timer set for {time_desc} ({label}), sir.")

        def _timer_thread():
            time.sleep(duration_seconds)
            if not timer_info["cancelled"]:
                if self.hud:
                    self.hud.set_state("speaking", f"🔔 Timer Complete: {label}", f"Timer of {time_desc} has finished.")
                self.tts.speak(f"Alert, sir: Your {time_desc} timer for {label} is complete.")
                if timer_info in self.active_timers:
                    self.active_timers.remove(timer_info)

        threading.Thread(target=_timer_thread, daemon=True).start()

    def list_active_timers(self):
        active = [t for t in self.active_timers if not t["cancelled"] and t["end_time"] > time.time()]
        if not active:
            self.tts.speak("You have no active timers running, sir.")
            return
        
        descriptions = []
        for i, t in enumerate(active, 1):
            remaining = int(t["end_time"] - time.time())
            m, s = divmod(remaining, 60)
            descriptions.append(f"{t['label']} with {m} minutes and {s} seconds remaining")
        
        self.tts.speak(f"You have {len(active)} active timers: " + ", ".join(descriptions))

    def cancel_all_timers(self):
        for t in self.active_timers:
            t["cancelled"] = True
        self.active_timers.clear()
        self.tts.speak("All active timers have been cancelled, sir.")

    # ---------------- SPOTIFY & MEDIA ----------------
    def media_next(self):
        pyautogui.press('nexttrack')
        self.tts.speak("Skipped to next track.")

    def media_prev(self):
        pyautogui.press('prevtrack')
        self.tts.speak("Playing previous track.")

    def media_toggle(self):
        pyautogui.press('playpause')

    # ---------------- FILE & FOLDER SEARCH ----------------
    def find_and_open_file(self, filename: str):
        """Searches user folders for file by name and opens it."""
        clean = filename.strip().lower()
        search_dirs = [
            os.path.join(os.path.expanduser("~"), "Downloads"),
            os.path.join(os.path.expanduser("~"), "Documents"),
            os.path.join(os.path.expanduser("~"), "Desktop"),
            os.path.join(os.path.expanduser("~"), "Pictures"),
            os.path.join(os.path.expanduser("~"), "Videos")
        ]
        
        self.tts.speak(f"Searching for {clean}, sir...")
        matches = []
        for d in search_dirs:
            if not os.path.exists(d):
                continue
            for root, dirs, files in os.walk(d):
                for f in files:
                    if clean in f.lower():
                        matches.append(os.path.join(root, f))
                        if len(matches) >= 3:
                            break
                if len(matches) >= 3:
                    break

        if matches:
            chosen = matches[0]
            os.startfile(chosen)
            self.tts.speak(f"Found and opened {os.path.basename(chosen)}, sir.")
        else:
            self.tts.speak(f"I could not locate any file named {clean} in your standard folders.")

    def _get_folder_path(self, folder_name: str) -> str:
        """Returns the dynamic path for common user folders across operating systems."""
        clean = folder_name.strip().lower()
        clean = re.sub(r'^(the|my|our)\s+', '', clean).strip()
        clean = re.sub(r'^(folder|directory)\s+', '', clean).strip()
        clean = re.sub(r'\s+(folder|directory|drive|disk|drow)$', '', clean).strip()
        # Any drive letter query (A:\ through Z:\, plus common phonetic aliases)
        phonetic_drives = {"see": "c", "sea": "c", "sito": "c", "dee": "d"}
        clean_drive = phonetic_drives.get(clean, clean)
        drive_m = re.match(r'^([a-z]):?$', clean_drive)
        if drive_m:
            drive_letter = drive_m.group(1).upper()
            drive_root = f"{drive_letter}:\\"
            if os.path.exists(drive_root):
                return drive_root
        if clean in ["this", "current", "here", "this folder", "current folder", "open folder"]:
            if hasattr(self, "last_opened_folder") and self.last_opened_folder and os.path.exists(self.last_opened_folder):
                return self.last_opened_folder
        
        # Check standard user folder first
        std_path = self.adapter.get_standard_folder(clean)
        if std_path and os.path.exists(std_path) and os.path.basename(std_path).lower() != os.path.basename(os.path.expanduser("~")).lower():
            return std_path
        
        # If not an existing root standard folder, search subdirectories (e.g. Camera Roll in Pictures)
        sub_path = self._search_subfolders(clean)
        if sub_path and os.path.exists(sub_path):
            return sub_path

        return std_path

    def count_folder_contents(self, query: str):
        """
        Inspects and counts folders and files in the requested directory (e.g. Pictures, Downloads, Documents).
        Answers queries like 'how many folders are there in pictures folder', 'how many files in downloads',
        'what folders are in pictures'.
        """
        clean = query.strip().lower()
        
        # 1. Determine target directory
        target_name = "current"
        candidates = [
            "pictures", "photos", "downloads", "documents", "desktop", "videos",
            "music", "projects", "c drive", "d drive", "camera roll", "screenshots", "saved pictures"
        ]
        for cand in candidates:
            if cand in clean:
                target_name = cand
                break

        if target_name in ["current", "this folder", "here", "open folder", "this directory", "current folder"]:
            if hasattr(self, "last_opened_folder") and self.last_opened_folder and os.path.exists(self.last_opened_folder):
                target_dir = self.last_opened_folder
                target_name = os.path.basename(target_dir.rstrip("\\/"))
            else:
                target_dir = self._get_folder_path("pictures")
                target_name = "pictures"
        else:
            target_dir = self._get_folder_path(target_name)

        if not target_dir or not os.path.exists(target_dir):
            sub = self._search_subfolders(target_name)
            if sub and os.path.exists(sub):
                target_dir = sub
                target_name = os.path.basename(sub.rstrip("\\/"))
            else:
                self.tts.speak(f"Could not locate your {target_name} directory, sir.")
                return

        try:
            dirs = []
            files = []
            for entry in os.scandir(target_dir):
                if entry.name.startswith('.') or entry.name.lower() == 'desktop.ini':
                    continue
                if entry.is_dir():
                    dirs.append(entry.name)
                elif entry.is_file():
                    files.append(entry.name)

            is_folder_query = bool(re.search(r'\b(how many|count|what|list)\s+(folders?|subfolders?|directories|dirs)\b', clean)) or \
                              bool(re.search(r'\b(folders?|subfolders?|directories|dirs)\s+(are\s+there|exist|inside|in)\b', clean))
            is_file_query = bool(re.search(r'\b(how many|count|what|list)\s+(files?|images?|photos?|documents?)\b', clean)) or \
                            bool(re.search(r'\b(files?|images?|photos?|documents?)\s+(are\s+there|exist|inside|in)\b', clean))

            if is_folder_query and is_file_query:
                # If user asked for both e.g. "how many files and folders", report general total
                is_folder_query = False
                is_file_query = False

            display_folder = target_name.title()

            if is_folder_query:
                if not dirs:
                    msg = f"There are no folders in your {display_folder} folder, sir."
                elif len(dirs) == 1:
                    msg = f"There is 1 folder in your {display_folder} folder, sir: {dirs[0]}."
                else:
                    sample = ", ".join(dirs[:6])
                    more = f", and {len(dirs) - 6} more" if len(dirs) > 6 else ""
                    msg = f"There are {len(dirs)} folders in your {display_folder} folder, sir: {sample}{more}."
            elif is_file_query:
                if not files:
                    msg = f"There are no files in your {display_folder} folder, sir."
                elif len(files) == 1:
                    msg = f"There is 1 file in your {display_folder} folder, sir: {files[0]}."
                else:
                    sample = ", ".join(files[:4])
                    more = f", and {len(files) - 4} others" if len(files) > 4 else ""
                    msg = f"There are {len(files)} files in your {display_folder} folder, sir, including {sample}{more}."
            else:
                total = len(dirs) + len(files)
                folder_str = f"{len(dirs)} folder" if len(dirs) == 1 else f"{len(dirs)} folders"
                file_str = f"{len(files)} file" if len(files) == 1 else f"{len(files)} files"
                msg = f"There are {total} items in your {display_folder} folder, sir: {folder_str} and {file_str}."

            if self.hud:
                self.hud.set_state("speaking", f"Folder Count: {display_folder}", msg)
            self.tts.speak(msg)
        except Exception as e:
            print(f"[Folder Count Error] {e}")
            self.tts.speak(f"Unable to inspect contents in {target_name}, sir.")

    def open_latest_file(self, folder_name: str = "downloads"):
        """Finds and opens the most recently created/modified file in the specified folder."""
        clean = folder_name.strip().lower()
        clean = re.sub(r'^(the|my|our)\s+', '', clean).strip()
        target_dir = self._get_folder_path(clean)
        if not os.path.exists(target_dir):
            self.tts.speak(f"Could not locate your {clean} directory, sir.")
            return

        try:
            files = [
                os.path.join(target_dir, f) for f in os.listdir(target_dir)
                if os.path.isfile(os.path.join(target_dir, f))
            ]
            if not files:
                self.tts.speak(f"There are no files inside your {clean} folder, sir.")
                return

            latest_file = max(files, key=os.path.getmtime)
            os.startfile(latest_file)
            self.tts.speak(f"Opening the latest file: {os.path.basename(latest_file)}, sir.")
        except Exception as e:
            print(f"[Open Latest Error] {e}")
            self.tts.speak(f"Could not open the latest file in {clean}.")

    def list_files_in_folder(self, folder_name: str = "current"):
        """Announces the top files in the specified folder sorted by most recently modified."""
        clean = folder_name.strip().lower()
        clean = re.sub(r'^(the|my|our)\s+', '', clean).strip()
        
        # If 'current' or 'this folder' or generic file listing, use last opened folder if available
        if clean in ["current", "this", "here", "this folder", "files", "folder", "to the files", "the files", "directory", ""]:
            if hasattr(self, "last_opened_folder") and self.last_opened_folder and os.path.exists(self.last_opened_folder):
                target_dir = self.last_opened_folder
                clean = os.path.basename(target_dir.rstrip("\\/")) or target_dir
            else:
                target_dir = self._get_folder_path("downloads")
                clean = "downloads"
        else:
            target_dir = self._get_folder_path(clean)

        if not os.path.exists(target_dir):
            self.tts.speak(f"Could not locate your {clean} directory, sir.")
            return

        try:
            entries = []
            for f in os.listdir(target_dir):
                if f.startswith('.'):
                    continue
                full_path = os.path.join(target_dir, f)
                try:
                    mtime = os.path.getmtime(full_path)
                except Exception:
                    mtime = 0
                entries.append((f, mtime))

            if not entries:
                self.tts.speak(f"Your {clean} directory is currently empty, sir.")
                return
            
            # Sort newest first so the user gets their latest downloaded / created files
            entries.sort(key=lambda x: x[1], reverse=True)
            top = [item[0] for item in entries[:5]]
            summary = ", ".join(top)
            count = len(entries)
            self.tts.speak(f"You have {count} items in {clean}. Recent items include: {summary}. You can say open file followed by the name to open any of them.")
        except Exception as e:
            self.tts.speak(f"Unable to read files in {clean}, sir.")

    def open_this_pc(self):
        """Opens 'This PC' or system root volume in the file manager."""
        self.adapter.open_this_pc()
        self.tts.speak("Opening file manager, sir.")

    def open_drive(self, drive_letter: str):
        """Opens a specific local disk drive or volume across operating systems."""
        letter = drive_letter.upper()
        if self.adapter.open_drive(letter):
            self.last_opened_folder = f"{letter}:\\"
            self.tts.speak(f"Opening {letter} drive, sir.")
        else:
            self.tts.speak(f"Drive {letter} was not found on your system, sir.")

    def open_folder(self, folder_name: str):
        clean = folder_name.strip().lower()
        clean = re.sub(r'^(enter|go to|navigate to|open up|open|launch|access|show|bring up|please|can you|could you)\s+', '', clean).strip()
        clean = re.sub(r'^(the|my|our)\s+', '', clean).strip()
        clean = re.sub(r'^(folder|directory)\s+', '', clean).strip()
        clean = re.sub(r'\s+(folder|directory)$', '', clean).strip()
        clean = re.sub(r'^[,\.\?!:\s]+|[,\.\?!:\s]+$', '', clean).strip()

        if clean in ["this pc", "my computer", "computer"]:
            self.open_this_pc()
            return

        # 1. Check for nested subfolder query: e.g., "python folder in desktop" or "react project on desktop"
        nested_match = re.search(r'^(.*?)\s+(?:in|inside|on|from)\s+(?:the\s+|my\s+)?(desktop|downloads|documents|pictures|photos|videos|music|projects)\b', clean)
        if nested_match:
            sub_name = nested_match.group(1).replace("folder", "").replace("directory", "").strip()
            parent_name = nested_match.group(2).strip()
            parent_path = self._get_folder_path(parent_name)
            
            if sub_name and os.path.exists(parent_path):
                found_item = None
                for entry in os.listdir(parent_path):
                    if sub_name == entry.lower() or sub_name in entry.lower():
                        found_item = os.path.join(parent_path, entry)
                        break
                
                if found_item:
                    self.last_opened_folder = found_item
                    self.adapter.open_path(found_item)
                    self.tts.speak(f"Opening {os.path.basename(found_item)} in your {parent_name.title()} folder, sir.")
                    return

        # 2. Direct folder opening
        target = self._get_folder_path(clean)
        if target and os.path.exists(target):
            self.last_opened_folder = target
            self.adapter.open_path(target)
            display_name = os.path.basename(target.rstrip('\\/')) or clean.title()
            self.tts.speak(f"Opening your {display_name} folder, sir.")
            return

        # 3. Subfolder search across standard locations
        sub = self._search_subfolders(clean)
        if sub and os.path.exists(sub):
            self.last_opened_folder = sub
            self.adapter.open_path(sub)
            display_name = os.path.basename(sub.rstrip('\\/')) or clean.title()
            self.tts.speak(f"Opening {display_name}, sir.")
            return

        if not self._find_and_open_fallback(clean):
            self.adapter.open_this_pc()
            self.tts.speak("Opening File Explorer, sir.")

    # ---------------- POWER & SYSTEM MANAGEMENT ----------------
    def schedule_shutdown(self, minutes: int = 10):
        self.adapter.shutdown_system(minutes)
        self.tts.speak(f"System shutdown scheduled in {minutes} minutes, sir. Say cancel shutdown to abort.")

    def cancel_shutdown(self):
        self.adapter.cancel_shutdown()
        self.tts.speak("Scheduled shutdown has been aborted, sir.")

    def restart_pc(self):
        self.tts.speak("Restarting system, sir.")
        self.adapter.restart_system()

    def sleep_pc(self):
        self.tts.speak("Putting system into sleep mode, sir.")
        self.adapter.sleep_system()

    def empty_recycle_bin(self):
        if self.adapter.empty_recycle_bin():
            self.tts.speak("Recycle Bin has been emptied, sir.")
        else:
            self.tts.speak("Unable to empty the Recycle Bin.")

    # ---------------- ADVANCED WORKSPACE & FILE AUTOMATION ----------------
    def organize_folder(self, folder_name: str = "downloads"):
        """Voice-driven automatic file organization by file type category."""
        clean = folder_name.strip().lower()
        clean = re.sub(r'^(the|my|our)\s+', '', clean).strip()
        clean = re.sub(r'\s+(folder|directory)$', '', clean).strip()
        target_dir = self._get_folder_path(clean)

        if not os.path.exists(target_dir):
            self.tts.speak(f"Could not locate your {folder_name} folder, sir.")
            return

        categories = {
            "Documents": [".pdf", ".docx", ".doc", ".txt", ".xlsx", ".pptx", ".csv", ".epub", ".rtf"],
            "Images": [".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico", ".bmp", ".tiff"],
            "Audio": [".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".wma"],
            "Video": [".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv"],
            "Archives": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".iso"],
            "Code": [".py", ".js", ".ts", ".html", ".css", ".json", ".cpp", ".c", ".java", ".sh", ".rs"],
            "Installers": [".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm", ".apk"]
        }

        moved_count = 0
        try:
            for item in os.listdir(target_dir):
                item_path = os.path.join(target_dir, item)
                if os.path.isdir(item_path) or item.startswith("."):
                    continue

                _, ext = os.path.splitext(item)
                ext = ext.lower()
                if not ext:
                    continue

                cat_name = "Other"
                for cat, exts in categories.items():
                    if ext in exts:
                        cat_name = cat
                        break

                dest_dir = os.path.join(target_dir, cat_name)
                os.makedirs(dest_dir, exist_ok=True)
                dest_path = os.path.join(dest_dir, item)

                if os.path.exists(dest_path):
                    base, e = os.path.splitext(item)
                    dest_path = os.path.join(dest_dir, f"{base}_{int(time.time())}{e}")

                shutil.move(item_path, dest_path)
                moved_count += 1

            if moved_count > 0:
                self.tts.speak(f"Successfully organized {moved_count} files in your {clean} folder into categorized directories, sir.")
            else:
                self.tts.speak(f"Your {clean} folder is already clean and organized, sir.")
        except Exception as e:
            print(f"[File Organization Error] {e}")
            self.tts.speak(f"An error occurred while organizing your files, sir.")

    def launch_workspace_profile(self, profile_name: str):
        """Launches multi-app workspace profiles and arranges windows."""
        clean = profile_name.lower().strip()
        self.tts.speak(f"Activating {clean} workspace profile, sir.")

        try:
            if any(w in clean for w in ["code", "coding", "dev", "developer"]):
                try:
                    self.open_application("vs code")
                except Exception:
                    pass
                time.sleep(0.5)
                try:
                    if self.adapter.system == "Windows":
                        if shutil.which("wt.exe"):
                            subprocess.Popen(["wt.exe"])
                        elif shutil.which("cmd.exe"):
                            subprocess.Popen(["cmd.exe"])
                    else:
                        self.open_application("terminal")
                except Exception:
                    pass
                try:
                    self.snap_window("left")
                except Exception:
                    pass
                self.tts.speak("Coding workspace ready. Code editor and terminal opened, sir.")

            elif any(w in clean for w in ["study", "research", "read", "writing"]):
                try:
                    self.open_folder("documents")
                except Exception:
                    pass
                time.sleep(0.5)
                try:
                    self.open_application("notepad")
                except Exception:
                    pass
                self.tts.speak("Study workspace active. Documents and notes opened, sir.")

            elif any(w in clean for w in ["relax", "media", "music"]):
                try:
                    self.minimize_all()
                except Exception:
                    pass
                time.sleep(0.5)
                try:
                    self.open_application("spotify")
                except Exception:
                    pass
                self.tts.speak("Relaxation profile active. Background windows cleared, sir.")
            else:
                self.tts.speak(f"I don't have a preset profile for {clean}, sir. You can ask for coding, study, or relax profile.")
        except Exception as e:
            print(f"[Workspace Profile Notice] {e}")

    def play_local_media(self, query: str = ""):
        """Finds and plays local offline audio tracks (.mp3, .wav, .flac) without needing internet."""
        search_dirs = [
            self.adapter.get_standard_folder("music"),
            self.adapter.get_standard_folder("downloads"),
            self.adapter.get_standard_folder("desktop")
        ]
        valid_exts = ('.mp3', '.wav', '.flac', '.m4a', '.ogg', '.wma')
        found_tracks = []
        clean_q = query.lower().strip() if query else ""

        for d in search_dirs:
            try:
                if not os.path.exists(d):
                    continue
                for root, dirs, files in os.walk(d, onerror=lambda e: None):
                    for f in files:
                        if f.lower().endswith(valid_exts):
                            full_p = os.path.join(root, f)
                            if clean_q:
                                if clean_q in f.lower():
                                    found_tracks.append(full_p)
                            else:
                                found_tracks.append(full_p)
            except Exception:
                continue

        if not found_tracks:
            if clean_q:
                self.tts.speak(f"Could not find any local music matching {query}, sir.")
            else:
                self.tts.speak("No local audio files found in your music or downloads folders, sir.")
            return

        chosen = found_tracks[0]
        track_name = os.path.splitext(os.path.basename(chosen))[0]
        self.tts.speak(f"Playing {track_name} from local storage, sir.")
        self.adapter.open_path(chosen)

    # ---------------- SMART WRITING & CLIPBOARD INTELLIGENCE ----------------
    def summarize_selection(self):
        """Summarizes highlighted text or current clipboard."""
        text = self.writer.get_selected_or_clipboard_text()
        if not text:
            self.tts.speak("Please highlight or copy the text you would like me to summarize, sir.")
            return
        summary = self.writer.summarize_text(text, max_sentences=2)
        self.tts.speak(f"Summary: {summary}")

    def fix_grammar_selection(self, replace: bool = True):
        """Fixes grammar, punctuation, and capitalization of selected text."""
        text = self.writer.get_selected_or_clipboard_text()
        if not text:
            self.tts.speak("Please highlight or copy the text you would like me to fix, sir.")
            return
        fixed = self.writer.fix_grammar(text)
        if replace:
            self.writer.replace_selection_with(fixed)
            self.tts.speak("Grammar and capitalization corrected, sir.")
        else:
            self.tts.speak(f"Corrected: {fixed}")

    def make_professional_selection(self, replace: bool = True):
        """Rewrites selected text into professional workplace tone."""
        text = self.writer.get_selected_or_clipboard_text()
        if not text:
            self.tts.speak("Please highlight or copy the text you would like me to polish, sir.")
            return
        polished = self.writer.make_professional(text)
        if replace:
            self.writer.replace_selection_with(polished)
            self.tts.speak("Text polished into professional workplace tone, sir.")
        else:
            self.tts.speak(f"Polished: {polished}")

    def read_clipboard_history(self, count: int = 3):
        """Reads recent clipboard snippets aloud."""
        items = self.clipboard_history.get_recent(count)
        if not items:
            self.tts.speak("Your clipboard history is currently empty, sir.")
            return
        self.tts.speak(f"Here are your last {len(items)} clipboard items:")
        for i, item in enumerate(items, 1):
            preview = (item[:70] + "...") if len(item) > 70 else item
            self.tts.speak(f"Item {i}: {preview}")

    def paste_clipboard_history_item(self, index: int = 1):
        """Pastes a specific item from clipboard history into the active window."""
        if self.clipboard_history.paste_item(index):
            self.tts.speak(f"Pasted clipboard item number {index}, sir.")
        else:
            self.tts.speak(f"Could not find item number {index} in your clipboard history, sir.")

    def summarize_document_rag(self, keyword_or_file: str = ""):
        """Offline RAG document query & latest document summarization."""
        clean = keyword_or_file.lower().strip() if keyword_or_file else ""
        if not clean or "latest" in clean or "pdf" in clean:
            downloads_dir = self.adapter.get_standard_folder("downloads")
            summary = self.rag.summarize_latest_file(downloads_dir, ext_filter=".pdf")
            if not summary:
                docs_dir = self.adapter.get_standard_folder("documents")
                summary = self.rag.summarize_latest_file(docs_dir, ext_filter=".pdf")
            if summary:
                self.tts.speak(summary)
            else:
                self.tts.speak("No recent PDF documents found to summarize, sir.")
        else:
            results = self.rag.query(clean, top_k=1)
            if results:
                best = results[0]
                self.tts.speak(f"From {best['filename']}: {best['text'][:250]}...")
            else:
                self.tts.speak(f"No indexed document matches found for {keyword_or_file}, sir.")

    # ---------------- WINDOWS CONTROL ----------------
    def switch_to_window(self, app_name: str):
        import pygetwindow as gw
        clean_name = app_name.strip().lower()
        if clean_name.startswith("the "):
            clean_name = clean_name[4:].strip()
        
        windows = gw.getAllWindows()
        matched = None
        for w in windows:
            if w.title and clean_name in w.title.lower():
                matched = w
                break
        
        if matched:
            try:
                if matched.isMinimized:
                    matched.restore()
                matched.activate()
                self.tts.speak(f"Switched to {clean_name}")
            except Exception:
                self.tts.speak(f"Could not bring {clean_name} to foreground.")
        else:
            self.tts.speak(f"No open window found for {clean_name}")

    def mouse_click(self, click_type: str = "left"):
        if click_type == "left":
            pyautogui.click()
        elif click_type == "right":
            pyautogui.rightClick()
        elif click_type == "double":
            pyautogui.doubleClick()
        elif click_type == "center":
            sw, sh = pyautogui.size()
            pyautogui.click(sw // 2, sh // 2)

    def move_mouse(self, direction: str, distance: int = 200):
        dx, dy = 0, 0
        if direction == "up":
            dy = -distance
        elif direction == "down":
            dy = distance
        elif direction == "left":
            dx = -distance
        elif direction == "right":
            dx = distance
        pyautogui.moveRel(dx, dy, duration=0.2)

    def open_search_result(self, index: int = 1):
        sw, sh = pyautogui.size()
        if index == 1:
            target_x = int(sw * 0.28)
            target_y = int(sh * 0.33)
        elif index == 2:
            target_x = int(sw * 0.28)
            target_y = int(sh * 0.48)
        elif index == 3:
            target_x = int(sw * 0.28)
            target_y = int(sh * 0.63)
        else:
            target_x = int(sw * 0.28)
            target_y = int(sh * 0.33 + (index - 1) * (sh * 0.15))

        pyautogui.click(target_x, target_y)
        self.tts.speak(f"Opening result number {index}, sir.")

    def find_and_open_link(self, keyword: str):
        import pyperclip
        pyautogui.hotkey('ctrl', 'f')
        time.sleep(0.1)
        pyperclip.copy(keyword.strip())
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.1)
        pyautogui.press('escape')
        time.sleep(0.1)
        pyautogui.press('enter')
        self.tts.speak(f"Accessing link for {keyword}, sir.")

    def close_application(self, app_name: str):
        clean_name = app_name.strip().lower()
        if clean_name.startswith("the "):
            clean_name = clean_name[4:].strip()

        # If user asked to close the window, open window, or current application
        if clean_name in [
            "window", "this window", "open window", "the window", "the open window",
            "active window", "current window", "open", "this", "it",
            "entire application", "the entire application", "entire app", "current application"
        ]:
            self.close_window()
            return

        # 1. Dynamically retrieve all known binary process names from AppKnowledgeBase
        target_procs = self.knowledge_base.get_process_names(clean_name)

        # Also resolve via knowledge base to get target launch path / exe base
        resolved = self.knowledge_base.resolve_application(clean_name)
        if resolved:
            _, launch_path, proc_name = resolved
            if proc_name:
                target_procs.add(proc_name.lower())
                target_procs.add(os.path.splitext(proc_name)[0].lower())
            if launch_path:
                base = os.path.splitext(os.path.basename(launch_path))[0].lower()
                target_procs.add(base)

        # Protected core OS and assistant runtime processes blacklist
        protected_processes = {
            "system", "system idle process", "registry", "smss.exe", "csrss.exe",
            "wininit.exe", "services.exe", "lsass.exe", "svchost.exe", "fontdrvhost.exe",
            "dwm.exe", "explorer.exe", "spoolsv.exe", "sihost.exe", "taskhostw.exe",
            "conhost.exe", "runtimebroker.exe", "python.exe", "pythonw.exe", "python",
            "python3", "init", "systemd", "kernel", "launchd"
        }

        closed_count = 0
        for proc in psutil.process_iter(['name', 'pid', 'exe']):
            try:
                proc_name = (proc.info['name'] or '').lower()
                proc_exe = (proc.info.get('exe') or '').lower()
                if proc_name in protected_processes or os.path.splitext(proc_name)[0] in protected_processes:
                    continue

                matched = False
                for p in target_procs:
                    if p in protected_processes:
                        continue
                    if p == proc_name or proc_name.startswith(f"{p}.") or (len(p) >= 4 and proc_name.startswith(p)) or (p and p in proc_exe):
                        matched = True
                        break

                if not matched and clean_name and clean_name not in {"app", "host", "the", "window", "process"}:
                    base_proc = os.path.splitext(proc_name)[0]
                    if clean_name == proc_name or clean_name == base_proc or (len(clean_name) >= 4 and base_proc.startswith(clean_name)):
                        matched = True

                if matched:
                    proc.terminate()
                    closed_count += 1
                    # Self-learning: remember this process name for clean_name
                    self.knowledge_base.learn_alias(clean_name, proc_name)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if closed_count > 0:
            self.tts.speak(f"Closed {clean_name}, sir.")
        else:
            self.tts.speak(f"No running process found for {clean_name}, sir.")

    def type_text(self, text: str):
        import pyperclip
        pyperclip.copy(text)
        pyautogui.hotkey('ctrl', 'v')
        self.tts.speak(f"Typed {text}")

    def press_key(self, key_name: str):
        key = key_name.lower().strip()
        if key in ["enter", "return"]:
            pyautogui.press('enter')
        elif key in ["backspace", "delete"]:
            pyautogui.press('backspace')
        elif key in ["space", "spacebar"]:
            pyautogui.press('space')
        elif key in ["tab"]:
            pyautogui.press('tab')
        elif key in ["escape", "esc"]:
            pyautogui.press('escape')

    def scroll_page(self, direction: str, amount: int = 1):
        direction = direction.lower().strip()
        if "top" in direction:
            pyautogui.hotkey('ctrl', 'home')
        elif "bottom" in direction:
            pyautogui.hotkey('ctrl', 'end')
        elif "page down" in direction or "page_down" in direction or direction == "pagedown":
            pyautogui.press('pagedown')
        elif "page up" in direction or "page_up" in direction or direction == "pageup":
            pyautogui.press('pageup')
        elif "up" in direction:
            pyautogui.scroll(700 * max(1, amount))
        elif "down" in direction:
            pyautogui.scroll(-700 * max(1, amount))

    def browser_action(self, action: str):
        if action == "refresh":
            pyautogui.hotkey('ctrl', 'r')
            self.tts.speak("Refreshed")
        elif action == "back":
            pyautogui.hotkey('alt', 'left')
        elif action == "forward":
            pyautogui.hotkey('alt', 'right')
        elif action == "downloads":
            pyautogui.hotkey('ctrl', 'j')
            self.tts.speak("Opening downloads")
        elif action == "history":
            pyautogui.hotkey('ctrl', 'h')
            self.tts.speak("Opening history")
        elif action == "bookmark":
            pyautogui.hotkey('ctrl', 'd')
            self.tts.speak("Page bookmarked")
        elif action == "zoom_in":
            pyautogui.hotkey('ctrl', '+')
        elif action == "zoom_out":
            pyautogui.hotkey('ctrl', '-')
        elif action == "zoom_reset":
            pyautogui.hotkey('ctrl', '0')
        elif action == "fullscreen":
            pyautogui.press('f11')

    def edit_action(self, action: str):
        if action == "select_all":
            pyautogui.hotkey('ctrl', 'a')
        elif action == "copy":
            pyautogui.hotkey('ctrl', 'c')
            self.tts.speak("Copied")
        elif action == "paste":
            pyautogui.hotkey('ctrl', 'v')
            self.tts.speak("Pasted")
        elif action == "undo":
            pyautogui.hotkey('ctrl', 'z')
            self.tts.speak("Undone")
        elif action == "save":
            pyautogui.hotkey('ctrl', 's')
            self.tts.speak("Saved")

    def close_window(self):
        pyautogui.hotkey('alt', 'f4')
        self.tts.speak("Window closed")

    def close_tab(self):
        pyautogui.hotkey('ctrl', 'w')
        self.tts.speak("Tab closed")

    def new_tab(self):
        pyautogui.hotkey('ctrl', 't')
        self.tts.speak("New tab opened")

    def switch_tab(self):
        pyautogui.hotkey('ctrl', 'tab')

    def minimize_all(self):
        self.adapter.minimize_all()
        self.tts.speak("Showing desktop")

    def snap_window(self, direction: str):
        self.adapter.snap_window(direction)

    def lock_pc(self):
        self.tts.speak("Locking your computer")
        self.adapter.lock_screen()

    def get_battery_status(self):
        battery = psutil.sensors_battery()
        if not battery:
            self.tts.speak("No battery sensor detected. System is running on AC power.")
            return

        percent = round(battery.percent)
        plugged = "plugged in and charging" if battery.power_plugged else "discharging on battery"
        
        if battery.secsleft and battery.secsleft > 0 and not battery.power_plugged:
            hours = battery.secsleft // 3600
            mins = (battery.secsleft % 3600) // 60
            self.tts.speak(f"Battery is at {percent}%, {plugged}. Approximately {hours} hours and {mins} minutes remaining.")
        else:
            self.tts.speak(f"Battery is at {percent}%, {plugged}.")

    def get_system_stats(self):
        cpu_pct = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory()
        ram_pct = ram.percent
        ram_avail_gb = round(ram.available / (1024 ** 3), 1)
        self.tts.speak(f"CPU usage is currently at {cpu_pct} percent. Memory usage is at {ram_pct} percent, with {ram_avail_gb} gigabytes available.")

    def set_brightness(self, level: int):
        if sbc is None:
            self.tts.speak("Brightness control module is not available.")
            return
        try:
            target = max(5, min(100, level))
            sbc.set_brightness(target)
            self.tts.speak(f"Brightness set to {target} percent")
        except Exception:
            self.tts.speak("Could not adjust screen brightness.")

    def change_brightness(self, delta: int):
        if sbc is None:
            self.tts.speak("Brightness control module is not available.")
            return
        try:
            current = sbc.get_brightness()
            curr_val = current[0] if isinstance(current, list) else current
            new_val = max(5, min(100, curr_val + delta))
            sbc.set_brightness(new_val)
            self.tts.speak(f"Brightness adjusted to {new_val} percent")
        except Exception:
            self.tts.speak("Could not change brightness.")

    def take_note(self, note_text: str):
        if not note_text.strip():
            self.tts.speak("What note would you like me to save?")
            return
        
        timestamp = datetime.now().strftime("%Y-%m-%d %I:%M %p")
        try:
            os.makedirs(os.path.dirname(self.notes_file), exist_ok=True)
            with open(self.notes_file, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {note_text.strip()}\n")
            self.tts.speak("Note saved successfully.")
        except Exception as e:
            print(f"[Note Error] {e}")
            self.tts.speak("Unable to save note.")

    def read_notes(self):
        if not os.path.exists(self.notes_file):
            self.tts.speak("You have no saved notes yet.")
            return
        
        try:
            with open(self.notes_file, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
            
            if not lines:
                self.tts.speak("Your notes file is currently empty.")
                return

            recent = lines[-3:]
            self.tts.speak(f"You have {len(lines)} total notes. Here are the most recent:")
            for note in recent:
                self.tts.speak(note)
        except Exception as e:
            print(f"[Read Notes Error] {e}")
            self.tts.speak("Could not read your notes.")

    def search_web(self, query: str):
        if not query.strip():
            self.tts.speak("What would you like me to search for?")
            return
        encoded = urllib.parse.quote(query)
        webbrowser.open(f"https://www.google.com/search?q={encoded}")
        self.tts.speak(f"Searching Google for {query}")

    def search_youtube(self, query: str):
        if not query.strip():
            self.tts.speak("What should I search on YouTube?")
            return
        encoded = urllib.parse.quote(query)
        webbrowser.open(f"https://www.youtube.com/results?search_query={encoded}")
        self.tts.speak(f"Searching YouTube for {query}")

    def take_screenshot(self):
        screenshots_dir = os.path.join(os.path.expanduser("~"), "Pictures", "AssistantScreenshots")
        os.makedirs(screenshots_dir, exist_ok=True)
        filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        filepath = os.path.join(screenshots_dir, filename)
        screenshot = pyautogui.screenshot()
        screenshot.save(filepath)
        self.tts.speak("Screenshot captured and saved to your Pictures folder, sir.")
        print(f"Screenshot saved to: {filepath}")

    def volume_control(self, action: str):
        if action == "up":
            for _ in range(5):
                pyautogui.press('volumeup')
        elif action == "down":
            for _ in range(5):
                pyautogui.press('volumedown')
        elif action == "mute":
            pyautogui.press('volumemute')
            self.tts.speak("Audio toggled")

    def list_audio_devices(self):
        """Discovers, displays, and announces all connected audio microphones and speakers."""
        import sounddevice as sd
        from config import load_user_settings
        try:
            devices = sd.query_devices()
            apis = sd.query_hostapis()
            def_in, def_out = sd.default.device
            
            in_devs = [d for d in devices if d.get('max_input_channels', 0) > 0]
            out_devs = [d for d in devices if d.get('max_output_channels', 0) > 0]
            
            settings = load_user_settings()
            saved_in = settings.get("audio_device_index")
            saved_out_idx = settings.get("audio_output_device_index")
            saved_out_name = settings.get("audio_output_device_name")
            
            active_mic = devices[saved_in]['name'] if saved_in is not None and saved_in < len(devices) else (devices[def_in]['name'] if def_in is not None and def_in < len(devices) else "Default Microphone")
            active_spk = saved_out_name if saved_out_name else (devices[saved_out_idx]['name'] if saved_out_idx is not None and saved_out_idx < len(devices) else (devices[def_out]['name'] if def_out is not None and def_out < len(devices) else "Default Speaker"))
            
            print("\n" + "="*55)
            print("         🎙️ CONNECTED AUDIO HARDWARE REPORT")
            print("="*55)
            print(f"[*] Active Microphone:  {active_mic}")
            print(f"[*] Active Speaker/Out: {active_spk}")
            print(f"[*] Input Channels:     {len(in_devs)} devices detected")
            print(f"[*] Output Channels:    {len(out_devs)} devices detected")
            print("\n--- Available Microphones ---")
            for idx, dev in enumerate(devices):
                if dev.get('max_input_channels', 0) > 0:
                    api = apis[dev['hostapi']]['name'] if dev.get('hostapi', 0) < len(apis) else ""
                    tag = " [ACTIVE]" if (saved_in == idx or (saved_in is None and idx == def_in)) else ""
                    print(f"  [{idx}] {dev['name']} ({api}){tag}")
            print("\n--- Available Speakers / Outputs ---")
            for idx, dev in enumerate(devices):
                if dev.get('max_output_channels', 0) > 0:
                    api = apis[dev['hostapi']]['name'] if dev.get('hostapi', 0) < len(apis) else ""
                    tag = " [ACTIVE]" if (saved_out_idx == idx or dev['name'] == saved_out_name or (saved_out_idx is None and not saved_out_name and idx == def_out)) else ""
                    print(f"  [{idx}] {dev['name']} ({api}){tag}")
            print("="*55 + "\n")
            
            if self.hud:
                self.hud.set_state("idle", "Audio Hardware Online", f"Mic: {active_mic[:25]} | Spk: {active_spk[:25]}")
            
            speech = f"Connected audio hardware, sir: Active microphone is {active_mic.split('(')[0].strip()}. Active sound output is {active_spk.split('(')[0].strip()}. I found {len(in_devs)} microphones and {len(out_devs)} output devices available."
            self.tts.speak(speech)
            return speech
        except Exception as e:
            err = f"Unable to query audio hardware: {e}"
            print(f"[Audio Error] {err}")
            self.tts.speak("I encountered an issue querying connected audio devices, sir.")
            return err

    def tell_time(self):
        now = datetime.now().strftime("%I:%M %p")
        self.tts.speak(f"It is currently {now}")

    def tell_date(self):
        now = datetime.now().strftime("%A, %B %d, %Y")
        self.tts.speak(f"Today is {now}")

    def run_diagnostics(self):
        cpu_pct = psutil.cpu_percent(interval=0.2)
        ram = psutil.virtual_memory()
        battery = psutil.sensors_battery()
        bat_str = f", battery is at {round(battery.percent)} percent" if battery else ""
        msg = f"System diagnostics complete, sir. CPU load is at {cpu_pct} percent, memory usage is at {ram.percent} percent with {round(ram.available / (1024**3), 1)} gigabytes free{bat_str}. All hardware and neural subsystems operational."
        self.tts.speak(msg)

    def read_aloud(self, force_clipboard: bool = False):
        """
        Reads aloud highlighted/selected text, clipboard text, or active window content.
        1. If user highlighted text, copies and reads it.
        2. If force_clipboard or nothing selected, reads clipboard content if available.
        3. If clipboard is empty, reads the active window title and screen content via vision.
        """
        import pyperclip
        selected_text = ""
        prev_clipboard = ""
        try:
            prev_clipboard = pyperclip.paste()
        except Exception:
            pass

        if not force_clipboard:
            try:
                # Clear clipboard temporarily and trigger Ctrl+C to capture active selection
                pyperclip.copy("")
                try:
                    pyautogui.hotkey('ctrl', 'c')
                except Exception:
                    pass
                time.sleep(0.18)
                selected_text = pyperclip.paste().strip()
            except Exception as e:
                print(f"[Read Aloud Selection Notice] {e}")

        # If no active selection was copied, fallback to previous or current clipboard
        if not selected_text:
            try:
                curr_clip = pyperclip.paste().strip()
                selected_text = curr_clip or prev_clipboard.strip()
            except Exception:
                selected_text = ""

        if selected_text:
            # Clean up excessive whitespace
            clean_text = " ".join(selected_text.split())
            preview = clean_text[:120] + ("..." if len(clean_text) > 120 else "")
            print(f"[*] Reading aloud ({len(clean_text)} characters): {preview}")
            if self.hud:
                self.hud.set_state("speaking", "Reading Aloud...", preview)
            self.tts.speak(clean_text)
        else:
            # If no text is selected and clipboard is empty, fallback to reading screen via vision
            if getattr(self, 'vision', None):
                self.tts.speak("No text was selected, sir. Reading your active screen instead.")
                try:
                    self.vision.analyze_screen("Describe and read what is on the screen concisely.")
                except Exception as e:
                    print(f"[Vision Read Error] {e}")
                    self.tts.speak("Could not capture the screen at this moment, sir.")
            else:
                self.tts.speak("No text is selected or found on the clipboard to read aloud, sir. Please highlight or copy some text first.")

    # ---------------- PRODUCTIVITY, MACROS & AUDIT PRIVACY ----------------
    def give_morning_briefing(self):
        """Generates and vocalizes a comprehensive morning/daily briefing."""
        briefing = self.calendar_briefing.generate_morning_briefing(self)
        self.tts.speak(briefing)
        return briefing

    def toggle_network_killswitch(self, enable: bool = None):
        """Toggles or sets the process-level network kill-switch."""
        if enable is None:
            enable = not NetworkKillSwitch.is_active()
        if enable:
            NetworkKillSwitch.enable()
            self.tts.speak("Process network kill-switch activated, sir. All outbound socket connections are strictly hard-blocked.")
        else:
            NetworkKillSwitch.disable()
            self.tts.speak("Process network kill-switch deactivated, sir. Local process network access restored.")

    def read_audit_log(self):
        """Reads a transparency summary of recent voice assistant operations."""
        summary = self.audit.get_summary_speech()
        self.tts.speak(summary)
        return summary

    # ---------------- VOICE PERSONALITY & OUTPUT CONTROL ----------------
    def change_voice(self, voice_query: str):
        """Changes the assistant's voice personality dynamically."""
        return self.tts.change_voice(voice_query)

    def list_voices(self):
        """Vocalizes available voice personalities."""
        voices = self.tts.get_available_voices()
        names = [v.split(" (")[0] for v in voices.keys()]
        msg = f"Available voice personalities include: {', '.join(names)}, sir. You can say 'change voice to' followed by any name."
        self.tts.speak(msg)



