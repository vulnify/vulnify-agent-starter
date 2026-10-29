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
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        decision = DECISIONS[body["action"]]
        self._send(
            {
                "id": "evt_" + body["action"],
                "decision": decision,
                "finalDecision": decision,
                "reasons": ["test"],
                "review": {"status": "PENDING"} if decision == "REVIEW" else None,
            }
        )

    def do_GET(self):  # review resolved: approved
        event_id = self.path.rsplit("/", 1)[-1]
        self._send(
            {
                "id": event_id,
                "decision": "REVIEW",
                "finalDecision": "ALLOW",
                "reasons": ["test"],
                "review": {"status": "APPROVED"},
            }
        )

    def log_message(self, *args):
        return


class GuardedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), FakeApi)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        client = Vulnify(
            api_key="vln_test_mock",
            base_url=f"http://127.0.0.1:{cls.srv.server_port}",
            retries=0,
        )
        cls.box = GuardedToolbox(client, "StarterAgent", TOOLS, review_timeout=5)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def test_allow_runs(self):
        result = self.box.call("read_ticket", ticket_id="T-1")
        self.assertTrue(result.ran)
        self.assertEqual(result.decision, "ALLOW")
        self.assertIn("Ticket T-1", result.output)

    def test_review_waits_then_runs_when_approved(self):
        result = self.box.call("export_report", to="x@example.com", records=800)
        self.assertTrue(result.reviewed)
        self.assertTrue(result.ran)
        self.assertIn("Exported 800", result.output)

    def test_review_without_wait_does_not_run(self):
        box = GuardedToolbox(self.box.client, "StarterAgent", TOOLS, review_timeout=0)
        result = box.call("export_report", to="x@example.com", records=800)
        self.assertEqual(result.decision, "REVIEW")
        self.assertFalse(result.ran)
        self.assertNotIn("Exported", result.output)

    def test_block_refuses(self):
        result = self.box.call("delete_table", table="customers")
        self.assertFalse(result.ran)
        self.assertEqual(result.decision, "BLOCK")
        self.assertNotIn("Dropped", result.output)


if __name__ == "__main__":
    unittest.main()
