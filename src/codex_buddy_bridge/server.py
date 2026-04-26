from __future__ import annotations

import hashlib
import json
import signal
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Mapping, Optional

from .ble import Publisher
from .ble import log
from .policy import (
    ApprovalPrompt,
    HardwareApprovalPolicy,
    PolicyConfig,
    PolicyDecision,
    PolicyOutcome,
    prompt_from_hook_payload,
)
from .state import (
    IDLE_SNAPSHOT,
    Snapshot,
    hook_event_name,
    hook_payload,
    known_hook_events,
    sanitized_identity,
    sanitized_preview,
    snapshot_for_hook,
)


KNOWN_HOOK_EVENTS = set(known_hook_events())
DEFAULT_PERMISSION_TIMEOUT = 12.0


@dataclass
class PermissionWaiter:
    prompt: ApprovalPrompt
    response: Optional[Dict[str, Any]] = None
    settled: bool = False


class BuddyDaemon:
    def __init__(
        self,
        publisher: Publisher,
        *,
        permission_timeout: float = DEFAULT_PERMISSION_TIMEOUT,
        policy: Optional[HardwareApprovalPolicy] = None,
    ) -> None:
        self.publisher = publisher
        self.policy = policy or HardwareApprovalPolicy(PolicyConfig.from_env())
        self.permission_timeout = permission_timeout
        self._current: Snapshot = IDLE_SNAPSHOT
        self._last_hook_event: Optional[str] = None
        self._event_counts: Dict[str, int] = {}
        self._active_permission: Optional[PermissionWaiter] = None
        self._last_permission_result: Optional[Dict[str, Optional[str]]] = None
        self._idle_timer: Optional[threading.Timer] = None
        self._keepalive_stop = threading.Event()
        self._keepalive_thread: Optional[threading.Thread] = None
        self._permission_condition = threading.Condition()
        self._lock = threading.Lock()
        configure_device_input = getattr(self.publisher, "configure_device_input", None)
        if callable(configure_device_input):
            configure_device_input(
                policy=self.policy,
                active_prompt=self.active_prompt,
                permission_handler=self.handle_device_permission,
            )

    @property
    def current(self) -> Snapshot:
        with self._lock:
            return self._current

    @property
    def diagnostics(self) -> Dict[str, Any]:
        with self._lock:
            diagnostics = {
                "last_hook_event": self._last_hook_event,
                "event_counts": dict(self._event_counts),
                "last_permission_result": (
                    dict(self._last_permission_result) if self._last_permission_result else None
                ),
            }
        diagnostics_fn = getattr(self.publisher, "diagnostics", None)
        publisher_diagnostics = diagnostics_fn() if callable(diagnostics_fn) else {}
        if publisher_diagnostics:
            diagnostics["publisher"] = publisher_diagnostics
        return diagnostics

    def start(self) -> None:
        self.publisher.start()
        self.publish(IDLE_SNAPSHOT)
        self._keepalive_thread = threading.Thread(target=self._keepalive_loop, daemon=True)
        self._keepalive_thread.start()

    def stop(self) -> None:
        self._keepalive_stop.set()
        with self._lock:
            if self._idle_timer:
                self._idle_timer.cancel()
                self._idle_timer = None
        if self._keepalive_thread:
            self._keepalive_thread.join(timeout=1)
        self.publisher.stop()

    def handle_hook(self, payload: Dict[str, Any]) -> Snapshot:
        if hook_event_name(payload) == "PermissionRequest":
            snapshot, _ = self._publish_permission_request(payload)
            return snapshot
        snapshot, idle_delay = snapshot_for_hook(payload)
        self.publish(snapshot, hook_event=_safe_hook_event_name(payload))
        if idle_delay is not None:
            self._schedule_idle(idle_delay)
        return snapshot

    def handle_hook_with_response(self, payload: Dict[str, Any]) -> tuple[Snapshot, Optional[Dict[str, Any]]]:
        if hook_event_name(payload) != "PermissionRequest":
            return self.handle_hook(payload), None

        snapshot, waiter = self._publish_permission_request(payload)
        response = self._wait_for_permission_response(waiter)
        return snapshot, response

    def active_prompt(self) -> Optional[ApprovalPrompt]:
        with self._permission_condition:
            if self._active_permission is None:
                return None
            return self._active_permission.prompt

    def handle_device_permission(self, payload: Dict[str, object], result: PolicyDecision) -> None:
        response = _response_for_policy_decision(result)
        routed_snapshot: Optional[Snapshot] = None
        with self._permission_condition:
            waiter = self._active_permission
            if waiter is None:
                self._last_permission_result = _permission_result(result, routed=False)
                return
            self._last_permission_result = _permission_result(result, routed=response is not None)
            if response is not None:
                waiter.response = response
                waiter.settled = True
                self._active_permission = None
                self._permission_condition.notify_all()
                routed_snapshot = _permission_routed_snapshot(result)
            if result.outcome == PolicyOutcome.REJECT_HARDWARE_APPROVE:
                waiter.settled = True
                self._active_permission = None
                self._permission_condition.notify_all()

        if routed_snapshot is not None:
            self.publish(routed_snapshot, hook_event=None)
            self._schedule_idle(2.0)
            return

        if waiter is not None and result.outcome == PolicyOutcome.REJECT_HARDWARE_APPROVE:
            self.publish(_policy_rejected_snapshot(waiter.prompt.prompt_id), hook_event=None)

    def publish(self, snapshot: Snapshot, hook_event: Optional[str] = None) -> None:
        with self._lock:
            if self._idle_timer:
                self._idle_timer.cancel()
                self._idle_timer = None
            if hook_event is not None:
                self._last_hook_event = hook_event
                self._event_counts[hook_event] = self._event_counts.get(hook_event, 0) + 1
            self._current = snapshot
        self.publisher.publish(snapshot.to_wire())
        event_prefix = f"event={hook_event!r} " if hook_event is not None else ""
        log(f"[codex-buddy] {event_prefix}{sanitized_preview(snapshot)}")

    def _republish_current(self) -> None:
        with self._lock:
            snapshot = self._current
        self.publisher.publish(snapshot.to_wire())

    def _keepalive_loop(self) -> None:
        while not self._keepalive_stop.wait(10):
            self._republish_current()

    def _schedule_idle(self, delay: float) -> None:
        def send_idle() -> None:
            self.publish(IDLE_SNAPSHOT)

        with self._lock:
            self._idle_timer = threading.Timer(delay, send_idle)
            self._idle_timer.daemon = True
            self._idle_timer.start()

    def _publish_permission_request(self, payload: Dict[str, Any]) -> tuple[Snapshot, PermissionWaiter]:
        raw_hook = hook_payload(payload)
        prompt = _sanitized_prompt_from_hook(raw_hook, payload)
        waiter = PermissionWaiter(prompt=prompt)
        with self._permission_condition:
            self._active_permission = waiter
        snapshot = _permission_snapshot(
            prompt.prompt_id,
            _safe_tool_name(raw_hook.get("tool_name")),
            sanitized_identity(payload),
        )
        self.publish(snapshot, hook_event=_safe_hook_event_name(payload))
        return snapshot, waiter

    def _wait_for_permission_response(self, waiter: PermissionWaiter) -> Optional[Dict[str, Any]]:
        deadline = time.monotonic() + max(self.permission_timeout, 0.0)
        with self._permission_condition:
            while not waiter.settled:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    if self._active_permission is waiter:
                        self._active_permission = None
                    return None
                self._permission_condition.wait(timeout=remaining)
            return dict(waiter.response) if waiter.response is not None else None


