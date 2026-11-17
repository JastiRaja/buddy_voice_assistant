import os
import re
import sys
import shutil
import platform
import subprocess
from typing import Dict, List, Optional, Tuple
from pathlib import Path

class BaseOSAdapter:
    """Abstract base adapter for cross-platform OS interactions."""
    def __init__(self):
        self.system = platform.system()
        self.home = Path.home()

    @property
    def modifier_key(self) -> str:
        return 'command' if self.system == 'Darwin' else 'ctrl'

    @property
    def alt_key(self) -> str:
        return 'option' if self.system == 'Darwin' else 'alt'

    @property
    def super_key(self) -> str:
        if self.system == 'Darwin':
            return 'command'
        elif self.system == 'Windows':
            return 'win'
        return 'super'

    def scan_installed_apps(self) -> Dict[str, str]:
        return {}

    def open_path(self, path: str) -> bool:
        try:
            if self.system == 'Darwin':
                subprocess.Popen(['open', path])
            elif self.system == 'Linux':
                subprocess.Popen(['xdg-open', path])
            else:
                if hasattr(os, 'startfile'):
                    os.startfile(path)
                else:
                    subprocess.Popen(['explorer.exe', path])
            return True
        except Exception as e:
            print(f"[OSAdapter open_path Error] {e}")
            return False

    PROTECTED_PROCESSES = {
        "system", "system idle process", "registry", "smss.exe", "csrss.exe",
        "wininit.exe", "services.exe", "lsass.exe", "svchost.exe", "fontdrvhost.exe",
        "dwm.exe", "explorer.exe", "spoolsv.exe", "sihost.exe", "taskhostw.exe",
        "conhost.exe", "runtimebroker.exe", "python.exe", "pythonw.exe", "python",
        "python3", "init", "systemd", "kernel", "launchd"
    }

    def close_app(self, process_or_title: str) -> bool:
        clean = process_or_title.lower().strip()
        if not clean or clean in {"app", "window", "process", "program", "system", "host", "the"}:
            return False
        try:
            import psutil
            killed = False
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    pname = (proc.info['name'] or '').lower()
                    if pname in self.PROTECTED_PROCESSES or os.path.splitext(pname)[0] in self.PROTECTED_PROCESSES:
                        continue
                    base_name = os.path.splitext(pname)[0]
                    matched = (
                        clean == pname or
                        clean == base_name or
                        f"{clean}.exe" == pname or
                        (len(clean) >= 4 and base_name.startswith(clean))
                    )
                    if matched:
                        proc.terminate()
                        killed = True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return killed
        except Exception:
            return False

    def lock_screen(self) -> bool:
        return False

    def sleep_system(self) -> bool:
        return False

    def restart_system(self) -> bool:
        return False

    def shutdown_system(self, delay_minutes: int = 0) -> bool:
        return False

    def cancel_shutdown(self) -> bool:
        return False

    def empty_recycle_bin(self) -> bool:
        return False

    def get_standard_folder(self, folder_name: str) -> str:
        clean = folder_name.lower().strip()
        mapping = {
            "downloads": self.home / "Downloads",
            "download": self.home / "Downloads",
            "documents": self.home / "Documents",
            "document": self.home / "Documents",
            "desktop": self.home / "Desktop",
            "pictures": self.home / "Pictures",
            "photos": self.home / "Pictures",
            "videos": self.home / "Videos",
            "music": self.home / "Music",
            "projects": self.home / "Projects"
        }
        target = mapping.get(clean, self.home / clean.capitalize())
        return str(target if target.exists() else self.home)

    def list_volumes(self) -> List[str]:
        return []

    def open_this_pc(self) -> bool:
        return self.open_path(str(self.home))

    def open_drive(self, drive_identifier: str) -> bool:
        return False

    def snap_window(self, direction: str):
        pass

    def minimize_all(self):
        pass


