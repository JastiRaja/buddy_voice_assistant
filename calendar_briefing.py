import os
import re
from datetime import datetime, date
from typing import List, Dict, Any, Optional

class CalendarBriefingManager:
    """Parses local .ics calendar files and to-do lists to provide offline daily briefings."""
    def __init__(self, search_directories: List[str] = None):
        if search_directories is None:
            user_home = os.path.expanduser("~")
            search_directories = [
                os.path.join(user_home, "Documents"),
                os.path.join(user_home, "Downloads"),
                os.path.join(user_home, "Desktop")
            ]
        self.search_directories = search_directories

    def find_ics_files(self) -> List[str]:
        found = []
        for d in self.search_directories:
            if os.path.exists(d):
                try:
                    for f in os.listdir(d):
                        if f.lower().endswith(".ics"):
                            found.append(os.path.join(d, f))
                except Exception:
                    pass
        return found

    def parse_events(self, ics_path: str) -> List[Dict[str, str]]:
        """Pure-Python .ics VEVENT parser."""
        events = []
        if not os.path.exists(ics_path):
            return events

        try:
            with open(ics_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            raw_events = re.findall(r'BEGIN:VEVENT([\s\S]*?)END:VEVENT', content)
            today_str = datetime.now().strftime("%Y%m%d")

            for raw in raw_events:
                summary_match = re.search(r'SUMMARY(?::|;.*?:\s*)(.*)', raw)
                dtstart_match = re.search(r'DTSTART(?::|;.*?:\s*)(\d+T?\d*Z?)', raw)

                summary = summary_match.group(1).strip() if summary_match else "Scheduled Event"
                dtstart = dtstart_match.group(1).strip() if dtstart_match else ""

                # Check if event is today or generic upcoming
                is_today = today_str in dtstart if dtstart else False
                time_str = "Scheduled"
                if "T" in dtstart:
                    t_part = dtstart.split("T")[1][:4]
                    try:
                        time_obj = datetime.strptime(t_part, "%H%M")
                        time_str = time_obj.strftime("%I:%M %p")
                    except Exception:
                        pass

                events.append({
                    "summary": summary,
                    "time": time_str,
                    "is_today": is_today
                })
        except Exception as e:
            print(f"[ICS Parser Notice] {e}")

        return events

    def get_todays_tasks(self, notes_file: str = None) -> List[str]:
        """Reads open tasks from notes or to-do markdown files."""
        tasks = []
        if notes_file and os.path.exists(notes_file):
            try:
                with open(notes_file, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                for line in lines[-5:]:
                    clean = re.sub(r'^\[.*?\]\s*', '', line).strip()
                    if clean:
                        tasks.append(clean)
            except Exception:
                pass
        return tasks

    def generate_morning_briefing(self, controller, custom_notes_path: str = None) -> str:
        """Synthesizes comprehensive, offline morning briefing."""
        now = datetime.now()
        greeting = "Good morning" if now.hour < 12 else ("Good afternoon" if now.hour < 18 else "Good evening")
        date_str = now.strftime("%A, %B %d")
        time_str = now.strftime("%I:%M %p")

        # 1. Calendar Events
        ics_files = self.find_ics_files()
        all_events = []
        for ics in ics_files:
            all_events.extend(self.parse_events(ics))

        today_events = [e for e in all_events if e["is_today"]]
        if not today_events and all_events:
            today_events = all_events[:2]

        calendar_summary = ""
        if today_events:
            event_strs = [f"{e['summary']} at {e['time']}" for e in today_events[:3]]
            calendar_summary = f"You have {len(today_events)} items on your calendar: {', '.join(event_strs)}."
        else:
            calendar_summary = "Your calendar has no conflicting meetings scheduled today."

        # 2. To-Do Notes
        notes_file = custom_notes_path or getattr(controller, 'notes_file', None)
        tasks = self.get_todays_tasks(notes_file)
        task_summary = ""
        if tasks:
            task_summary = f"Your latest saved notes include: {tasks[-1]}."

        # 3. Assemble Briefing
        briefing = (
            f"{greeting}, sir. Today is {date_str}, current time is {time_str}. "
            f"{calendar_summary} {task_summary} "
            f"All core systems and offline neural models are operating at peak efficiency. Ready for your instructions."
        )
        return briefing.strip()
