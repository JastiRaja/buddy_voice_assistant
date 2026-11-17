import os
import sys
import io
import re
import time
import base64
import ctypes
from ctypes import wintypes
import requests
import psutil
import pyautogui
from PIL import Image, ImageDraw, ImageFont
from config import load_user_settings
from screen_ocr import ScreenOCRExtractor

class VisionAssistant:
    def __init__(self, tts, hud=None):
        self.tts = tts
        self.hud = hud
        self.ocr = ScreenOCRExtractor(self)

    def capture_screen(self) -> Image.Image:
        """Captures the primary monitor screenshot, temporarily hiding the HUD overlay to prevent self-capture."""
        hud_root = getattr(self.hud, 'root', None)
        did_hide = False
        try:
            if hud_root and hasattr(hud_root, 'attributes'):
                hud_root.attributes("-alpha", 0.0)
                hud_root.update()
                did_hide = True
                time.sleep(0.06)  # Give DWM desktop compositor 60ms to paint the window underneath
        except Exception:
            pass

        try:
            return pyautogui.screenshot()
        except Exception:
            try:
                from PIL import ImageGrab
                return ImageGrab.grab()
            except Exception as e:
                print(f"[Vision Capture Error] {e}")
                return Image.new("RGB", (1920, 1080), color=(15, 23, 42))
        finally:
            if did_hide and hud_root:
                try:
                    hud_root.attributes("-alpha", 0.96)
                    hud_root.update()
                except Exception:
                    pass

    def get_screen_telemetry(self) -> dict:
        """
        Extracts comprehensive on-screen telemetry, active window geometry,
        foreground process details, task category, and visible applications.
        Filters out assistant HUD / overlay so only actual user applications are inspected.
        """
        sw, sh = pyautogui.size()
        telemetry = {
            "resolution": f"{sw}x{sh}",
            "width": sw,
            "height": sh,
            "timestamp": time.strftime("%I:%M:%S %p"),
            "active_title": "Desktop / Windows",
            "process_name": "explorer.exe",
            "pid": None,
            "category": "Desktop Environment",
            "rect": (0, 0, sw, sh),
            "is_fullscreen": False,
            "child_controls": [],
            "visible_windows": [],
            "has_error_dialog": False,
            "error_text": ""
        }

        # 1. Active Window Inspection via Win32 API (Windows) or Adapter
        try:
            if hasattr(ctypes, 'windll'):
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                current_pid = os.getpid()
                GW_HWNDNEXT = 2

                # If focused window is J.A.R.V.I.S. HUD or assistant process, walk Z-order to inspect user's true window
                checked = 0
                while hwnd and checked < 15:
                    checked += 1
                    pid = wintypes.DWORD()
                    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                    win_title = ""
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
                        win_title = buff.value.strip()

                    is_assistant = (
                        pid.value == current_pid or
                        any(k in win_title.lower() for k in ["j.a.r.v.i.s.", "jarvis", "buddy", "visualizer", "commands catalog"])
                    )

                    if not is_assistant and ctypes.windll.user32.IsWindowVisible(hwnd) and length > 0:
                        break  # Found user's primary application window
                    hwnd = ctypes.windll.user32.GetWindow(hwnd, GW_HWNDNEXT)

                if hwnd:
                    # Title
                    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
                        title = buff.value.strip()
                        if title:
                            telemetry["active_title"] = title

                    # Bounds
                    rect = wintypes.RECT()
                    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    w = rect.right - rect.left
                    h = rect.bottom - rect.top
                    telemetry["rect"] = (rect.left, rect.top, rect.right, rect.bottom)
                    if w >= sw * 0.95 and h >= sh * 0.95:
                        telemetry["is_fullscreen"] = True

                    # Process
                    pid = wintypes.DWORD()
                    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    telemetry["pid"] = pid.value
                    try:
                        p = psutil.Process(pid.value)
                        telemetry["process_name"] = p.name()
                    except Exception:
                        pass

                    # Child Controls & Text
                    telemetry["child_controls"] = self._extract_child_controls(hwnd)
            elif sys.platform == 'darwin':
                import subprocess
                try:
                    cmd = "osascript -e 'tell application \"System Events\" to get name of first application process whose frontmost is true'"
                    out = subprocess.check_output(cmd, shell=True, timeout=1).decode('utf-8').strip()
                    if out:
                        telemetry["process_name"] = out
                        telemetry["active_title"] = out
                except Exception:
                    pass
            elif sys.platform.startswith('linux'):
                import subprocess
                import shutil
                try:
                    if shutil.which("xdotool"):
                        w_id = subprocess.check_output(["xdotool", "getactivewindow"], timeout=1).decode().strip()
                        if w_id:
                            w_name = subprocess.check_output(["xdotool", "getwindowname", w_id], timeout=1).decode().strip()
                            w_pid = subprocess.check_output(["xdotool", "getwindowpid", w_id], timeout=1).decode().strip()
                            if w_name:
                                telemetry["active_title"] = w_name
                            if w_pid:
                                telemetry["pid"] = int(w_pid)
                                telemetry["process_name"] = psutil.Process(int(w_pid)).name()
                except Exception:
                    pass
        except Exception as e:
            print(f"[Vision Telemetry Notice] {e}")

        # 2. Categorize Active Application & Context
        proc_lower = telemetry["process_name"].lower()
        title_lower = telemetry["active_title"].lower()

        if any(err_kw in title_lower or err_kw in proc_lower for err_kw in ["error", "exception", "failed", "crash", "warning", "not responding", "alert"]):
            telemetry["has_error_dialog"] = True
            telemetry["category"] = "System Error / Alert Dialog"
        elif any(k in proc_lower for k in ["code", "devenv", "pycharm", "sublime", "notepad++", "eclipse", "idea", "atom"]):
            telemetry["category"] = "Software Development / Code Editor"
        elif any(k in proc_lower for k in ["chrome", "msedge", "firefox", "brave", "opera", "vivaldi"]):
            telemetry["category"] = "Web Browser Navigation"
        elif any(k in proc_lower for k in ["cmd", "powershell", "windowsterminal", "mintty", "bash", "conhost"]):
            telemetry["category"] = "Terminal & Command Console"
        elif any(k in proc_lower for k in ["explorer"]):
            telemetry["category"] = "File System & Folder Management"
        elif any(k in proc_lower for k in ["spotify", "vlc", "wmplayer", "music", "video"]):
            telemetry["category"] = "Media Playback"
        elif any(k in proc_lower for k in ["word", "excel", "powerpnt", "acrobat", "foxit", "notepad"]):
            telemetry["category"] = "Document & Note Editor"
        elif any(k in proc_lower for k in ["discord", "slack", "teams", "telegram", "whatsapp"]):
            telemetry["category"] = "Communication & Collaboration"
        elif any(k in proc_lower for k in ["taskmgr", "settings", "control", "mmc", "regedit"]):
            telemetry["category"] = "System Administration & Settings"
        else:
            telemetry["category"] = "Windows Application"

        # 3. Discover Open Applications in Background
        telemetry["visible_windows"] = self._get_open_apps()

        return telemetry

    def _extract_child_controls(self, hwnd) -> list:
        """Discovers text from buttons, labels, and status bars of the target window."""
        texts = []
        try:
            EnumChildWindows = ctypes.windll.user32.EnumChildWindows
            EnumChildProc = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.LPARAM)
            GetWindowText = ctypes.windll.user32.GetWindowTextW
            GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
            IsWindowVisible = ctypes.windll.user32.IsWindowVisible

            def child_cb(child_hwnd, _):
                if IsWindowVisible(child_hwnd):
                    length = GetWindowTextLength(child_hwnd)
                    if 0 < length < 256:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        GetWindowText(child_hwnd, buff, length + 1)
                        val = buff.value.strip()
                        if val and len(val) > 1 and val not in texts and not val.isdigit():
                            if not any(k in val.lower() for k in ["j.a.r.v.i.s.", "jarvis", "buddy", "neural core", "awaiting command", "continuous session", "telemetry"]):
                                texts.append(val)
                return 1

            EnumChildWindows(hwnd, EnumChildProc(child_cb), 0)
        except Exception:
            pass
        return texts[:12]

    def _get_open_apps(self) -> list:
        """Returns friendly list of top open user applications."""
        apps = []
        try:
            seen_procs = set()
            for p in psutil.process_iter(['name']):
                try:
                    name = p.info['name']
                    lower_name = name.lower()
                    if lower_name.endswith('.exe') and not lower_name.startswith(('svchost', 'system', 'registry', 'smss', 'csrss', 'wininit', 'services', 'lsass', 'runtimebroker', 'shellexperience', 'taskhostw', 'searchhost', 'startmenuexperience', 'textinputhost', 'fontdrvhost', 'dwm', 'ctfmon', 'conhost')):
                        base = os.path.splitext(name)[0].title()
                        if base not in seen_procs:
                            seen_procs.add(base)
                            apps.append(base)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            pass
        return apps[:8]

    def create_annotated_thumbnail(self, screenshot: Image.Image, active_rect: tuple, target_size=(460, 260)) -> Image.Image:
        """
        Creates a high-tech holographic preview thumbnail with glowing
        bounding box overlay for the active window.
        """
        try:
            orig_w, orig_h = screenshot.size
            thumb = screenshot.copy()
            thumb.thumbnail(target_size, Image.Resampling.LANCZOS)
            
            tw, th = thumb.size
            scale_x = tw / float(orig_w) if orig_w else 1.0
            scale_y = th / float(orig_h) if orig_h else 1.0

            x1, y1, x2, y2 = active_rect
            bx1 = max(2, int(x1 * scale_x))
            by1 = max(2, int(y1 * scale_y))
            bx2 = min(tw - 2, int(x2 * scale_x))
            by2 = min(th - 2, int(y2 * scale_y))

            draw = ImageDraw.Draw(thumb)
            if bx2 > bx1 and by2 > by1:
                # Outer cyan box
                draw.rectangle([bx1, by1, bx2, by2], outline="#00f2fe", width=2)
                # Corner tech brackets
                bracket_len = min(14, (bx2 - bx1) // 4, (by2 - by1) // 4)
                if bracket_len > 3:
                    # Top-left
                    draw.line([(bx1, by1), (bx1 + bracket_len, by1)], fill="#ffffff", width=3)
                    draw.line([(bx1, by1), (bx1, by1 + bracket_len)], fill="#ffffff", width=3)
                    # Top-right
                    draw.line([(bx2, by1), (bx2 - bracket_len, by1)], fill="#ffffff", width=3)
                    draw.line([(bx2, by1), (bx2, by1 + bracket_len)], fill="#ffffff", width=3)
                    # Bottom-left
                    draw.line([(bx1, by2), (bx1 + bracket_len, by2)], fill="#ffffff", width=3)
                    draw.line([(bx1, by2), (bx1, by2 - bracket_len)], fill="#ffffff", width=3)
                    # Bottom-right
                    draw.line([(bx2, by2), (bx2 - bracket_len, by2)], fill="#ffffff", width=3)
                    draw.line([(bx2, by2), (bx2, by2 - bracket_len)], fill="#ffffff", width=3)

            return thumb
        except Exception as e:
            print(f"[Thumbnail Annotation Error] {e}")
            return screenshot.resize(target_size)

    def generate_screen_summary(self, telemetry: dict, user_prompt: str = "") -> str:
        """
        Generates a concise, intelligent natural language summary of what is on screen
        completely locally on-device.
        """
        title = telemetry.get("active_title", "Desktop")
        category = telemetry.get("category", "Application")
        proc = telemetry.get("process_name", "explorer.exe").replace(".exe", "").title()
        res = telemetry.get("resolution", "1920x1080")
        is_fs = telemetry.get("is_fullscreen", False)
        controls = telemetry.get("child_controls", [])
        other_apps = telemetry.get("visible_windows", [])

        # Check for error debug query
        is_debug_prompt = any(k in user_prompt.lower() for k in ["error", "issue", "debug", "fix", "problem", "broken"])

        if telemetry.get("has_error_dialog"):
            ctrl_text = f" with text '{', '.join(controls[:3])}'" if controls else ""
            summary = f"I detected an active error or alert dialog titled '{title}' from {proc}{ctrl_text}. You can review the prompt or dismiss it."
            return summary

        if is_debug_prompt:
            if controls:
                summary = f"I inspected your screen. Active window is {proc} showing '{title}'. Detected on-screen elements include: {', '.join(controls[:4])}."
            else:
                summary = f"I inspected your active screen in {proc} with title '{title}'. No critical system alert dialogs were found in foreground."
            return summary

        # Standard screen reading synthesis
        layout_str = "in full screen" if is_fs else "in the active window"
        summary_parts = []
        
        if "Browser" in category:
            summary_parts.append(f"You are currently viewing {proc} on your {res} display, browsing '{title}'.")
        elif "Code" in category:
            summary_parts.append(f"You have {proc} open {layout_str}, working on '{title}'.")
        elif "Folder" in category or "File" in category:
            summary_parts.append(f"You are navigating File Explorer in folder '{title}'.")
        elif "Terminal" in category:
            summary_parts.append(f"You are in the terminal command console '{title}'.")
        elif "Desktop" in category:
            summary_parts.append(f"You are currently viewing the Windows desktop on a {res} resolution display.")
        else:
            summary_parts.append(f"Your primary focused application is {proc}, with the window title '{title}'.")

        # Mention companion apps if present
        bg_apps = [a for a in other_apps if a.lower() != proc.lower()][:3]
        if bg_apps:
            summary_parts.append(f"Background running applications include {', '.join(bg_apps)}.")

        return " ".join(summary_parts)

    def _call_gemini_vision(self, image: Image.Image, prompt: str) -> str:
        """
        Inspects screen screenshot using Gemini 1.5 Flash Multimodal Vision when an API key is available.
        Returns concise spoken answer, or None on failure or if offline.
        """
        try:
            settings = load_user_settings()
            if settings.get("strict_offline_mode", False):
                return None

            api_key = (
                settings.get("gemini_api_key", "").strip() or
                os.environ.get("GEMINI_API_KEY", "").strip() or
                os.environ.get("GOOGLE_API_KEY", "").strip()
            )
            if not api_key:
                return None

            # Downscale screenshot for fast, low-latency transmission (max 1280x720)
            img = image.copy()
            img.thumbnail((1280, 720), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=80)
            b64_image = base64.b64encode(buf.getvalue()).decode("utf-8")

            sys_instruction = (
                "You are J.A.R.V.I.S., a witty, highly capable Windows voice assistant. "
                "Analyze this screenshot of the user's computer screen and answer their question concisely in 1 to 2 spoken sentences. "
                "Focus strictly on the user's active window, open documents, emails, code, web browser, or folders. "
                "Do NOT describe or mention any assistant HUD, floating overlay, or voice assistant UI widget if visible. "
                "Do not use markdown formatting such as asterisks, hashes, or bullet points, as your response will be read aloud by TTS."
            )
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": f"{sys_instruction}\n\nUser Question: {prompt}"},
                            {
                                "inline_data": {
                                    "mime_type": "image/jpeg",
                                    "data": b64_image
                                }
                            }
                        ]
                    }
                ]
            }

            for model_name in ["gemini-flash-lite-latest", "gemini-3.1-flash-lite", "gemini-flash-latest", "gemini-1.5-flash"]:
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
                    resp = requests.post(url, json=payload, timeout=12)
                    if resp.status_code == 200:
                        data = resp.json()
                        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                        # Clean up markdown punctuation for clean speech
                        text = re.sub(r'[*_#`]', '', text).strip()
                        return text
                    elif resp.status_code in [404, 503, 429]:
                        continue
                    else:
                        print(f"[Gemini Vision API Notice] HTTP {resp.status_code}: {resp.text[:100]}")
                        break
                except Exception as loop_err:
                    print(f"[Gemini Vision Loop Notice] {loop_err}")
                    continue

            return None
        except Exception as e:
            print(f"[Gemini Vision Call Exception] {e}")
            return None

    def analyze_screen(self, user_prompt: str = "Describe what is currently on my screen concisely in 2 to 3 sentences.", show_visualizer: bool = True):
        """
        Visualizes and reads the content on screen.
        If Gemini API key is configured, utilizes Gemini 1.5 Flash Multimodal Vision
        for true visual perception and understanding.
        Otherwise falls back cleanly to local on-device telemetry extraction.
        """
        if self.hud:
            self.hud.set_state("transcribing", "Visualizing Screen...", "Capturing screen and visual UI elements...")

        # 1. Capture screenshot
        screenshot = self.capture_screen()

        # 2. Extract local on-device telemetry & controls
        telemetry = self.get_screen_telemetry()

        # 3. Create annotated holographic thumbnail
        thumbnail = self.create_annotated_thumbnail(screenshot, telemetry.get("rect", (0, 0, 1920, 1080)))

        # 4. Synthesize intelligent description via Gemini Vision if available, or local engine
        speech_summary = None
        gemini_response = self._call_gemini_vision(screenshot, user_prompt)
        if gemini_response:
            speech_summary = gemini_response
            telemetry["ai_engine"] = "Gemini 1.5 Flash Vision"
        else:
            speech_summary = self.generate_screen_summary(telemetry, user_prompt)
            telemetry["ai_engine"] = "Local Telemetry Engine"

        telemetry["summary"] = speech_summary
        telemetry["prompt"] = user_prompt

        # 5. Display the Visualizer Overlay Window on HUD
        if show_visualizer and self.hud:
            try:
                self.hud.show_screen_visualizer(telemetry, thumbnail)
            except Exception as e:
                print(f"[Visualizer Display Error] {e}")

        # 6. Update HUD state and Speak aloud
        if self.hud:
            self.hud.set_state("speaking", "Screen Visualized", speech_summary)

        self.tts.speak(speech_summary)

    def copy_screen_text(self):
        """Extracts visible text on screen and copies directly to the clipboard."""
        if self.hud:
            self.hud.set_state("transcribing", "OCR Text Extraction...", "Reading visible text on screen...")
        success, word_count, preview = self.ocr.copy_screen_text_to_clipboard()
        if success:
            msg = f"Extracted {word_count} words from your screen and copied them to your clipboard, sir."
        else:
            msg = "I was unable to copy the text to your clipboard, sir."
        if self.hud:
            self.hud.set_state("speaking", "Text Copied", msg)
        self.tts.speak(msg)

    def explain_screen_error(self, text_input: str = None):
        """Analyzes active screen or terminal output for errors and provides a remedy."""
        if self.hud:
            self.hud.set_state("transcribing", "Diagnosing Error...", "Inspecting stack trace and error logs...")

        screenshot = self.capture_screen()
        gemini_response = self._call_gemini_vision(
            screenshot,
            "Diagnose the error, exception, or failure shown on this screen, or state that no error was detected, concisely in 1 to 2 spoken sentences."
        )

        if gemini_response:
            diagnosis = gemini_response
        else:
            diagnosis = self.ocr.diagnose_screen_error(text_input)

        if self.hud:
            self.hud.set_state("speaking", "Diagnostic Complete", diagnosis)
        self.tts.speak(diagnosis)
