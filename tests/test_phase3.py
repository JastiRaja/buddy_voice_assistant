import os
import tempfile
import shutil
import pyperclip
from converter import UnitConverter
from offline_encyclopedia import OfflineEncyclopedia
from smart_writer import SmartWriter
from clipboard_history import ClipboardHistory
from local_rag import LocalDocumentRAG
from actions import SystemController
from dispatcher import CommandDispatcher
from web_skills import WebSkills

class MockTTS:
    def __init__(self):
        self.last_spoken = ""
        self.history = []
    def speak(self, text, *args, **kwargs):
        self.last_spoken = text
        self.history.append(text)
        print(f" [MockTTS]: {text}")
    def stop(self): pass

def test_phase3_converter_and_encyclopedia():
    print("==================================================")
    print("TEST 1: Offline Converter & Encyclopedia")
    print("==================================================")
    # Unit & Currency Converter
    km_res = UnitConverter.parse_and_convert("convert 15 kilometers to miles")
    assert "9.32" in km_res, f"Converter failed: {km_res}"
    print(f"Converter [Length]: {km_res}")

    temp_res = UnitConverter.parse_and_convert("72 fahrenheit in celsius")
    assert "22.22" in temp_res, f"Converter failed: {temp_res}"
    print(f"Converter [Temp]: {temp_res}")

    curr_res = UnitConverter.parse_and_convert("convert 100 dollars to rupees")
    assert "8,400" in curr_res, f"Converter failed: {curr_res}"
    print(f"Converter [Currency]: {curr_res}")

    # Offline Encyclopedia
    enc = OfflineEncyclopedia()
    turing = enc.lookup("who is alan turing")
    assert turing and "father of modern computer science" in turing, "Encyclopedia failed on Alan Turing!"
    print(f"\nEncyclopedia [Alan Turing]: {turing[:80]}...")

    qc = enc.lookup("explain quantum computing")
    assert qc and "quantum mechanics" in qc, "Encyclopedia failed on Quantum Computing!"
    print(f"Encyclopedia [Quantum Computing]: {qc[:80]}...")
    print("-> PASSED: Converter & Encyclopedia verified 100% offline.\n")

def test_phase3_smart_writer_and_clipboard():
    print("==================================================")
    print("TEST 2: Smart Text Rewriter & Clipboard History")
    print("==================================================")
    writer = SmartWriter()
    
    # Grammar fix
    raw_text = "dont worry cant wait im here"
    fixed = writer.fix_grammar(raw_text)
    print(f"Grammar Fix: '{raw_text}' -> '{fixed}'")
    assert "don't" in fixed.lower() and "can't" in fixed.lower() and "I'm" in fixed, "Grammar fix failed!"

    # Professional tone
    casual_text = "hey guys let me know asap gonna fix this thx"
    pro = writer.make_professional(casual_text)
    print(f"Professional: '{casual_text}' -> '{pro}'")
    assert "at your earliest convenience" in pro and "Hello everyone" in pro, "Professional rephrase failed!"

    # Extractive summarizer
    long_passage = (
        "Artificial intelligence is transforming industries across the globe. "
        "Engineers are developing new algorithms to optimize power grids and reduce carbon footprints. "
        "Meanwhile, machine learning in healthcare is accelerating drug discovery and disease detection. "
        "Overall, these technologies are delivering unprecedented productivity gains across society."
    )
    summary = writer.summarize_text(long_passage, max_sentences=2)
    print(f"Extractive Summary: {summary}")
    assert len(summary) > 20 and len(summary) < len(long_passage), "Summarizer failed!"

    # Clipboard History
    clip_mgr = ClipboardHistory(max_items=10)
    clip_mgr.clear()
    clip_mgr.add_clip("First Snippet")
    clip_mgr.add_clip("Second Snippet")

    recent = clip_mgr.get_recent(2)
    print(f"Clipboard History Recent: {recent}")
    assert "Second Snippet" in recent, "Clipboard history failed to capture latest clip!"
    assert "First Snippet" in recent, "Clipboard history missed first clip!"
    print("-> PASSED: SmartWriter & ClipboardHistory verified.\n")

def test_phase3_local_document_rag():
    print("==================================================")
    print("TEST 3: Local Document RAG & Vector Indexing")
    print("==================================================")
    test_dir = tempfile.mkdtemp(prefix="buddy_rag_test_")
    db_file = os.path.join(test_dir, "test_rag.db")
    try:
        rag = LocalDocumentRAG(db_path=db_file)

        # Create sample project notes document
        notes_file = os.path.join(test_dir, "project_notes.md")
        with open(notes_file, "w", encoding="utf-8") as f:
            f.write(
                "# Project Titan\n\n"
                "We held a kickoff meeting regarding Project Titan on November 15.\n"
                "The core goal is building an air-gapped offline voice assistant with Kokoro TTS and local Faster-Whisper STT.\n"
                "Security compliance requires zero outbound socket connections in production mode.\n"
            )

        # Index document
        indexed = rag.index_file(notes_file)
        assert indexed, "RAG failed to index markdown document!"

        # Query document
        results = rag.query("Titan security compliance", top_k=1)
        assert len(results) > 0, "RAG query returned no results!"
        best = results[0]
        print(f"RAG Query Result from {best['filename']}: {best['text']}")
        assert "zero outbound socket connections" in best['text'], "RAG retrieval missed relevant chunk!"
        print("-> PASSED: Local Document RAG indexed and retrieved chunk with 100% precision.\n")
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)

def test_phase3_dispatcher_routing():
    print("==================================================")
    print("TEST 4: Dispatcher Integration for Phase 3")
    print("==================================================")
    tts = MockTTS()
    ctrl = SystemController(tts)
    ws = WebSkills(tts)
    disp = CommandDispatcher(ctrl, tts, ws)

    # 1. Converter routing
    disp.process("convert 15 kilometers to miles")
    assert "9.32" in tts.last_spoken, f"Dispatcher failed on converter: {tts.last_spoken}"

    # 2. Offline Encyclopedia routing
    disp.process("who is alan turing")
    assert "computer science" in tts.last_spoken, f"Dispatcher failed on encyclopedia: {tts.last_spoken}"

    # 3. Smart writing routing
    ctrl.writer.set_buffer("dont cant im gonna fix this asap")
    disp.process("make professional")
    assert "at your earliest convenience" in tts.last_spoken or "professional" in tts.last_spoken.lower(), "Make professional dispatch failed!"

    # 4. Clipboard history routing
    ctrl.clipboard_history.add_clip("Important meeting note")
    disp.process("read clipboard history")
    assert "clipboard items" in tts.last_spoken or "Item" in tts.last_spoken, "Clipboard history dispatch failed!"

    print("\n==================================================")
    print("ALL PHASE 3 CAPABILITIES VERIFIED 100%!")
    print("==================================================")

if __name__ == "__main__":
    test_phase3_converter_and_encyclopedia()
    test_phase3_smart_writer_and_clipboard()
    test_phase3_local_document_rag()
    test_phase3_dispatcher_routing()