class WindowsAdapter(BaseOSAdapter):
    """Windows-specific OS adapter with robust fallback mechanisms."""
    def __init__(self):
        super().__init__()
        self.system = 'Windows'
    def scan_installed_apps(self) -> Dict[str, str]:
        apps = {}
        user_home = str(self.home)
        onedrive = os.path.join(user_home, "OneDrive")
        paths = [
            os.path.expandvars(r'%ProgramData%\Microsoft\Windows\Start Menu\Programs'),
            os.path.expandvars(r'%APPDATA%\Microsoft\Windows\Start Menu\Programs'),
            os.path.expandvars(r'%USERPROFILE%\Desktop'),
            os.path.join(onedrive, "Desktop"),
            os.path.expandvars(r'%PUBLIC%\Desktop'),
            os.path.expandvars(r'%LOCALAPPDATA%\Programs')
        ]
        valid_exts = ('.lnk', '.url', '.exe', '.bat', '.cmd')
        skip_dirs = {'doc', 'docs', 'html', 'library', 'documentation', 'lib', 'libs', 'include', 'site-packages', 'node_modules', 'locales', 'resources', 'translations', '__pycache__', 'tcl', 'test', 'tests'}
        skip_keywords = ['uninstall', 'help', 'readme', 'documentation', 'desktop.ini', 'license', 'changelog']

        for p in paths:
            if os.path.exists(p):
                for root, dirs, files in os.walk(p):
                    dirs[:] = [d for d in dirs if d.lower() not in skip_dirs and not d.startswith('.')]
                    for f in files:
                        lower_f = f.lower()
                        if lower_f.endswith(valid_exts) and not any(skip in lower_f for skip in skip_keywords):
                            name = os.path.splitext(f)[0].lower().strip()
                            full_path = os.path.join(root, f)
                            if name not in apps or full_path.lower().endswith('.lnk'):
                                apps[name] = full_path

                            simplified = re.sub(r'\s*(\(\d+[\s\-]*bit\)|v?\d+(\.\d+)*|\(x86\)|\(x64\)|shortcut)\s*', '', name).strip()
                            if simplified:
                                if simplified not in apps or full_path.lower().endswith('.lnk'):
                                    apps[simplified] = full_path

                            norm = re.sub(r'[\s\-_]+', '', simplified)
                            if norm:
                                if norm not in apps or full_path.lower().endswith('.lnk'):
                                    apps[norm] = full_path

        return apps

    def open_path(self, path: str) -> bool:
        try:
            if hasattr(os, 'startfile') and os.path.exists(path):
                os.startfile(path)
                return True
            subprocess.Popen(['explorer.exe', path])
            return True
        except Exception:
            return super().open_path(path)

    def lock_screen(self) -> bool:
        try:
            import ctypes
            ctypes.windll.user32.LockWorkStation()
            return True
        except Exception:
            subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], check=False)
            return True

    def sleep_system(self) -> bool:
        subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], check=False)
        return True

    def restart_system(self) -> bool:
        subprocess.run(["shutdown", "/r", "/t", "5"], check=False)
        return True

    def shutdown_system(self, delay_minutes: int = 0) -> bool:
        secs = max(0, delay_minutes * 60)
        subprocess.run(["shutdown", "/a"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["shutdown", "/s", "/t", str(secs)], check=False)
        return True

    def cancel_shutdown(self) -> bool:
        subprocess.run(["shutdown", "/a"], check=False)
        return True

    def empty_recycle_bin(self) -> bool:
        try:
            import ctypes
            # Flags: SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND = 7
            ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 7)
            return True
        except Exception:
            try:
                subprocess.run(
                    ["powershell.exe", "-NoProfile", "-Command", "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"],
                    check=False
                )
                return True
            except Exception:
                return False

    def _get_registry_shell_folders(self) -> dict:
        """Queries Windows User Shell Folders dynamically from registry for relocated or custom paths."""
        folders = {}
        reg_names = {
            'my pictures': 'pictures',
            'personal': 'documents',
            '{f42ee2d3-909f-4907-8871-4c22fc0bf756}': 'documents',
            'desktop': 'desktop',
            '{374de290-123f-4565-9164-39c4925e467b}': 'downloads',
            'my video': 'videos',
            '{35286a68-3c57-41a1-bbb1-0eae73d76c95}': 'videos',
            'my music': 'music',
            '{ab5fb87b-7ce2-4f83-915d-550846c9537b}': 'camera roll',
            '{767e6811-49cb-4273-87c2-20f355e1085b}': 'camera roll',
            '{3b193882-d3ad-4eab-965a-69829d1fb59f}': 'saved pictures',
            '{b7bede81-df94-4682-a7d8-57a52620b86f}': 'screenshots'
        }
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders') as key:
                i = 0
                while True:
                    try:
                        name, val, typ = winreg.EnumValue(key, i)
                        expanded = os.path.expandvars(val)
                        clean_name = name.lower()
                        if clean_name in reg_names and os.path.exists(expanded):
                            category = reg_names[clean_name]
                            if category not in folders:
                                folders[category] = []
                            if expanded not in folders[category]:
                                folders[category].append(expanded)
                        i += 1
                    except OSError:
                        break
        except Exception:
            pass
        return folders

    def get_standard_folder(self, folder_name: str) -> str:
        clean = folder_name.lower().strip()
        user_home = self.home
        onedrive = user_home / "OneDrive"

        # 1. Query Windows User Shell Folders dynamically from Registry
        reg_folders = self._get_registry_shell_folders()
        if clean in reg_folders and reg_folders[clean]:
            return reg_folders[clean][0]

        # 2. Standard user library mappings across Home and OneDrive
        folder_map = {
            "downloads": [user_home / "Downloads", onedrive / "Downloads"],
            "download": [user_home / "Downloads", onedrive / "Downloads"],
            "documents": [user_home / "Documents", onedrive / "Documents"],
            "document": [user_home / "Documents", onedrive / "Documents"],
            "desktop": [user_home / "Desktop", onedrive / "Desktop"],
            "pictures": [user_home / "Pictures", onedrive / "Pictures"],
            "photos": [user_home / "Pictures", onedrive / "Pictures"],
            "videos": [user_home / "Videos"],
            "music": [user_home / "Music"],
            "projects": [user_home / "Projects"]
        }

        # 3. Dynamically discover projects / code repositories on any mounted drive
        if clean in ["projects", "project", "code"]:
            for vol in self.list_volumes():
                for proj_dir in ["Projects", "My Projects", "source/repos", "Workspace", "workspace"]:
                    cand = Path(vol) / proj_dir
                    if cand.exists():
                        folder_map["projects"].append(cand)

        def find_existing(candidates):
            for c in candidates:
                try:
                    if Path(c).exists():
                        return str(c)
                except Exception:
                    pass
            return str(candidates[0])

        if clean in folder_map:
            return find_existing(folder_map[clean])

        return str(user_home / clean.capitalize())

    def list_volumes(self) -> List[str]:
        drives = []
        for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
            drive_path = f"{letter}:\\"
            if os.path.exists(drive_path):
                drives.append(drive_path)
        return drives

    def open_this_pc(self) -> bool:
        try:
            subprocess.Popen(['explorer.exe', 'shell:MyComputerFolder'])
            return True
        except Exception:
            return self.open_path(str(self.home))

    def open_drive(self, drive_letter: str) -> bool:
        clean = drive_letter.upper().replace("DRIVE", "").replace(":", "").strip()
        clean = "C" if clean in ["SEE", "SEA", "C"] else ("D" if clean in ["DEE", "D"] else clean)
        path = f"{clean}:\\"
        if os.path.exists(path):
            return self.open_path(path)
        return False

    def snap_window(self, direction: str):
        import pyautogui
        if direction == "left":
            pyautogui.hotkey('win', 'left')
        elif direction == "right":
            pyautogui.hotkey('win', 'right')
        elif direction in ["up", "maximize"]:
            pyautogui.hotkey('win', 'up')
        elif direction in ["down", "minimize"]:
            pyautogui.hotkey('win', 'down')

    def minimize_all(self):
        import pyautogui
        pyautogui.hotkey('win', 'd')


