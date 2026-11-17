import time
import threading
import pyperclip
import pyautogui
from typing import List, Optional
from os_adapter import get_os_adapter

class ClipboardHistory:
    """Monitors and maintains a local history of copied clipboard snippets."""
    def __init__(self, max_items: int = 25):
        self.max_items = max_items
        self.history = []
        self._lock = threading.Lock()
        self._last_clip = ""
        self._running = False
        self._thread = None
        self.adapter = get_os_adapter()

    def start(self):
        """Starts background clipboard polling."""
        if self._running:
            return
        self._running = True
        try:
            self._last_clip = pyperclip.paste()
            if self._last_clip and self._last_clip.strip():
                self.history.append({"text": self._last_clip.strip(), "time": time.time()})
        except Exception:
            pass

        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def add_clip(self, text: str):
        """Manually record a clip into history."""
        if not text or not text.strip():
            return
        clean = text.strip()
        with self._lock:
            self._last_clip = clean
            if not self.history or self.history[0]["text"] != clean:
                self.history.insert(0, {"text": clean, "time": time.time()})
                if len(self.history) > self.max_items:
                    self.history.pop()

    def _monitor_loop(self):
        while self._running:
            try:
                current = pyperclip.paste()
                if current and current.strip() and current != self._last_clip:
                    self.add_clip(current)
            except Exception:
                pass
            time.sleep(0.75)

    def get_recent(self, count: int = 3) -> List[str]:
        with self._lock:
            return [item["text"] for item in self.history[:count]]

    def get_item(self, index: int) -> Optional[str]:
        """Index is 1-based for human voice commands (item 1 = most recent)."""
        with self._lock:
            pos = index - 1
            if 0 <= pos < len(self.history):
                return self.history[pos]["text"]
            return None

    def paste_item(self, index: int = 1) -> bool:
        item = self.get_item(index)
        if item:
            try:
                pyperclip.copy(item)
                time.sleep(0.1)
                mod = self.adapter.modifier_key
                pyautogui.hotkey(mod, 'v')
                return True
            except Exception as e:
                print(f"[Clipboard Paste Error] {e}")
        return False

    def clear(self):
        with self._lock:
            self.history.clear()
            self._last_clip = ""
