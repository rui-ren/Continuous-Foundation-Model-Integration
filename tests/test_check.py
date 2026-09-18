import io
from pathlib import Path
import subprocess
import sys
import unittest

import cfmi
from tools.check import ROOT, run_suite


class CheckRunnerTests(unittest.TestCase):
    def run_case(self, method) -> tuple[int, str]:
        case_type = type("Probe", (unittest.TestCase,), {"test_probe": method})
        stream = io.StringIO()
        code = run_suite(unittest.defaultTestLoader.loadTestsFromTestCase(case_type), stream)
        return code, stream.getvalue()

    def test_successful_suite_passes(self) -> None:
        code, output = self.run_case(lambda case: case.assertTrue(True))
        self.assertEqual(code, 0)
        self.assertIn("1 executed, zero skipped", output)
        self.assertIn("no GPU acceptance", output)

    def test_empty_suite_fails(self) -> None:
        stream = io.StringIO()
        self.assertEqual(run_suite(unittest.TestSuite(), stream), 1)
        self.assertIn("no CPU tests selected", stream.getvalue())

    def test_failed_test_fails(self) -> None:
        code, _ = self.run_case(lambda case: case.fail("injected failure"))
        self.assertEqual(code, 1)

    def test_test_error_fails(self) -> None:
        def error(case):
            raise RuntimeError("injected error")

        code, _ = self.run_case(error)
        self.assertEqual(code, 1)

    def test_skipped_test_fails(self) -> None:
        code, _ = self.run_case(lambda case: case.skipTest("missing capability"))
        self.assertEqual(code, 1)

    def test_expected_failure_fails(self) -> None:
        code, _ = self.run_case(
            unittest.expectedFailure(lambda case: case.fail("known failure"))
        )
        self.assertEqual(code, 1)

    def test_unexpected_success_fails(self) -> None:
        code, _ = self.run_case(unittest.expectedFailure(lambda case: None))
        self.assertEqual(code, 1)

    def test_cli_unmatched_pattern_is_nonzero(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "check.py"), "--pattern", "no_tests_*.py"],
            capture_output=True,
            text=True,
            cwd=ROOT / "tests",
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("no CPU tests selected", result.stderr)

    def test_import_uses_this_checkout(self) -> None:
        self.assertEqual(
            Path(cfmi.__file__).resolve(), ROOT / "src" / "cfmi" / "__init__.py"
        )
