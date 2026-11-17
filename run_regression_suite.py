import sys
import os
import unittest

# Ensure root repository directory is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from tests import test_phase1
from tests import test_phase2
from tests import test_phase3
from tests import test_phase4
from tests import test_phase5

def run_all():
    print("=" * 60)
    print("      J.A.R.V.I.S. FULL SYSTEM REGRESSION SUITE")
    print("=" * 60)

    print("\n>>> [1/5] EXECUTING PHASE 1 TESTS: CORE & INTENT ROUTER <<<")
    test_phase1.run_tests()

    print("\n>>> [2/5] EXECUTING PHASE 2 TESTS: CROSS-PLATFORM & AUTOMATION <<<")
    test_phase2.test_phase2_os_adapters()
    test_phase2.test_phase2_file_organization()
    test_phase2.test_phase2_workspace_profiles_and_media()

    print("\n>>> [3/5] EXECUTING PHASE 3 TESTS: RAG & OFFLINE INTELLIGENCE <<<")
    test_phase3.test_phase3_converter_and_encyclopedia()
    test_phase3.test_phase3_smart_writer_and_clipboard()
    test_phase3.test_phase3_local_document_rag()
    test_phase3.test_phase3_dispatcher_routing()

    print("\n>>> [4/5] EXECUTING PHASE 4 TESTS: VISION & ERROR DIAGNOSTICS <<<")
    test_phase4.test_phase4_error_diagnostics()
    test_phase4.test_phase4_ocr_screen_text_extractor()
    test_phase4.test_phase4_dispatcher_routing()

    print("\n>>> [5/5] EXECUTING PHASE 5 TESTS: PRODUCTIVITY, MACROS & SANDBOX <<<")
    suite = unittest.TestLoader().loadTestsFromTestCase(test_phase5.TestPhase5ProductivityAndSecurity)
    res = unittest.TextTestRunner(verbosity=2).run(suite)
    if not res.wasSuccessful():
        print("[!] Phase 5 tests failed.")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  🎉 ALL 5 REGRESSION SUITES PASSED (100% SUCCESS RATE)!")
    print("=" * 60)

if __name__ == "__main__":
    run_all()
