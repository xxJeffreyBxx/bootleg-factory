"""POST /api/tasks against a real server on a free port. Run: python -m unittest test_web_post"""

import http.client
import json
import os
import tempfile
import unittest

import db
import web


class PostTaskTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Point the shared connection at a throwaway file; tasks.db stays untouched.
        cls.tmp = tempfile.TemporaryDirectory()
        cls.old_path, cls.old_conn = db.DB_PATH, db._conn
        db.DB_PATH = os.path.join(cls.tmp.name, "test.db")
        db._conn = None
        cls.port = web.start(preferred=18777)

    @classmethod
    def tearDownClass(cls):
        if db._conn is not None:
            db._conn.close()
        db.DB_PATH, db._conn = cls.old_path, cls.old_conn
        cls.tmp.cleanup()

    def post(self, body=b"", length=None):
        """Send a POST; `length` overrides Content-Length without sending that many bytes."""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.putrequest("POST", "/api/tasks")
            conn.putheader("Content-Type", "application/json")
            conn.putheader("Content-Length", str(len(body) if length is None else length))
            conn.endheaders(body)
            resp = conn.getresponse()  # raises socket.timeout if the handler hangs
            return resp.status, json.loads(resp.read())
        finally:
            conn.close()

    def test_negative_content_length_is_400(self):
        status, body = self.post(length=-1)
        self.assertEqual(status, 400)
        self.assertEqual(body, {"error": "bad Content-Length"})

    def test_oversized_body_is_413(self):
        # Only the header is checked, so there is no need to send 64 KB.
        status, body = self.post(length=web.MAX_BODY + 1)
        self.assertEqual(status, 413)
        self.assertEqual(body, {"error": "body too large"})

    def test_blank_text_is_400(self):
        status, body = self.post(json.dumps({"text": "   "}).encode())
        self.assertEqual(status, 400)
        self.assertEqual(body, {"error": "text is required"})

    def test_non_json_is_400(self):
        status, body = self.post(b"not json")
        self.assertEqual(status, 400)
        self.assertEqual(body, {"error": "body must be JSON"})

    def test_valid_body_returns_id(self):
        status, body = self.post(json.dumps({"text": "write a test"}).encode())
        self.assertEqual(status, 200)
        self.assertIsInstance(body["id"], int)
        self.assertEqual(db.get_task(body["id"])["text"], "write a test")


if __name__ == "__main__":
    unittest.main()
