"""Hermes plugin that bridges lifecycle events to Petdex Desktop."""

from __future__ import annotations

from typing import Any

if __package__:
    from .bridge import AGENT_SOURCE, PetdexBridge
else:  # Direct import by test runners and source checkers.
    from bridge import AGENT_SOURCE, PetdexBridge

_bridge = PetdexBridge()
_USAGE = "Usage: /rndk-petdex [status|ping|idle]"
_REVIEW_TOOLS = frozenset({"read_file", "search_files", "web_search", "browser_navigate"})


def _clip(text: str, limit: int = 40) -> str:
    return text if len(text) <= limit else f"{text[:limit - 1]}…"


def _arg(args: dict[str, Any] | None, *names: str) -> str | None:
    if not isinstance(args, dict):
        return None
    for name in names:
        value = args.get(name)
        if isinstance(value, str) and value:
            return value
    return None


def _basename(value: str | None) -> str | None:
    if not value:
        return None
    return value.replace("\\", "/").rsplit("/", 1)[-1]


def _format_tool(tool_name: str, args: dict[str, Any] | None, phase: str) -> str:
    past = phase == "done"
    name = str(tool_name or "tool")
    kind = name.rsplit("__", 1)[-1].lower()
    if kind in {"read_file", "get_record_text", "extract_record_content"}:
        target = _basename(_arg(args, "path", "file_path", "uuid"))
        return _clip(f"{'Read' if past else 'Reading'} {target or 'file'}")
    if kind in {"write_file", "patch", "update_record_content"}:
        target = _basename(_arg(args, "path", "file_path", "uuid"))
        return _clip(f"{'Edited' if past else 'Editing'} {target or 'file'}")
    if kind in {"terminal", "execute_code"}:
        command = _arg(args, "command", "code")
        first = (command or "command").split()[0]
        return _clip(f"{'Ran' if past else 'Running'} {first}")
    if kind in {"search_files", "web_search", "searxng_web_search"}:
        query = _arg(args, "pattern", "query")
        return _clip(f"{'Searched' if past else 'Searching'} {query or 'files'}")
    return _clip(f"{'Called' if past else 'Calling'} {name}")


def _is_failed(status: str | None, error_type: str | None, result: Any) -> bool:
    if status in {"error", "blocked", "cancelled"} or error_type:
        return True
    if isinstance(result, dict):
        return bool(result.get("error"))
    return False


def _pre_tool_call(
    tool_name: str = "",
    args: dict[str, Any] | None = None,
    **kwargs: Any,
) -> None:
    state = "review" if tool_name.lower() in _REVIEW_TOOLS else "running"
    _bridge.send_state(state)
    _bridge.send_bubble(_format_tool(tool_name, args, "running"))


def _post_tool_call(
    tool_name: str = "",
    args: dict[str, Any] | None = None,
    result: Any = None,
    status: str | None = None,
    error_type: str | None = None,
    **kwargs: Any,
) -> None:
    failed = _is_failed(status, error_type, result)
    _bridge.send_state("failed" if failed else "idle", duration=2500 if failed else None)
    text = _format_tool(tool_name, args, "done")
    _bridge.send_bubble(f"Failed {tool_name}" if failed else text)


def _on_session_start(**kwargs: Any) -> None:
    _bridge.send_state("jumping", duration=800)
    _bridge.send_bubble("Thinking…")


def _on_session_end(**kwargs: Any) -> None:
    _bridge.send_state("waving", duration=1600)
    _bridge.send_bubble("Done.")


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
    ctx.register_hook("on_session_start", _on_session_start)
    ctx.register_hook("pre_tool_call", _pre_tool_call)
    ctx.register_hook("post_tool_call", _post_tool_call)
    ctx.register_hook("on_session_end", _on_session_end)
    ctx.register_command(
        "rndk-petdex",
        handle_command,
        description="Bridge Hermes activity to the shared Petdex Desktop mascot",
        args_hint="[status|ping|idle]",
    )
