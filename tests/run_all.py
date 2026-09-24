"""
tests/run_all.py
------------------
Runs the full test suite using Python's built-in unittest module
(no pytest / third-party test framework required).

Run:
    python tests/run_all.py
"""
import os
import sys
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTS_DIR)

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=TESTS_DIR, pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
