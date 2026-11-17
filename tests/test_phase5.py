import os
import sys
import time
import socket
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from macro_manager import MacroManager, DEFAULT_MACROS
from calendar_briefing import CalendarBriefingManager
from audit_and_sandbox import NetworkKillSwitch, ActionAuditLogger
from actions import SystemController
from dispatcher import CommandDispatcher
from intent_router import IntentRouter
from tts import TextToSpeech

class TestPhase5ProductivityAndSecurity(unittest.TestCase):
    def setUp(self):
        self.mock_tts = MagicMock(spec=TextToSpeech)
        self.mock_tts.speak = MagicMock()
        self.temp_dir = tempfile.mkdtemp()

    def test_macro_manager_defaults_and_custom(self):
        macro_file = os.path.join(self.temp_dir, "test_macros.json")
        manager = MacroManager(config_file=macro_file)
        
        # Test defaults
        self.assertIn("wrap up for the day", manager.macros)
        self.assertIn("presentation mode", manager.macros)
        self.assertIn("focus mode", manager.macros)

        # Test custom macro registration and persistence
        custom_actions = [
            {"action": "speak", "params": {"text": "Custom routine active"}},
            {"action": "mute_volume", "params": {}}
        ]
        manager.register_macro("activate stealth mode", custom_actions)
        self.assertIsNotNone(manager.get_macro("activate stealth mode"))

        # Reload from disk
        manager2 = MacroManager(config_file=macro_file)
        self.assertIn("activate stealth mode", manager2.macros)

        # Test execution
        mock_controller = MagicMock()
        success = manager.execute_macro("activate stealth mode", mock_controller, self.mock_tts)
        self.assertTrue(success)
        self.mock_tts.speak.assert_called_with("Custom routine active")
        mock_controller.volume_control.assert_called_with("mute")

    def test_calendar_briefing_parser(self):
        # Create a mock .ics file
        ics_path = os.path.join(self.temp_dir, "test_calendar.ics")
        ics_content = (
            "BEGIN:VCALENDAR\n"
            "VERSION:2.0\n"
            "BEGIN:VEVENT\n"
            "SUMMARY:Team Architecture Review\n"
            "DTSTART:20261116T143000Z\n"
            "END:VEVENT\n"
            "BEGIN:VEVENT\n"
            "SUMMARY:One on One Sync\n"
            "DTSTART:20261116T160000Z\n"
            "END:VEVENT\n"
            "END:VCALENDAR\n"
        )
        with open(ics_path, "w", encoding="utf-8") as f:
            f.write(ics_content)

        briefing_mgr = CalendarBriefingManager(search_directories=[self.temp_dir])
        events = briefing_mgr.parse_events(ics_path)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["summary"], "Team Architecture Review")

        # Create mock notes file
        notes_path = os.path.join(self.temp_dir, "notes.txt")
        with open(notes_path, "w", encoding="utf-8") as f:
            f.write("[2026-11-16] Finalize offline regression suite\n")

        briefing_text = briefing_mgr.generate_morning_briefing(MagicMock(), custom_notes_path=notes_path)
        self.assertIn("Team Architecture Review", briefing_text)
        self.assertIn("Finalize offline regression suite", briefing_text)
        self.assertIn("operating at peak efficiency", briefing_text)

    def test_network_killswitch_process_sandbox(self):
        # Test enabling kill-switch
        NetworkKillSwitch.enable()
        self.assertTrue(NetworkKillSwitch.is_active())

        # Test outbound socket blocking
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with self.assertRaises(PermissionError):
                s.connect(("8.8.8.8", 53))
        finally:
            s.close()

        # Test disabling kill-switch
        NetworkKillSwitch.disable()
        self.assertFalse(NetworkKillSwitch.is_active())

    def test_action_audit_logger(self):
        log_file = os.path.join(self.temp_dir, "test_audit.log")
        logger = ActionAuditLogger(log_path=log_file)
        
        logger.log("open_app", {"target": "terminal"}, status="SUCCESS")
        logger.log("lock_pc", {}, status="SUCCESS")
        
        entries = logger.get_recent(5)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["action"], "open_app")
        self.assertEqual(entries[1]["action"], "lock_pc")

        summary = logger.get_summary_speech()
        self.assertIn("2 operations", summary)
        self.assertIn("open_app", summary)

    def test_dispatcher_phase5_commands(self):
        controller = MagicMock(spec=SystemController)
        controller.audit = ActionAuditLogger(os.path.join(self.temp_dir, "dispatcher_audit.log"))
        controller.macros = MacroManager()
        controller.dictation_mode = False
        controller.strict_offline_mode = False
        
        dispatcher = CommandDispatcher(controller, self.mock_tts, MagicMock())
        dispatcher.active_until = time.time() + 100.0  # awake

        # Test morning briefing trigger
        dispatcher.process("morning briefing")
        controller.give_morning_briefing.assert_called_once()

        # Test network killswitch trigger
        dispatcher.process("enable network kill switch")
        controller.toggle_network_killswitch.assert_called_with(True)

        # Test audit log trigger
        dispatcher.process("read audit log")
        controller.read_audit_log.assert_called_once()

    def test_intent_router_phase5_semantic_resolutions(self):
        router = IntentRouter()
        
        res1 = router.resolve("what's on my schedule today")
        self.assertIsNotNone(res1)
        self.assertEqual(res1["name"], "morning_briefing")

        res2 = router.resolve("wrap up for the day")
        self.assertIsNotNone(res2)
        self.assertEqual(res2["name"], "execute_macro")

        res3 = router.resolve("activate network kill switch")
        self.assertIsNotNone(res3)
        self.assertEqual(res3["name"], "toggle_network_killswitch")
        self.assertTrue(res3["parameters"]["enable"])

        res4 = router.resolve("read audit log summary")
        self.assertIsNotNone(res4)
        self.assertEqual(res4["name"], "read_audit_log")

if __name__ == "__main__":
    unittest.main()
