from __future__ import annotations

import json
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional

from .ble import Publisher
from .ble import log
from .state import (
    IDLE_SNAPSHOT,
    Snapshot,
    hook_event_name,
    known_hook_events,
    sanitized_preview,
    snapshot_for_hook,
)


KNOWN_HOOK_EVENTS = set(known_hook_events())


class BuddyDaemon:
    def __init__(self, publisher: Publisher) -> None:
        self.publisher = publisher
        self._current: Snapshot = IDLE_SNAPSHOT
        self._last_hook_event: Optional[str] = None
        self._event_counts: Dict[str, int] = {}
        self._idle_timer: Optional[threading.Timer] = None
        self._keepalive_stop = threading.Event()
        self._keepalive_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

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
        snapshot, idle_delay = snapshot_for_hook(payload)
        self.publish(snapshot, hook_event=_safe_hook_event_name(payload))
        if idle_delay is not None:
            self._schedule_idle(idle_delay)
        return snapshot

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
                snapshot = daemon.handle_hook(payload)
            except Exception as exc:
                body = json.dumps({"ok": False, "error": str(exc)}).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            body = json.dumps({"ok": True, "current": snapshot.to_wire()}).encode("utf-8")
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
