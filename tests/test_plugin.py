from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]


class FakeContext:
    def __init__(self) -> None:
        self.hooks: dict[str, Callable[..., Any]] = {}
        self.commands: dict[str, dict[str, Any]] = {}

    def register_hook(self, name: str, callback: Callable[..., Any]) -> None:
        self.hooks[name] = callback

    def register_command(
        self,
        name: str,
        handler: Callable[[str], str],
        description: str = "",
        args_hint: str = "",
    ) -> None:
        self.commands[name] = {
            "handler": handler,
            "description": description,
            "args_hint": args_hint,
        }


class StubBridge:
    def __init__(self, succeed: bool = True) -> None:
        self.calls: list[tuple[str, int | None]] = []
        self.bubbles: list[str] = []
        self.succeed = succeed

    def send_state(self, state: str, duration: int | None = None) -> bool:
        self.calls.append((state, duration))
        return self.succeed

    def send_bubble(self, text: str) -> bool:
        self.bubbles.append(text)
        return self.succeed

    def diagnose(self) -> dict[str, object]:
        return {
            "sidecar": "reachable",
            "hooks": "enabled",
            "token": "ready",
            "state": "idle",
            "agent_source": "rndk-hermes",
        }


def load_plugin() -> ModuleType:
    name = f"rndk_petdex_bridge_test_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(
        name,
        ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_registers_only_bridge_hooks_and_namespaced_command() -> None:
    plugin = load_plugin()
    context = FakeContext()

    plugin.register(context)

    assert set(context.hooks) == {
        "on_session_start",
        "pre_tool_call",
        "post_tool_call",
        "on_session_end",
    }
    assert set(context.commands) == {"rndk-petdex"}
    assert context.commands["rndk-petdex"]["args_hint"] == "[status|ping|idle]"


def test_hooks_map_hermes_lifecycle_to_petdex_states() -> None:
    plugin = load_plugin()
    stub = StubBridge()
    setattr(plugin, "_bridge", stub)
    context = FakeContext()
    plugin.register(context)

    context.hooks["on_session_start"](session_id="session-1")
    context.hooks["pre_tool_call"](tool_name="read_file", args={"path": "/tmp/README.md"})
    context.hooks["post_tool_call"](
        tool_name="read_file",
        args={"path": "/tmp/README.md"},
        result="ok",
        status="ok",
    )
    context.hooks["on_session_end"](session_id="session-1")

    assert stub.calls == [
        ("jumping", 800),
        ("review", None),
        ("idle", None),
        ("waving", 1600),
    ]
    assert stub.bubbles == ["Thinking…", "Reading README.md", "Read README.md", "Done."]


def test_status_command_returns_diagnostics_without_token_value() -> None:
    plugin = load_plugin()
    setattr(plugin, "_bridge", StubBridge())

    output = plugin.handle_command("status")

    assert "RNDK Petdex Bridge" in output
    assert "sidecar: reachable" in output
    assert "hooks: enabled" in output
    assert "token: ready" in output
    assert "agent_source: rndk-hermes" in output


def test_empty_command_defaults_to_status() -> None:
    plugin = load_plugin()
    setattr(plugin, "_bridge", StubBridge())

    assert plugin.handle_command("") == plugin.handle_command("status")


def test_ping_and_idle_commands_send_only_fixed_states() -> None:
    plugin = load_plugin()
    stub = StubBridge()
    setattr(plugin, "_bridge", stub)

    assert "sent" in plugin.handle_command("ping").lower()
    assert "sent" in plugin.handle_command("idle").lower()
    assert stub.calls == [("waving", 1600), ("idle", None)]


def test_failed_send_is_reported_without_raising() -> None:
    plugin = load_plugin()
    setattr(plugin, "_bridge", StubBridge(succeed=False))

    output = plugin.handle_command("ping")

    assert "not sent" in output.lower()


def test_unknown_command_returns_usage_and_does_not_send() -> None:
    plugin = load_plugin()
    stub = StubBridge()
    setattr(plugin, "_bridge", stub)

    output = plugin.handle_command("shell rm -rf /")

    assert "Usage:" in output
    assert stub.calls == []
