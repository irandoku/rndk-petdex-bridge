"""Small, fail-open client for the local Petdex Desktop sidecar."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

AGENT_SOURCE = "rndk-hermes"
DEFAULT_BASE_URL = "http://127.0.0.1:7777"
TOKEN_HEADER = "X-Petdex-Update-Token"
SUPPORTED_STATES = frozenset({"idle", "running", "waving"})


class PetdexBridge:
    """Send Hermes activity to Petdex Desktop without affecting Hermes on errors."""

    def __init__(
        self,
        petdex_home: Optional[Path] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 0.3,
    ) -> None:
        self.petdex_home = petdex_home or Path.home() / ".petdex"
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @property
    def runtime_dir(self) -> Path:
        return self.petdex_home / "runtime"

    @property
    def hooks_enabled(self) -> bool:
        return not (self.runtime_dir / "hooks-disabled").exists()

    def _token(self) -> Optional[str]:
        try:
            token = (self.runtime_dir / "update-token").read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return token or None

    def _request(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        headers = {"Accept": "application/json"}
        data = None
        if method == "POST":
            token = self._token()
            if not token:
                return None
            headers[TOKEN_HEADER] = token
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload or {}, separators=(",", ":")).encode("utf-8")

        request = Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
            return None
        return decoded if isinstance(decoded, dict) else None

    def send_state(self, state: str, duration: Optional[int] = None) -> bool:
        if state not in SUPPORTED_STATES:
            raise ValueError(f"Unsupported Petdex state: {state}")
        if duration is not None and (not isinstance(duration, int) or duration < 0):
            raise ValueError("duration must be a non-negative integer or None")
        if not self.hooks_enabled:
            return False

        result = self._request(
            "/state",
            method="POST",
            payload={
                "state": state,
                "duration": duration,
                "agent_source": AGENT_SOURCE,
            },
        )
        return result is not None

    def diagnose(self) -> Dict[str, Any]:
        health = self._request("/health")
        state = self._request("/state") if health is not None else None
        return {
            "sidecar": "reachable" if health is not None else "unreachable",
            "hooks": "enabled" if self.hooks_enabled else "disabled",
            "token": "ready" if self._token() else "missing",
            "state": state.get("state", "unknown") if state else "unknown",
            "agent_source": AGENT_SOURCE,
        }
