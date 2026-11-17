import os
import re
from typing import Optional, Dict

# Built-in Air-Gapped Offline Knowledge Base
OFFLINE_KNOWLEDGE = {
    "alan turing": (
        "Alan Turing was an English mathematician, computer scientist, and cryptanalyst. "
        "He is widely considered to be the father of modern computer science and artificial intelligence, "
        "and played a pivotal role in cracking intercepted coded messages at Bletchley Park during World War II."
    ),
    "quantum computing": (
        "Quantum computing is a rapidly-emerging technology that harnesses the laws of quantum mechanics, "
        "specifically superposition and entanglement, to solve complex mathematical and computational problems "
        "vastly faster than classical supercomputers."
    ),
    "albert einstein": (
        "Albert Einstein was a German-born theoretical physicist widely acknowledged to be one of the greatest "
        "and most influential physicists of all time, best known for developing the theory of relativity and his mass-energy equivalence equation E equals m c squared."
    ),
    "artificial intelligence": (
        "Artificial Intelligence, or AI, refers to the simulation of human intelligence processes by computer systems. "
        "These processes include learning, reasoning, problem solving, perception, and natural language understanding."
    ),
    "machine learning": (
        "Machine learning is a branch of artificial intelligence and computer science focused on the use of data and algorithms "
        "to imitate the way humans learn, gradually improving accuracy without being explicitly programmed."
    ),
    "python": (
        "Python is a high-level, general-purpose programming language created by Guido van Rossum and first released in 1991. "
        "Its design philosophy emphasizes code readability through the use of significant indentation."
    ),
    "dna": (
        "DNA, or deoxyribonucleic acid, is the hereditary material in humans and almost all other organisms. "
        "It consists of two long chains of nucleotides twisted into a double helix carrying genetic instructions."
    ),
    "black hole": (
        "A black hole is a region of spacetime where gravity is so strong that nothing, including light and other electromagnetic waves, "
        "can escape from within its event horizon."
    ),
    "internet": (
        "The Internet is a global system of interconnected computer networks that uses the Internet protocol suite TCP/IP "
        "to communicate between networks and devices."
    ),
    "nikola tesla": (
        "Nikola Tesla was a Serbian-American inventor, electrical engineer, and futurist best known for his contributions "
        "to the design of the modern alternating current electricity supply system."
    ),
    "isaac newton": (
        "Sir Isaac Newton was an English polymath active as a mathematician, physicist, astronomer, and author who established "
        "classical mechanics, the laws of motion, and universal gravitation."
    ),
    "marie curie": (
        "Marie Curie was a Polish and naturalized-French physicist and chemist who conducted pioneering research on radioactivity. "
        "She was the first woman to win a Nobel Prize and the only person to win Nobel Prizes in two different scientific fields."
    ),
    "solar system": (
        "The Solar System is the gravitationally bound system of the Sun and the objects that orbit it, including eight major planets, "
        "their moons, dwarf planets, asteroids, and comets."
    ),
    "photosynthesis": (
        "Photosynthesis is a biological process used by plants and other organisms to convert light energy into chemical energy, "
        "synthesizing organic compounds like sugars from carbon dioxide and water while releasing oxygen."
    )
}

class OfflineEncyclopedia:
    """Provides offline encyclopedia lookups and Kiwix .zim archive integration."""
    def __init__(self, encyclopedia_dir: str = None):
        if encyclopedia_dir is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            encyclopedia_dir = os.path.join(base_dir, "models", "encyclopedia")
        self.encyclopedia_dir = encyclopedia_dir
        self.zim_file = self._find_zim_file()

    def _find_zim_file(self) -> Optional[str]:
        if os.path.exists(self.encyclopedia_dir):
            for f in os.listdir(self.encyclopedia_dir):
                if f.endswith(".zim"):
                    return os.path.join(self.encyclopedia_dir, f)
        return None

    def lookup(self, query: str) -> Optional[str]:
        """Looks up a topic in the offline knowledge store or .zim archive."""
        clean = query.lower().strip()
        clean = re.sub(r'^(who was|who is|what was|what is|tell me about|explain|describe)\s+', '', clean).strip()
        clean = re.sub(r'[,\.\?!:\s]+$', '', clean).strip()

        # 1. Check local .zim file if libzim is installed
        if self.zim_file:
            try:
                import libzim
                # Query libzim archive if available
                archive = libzim.Archive(self.zim_file)
                entry = archive.get_entry_by_path(clean)
                if entry:
                    item = entry.get_item()
                    content = bytes(item.content).decode("utf-8", errors="ignore")
                    text = re.sub(r'<[^>]+>', '', content)[:400].strip()
                    return f"According to offline encyclopedia: {text}..."
            except Exception:
                pass

        # 2. Check built-in offline knowledge base
        for key, text in OFFLINE_KNOWLEDGE.items():
            if key in clean or (len(clean) >= 4 and clean in key):
                return text

        return None
