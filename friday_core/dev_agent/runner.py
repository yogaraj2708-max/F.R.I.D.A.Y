"""
F.R.I.D.A.Y. 3.0 — Developer Agent Automated Test Runner
Runs test suites in child processes and extracts structured verification reports.
"""

import sys
import time
import subprocess
import logging
from typing import Optional, List
from friday_core.dev_agent.models import CodeVerificationReport

logger = logging.getLogger("FRIDAY.TestRunner")


class TestRunner:
    """
    Executes automated tests in isolated subprocesses and verifies correctness.
    """
    def __init__(self, python_executable: Optional[str] = None):
        self.python_executable = python_executable or sys.executable

    def run_unittest(self, test_path: str, timeout_sec: float = 30.0) -> CodeVerificationReport:
        """Runs python -m unittest <test_path> and captures outcome."""
        start_time = time.perf_counter()
        cmd = [self.python_executable, "-m", "unittest", test_path]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec
            )
            duration = time.perf_counter() - start_time
            output = proc.stdout + "\n" + proc.stderr
            passed = proc.returncode == 0

            return CodeVerificationReport(
                syntax_valid=True,
                tests_passed=passed,
                test_output=output.strip(),
                exit_code=proc.returncode,
                duration_sec=round(duration, 3)
            )
        except subprocess.TimeoutExpired:
            duration = time.perf_counter() - start_time
            return CodeVerificationReport(
                syntax_valid=True,
                tests_passed=False,
                test_output=f"Test timed out after {timeout_sec} seconds.",
                exit_code=-1,
                duration_sec=round(duration, 3)
            )
        except Exception as e:
            duration = time.perf_counter() - start_time
            return CodeVerificationReport(
                syntax_valid=False,
                tests_passed=False,
                test_output=str(e),
                exit_code=-1,
                duration_sec=round(duration, 3)
            )
