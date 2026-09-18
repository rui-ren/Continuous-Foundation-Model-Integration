"""Run CPU checks without dependencies; incomplete execution is not a pass."""

import argparse
from pathlib import Path
import sys
from typing import TextIO
import unittest


ROOT = Path(__file__).resolve().parents[1]


def run_suite(suite: unittest.TestSuite, stream: TextIO) -> int:
    selected = suite.countTestCases()
    if selected == 0:
        print("ERROR: no CPU tests selected.", file=stream)
        return 1
    print(f"Selected {selected} CPU tests; no GPU acceptance is performed.", file=stream)
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    if (
        not result.wasSuccessful()
        or result.skipped
        or result.expectedFailures
        or result.testsRun != selected
    ):
        print("CPU checks failed or incomplete.", file=stream)
        return 1
    print(f"CPU checks passed: {result.testsRun} executed, zero skipped.", file=stream)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pattern", default="test_*.py", help="Test filename pattern")
    args = parser.parse_args()
    # Prefer this checkout over any installed package or another worktree.
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))
    suite = unittest.TestLoader().discover(
        start_dir=str(ROOT / "tests"),
        pattern=args.pattern,
        top_level_dir=str(ROOT),
    )
    return run_suite(suite, sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
