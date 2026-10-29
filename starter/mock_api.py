"""Local stand-in for POST /v1/events and GET /v1/events/{id}.

The real Vulnify client talks to it. Decisions come from vulnify/policies.
Nothing is sent to api.vulnify.io. A REVIEW stays pending unless approve_reviews
is set, in which case the next read returns finalDecision ALLOW.
"""
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional, Tuple

from starter.policies import decide, load_policies, to_api


class _Server(HTTPServer):
    def __init__(self, policies: list, approve_reviews: bool) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.policies = policies
        self.approve_reviews = approve_reviews
        self.events: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()


class _Handler(BaseHTTPRequestHandler):
    server: _Server

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/v1/events":
            self._send(404, {"error": "not_found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            event = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            self._send(400, {"error": "invalid_json"})
            return
        try:
            result = decide(event, self.server.policies)
        except ValueError as err:
            self._send(400, {"error": "invalid_policy", "message": str(err)})
            return
        event_id = str(uuid.uuid4())
        body = to_api(result, event_id)
        with self.server.lock:
            self.server.events[event_id] = body
        self._send(200, body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/")
        prefix = "/v1/events/"
        if not path.startswith(prefix):
            self._send(404, {"error": "not_found"})
            return
        event_id = path[len(prefix):]
        with self.server.lock:
            stored = self.server.events.get(event_id)
            if stored is None:
                self._send(404, {"error": "not_found"})
                return
            body = dict(stored)
            if self.server.approve_reviews and body.get("decision") == "REVIEW":
                body["finalDecision"] = "ALLOW"
                body["decision"] = "REVIEW"
                body["review"] = {"status": "APPROVED"}
        self._send(200, body)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send(self, status: int, body: Dict[str, Any]) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def start_mock(approve_reviews: bool = False) -> Tuple[_Server, str]:
    server = _Server(load_policies(), approve_reviews)
    threading.Thread(target=server.serve_forever, name="vulnify-mock", daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"


def stop_mock(server: Optional[_Server]) -> None:
    if server is None:
        return
    server.shutdown()
    server.server_close()
