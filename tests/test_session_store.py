"""
Unit tests for friday_ui.core.session_store.SessionStore
Verifies SQLite persistence, session creation, message indexing, and session deletion.
"""

import unittest
from friday_ui.core.session_store import SessionStore


class TestSessionStore(unittest.TestCase):
    def setUp(self):
        self.store = SessionStore(":memory:")

    def tearDown(self):
        self.store.close()

    def test_create_and_get_session(self):
        sid = self.store.create_session("Custom Briefing")
        self.assertTrue(sid.startswith("sess_"))
        sessions = self.store.get_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["id"], sid)
        self.assertEqual(sessions[0]["title"], "Custom Briefing")

    def test_add_and_retrieve_messages(self):
        sid = self.store.create_session("Operation Titan")
        self.store.add_message(sid, "user", "System status report")
        self.store.add_message(sid, "friday", "All systems operational, Boss.")

        messages = self.store.get_messages(sid)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["content"], "System status report")
        self.assertEqual(messages[1]["role"], "friday")
        self.assertEqual(messages[1]["content"], "All systems operational, Boss.")

    def test_auto_title_update_on_first_user_message(self):
        sid = self.store.create_session("New Tactical Session")
        self.store.add_message(sid, "user", "What is quantum computing and how does it work?")

        sessions = self.store.get_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertTrue("quantum" in sessions[0]["title"].lower())

    def test_get_latest_session_id(self):
        # When empty, creates a session
        sid1 = self.store.get_latest_session_id()
        self.assertIsNotNone(sid1)

        # When not empty, returns the existing latest session
        sid2 = self.store.get_latest_session_id()
        self.assertEqual(sid1, sid2)

    def test_delete_session(self):
        sid = self.store.create_session("To Delete")
        self.store.add_message(sid, "user", "Temporary query")
        self.assertEqual(len(self.store.get_sessions()), 1)

        res = self.store.delete_session(sid)
        self.assertTrue(res)
        self.assertEqual(len(self.store.get_sessions()), 0)
        self.assertEqual(len(self.store.get_messages(sid)), 0)

    def test_clear_all_sessions(self):
        self.store.create_session("Session A")
        self.store.create_session("Session B")
        self.assertEqual(len(self.store.get_sessions()), 2)

        self.store.clear_all_sessions()
        self.assertEqual(len(self.store.get_sessions()), 0)


if __name__ == "__main__":
    unittest.main()
