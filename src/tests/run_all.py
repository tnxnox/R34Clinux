from __future__ import annotations

import os
import sys
import unittest

if __name__ == "__main__":
    tests_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.normpath(os.path.join(tests_dir, ".."))
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    loader = unittest.TestLoader()
    suite = loader.discover(tests_dir, pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
