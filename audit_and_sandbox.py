import os
import time
import json
import socket
from datetime import datetime
from typing import Dict, List, Any, Optional

# Original socket references for restoration
_ORIGINAL_SOCKET_CONNECT = socket.socket.connect
_ORIGINAL_CREATE_CONNECTION = socket.create_connection

class NetworkKillSwitch:
    """Process-level socket sandbox blocking all outbound network traffic."""
    _active = False

    @classmethod
    def enable(cls):
        """Hard blocks outbound external socket connect calls while permitting local loopback."""
        if cls._active:
            return

        def _is_loopback(address):
            if isinstance(address, tuple) and len(address) >= 1:
                host = str(address[0]).lower()
                return host in ("127.0.0.1", "localhost", "::1", "0.0.0.0")
            elif isinstance(address, str):
                return address.lower() in ("127.0.0.1", "localhost", "::1")
            return False

        def _blocked_connect(sock, address, *args, **kwargs):
            if _is_loopback(address):
                return _ORIGINAL_SOCKET_CONNECT(sock, address, *args, **kwargs)
            raise PermissionError("Air-Gapped Privacy Active: Outbound socket connection blocked by process kill-switch.")

        def _blocked_create_connection(address, *args, **kwargs):
            if _is_loopback(address):
                return _ORIGINAL_CREATE_CONNECTION(address, *args, **kwargs)
            raise PermissionError("Air-Gapped Privacy Active: Outbound socket connection blocked by process kill-switch.")

        socket.socket.connect = _blocked_connect
        socket.create_connection = _blocked_create_connection
        cls._active = True
        print("[*] OS Process Network Kill-Switch: ACTIVATED (External outbound sockets blocked; local loopback permitted).")

    @classmethod
    def disable(cls):
        """Restores standard network connectivity."""
        if not cls._active:
            return
        socket.socket.connect = _ORIGINAL_SOCKET_CONNECT
        socket.create_connection = _ORIGINAL_CREATE_CONNECTION
        cls._active = False
        print("[*] OS Process Network Kill-Switch: DEACTIVATED.")

    @classmethod
    def is_active(cls) -> bool:
        return cls._active


class ActionAuditLogger:
    """Maintains an append-only transparency log of all local assistant operations."""
    def __init__(self, log_path: str = None):
        if log_path is None:
            log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".buddy_audit.log")
        self.log_path = log_path

    def log(self, action_name: str, params: Dict[str, Any] = None, status: str = "SUCCESS", details: str = ""):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "time_str": datetime.now().strftime("%Y-%m-%d %I:%M:%S %p"),
            "action": action_name,
            "params": params or {},
            "status": status,
            "air_gapped_active": NetworkKillSwitch.is_active(),
            "details": details
        }
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            print(f"[Audit Log Error] {e}")

    def get_recent(self, count: int = 5) -> List[Dict[str, Any]]:
        entries = []
        if os.path.exists(self.log_path):
            try:
                with open(self.log_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                for line in lines[-count:]:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
            except Exception:
                pass
        return entries

    def get_summary_speech(self) -> str:
        recent = self.get_recent(3)
        if not recent:
            return "No previous actions have been recorded in the local audit log, sir."

        action_names = [e.get("action", "action") for e in recent]
        count = len(recent)
        killswitch_status = "active and blocking network traffic" if NetworkKillSwitch.is_active() else "inactive"
        return f"Recent audit log shows {count} operations including {', '.join(action_names)}. The process network kill-switch is currently {killswitch_status}, sir."
