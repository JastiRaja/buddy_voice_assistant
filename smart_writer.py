import re
import time
import pyperclip
import pyautogui
from typing import Optional, List
from os_adapter import get_os_adapter

class SmartWriter:
    """Provides on-device text rewriting, grammar polishing, and summarization."""
    def __init__(self, tts=None):
        self.tts = tts
        self.adapter = get_os_adapter()
        self.internal_buffer = ""

    def set_buffer(self, text: str):
        """Allows programmatically feeding text when in headless/sandboxed mode."""
        self.internal_buffer = text.strip() if text else ""

    def get_selected_or_clipboard_text(self) -> str:
        """Copies highlighted text if any; falls back to current clipboard or internal buffer."""
        old_clip = ""
        try:
            old_clip = pyperclip.paste()
        except Exception:
            pass

        # Try hotkey if in interactive environment
        try:
            mod = self.adapter.modifier_key
            pyautogui.hotkey(mod, 'c')
            time.sleep(0.15)
            new_clip = pyperclip.paste()
            if new_clip and new_clip.strip() and new_clip != old_clip:
                self.internal_buffer = new_clip.strip()
                return self.internal_buffer
        except Exception:
            pass

        if old_clip and old_clip.strip():
            self.internal_buffer = old_clip.strip()
            return self.internal_buffer

        return self.internal_buffer

    def replace_selection_with(self, new_text: str):
        """Copies text to clipboard and pastes it directly into the focused window."""
        if not new_text:
            return
        self.internal_buffer = new_text
        try:
            pyperclip.copy(new_text)
            time.sleep(0.1)
            mod = self.adapter.modifier_key
            pyautogui.hotkey(mod, 'v')
        except Exception:
            pass

    def summarize_text(self, text: str, max_sentences: int = 2) -> str:
        """Local extractive summarizer scoring sentences by key term frequencies."""
        clean = text.strip()
        if not clean:
            return ""

        sentences = re.split(r'(?<=[.!?])\s+', clean)
        if len(sentences) <= max_sentences:
            return clean

        # Compute word frequencies (ignoring common stopwords)
        stopwords = {
            "the", "and", "is", "in", "it", "of", "to", "a", "for", "on", "that", "this",
            "with", "as", "at", "by", "from", "an", "be", "was", "are", "or", "have", "has"
        }
        words = re.findall(r'\b[a-zA-Z]{3,}\b', clean.lower())
        word_freq = {}
        for w in words:
            if w not in stopwords:
                word_freq[w] = word_freq.get(w, 0) + 1

        # Score sentences
        scores = []
        for s in sentences:
            score = 0
            s_words = re.findall(r'\b[a-zA-Z]{3,}\b', s.lower())
            for sw in s_words:
                score += word_freq.get(sw, 0)
            scores.append((score / max(1, len(s_words)), s))

        # Select highest scoring sentences
        scores.sort(key=lambda x: x[0], reverse=True)
        top = [s for _, s in scores[:max_sentences]]
        return " ".join(top)

    def fix_grammar(self, text: str) -> str:
        """Applies local grammar, punctuation, and capitalization correction."""
        if not text:
            return ""

        t = text.strip()

        # Contractions
        contractions = {
            r'\bdont\b': "don't",
            r'\bcant\b': "can't",
            r'\bwont\b': "won't",
            r'\bim\b': "I'm",
            r'\byoure\b': "you're",
            r'\btheyre\b': "they're",
            r'\bwasnt\b': "wasn't",
            r'\bisnt\b': "isn't",
            r'\barent\b': "aren't",
            r'\bive\b': "I've",
            r'\byouve\b': "you've",
            r'\bweve\b': "we've",
            r'\btheyve\b': "they've",
            r'\bwouldnt\b': "wouldn't",
            r'\bcouldnt\b': "couldn't",
            r'\bshouldnt\b': "shouldn't",
            r'\bthats\b': "that's",
            r'\bwhats\b': "what's"
        }
        for pat, repl in contractions.items():
            t = re.sub(pat, repl, t, flags=re.IGNORECASE)

        # Capitalize standalone 'i'
        t = re.sub(r'\b(i)\b', 'I', t)

        # Capitalize start of sentences
        t = re.sub(r'(?:^|[.!?]\s+)([a-z])', lambda m: m.group(0).upper(), t)

        # Add period at end if missing
        if t and t[-1] not in ['.', '!', '?']:
            t += '.'

        return t

    def make_professional(self, text: str) -> str:
        """Rewrites colloquial or informal phrases into professional workplace language."""
        if not text:
            return ""

        t = self.fix_grammar(text)

        replacements = [
            (r'\basap\b', "at your earliest convenience"),
            (r'\bgonna\b', "going to"),
            (r'\bwanna\b', "would like to"),
            (r'\bgotta\b', "need to"),
            (r'\bkinda\b', "somewhat"),
            (r'\blet me know\b', "please keep me informed"),
            (r'\bthanks a lot\b', "Thank you very much"),
            (r'\bthx\b', "Thank you"),
            (r'\bhey guys\b', "Hello everyone"),
            (r'\bfix this\b', "resolve this matter"),
            (r'\bi can\'?t do it\b', "I am unable to accommodate this request"),
            (r'\bcan\'?t do it\b', "unable to accommodate this request"),
            (r'\bcheck out\b', "review"),
            (r'(?<!not\s)\bbad\b', "suboptimal"),
            (r'\bneed help\b', "would appreciate your assistance")
        ]

        for pat, repl in replacements:
            t = re.sub(pat, repl, t, flags=re.IGNORECASE)

        # Re-capitalize start of sentence
        t = re.sub(r'(?:^|[.!?]\s+)([a-z])', lambda m: m.group(0).upper(), t)
        return t
