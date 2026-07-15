"""Hermes plugin that bridges lifecycle events to Petdex Desktop."""

from __future__ import annotations

from typing import Any

if __package__:
    from .bridge import AGENT_SOURCE, PetdexBridge
else:  # Direct import by test runners and source checkers.
    from bridge import AGENT_SOURCE, PetdexBridge

_bridge = PetdexBridge()
_USAGE = "Usage: /rndk-petdex [status|ping|idle]"


def _pre_tool_call(
    tool_name: str = "",
    args: dict[str, Any] | None = None,
    **kwargs: Any,
) -> None:
    _bridge.send_state("running")


def _post_tool_call(
    tool_name: str = "",
    args: dict[str, Any] | None = None,
    result: Any = None,
    **kwargs: Any,
) -> None:
    _bridge.send_state("idle")


def _on_session_end(**kwargs: Any) -> None:
    _bridge.send_state("waving", duration=1600)


def _status() -> str:
    report = _bridge.diagnose()
    return "\n".join(
        [
            "RNDK Petdex Bridge",
            f"  sidecar: {report['sidecar']}",
            f"  hooks: {report['hooks']}",
            f"  token: {report['token']}",
            f"  state: {report['state']}",
            f"  agent_source: {report['agent_source']}",
        ]
    )


def _send_manual_state(state: str, duration: int | None = None) -> str:
    if _bridge.send_state(state, duration=duration):
        return f"Petdex state sent: {state} (agent_source={AGENT_SOURCE})."
    return "Petdex state not sent: sidecar unavailable, token missing, or hooks disabled."


def handle_command(raw_args: str) -> str:
    command = raw_args.strip().lower()
    if command in {"", "status"}:
        return _status()
    if command == "ping":
        return _send_manual_state("waving", duration=1600)
    if command == "idle":
        return _send_manual_state("idle")
    return _USAGE


def register(ctx: Any) -> None:
    ctx.register_hook("pre_tool_call", _pre_tool_call)
    ctx.register_hook("post_tool_call", _post_tool_call)
    ctx.register_hook("on_session_end", _on_session_end)
    ctx.register_command(
        "rndk-petdex",
        handle_command,
        description="Bridge Hermes activity to the shared Petdex Desktop mascot",
        args_hint="[status|ping|idle]",
    )