class MacOSAdapter(BaseOSAdapter):
    """macOS-specific adapter using AppleScript and macOS system binaries."""
    def __init__(self):
        super().__init__()
        self.system = 'Darwin'

    def scan_installed_apps(self) -> Dict[str, str]:
        apps = {}
        scan_dirs = ["/Applications", "/System/Applications", str(self.home / "Applications")]
        for d in scan_dirs:
            if os.path.exists(d):
                for item in os.listdir(d):
                    if item.endswith(".app"):
                        name = item[:-4].lower().strip()
                        apps[name] = os.path.join(d, item)
        return apps

    def lock_screen(self) -> bool:
        subprocess.run(["pmset", "displaysleepnow"], check=False)
        return True

    def sleep_system(self) -> bool:
        subprocess.run(["osascript", "-e", 'tell application "System Events" to sleep'], check=False)
        return True

    def restart_system(self) -> bool:
        subprocess.run(["osascript", "-e", 'tell application "System Events" to restart'], check=False)
        return True

    def shutdown_system(self, delay_minutes: int = 0) -> bool:
        subprocess.run(["osascript", "-e", 'tell application "System Events" to shut down'], check=False)
        return True

    def empty_recycle_bin(self) -> bool:
        subprocess.run(["osascript", "-e", 'tell application "Finder" to empty trash'], check=False)
        return True

    def list_volumes(self) -> List[str]:
        volumes_dir = "/Volumes"
        if os.path.exists(volumes_dir):
            return [os.path.join(volumes_dir, v) for v in os.listdir(volumes_dir) if not v.startswith('.')]
        return []

    def open_this_pc(self) -> bool:
        return self.open_path("/Volumes")

    def snap_window(self, direction: str):
        # On macOS, use standard window management or shortcuts
        import pyautogui
        if direction in ["up", "maximize"]:
            pyautogui.hotkey('ctrl', 'command', 'f')
        else:
            pyautogui.hotkey('ctrl', 'option', direction)

    def minimize_all(self):
        import pyautogui
        pyautogui.hotkey('command', 'option', 'm')


