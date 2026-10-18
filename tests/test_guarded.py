"""Offline tests: a fake Vulnify API decides, no network or key needed."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from vulnify import Vulnify

from starter.guarded import GuardedToolbox
from starter.main import TOOLS

DECISIONS = {"READ_DATA": "ALLOW", "EXPORT_DATA": "REVIEW", "DELETE_DATA": "BLOCK"}


class FakeApi(BaseHTTPRequestHandler):
    def _send(self, body):
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        d = DECISIONS[body["action"]]
        self._send({"id": "evt_" + body["action"], "decision": d, "finalDecision": d,
                    "reasons": ["test"], "review": {"status": "PENDING"} if d == "REVIEW" else None})

    def do_GET(self):  # review resolved: approved
        self._send({"id": self.path.rsplit("/", 1)[-1], "decision": "REVIEW", "finalDecision": "ALLOW",
                    "review": {"status": "APPROVED"}})

    def log_message(self, *a):
        pass


class GuardedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), FakeApi)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        client = Vulnify(api_key="test", base_url=f"http://127.0.0.1:{cls.srv.server_port}")
        cls.box = GuardedToolbox(client, "StarterAgent", TOOLS, review_timeout=5)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_allow_runs(self):
        self.assertIn("Ticket T-1", self.box.call("read_ticket", ticket_id="T-1"))

    def test_review_waits_then_runs_when_approved(self):
        self.assertIn("Exported 800", self.box.call("export_customers", to="x@example.com", records=800))

    def test_block_refuses(self):
        self.assertIn("REFUSED", self.box.call("delete_table", table="customers"))


if __name__ == "__main__":
    unittest.main()
