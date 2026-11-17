import os
import re
import math
import sqlite3
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

class LocalDocumentRAG:
    """
    On-device document indexing and RAG retrieval running 100% locally.
    Indexes local PDFs, Word docs (.docx), Markdown notes, and code files.
    """
    def __init__(self, db_path: str = None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(base_dir, "models", "rag_index.db")
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filepath TEXT UNIQUE,
                    filename TEXT,
                    mtime REAL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_id INTEGER,
                    chunk_text TEXT,
                    FOREIGN KEY (doc_id) REFERENCES documents (id) ON DELETE CASCADE
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_doc_filepath ON documents (filepath)")
            conn.commit()

    def extract_text(self, filepath: str) -> str:
        """Extracts plain text from .txt, .md, .py, .docx, and .pdf files."""
        if not os.path.exists(filepath):
            return ""

        lower = filepath.lower()

        # 1. Plain text / Markdown / Code / JSON
        if lower.endswith(('.txt', '.md', '.py', '.json', '.csv', '.log', '.html', '.css', '.js')):
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
            except Exception:
                return ""

        # 2. Word Document (.docx)
        if lower.endswith('.docx'):
            try:
                with zipfile.ZipFile(filepath) as z:
                    xml_content = z.read('word/document.xml')
                    tree = ET.fromstring(xml_content)
                    paragraphs = []
                    for node in tree.iter():
                        if node.tag.endswith('}t') and node.text:
                            paragraphs.append(node.text)
                    return " ".join(paragraphs)
            except Exception:
                return ""

        # 3. PDF Files
        if lower.endswith('.pdf'):
            # Try pypdf if available
            try:
                import pypdf
                reader = pypdf.PdfReader(filepath)
                pages_text = [p.extract_text() or "" for p in reader.pages]
                full_text = " ".join(pages_text).strip()
                if full_text:
                    return full_text
            except Exception:
                pass

            # Pure-Python compressed and uncompressed stream extractor
            try:
                import zlib
                with open(filepath, 'rb') as f:
                    raw_data = f.read()

                extracted = []
                streams = re.findall(rb'stream\r?\n([\s\S]*?)\r?\nendstream', raw_data)
                for s in streams:
                    decompressed = None
                    try:
                        decompressed = zlib.decompress(s).decode('latin-1', errors='ignore')
                    except Exception:
                        try:
                            decompressed = s.decode('latin-1', errors='ignore')
                        except Exception:
                            pass

                    if decompressed:
                        matches = re.findall(r'BT\s*(.*?)\s*ET', decompressed, re.DOTALL)
                        for m in matches:
                            strings = re.findall(r'\((.*?)\)\s*T[jJ]', m)
                            if strings:
                                extracted.extend(strings)
                            tj_matches = re.findall(r'\[(.*?)\]\s*TJ', m)
                            for tj in tj_matches:
                                sub_strings = re.findall(r'\((.*?)\)', tj)
                                if sub_strings:
                                    extracted.extend(sub_strings)

                if extracted:
                    return " ".join(extracted).strip()

                # Fallback to raw scan
                content = raw_data.decode('latin-1', errors='ignore')
                matches = re.findall(r'BT\s*(.*?)\s*ET', content, re.DOTALL)
                text_pieces = []
                for m in matches:
                    strings = re.findall(r'\((.*?)\)\s*T[jJ]', m)
                    if strings:
                        text_pieces.extend(strings)
                if text_pieces:
                    return " ".join(text_pieces).strip()
            except Exception:
                pass

        return ""

    def index_file(self, filepath: str) -> bool:
        """Chunks and indexes a single document into the local SQLite store."""
        full_path = os.path.abspath(filepath)
        if not os.path.exists(full_path):
            return False

        mtime = os.path.getmtime(full_path)
        text = self.extract_text(full_path)
        if not text or len(text.strip()) < 10:
            return False

        filename = os.path.basename(full_path)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, mtime FROM documents WHERE filepath = ?", (full_path,))
            row = cursor.fetchone()

            if row:
                doc_id, old_mtime = row
                if mtime <= old_mtime:
                    return True  # Already indexed and unchanged
                cursor.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
                cursor.execute("UPDATE documents SET mtime = ? WHERE id = ?", (mtime, doc_id))
            else:
                cursor.execute("INSERT INTO documents (filepath, filename, mtime) VALUES (?, ?, ?)", (full_path, filename, mtime))
                doc_id = cursor.lastrowid

            # Chunk into overlapping segments of ~400 characters
            paragraphs = [p.strip() for p in re.split(r'\n{2,}|\.\s+', text) if len(p.strip()) > 20]
            chunks = []
            curr = ""
            for p in paragraphs:
                if len(curr) + len(p) < 400:
                    curr += (" " + p if curr else p)
                else:
                    if curr:
                        chunks.append(curr)
                    curr = p
            if curr:
                chunks.append(curr)

            for c in chunks:
                cursor.execute("INSERT INTO chunks (doc_id, chunk_text) VALUES (?, ?)", (doc_id, c))
            conn.commit()

        return True

    def query(self, query_text: str, top_k: int = 2) -> List[Dict[str, Any]]:
        """RAG Retrieval: Scores chunks against query terms and returns best matches."""
        terms = re.findall(r'\b[a-zA-Z0-9]{3,}\b', query_text.lower())
        if not terms:
            return []

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.chunk_text, d.filename, d.filepath
                FROM chunks c
                JOIN documents d ON c.doc_id = d.id
            """)
            rows = cursor.fetchall()

        scores = []
        for chunk_text, fname, fpath in rows:
            chunk_lower = chunk_text.lower()
            score = sum(chunk_lower.count(t) * (1.5 if t in fname.lower() else 1.0) for t in terms)
            if score > 0:
                scores.append((score, chunk_text, fname, fpath))

        scores.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, text, fname, fpath in scores[:top_k]:
            results.append({
                "score": score,
                "text": text,
                "filename": fname,
                "filepath": fpath
            })
        return results

    def summarize_latest_file(self, folder_path: str, ext_filter: str = ".pdf") -> Optional[str]:
        """Finds latest file matching filter in folder and provides an executive voice summary."""
        if not os.path.exists(folder_path):
            return None

        candidates = []
        for f in os.listdir(folder_path):
            if f.lower().endswith(ext_filter):
                p = os.path.join(folder_path, f)
                candidates.append((os.path.getmtime(p), p))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0], reverse=True)
        latest_file = candidates[0][1]
        text = self.extract_text(latest_file)
        if not text:
            return f"Found {os.path.basename(latest_file)}, but could not extract readable text."

        # Extractive summarization
        from smart_writer import SmartWriter
        writer = SmartWriter()
        summary = writer.summarize_text(text, max_sentences=3)
        return f"Summary of {os.path.basename(latest_file)}: {summary}"
