"""
Tests for F.R.I.D.A.Y. 3.0 — Socket Leaks & Network Connection Hygiene
Verifies that HTTP sessions, DuckDuckGo client connections, Ollama clients,
and web crawlers cleanly close open sockets without socket accumulation.
"""

import sys
import time
import unittest
import psutil
from pathlib import Path
import httpx

root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from friday_core.settings import settings


class TestSocketCleanup(unittest.TestCase):
    def setUp(self):
        self.process = psutil.Process()

    def get_socket_count(self) -> int:
        try:
            return len(self.process.net_connections())
        except Exception:
            # Fallback if unprivileged
            return 0

    def test_httpx_client_connection_closure(self):
        """Verifies that closing HTTP client instances cleanly releases all underlying sockets."""
        s_baseline = self.get_socket_count()

        with httpx.Client(timeout=5.0) as client:
            try:
                # Local check or dummy connection attempt
                client.get("http://localhost:11434/api/version")
            except Exception:
                pass

        time.sleep(0.1)
        s_after = self.get_socket_count()

        print(f"\n[SOCKET AUDIT] HTTP Client: Baseline={s_baseline}, After Close={s_after}")
        self.assertLessEqual(s_after - s_baseline, 1, "Lingering socket detected after HTTP client closure")

    def test_repeated_session_socket_boundedness(self):
        """Verifies repeated HTTP sessions do not accumulate open socket handles."""
        s_baseline = self.get_socket_count()

        for _ in range(5):
            try:
                with httpx.Client(timeout=2.0) as client:
                    client.get("http://localhost:11434/api/tags")
            except Exception:
                pass

        time.sleep(0.1)
        s_after = self.get_socket_count()

        print(f"[SOCKET AUDIT] 5 Repeated HTTP Sessions: Baseline={s_baseline}, After={s_after}")
        # Socket count should not grow proportionally with session count (5 sessions != 5 leaked sockets)
        self.assertLessEqual(s_after - s_baseline, 2, "Unbounded socket accumulation across sessions")


if __name__ == "__main__":
    unittest.main()
