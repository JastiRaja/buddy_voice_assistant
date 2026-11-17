import os
import json
import time
from typing import Dict, List, Any, Optional

DEFAULT_MACROS = {
    "wrap up for the day": [
        {"action": "save_file", "params": {}},
        {"action": "mute_volume", "params": {}},
        {"action": "speak", "params": {"text": "Wrapping up your workstation for the day, sir."}},
        {"action": "lock_screen", "params": {}}
    ],
    "end of day": [
        {"action": "save_file", "params": {}},
        {"action": "mute_volume", "params": {}},
        {"action": "speak", "params": {"text": "Good evening, sir. Workstation secured."}},
        {"action": "lock_screen", "params": {}}
    ],
    "presentation mode": [
        {"action": "minimize_all", "params": {}},
        {"action": "set_volume", "params": {"direction": "mute"}},
        {"action": "speak", "params": {"text": "Presentation mode activated. Background windows cleared and volume muted."}}
    ],
    "focus mode": [
        {"action": "speak", "params": {"text": "Entering focus mode, sir."}},
        {"action": "launch_profile", "params": {"profile": "coding"}},
        {"action": "set_volume", "params": {"direction": "down"}}
    ]
}

class MacroManager:
    """Manages multi-step voice macros and automated routine chains."""
    def __init__(self, config_file: str = None):
        if config_file is None:
            config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".buddy_macros.json")
        self.config_file = config_file
        self.macros: Dict[str, List[Dict[str, Any]]] = {}
        self.load_macros()

    def load_macros(self):
        self.macros = dict(DEFAULT_MACROS)
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    user_macros = json.load(f)
                    self.macros.update(user_macros)
            except Exception as e:
                print(f"[MacroManager Load Warning] {e}")

    def save_macros(self):
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.macros, f, indent=4)
        except Exception as e:
            print(f"[MacroManager Save Error] {e}")

    def register_macro(self, trigger_phrase: str, actions: List[Dict[str, Any]]):
        clean = trigger_phrase.lower().strip()
        self.macros[clean] = actions
        self.save_macros()

    def get_macro(self, phrase: str) -> Optional[List[Dict[str, Any]]]:
        clean = phrase.lower().strip()
        return self.macros.get(clean)

    def execute_macro(self, phrase: str, controller, tts) -> bool:
        clean = phrase.lower().strip()
        actions = self.get_macro(clean)
        if not actions:
            return False

        print(f"[*] Executing Voice Macro Routine: '{clean}' ({len(actions)} steps)")
        for step in actions:
            act = step.get("action")
            params = step.get("params", {})
            try:
                if act == "speak":
                    tts.speak(params.get("text", ""))
                elif act == "save_file":
                    controller.edit_action("save")
                elif act == "lock_screen":
                    controller.lock_pc()
                elif act == "mute_volume":
                    controller.volume_control("mute")
                elif act == "set_volume":
                    controller.volume_control(params.get("direction", "down"))
                elif act == "minimize_all":
                    controller.minimize_all()
                elif act == "launch_profile":
                    controller.launch_workspace_profile(params.get("profile", "coding"))
                elif act == "open_app":
                    controller.open_application(params.get("target", ""))
                elif act == "wait":
                    time.sleep(float(params.get("seconds", 0.5)))
                time.sleep(0.3)
            except Exception as e:
                print(f"[Macro Step Error] Failed on step {act}: {e}")

        return True
