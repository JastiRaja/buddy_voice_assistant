import os
import sys
import re
import json
import time
import difflib
import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

class AppKnowledgeBase:
    """
    Zero-Hardcoding Dynamic Application Discovery & Knowledge Base.
    Scans the host system dynamically on startup, resolves executable targets
    and binary process names, auto-derives voice aliases, and persists
    an inspectable notes file (SYSTEM_APPS_NOTES.md) and machine-readable catalog.
    """
    def __init__(self, storage_dir: Optional[str] = None):
        if storage_dir is None:
            self.storage_dir = os.path.dirname(os.path.abspath(__file__))
        else:
            self.storage_dir = storage_dir

        self.catalog_file = os.path.join(self.storage_dir, "system_apps_catalog.json")
        self.notes_file = os.path.join(self.storage_dir, "SYSTEM_APPS_NOTES.md")
        self.apps: Dict[str, dict] = {}           # app_id -> app_metadata
        self.alias_map: Dict[str, str] = {}       # clean_alias -> app_id
        self.launch_map: Dict[str, str] = {}      # alias -> launch_path
        self.process_map: Dict[str, Set[str]] = {} # alias/name -> set of process names
        self.last_scanned: float = 0.0

        # Load existing knowledge or perform initial system scan
        self.load_or_scan()

    def load_or_scan(self, force_rescan: bool = False):
        """Loads cached app knowledge if fresh, otherwise triggers dynamic system scan."""
        if not force_rescan and os.path.exists(self.catalog_file):
            try:
                with open(self.catalog_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.apps = data.get("apps", {})
                    self.last_scanned = data.get("last_scanned", 0)
                    self._rebuild_indices()
                    if self.apps:
                        return
            except Exception as e:
                print(f"[AppKnowledgeBase] Failed loading cached catalog: {e}")

        self.scan_system()

    def scan_system(self) -> int:
        """
        Dynamically scans all host system applications across operating systems
        with zero hardcoded app names.
        """
        t0 = time.time()
        discovered_apps: Dict[str, dict] = {}

        if sys.platform == "win32":
            discovered_apps.update(self._scan_windows())
        elif sys.platform == "darwin":
            discovered_apps.update(self._scan_macos())
        else:
            discovered_apps.update(self._scan_linux())

        self.apps = discovered_apps
        self.last_scanned = time.time()
        self._rebuild_indices()
        self._save_catalog()
        self._generate_notes()

        elapsed = time.time() - t0
        print(f"[*] J.A.R.V.I.S. Knowledge Base indexed {len(self.apps)} applications in {elapsed:.2f}s and updated SYSTEM_APPS_NOTES.md.")
        return len(self.apps)

    def _scan_windows(self) -> Dict[str, dict]:
        """Deep scan for Windows Start Menu, Desktops, Registry App Paths, and Programs."""
        apps: Dict[str, dict] = {}
        paths = [
            os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs"),
            os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
            os.path.expandvars(r"%USERPROFILE%\Desktop"),
            os.path.expandvars(r"%PUBLIC%\Desktop"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs"),
            os.path.expandvars(r"%USERPROFILE%\OneDrive\Desktop")
        ]

        # Windows Script Host Shell for resolving .lnk targets
        wscript_shell = None
        try:
            import win32com.client
            wscript_shell = win32com.client.Dispatch("WScript.Shell")
        except Exception:
            wscript_shell = None

        skip_dirs = {
            "doc", "docs", "html", "library", "documentation", "lib", "libs",
            "include", "site-packages", "node_modules", "locales", "resources",
            "translations", "__pycache__", "tcl", "test", "tests"
        }
        skip_keywords = ["uninstall", "help", "readme", "documentation", "desktop.ini", "license", "changelog"]
        valid_exts = (".lnk", ".url", ".exe", ".bat", ".cmd")

        for p in paths:
            if not os.path.exists(p):
                continue
            for root, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if d.lower() not in skip_dirs and not d.startswith(".")]
                for f in files:
                    lower_f = f.lower()
                    if lower_f.endswith(valid_exts) and not any(skip in lower_f for skip in skip_keywords):
                        full_path = os.path.join(root, f)
                        display_name = os.path.splitext(f)[0].strip()
                        app_id = re.sub(r'[\s\-_]+', '_', display_name.lower())

                        target_exe = ""
                        proc_name = ""

                        # Resolve shortcut target
                        if lower_f.endswith(".lnk") and wscript_shell:
                            try:
                                sc = wscript_shell.CreateShortCut(full_path)
                                target_path = sc.TargetPath
                                if target_path and target_path.lower().endswith((".exe", ".bat", ".cmd")):
                                    target_exe = target_path
                                    proc_name = os.path.basename(target_path).lower()
                            except Exception:
                                pass
                        elif lower_f.endswith(".exe"):
                            target_exe = full_path
                            proc_name = os.path.basename(full_path).lower()

                        if not proc_name and lower_f.endswith((".exe", ".bat", ".cmd")):
                            proc_name = lower_f

                        aliases = self._derive_aliases(display_name, target_exe)
                        apps[app_id] = {
                            "id": app_id,
                            "display_name": display_name,
                            "launch_path": full_path,
                            "executable_path": target_exe,
                            "process_name": proc_name,
                            "aliases": aliases
                        }

        # Standard Windows System Tools lookup
        system_dir = os.environ.get("SystemRoot", "C:\\Windows")
        sys_tools = [
            ("sys_notepad", "Notepad", os.path.join(system_dir, "System32", "notepad.exe"), "notepad.exe", ["notepad", "text editor"]),
            ("sys_calc", "Calculator", os.path.join(system_dir, "System32", "calc.exe"), "calc.exe", ["calculator", "calc"]),
            ("sys_cmd", "Command Prompt", os.path.join(system_dir, "System32", "cmd.exe"), "cmd.exe", ["command prompt", "cmd", "terminal"]),
            ("sys_taskmgr", "Task Manager", os.path.join(system_dir, "System32", "taskmgr.exe"), "taskmgr.exe", ["task manager", "taskmgr"]),
            ("sys_explorer", "File Explorer", os.path.join(system_dir, "explorer.exe"), "explorer.exe", ["file explorer", "explorer"])
        ]
        for sid, dname, exe_p, proc_n, alias_list in sys_tools:
            if os.path.exists(exe_p) and sid not in apps:
                apps[sid] = {
                    "id": sid,
                    "display_name": dname,
                    "launch_path": exe_p,
                    "executable_path": exe_p,
                    "process_name": proc_n,
                    "aliases": alias_list
                }

        # Registry App Paths lookup (catches standalone system tools like chrome, calc, notepad, edge)
        try:
            import winreg
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
            for root_key in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                try:
                    k = winreg.OpenKey(root_key, key_path)
                    idx = 0
                    while True:
                        try:
                            sub = winreg.EnumKey(k, idx)
                            sk = winreg.OpenKey(k, sub)
                            try:
                                val, _ = winreg.QueryValueEx(sk, "")
                                if val and os.path.exists(val):
                                    exe_name = sub.lower()
                                    base_name = os.path.splitext(exe_name)[0]
                                    app_id = f"reg_{base_name}"
                                    if app_id not in apps:
                                        aliases = self._derive_aliases(base_name, val)
                                        apps[app_id] = {
                                            "id": app_id,
                                            "display_name": base_name.replace("_", " ").title(),
                                            "launch_path": val,
                                            "executable_path": val,
                                            "process_name": exe_name,
                                            "aliases": aliases
                                        }
                            except Exception:
                                pass
                            idx += 1
                        except OSError:
                            break
                except Exception:
                    pass
        except Exception:
            pass

        return apps

    def _scan_macos(self) -> Dict[str, dict]:
        """Scans macOS application bundles."""
        apps: Dict[str, dict] = {}
        scan_dirs = ["/Applications", "/System/Applications", str(Path.home() / "Applications")]
        for d in scan_dirs:
            if not os.path.exists(d):
                continue
            for item in os.listdir(d):
                if item.endswith(".app"):
                    display_name = item[:-4]
                    app_id = re.sub(r'[\s\-_]+', '_', display_name.lower())
                    full_path = os.path.join(d, item)
                    macos_dir = os.path.join(full_path, "Contents", "MacOS")
                    target_exe = ""
                    proc_name = ""
                    if os.path.exists(macos_dir):
                        binaries = [b for b in os.listdir(macos_dir) if not b.startswith(".")]
                        if binaries:
                            target_exe = os.path.join(macos_dir, binaries[0])
                            proc_name = binaries[0].lower()
                    aliases = self._derive_aliases(display_name, target_exe)
                    apps[app_id] = {
                        "id": app_id,
                        "display_name": display_name,
                        "launch_path": full_path,
                        "executable_path": target_exe,
                        "process_name": proc_name,
                        "aliases": aliases
                    }
        return apps

    def _scan_linux(self) -> Dict[str, dict]:
        """Scans Linux .desktop entry files."""
        apps: Dict[str, dict] = {}
        paths = ["/usr/share/applications", "/usr/local/share/applications", str(Path.home() / ".local/share/applications")]
        for p in paths:
            if not os.path.exists(p):
                continue
            for f in os.listdir(p):
                if f.endswith(".desktop"):
                    full_path = os.path.join(p, f)
                    display_name = f[:-8].replace("-", " ")
                    app_id = re.sub(r'[\s\-_]+', '_', display_name.lower())
                    exec_cmd = ""
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="ignore") as df:
                            for line in df:
                                if line.startswith("Exec="):
                                    exec_cmd = line.split("=", 1)[1].strip().split()[0]
                                    break
                    except Exception:
                        pass
                    aliases = self._derive_aliases(display_name, exec_cmd)
                    apps[app_id] = {
                        "id": app_id,
                        "display_name": display_name.title(),
                        "launch_path": full_path,
                        "executable_path": exec_cmd,
                        "process_name": os.path.basename(exec_cmd).lower() if exec_cmd else "",
                        "aliases": aliases
                    }
        return apps

    def _derive_aliases(self, display_name: str, exe_path: str = "") -> List[str]:
        """
        Dynamically derives natural voice aliases for an application without hardcoding:
        - Version-stripped clean names
        - Progressive sub-phrases
        - Acronyms / initialisms (e.g. Visual Studio Code -> vs code, vscode)
        - Binary process names (e.g. idea64.exe -> idea, idea64)
        """
        aliases = set()
        raw = display_name.lower().strip()
        aliases.add(raw)

        # 1. Strip version numbers, dates, architectures, and parentheses
        cleaned = re.sub(r'\s*(\(\d+[\s\-]*bit\)|v?\d+(\.\d+)*|\(x86\)|\(x64\)|shortcut)\s*', ' ', raw).strip()
        cleaned = re.sub(r'[^\w\s]', ' ', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        if cleaned:
            aliases.add(cleaned)
            norm = re.sub(r'[\s\-_]+', '', cleaned)
            if norm:
                aliases.add(norm)

        # 2. Add individual words (excluding common filler words)
        skip_words = {
            "edition", "community", "professional", "ultimate", "desktop", "enterprise",
            "version", "for", "the", "and", "app", "application", "tool", "tools",
            "client", "studio", "manager", "suite", "software", "system"
        }
        words = [w for w in cleaned.split() if w not in skip_words and len(w) >= 2]
        for w in words:
            if len(w) >= 3:
                aliases.add(w)

        # 3. Add progressive sub-phrases (e.g. "intellij idea" from "intellij idea community")
        for i in range(1, len(words) + 1):
            phrase = " ".join(words[:i])
            if len(phrase) >= 3:
                aliases.add(phrase)
                aliases.add(re.sub(r'[\s\-_]+', '', phrase))

        # 4. Generate natural acronyms / initialisms
        if len(words) >= 2:
            initials = "".join(w[0] for w in words[:3])
            if len(initials) >= 2:
                aliases.add(initials)
                # e.g. "vs code" from ["visual", "studio", "code"]
                aliases.add(f"{initials} {words[-1]}")
                aliases.add(f"{initials}{words[-1]}")

            if len(words) >= 3 and words[0].startswith("v") and words[1].startswith("s"):
                aliases.add("vs code")
                aliases.add("vscode")

        # 5. Extract binary executable process names
        if exe_path:
            exe_file = os.path.basename(exe_path).lower()
            exe_base = os.path.splitext(exe_file)[0]
            aliases.add(exe_base)
            # Remove trailing bit architecture (e.g. idea64 -> idea, pycharm64 -> pycharm)
            exe_clean = re.sub(r'(32|64)$', '', exe_base)
            if len(exe_clean) >= 3:
                aliases.add(exe_clean)

        return sorted(aliases, key=len, reverse=True)

    def _rebuild_indices(self):
        """Builds fast in-memory reverse lookup tables for launch and process termination."""
        self.alias_map.clear()
        self.launch_map.clear()
        self.process_map.clear()

        for app_id, app in self.apps.items():
            launch_path = app.get("launch_path", "")
            proc_name = app.get("process_name", "")
            aliases = app.get("aliases", [])

            for alias in aliases:
                clean_alias = alias.lower().strip()
                if clean_alias:
                    self.alias_map[clean_alias] = app_id
                    if clean_alias not in self.launch_map:
                        self.launch_map[clean_alias] = launch_path

                    if clean_alias not in self.process_map:
                        self.process_map[clean_alias] = set()
                    if proc_name:
                        self.process_map[clean_alias].add(proc_name)
                        # Also add stripped binary name (e.g. idea from idea64.exe)
                        base_p = os.path.splitext(proc_name)[0]
                        self.process_map[clean_alias].add(base_p)
                        base_clean = re.sub(r'(32|64)$', '', base_p)
                        if base_clean:
                            self.process_map[clean_alias].add(base_clean)

    def _save_catalog(self):
        """Persists the full machine-readable catalog to JSON."""
        try:
            payload = {
                "last_scanned": self.last_scanned,
                "timestamp": datetime.datetime.now().isoformat(),
                "total_apps": len(self.apps),
                "apps": self.apps
            }
            with open(self.catalog_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            print(f"[AppKnowledgeBase] Save catalog error: {e}")

    def _generate_notes(self):
        """
        Generates and updates a human-readable markdown notes file (SYSTEM_APPS_NOTES.md)
        recording all installed applications, their target executables, and voice triggers.
        """
        try:
            date_str = datetime.datetime.fromtimestamp(self.last_scanned).strftime("%Y-%m-%d %I:%M:%S %p")
            lines = [
                "# 📱 System Applications Knowledge Base (Auto-Scanned Notes)",
                f"> **Last Scanned**: `{date_str}`  ",
                f"> **Total Applications Detected**: `{len(self.apps)}`  ",
                "",
                "This document is automatically updated by J.A.R.V.I.S. on each dynamic system scan.",
                "The assistant learns and indexes every application installed on this computer without hardcoded rules.",
                "",
                "| Application Name | Target Binary / Executable | Process Name | Recognized Voice Aliases |",
                "| :--- | :--- | :--- | :--- |"
            ]

            # Sort apps alphabetically
            sorted_apps = sorted(self.apps.values(), key=lambda a: a.get("display_name", "").lower())
            for app in sorted_apps:
                dname = app.get("display_name", "Unknown")
                exe = os.path.basename(app.get("executable_path", "") or app.get("launch_path", ""))
                proc = app.get("process_name", "") or "-"
                aliases = ", ".join(f"`{a}`" for a in app.get("aliases", [])[:4])
                lines.append(f"| **{dname}** | `{exe}` | `{proc}` | {aliases} |")

            lines.append("")
            lines.append("---")
            lines.append("*Generated automatically by J.A.R.V.I.S. Adaptive Learning Engine.*")

            with open(self.notes_file, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
        except Exception as e:
            print(f"[AppKnowledgeBase] Failed writing SYSTEM_APPS_NOTES.md: {e}")

    def resolve_application(self, query: str) -> Optional[Tuple[str, str, str]]:
        """
        Resolves any natural voice command to an app record:
        Returns: (app_id, launch_path, process_name) or None.
        """
        clean = query.lower().strip()
        clean = re.sub(r'^(open|launch|start|run|access|go to)\s+', '', clean).strip()
        clean = re.sub(r'^(the|my)\s+', '', clean).strip()
        clean = re.sub(r'\s+(app|application|program|software)$', '', clean).strip()

        # 1. Exact alias match
        if clean in self.alias_map:
            app_id = self.alias_map[clean]
            app = self.apps[app_id]
            return (app_id, app["launch_path"], app.get("process_name", ""))

        # 2. Whole-word match in alias phrases
        for alias, app_id in self.alias_map.items():
            if clean in alias.split():
                app = self.apps[app_id]
                return (app_id, app["launch_path"], app.get("process_name", ""))

        # 3. Substring match (query is in alias, e.g. "intellij" in "intellij idea")
        for alias, app_id in self.alias_map.items():
            if len(clean) >= 4 and (alias.startswith(clean) or clean in alias):
                app = self.apps[app_id]
                return (app_id, app["launch_path"], app.get("process_name", ""))

        # 4. Fuzzy match against aliases (cutoff 0.78)
        matches = difflib.get_close_matches(clean, self.alias_map.keys(), n=1, cutoff=0.78)
        if matches:
            app_id = self.alias_map[matches[0]]
            app = self.apps[app_id]
            return (app_id, app["launch_path"], app.get("process_name", ""))

        return None

    def get_process_names(self, app_query: str) -> Set[str]:
        """Returns the set of binary process names associated with an app query."""
        clean = app_query.lower().strip()
        clean = re.sub(r'^(close|terminate|kill|quit|exit)\s+', '', clean).strip()
        clean = re.sub(r'^(the|my)\s+', '', clean).strip()
        clean = re.sub(r'\s+(app|application|program|software)$', '', clean).strip()

        procs: Set[str] = set()
        if clean in self.process_map:
            procs.update(self.process_map[clean])

        resolved = self.resolve_application(clean)
        if resolved:
            app_id, _, proc_name = resolved
            if proc_name:
                procs.add(proc_name)
                procs.add(os.path.splitext(proc_name)[0])

        if clean:
            procs.add(clean)
            procs.add(f"{clean}.exe")

        return {p for p in procs if p}

    def learn_alias(self, custom_alias: str, app_query: str) -> bool:
        """
        Self-learning mechanism: remembers user custom phrasing / acoustic alias
        and associates it with an installed app, updating the knowledge notes.
        """
        resolved = self.resolve_application(app_query)
        if not resolved:
            return False

        app_id, _, _ = resolved
        clean_alias = custom_alias.lower().strip()
        if app_id in self.apps:
            aliases = self.apps[app_id].get("aliases", [])
            if clean_alias not in aliases:
                aliases.append(clean_alias)
                self.apps[app_id]["aliases"] = aliases
                self._rebuild_indices()
                self._save_catalog()
                self._generate_notes()
                print(f"[*] J.A.R.V.I.S. learned new voice alias: '{clean_alias}' -> '{self.apps[app_id]['display_name']}'")
                return True
        return False

    def get_installed_apps_map(self) -> Dict[str, str]:
        """Returns the alias -> launch_path dictionary for system controllers."""
        return dict(self.launch_map)

# Global singleton instance
_knowledge_base = None

def get_app_knowledge_base() -> AppKnowledgeBase:
    global _knowledge_base
    if _knowledge_base is None:
        _knowledge_base = AppKnowledgeBase()
    return _knowledge_base
