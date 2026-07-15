from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from bridge import AGENT_SOURCE, PetdexBridge


class _SidecarHandler(BaseHTTPRequestHandler):
    requests: list[dict[str, object]] = []
    state = {"state": "idle", "duration": None}
    bubble = {"text": "", "agent_source": None}

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, payload: dict[str, object], status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json({"ok": True})
        elif self.path == "/state":
            self._json(self.state)
        elif self.path == "/bubble":
            self._json(self.bubble)
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        self.requests.append(
            {
                "path": self.path,
                "token": self.headers.get("X-Petdex-Update-Token"),
                "payload": payload,
            }
        )
        if self.path == "/state":
            self.state = payload
            self._json({"ok": True})
        else:
            self._json({"error": "not found"}, 404)


@contextmanager
def _sidecar():
    _SidecarHandler.requests = []
    _SidecarHandler.state = {"state": "idle", "duration": None}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SidecarHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host = str(server.server_address[0])
        port = int(server.server_address[1])
        yield f"http://{host}:{port}", _SidecarHandler
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _write_token(petdex_home: Path, value: str = "test-token") -> None:
    runtime = petdex_home / "runtime"
    runtime.mkdir(parents=True)
    (runtime / "update-token").write_text(value, encoding="utf-8")


def test_send_state_posts_token_duration_and_agent_source(tmp_path: Path) -> None:
    _write_token(tmp_path)
    with _sidecar() as (url, handler):
        bridge = PetdexBridge(petdex_home=tmp_path, base_url=url)

        assert bridge.send_state("running", duration=1200) is True

        assert handler.requests == [
            {
                "path": "/state",
                "token": "test-token",
                "payload": {
                    "state": "running",
                    "duration": 1200,
                    "agent_source": AGENT_SOURCE,
                },
            }
        ]


def test_kill_switch_prevents_network_call(tmp_path: Path) -> None:
    _write_token(tmp_path)
    (tmp_path / "runtime" / "hooks-disabled").touch()
    with _sidecar() as (url, handler):
        bridge = PetdexBridge(petdex_home=tmp_path, base_url=url)

        assert bridge.send_state("idle") is False
        assert handler.requests == []


def test_missing_token_prevents_network_call(tmp_path: Path) -> None:
    with _sidecar() as (url, handler):
        bridge = PetdexBridge(petdex_home=tmp_path, base_url=url)

        assert bridge.send_state("idle") is False
        assert handler.requests == []


def test_invalid_state_is_rejected(tmp_path: Path) -> None:
    bridge = PetdexBridge(petdex_home=tmp_path)

    with pytest.raises(ValueError, match="Unsupported Petdex state"):
        bridge.send_state("arbitrary")


def test_diagnose_reports_runtime_without_exposing_token(tmp_path: Path) -> None:
    secret = "do-not-print-this-token"
    _write_token(tmp_path, secret)
    with _sidecar() as (url, _handler):
        bridge = PetdexBridge(petdex_home=tmp_path, base_url=url)

        report = bridge.diagnose()

    assert report["sidecar"] == "reachable"
    assert report["hooks"] == "enabled"
    assert report["token"] == "ready"
    assert report["state"] == "idle"
    assert report["agent_source"] == AGENT_SOURCE
    assert secret not in json.dumps(report)


def test_unreachable_sidecar_fails_open(tmp_path: Path) -> None:
    _write_token(tmp_path)
    bridge = PetdexBridge(
        petdex_home=tmp_path,
        base_url="http://127.0.0.1:1",
        timeout=0.05,
    )

    assert bridge.send_state("running") is False
    assert bridge.diagnose()["sidecar"] == "unreachable"