def make_handler(daemon: BuddyDaemon):
    class HookHandler(BaseHTTPRequestHandler):
        server_version = "CodexBuddyBridge/0.1"

        def do_GET(self) -> None:
            if self.path != "/healthz":
                self.send_error(404)
                return
            body = json.dumps(
                {
                    "ok": True,
                    "current": daemon.current.to_wire(),
                    "diagnostics": daemon.diagnostics,
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            if self.path != "/hook":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(min(length, 1_000_000))
                payload = json.loads(raw.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("payload must be an object")
                snapshot, hook_response = daemon.handle_hook_with_response(payload)
            except Exception as exc:
                body = json.dumps({"ok": False, "error": str(exc)}).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            response_body: Dict[str, Any] = {"ok": True, "current": snapshot.to_wire()}
            if hook_response is not None:
                response_body.update(hook_response)
            body = json.dumps(response_body).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: object) -> None:
            return

    return HookHandler


def _safe_hook_event_name(payload: Dict[str, Any]) -> str:
    event = hook_event_name(payload)
    if event in KNOWN_HOOK_EVENTS:
        return event
    return "unknown"


def _sanitized_prompt_from_hook(
    payload: Mapping[str, Any],
    envelope: Mapping[str, Any],
) -> ApprovalPrompt:
    prompt = prompt_from_hook_payload(payload)
    return ApprovalPrompt(
        prompt_id=_public_prompt_id(envelope),
        kind=prompt.kind,
        command=prompt.command,
    )


def _public_prompt_id(payload: Mapping[str, Any]) -> str:
    parts = []
    nested = payload.get("hook")
    values = [payload]
    if isinstance(nested, Mapping):
        values.append(nested)
    received_at = payload.get("received_at")
    if isinstance(received_at, (int, float, str)):
        parts.append(str(received_at))
    for source in values:
        for key in ("session_id", "turn_id", "tool_use_id", "id", "request_id"):
            value = source.get(key)
            if isinstance(value, str) and value:
                parts.append(value)
    if not parts:
        parts.append(str(time.time_ns()))
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"perm-{digest}"


def _safe_tool_name(value: object) -> str:
    if not isinstance(value, str) or not value:
        return "Codex"
    if value == "Bash":
        return "Bash"
    if value == "apply_patch":
        return "Edit"
    if value.startswith("mcp__"):
        return "MCP"
    return "Codex"


def _permission_snapshot(
    prompt_id: str,
    tool_name: str,
    identity: Optional[Dict[str, str]] = None,
) -> Snapshot:
    entries = ["approval needed", "A approve if allowed", "B deny"]
    if identity:
        project = identity.get("project")
        thread = identity.get("thread")
        if project:
            entries.append(f"project {project}")
        if thread:
            entries.append(thread)
    return Snapshot(
        total=1,
        running=0,
        waiting=1,
        msg="approval needed",
        entries=entries[:8],
        prompt={
            "id": prompt_id,
            "tool": tool_name,
            "hint": "A approve / B deny",
        },
        identity=identity,
    )


def _policy_rejected_snapshot(prompt_id: str) -> Snapshot:
    return Snapshot(
        total=1,
        running=0,
        waiting=1,
        msg="approve in Codex",
        entries=["hardware approve blocked", "approve in Codex"],
        prompt={
            "id": prompt_id,
            "tool": "Codex",
            "hint": "approve in app",
        },
    )


def _permission_routed_snapshot(result: PolicyDecision) -> Snapshot:
    if result.outcome == PolicyOutcome.ALLOW_DENY:
        msg = "denied"
        entries = ["denied from buddy"]
    else:
        msg = "approved"
        entries = ["approved from buddy"]
    return Snapshot(
        total=1,
        running=0,
        waiting=0,
        msg=msg,
        entries=entries,
    )


def _response_for_policy_decision(result: PolicyDecision) -> Optional[Dict[str, Any]]:
    if result.outcome == PolicyOutcome.ALLOW_DENY:
        return _hook_decision("deny", "Denied from Codex Buddy hardware.")
    if result.outcome == PolicyOutcome.ALLOW_APPROVE:
        return _hook_decision("allow")
    return None


def _hook_decision(behavior: str, message: Optional[str] = None) -> Dict[str, Any]:
    decision: Dict[str, str] = {"behavior": behavior}
    if message:
        decision["message"] = message
    return {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": decision,
        }
    }


def _permission_result(result: PolicyDecision, *, routed: bool) -> Dict[str, Optional[str]]:
    entry = result.log_entry.to_dict()
    entry["routed"] = "true" if routed else "false"
    return entry


def serve(daemon: BuddyDaemon, host: str, port: int) -> None:
    httpd = ThreadingHTTPServer((host, port), make_handler(daemon))
    daemon.start()
    stop = threading.Event()

    def request_stop(signum: int, frame: object) -> None:
        stop.set()
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    previous_int = signal.signal(signal.SIGINT, request_stop)
    previous_term = signal.signal(signal.SIGTERM, request_stop)
    try:
        log(f"[codex-buddy] hook endpoint http://{host}:{port}/hook")
        httpd.serve_forever()
    finally:
        signal.signal(signal.SIGINT, previous_int)
        signal.signal(signal.SIGTERM, previous_term)
        httpd.server_close()
        daemon.stop()
