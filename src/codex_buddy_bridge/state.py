from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


DISPLAY_ONLY_PROMPT = {
    "id": "display-only",
    "tool": "Codex",
    "hint": "approve in app",
}


@dataclass(frozen=True)
class Snapshot:
    total: int
    running: int
    waiting: int
    msg: str
    entries: List[str] = field(default_factory=list)
    tokens: int = 0
    tokens_today: int = 0
    prompt: Optional[Dict[str, str]] = None

    def to_wire(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "total": self.total,
            "running": self.running,
            "waiting": self.waiting,
            "msg": self.msg,
            "entries": self.entries[:8],
            "tokens": self.tokens,
            "tokens_today": self.tokens_today,
        }
        if self.prompt:
            payload["prompt"] = dict(self.prompt)
        return payload


IDLE_SNAPSHOT = Snapshot(
    total=1,
    running=0,
    waiting=0,
    msg="Codex idle",
    entries=["Codex idle"],
)

RUNNING_SNAPSHOT = Snapshot(
    total=1,
    running=1,
    waiting=0,
    msg="Codex working",
    entries=["Codex working"],
)

WAITING_SNAPSHOT = Snapshot(
    total=1,
    running=0,
    waiting=1,
    msg="approval needed",
    entries=["approval needed"],
    prompt=DISPLAY_ONLY_PROMPT,
)

COMPLETED_SNAPSHOT = Snapshot(
    total=1,
    running=0,
    waiting=0,
    msg="completed",
    entries=["completed"],
)


def hook_payload(envelope: Mapping[str, Any]) -> Mapping[str, Any]:
    """Accept either the raw Codex hook payload or the hook script envelope."""
    nested = envelope.get("hook")
    if isinstance(nested, Mapping):
        return nested
    return envelope


def hook_event_name(envelope: Mapping[str, Any]) -> str:
    payload = hook_payload(envelope)
    event = payload.get("hook_event_name")
    return event if isinstance(event, str) else ""


def snapshot_for_hook(envelope: Mapping[str, Any]) -> Tuple[Snapshot, Optional[float]]:
    """Map a Codex hook payload into a sanitized device heartbeat.

    Returns a snapshot and an optional delay after which the caller should send
    the idle snapshot. No raw user prompt, command, path, transcript, or approval
    detail is copied into the snapshot.
    """
    event = hook_event_name(envelope)

    if event == "SessionStart":
        return IDLE_SNAPSHOT, None
    if event == "UserPromptSubmit":
        return RUNNING_SNAPSHOT, None
    if event == "PreToolUse":
        return RUNNING_SNAPSHOT, None
    if event == "PermissionRequest":
        return WAITING_SNAPSHOT, None
    if event == "PostToolUse":
        return RUNNING_SNAPSHOT, None
    if event == "Stop":
        return COMPLETED_SNAPSHOT, 2.0

    return IDLE_SNAPSHOT, None


def sanitized_preview(snapshot: Snapshot) -> str:
    parts = [
        f"msg={snapshot.msg!r}",
        f"running={snapshot.running}",
        f"waiting={snapshot.waiting}",
    ]
    if snapshot.prompt:
        parts.append("prompt=display-only")
    return " ".join(parts)


def known_hook_events() -> Iterable[str]:
    return (
        "SessionStart",
        "UserPromptSubmit",
        "PreToolUse",
        "PermissionRequest",
        "PostToolUse",
        "Stop",
    )
