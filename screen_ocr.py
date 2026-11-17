import os
import re
import time
import pyperclip
import pyautogui
from typing import Optional, Tuple, Dict, Any
from PIL import Image

# Diagnostic Knowledge Base for Common Stack Traces and Errors
ERROR_SIGNATURES = [
    {
        "pattern": r"(?:ModuleNotFoundError|ImportError):\s*No module named ['\"]?([a-zA-Z0-9_\-]+)['\"]?",
        "type": "Python Missing Package",
        "format": lambda m: f"Python could not find the module '{m.group(1)}'. You can resolve this by running: pip install {m.group(1)}."
    },
    {
        "pattern": r"SyntaxError:\s*(.*)",
        "type": "Syntax Error",
        "format": lambda m: f"A syntax error was detected: '{m.group(1).strip()}'. Please check for missing parentheses, brackets, or unescaped quotes."
    },
    {
        "pattern": r"TypeError:\s*(.*)",
        "type": "Type Error",
        "format": lambda m: f"A Python type error occurred: '{m.group(1).strip()}'. An operation was performed on incompatible data types."
    },
    {
        "pattern": r"AttributeError:\s*['\"]?([a-zA-Z0-9_]+)['\"]?\s*object has no attribute\s*['\"]?([a-zA-Z0-9_]+)['\"]?",
        "type": "Attribute Error",
        "format": lambda m: f"Attribute error: The '{m.group(1)}' object does not have the attribute '{m.group(2)}'. Verify the method name or check if the variable is None."
    },
    {
        "pattern": r"NameError:\s*name ['\"]?([a-zA-Z0-9_]+)['\"]? is not defined",
        "type": "Undefined Variable",
        "format": lambda m: f"Variable or function '{m.group(1)}' is referenced before assignment or is missing an import statement."
    },
    {
        "pattern": r"(?:FileNotFoundError|NoSuchFileException):\s*(.*)",
        "type": "File Not Found",
        "format": lambda m: f"File system error: '{m.group(1).strip()}' could not be located. Check the file path and working directory."
    },
    {
        "pattern": r"(?:PermissionError|AccessDeniedException|Access is denied)",
        "type": "Permission Denied",
        "format": lambda m: "Access was denied by the operating system. Check file permissions or run the terminal with elevated administrator privileges."
    },
    {
        "pattern": r"(?:Address already in use|EADDRINUSE|port\s*(\d+)\s*is already in use)",
        "type": "Port Conflict",
        "format": lambda m: "A local port conflict was detected. Another process is already running on that port. Terminate the existing server or change the port number."
    },
    {
        "pattern": r"Cannot find module ['\"]?([a-zA-Z0-9_\-@\/]+)['\"]?",
        "type": "Node.js Missing Dependency",
        "format": lambda m: f"Node.js dependency '{m.group(1)}' is missing. Run: npm install {m.group(1)} or check package.json."
    },
    {
        "pattern": r"TypeError:\s*Cannot read propert(?:y|ies) of (?:undefined|null)\s*\(reading ['\"]?([a-zA-Z0-9_]+)['\"]?\)",
        "type": "JavaScript Null Reference",
        "format": lambda m: f"JavaScript error: Attempted to access property '{m.group(1)}' on an undefined or null object. Add optional chaining (?.) to prevent this."
    },
    {
        "pattern": r"fatal:\s*not a git repository",
        "type": "Git Repository Error",
        "format": lambda m: "This directory is not initialized as a Git repository. Run 'git init' or navigate to the repository root directory."
    },
    {
        "pattern": r"fatal:\s*merge conflict",
        "type": "Git Merge Conflict",
        "format": lambda m: "Git encountered merge conflicts between branches. Inspect the marked files, resolve conflicting sections, and commit the changes."
    },
    {
        "pattern": r"is not recognized as an internal or external command",
        "type": "Command Not Found",
        "format": lambda m: "The command was not found in your system PATH environment variable. Verify spelling or add the executable directory to PATH."
    }
]


class ScreenOCRExtractor:
    """Provides local screen OCR text extraction and terminal/IDE error debugging."""
    def __init__(self, vision_assistant=None):
        self.vision = vision_assistant
        self._last_extracted_text = ""

    def extract_text_from_screen(self, image: Image.Image = None) -> str:
        """
        Extracts visible text from the screen using accessible control inspection,
        OCR engines (if available), or vision telemetry.
        """
        extracted_pieces = []

        # 1. Extract from Active Window Telemetry & Child Controls
        if self.vision:
            try:
                telemetry = self.vision.get_screen_telemetry()
                if telemetry.get("active_title"):
                    extracted_pieces.append(f"Window: {telemetry['active_title']}")
                controls = telemetry.get("child_controls", [])
                if controls:
                    extracted_pieces.extend(controls)
            except Exception:
                pass

        # 2. Check for Pytesseract if installed
        try:
            import pytesseract
            if image is None:
                image = pyautogui.screenshot()
            ocr_text = pytesseract.image_to_string(image)
            if ocr_text and ocr_text.strip():
                extracted_pieces.append(ocr_text.strip())
        except Exception:
            pass

        # 3. Check for EasyOCR if installed
        try:
            import easyocr
            import numpy as np
            if image is None:
                image = pyautogui.screenshot()
            reader = easyocr.Reader(['en'], gpu=False, verbose=False)
            results = reader.readtext(np.array(image), detail=0)
            if results:
                extracted_pieces.extend(results)
        except Exception:
            pass

        result = "\n".join(extracted_pieces).strip()
        self._last_extracted_text = result
        return result

    def copy_screen_text_to_clipboard(self, image: Image.Image = None) -> Tuple[bool, int, str]:
        """
        Extracts screen text and copies it into the clipboard.
        Returns: (success, word_count, preview_string)
        """
        text = self.extract_text_from_screen(image)
        if not text:
            # Fallback if no window controls active
            text = "Active Screen Capture - No visible text elements detected."

        words = text.split()
        word_count = len(words)
        preview = " ".join(words[:12]) if words else "Empty"

        try:
            pyperclip.copy(text)
            return True, word_count, preview
        except Exception:
            return False, word_count, preview

    def diagnose_screen_error(self, text_input: str = None) -> str:
        """
        Analyzes visible screen or terminal text for runtime exceptions,
        compiler crashes, or error dialogs, providing a concise 2-sentence fix.
        """
        raw = text_input if text_input is not None else self.extract_text_from_screen()
        if not raw:
            return "No readable error or exception trace was found on your active screen, sir."

        # Scan for known error patterns
        for sig in ERROR_SIGNATURES:
            m = re.search(sig["pattern"], raw, re.IGNORECASE)
            if m:
                diagnosis = sig["format"](m)
                return f"I diagnosed an on-screen error: {diagnosis}"

        # Generic Traceback Check
        if "traceback" in raw.lower():
            lines = [l.strip() for l in raw.split("\n") if l.strip()]
            last_line = lines[-1] if lines else "unknown runtime exception"
            return f"I detected a runtime exception stack trace ending with: '{last_line}'. Check the line number mentioned above for the failing variable or method."

        if "error" in raw.lower() or "failed" in raw.lower():
            return "An application error is displayed on screen. Check logs or verify required input fields and network connectivity."

        return "I inspected your active screen. No critical errors or unhandled exceptions were detected, sir."