class LinuxAdapter(BaseOSAdapter):
    """Linux-specific adapter using XDG desktop entries and freedesktop standards."""
    def __init__(self):
        super().__init__()
        self.system = 'Linux'

    def scan_installed_apps(self) -> Dict[str, str]:
        apps = {}
        paths = ["/usr/share/applications", "/usr/local/share/applications", str(self.home / ".local/share/applications")]
        for p in paths:
            if os.path.exists(p):
                for f in os.listdir(p):
                    if f.endswith(".desktop"):
                        name = f[:-8].lower().replace("-", " ")
                        full_path = os.path.join(p, f)
                        apps[name] = full_path
        return apps

    def lock_screen(self) -> bool:
        for cmd in [["loginctl", "lock-session"], ["xdg-screensaver", "lock"], ["gnome-screensaver-command", "-l"]]:
            try:
                res = subprocess.run(cmd, check=False)
                if res.returncode == 0:
                    return True
            except Exception:
                continue
        return False

    def sleep_system(self) -> bool:
        subprocess.run(["systemctl", "suspend"], check=False)
        return True

    def restart_system(self) -> bool:
        subprocess.run(["systemctl", "reboot"], check=False)
        return True

    def shutdown_system(self, delay_minutes: int = 0) -> bool:
        subprocess.run(["shutdown", f"+{delay_minutes}"], check=False)
        return True

    def cancel_shutdown(self) -> bool:
        subprocess.run(["shutdown", "-c"], check=False)
        return True

    def empty_recycle_bin(self) -> bool:
        trash_dir = self.home / ".local/share/Trash"
        if trash_dir.exists():
            success = True
            for sub in ["files", "info"]:
                target_sub = trash_dir / sub
                if target_sub.exists():
                    for item in target_sub.iterdir():
                        try:
                            if item.is_dir():
                                shutil.rmtree(str(item), ignore_errors=True)
                            else:
                                item.unlink(missing_ok=True)
                        except Exception:
                            success = False
            return success
        return False

    def list_volumes(self) -> List[str]:
        vols = []
        for p in ["/media", "/mnt"]:
            if os.path.exists(p):
                for item in os.listdir(p):
                    vols.append(os.path.join(p, item))
        return vols

    def open_this_pc(self) -> bool:
        return self.open_path("/")

    def snap_window(self, direction: str):
        import pyautogui
        pyautogui.hotkey('super', direction)

    def minimize_all(self):
        import pyautogui
        pyautogui.hotkey('super', 'd')


def get_os_adapter() -> BaseOSAdapter:
    """Factory function returning the active platform adapter."""
    plat = platform.system()
    if plat == 'Windows':
        return WindowsAdapter()
    elif plat == 'Darwin':
        return MacOSAdapter()
    elif plat == 'Linux':
        return LinuxAdapter()
    return BaseOSAdapter()
