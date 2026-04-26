from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePath
import hashlib
import re
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
    identity: Optional[Dict[str, str]] = None

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
        if self.identity:
            payload["identity"] = dict(self.identity)
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
    identity = sanitized_identity(envelope)

    if event == "SessionStart":
        return _with_identity(IDLE_SNAPSHOT, identity), None
    if event == "UserPromptSubmit":
        return _with_identity(RUNNING_SNAPSHOT, identity), None
    if event == "PreToolUse":
        return _with_identity(RUNNING_SNAPSHOT, identity), None
    if event == "PermissionRequest":
        return _with_identity(WAITING_SNAPSHOT, identity), None
    if event == "PostToolUse":
        return _with_identity(RUNNING_SNAPSHOT, identity), None
    if event == "Stop":
        return _completion_snapshot(identity), 2.0

    return IDLE_SNAPSHOT, None


def sanitized_preview(snapshot: Snapshot) -> str:
    parts = [
        f"msg={snapshot.msg!r}",
        f"running={snapshot.running}",
        f"waiting={snapshot.waiting}",
    ]
    if snapshot.prompt:
        parts.append("prompt=display-only")
    if snapshot.identity:
        parts.append(f"identity={snapshot.identity!r}")
    return " ".join(parts)


def sanitized_identity(envelope: Mapping[str, Any]) -> Optional[Dict[str, str]]:
    payload = hook_payload(envelope)
    project = _sanitized_project_label(envelope, payload)
    thread = _sanitized_thread_label(envelope, payload)
    if not project and not thread:
        return None

    identity: Dict[str, str] = {}
    if project:
        identity["project"] = project
    if thread:
        identity["thread"] = thread
    return identity


def _sanitized_project_label(
    envelope: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> Optional[str]:
    for source in (payload, envelope):
        for key in (
            "cwd",
            "current_working_directory",
            "workspace",
            "workspace_path",
            "project_path",
            "repo_path",
        ):
            value = source.get(key)
            if isinstance(value, str):
                label = _clean_label(PurePath(value).name or value, max_len=22)
                if label:
                    return label
    return None


def _sanitized_thread_label(
    envelope: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> Optional[str]:
    parts: List[str] = []
    for source in (payload, envelope):
        for key in ("session_id", "conversation_id", "thread_id", "turn_id", "transcript_path"):
            value = source.get(key)
            if isinstance(value, str) and value:
                parts.append(value)
    if not parts:
        return None
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:8]
    return f"thread-{digest}"


def _clean_label(value: str, *, max_len: int) -> Optional[str]:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-_.")
    if not cleaned:
        return None
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip("-_.")
    return cleaned or None


def _with_identity(snapshot: Snapshot, identity: Optional[Dict[str, str]]) -> Snapshot:
    if not identity:
        return snapshot
    return Snapshot(
        total=snapshot.total,
        running=snapshot.running,
        waiting=snapshot.waiting,
        msg=snapshot.msg,
        entries=_identity_entries(snapshot.entries, identity),
        tokens=snapshot.tokens,
        tokens_today=snapshot.tokens_today,
        prompt=snapshot.prompt,
        identity=identity,
    )


def _completion_snapshot(identity: Optional[Dict[str, str]]) -> Snapshot:
    entries = ["completed"]
    if identity:
        entries = _identity_entries(entries, identity)
    return Snapshot(
        total=1,
        running=0,
        waiting=0,
        msg="completed",
        entries=entries,
        identity=identity,
    )


def _identity_entries(entries: List[str], identity: Dict[str, str]) -> List[str]:
    updated = list(entries)
    project = identity.get("project")
    thread = identity.get("thread")
    if project:
        updated.append(f"project {project}")
    if thread:
        updated.append(thread)
    return updated[:8]


def known_hook_events() -> Iterable[str]:
    return (
        "SessionStart",
        "UserPromptSubmit",
        "PreToolUse",
        "PermissionRequest",
        "PostToolUse",
        "Stop",
    )
