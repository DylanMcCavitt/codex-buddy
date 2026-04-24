from __future__ import annotations

import json
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional

from .ble import Publisher
from .ble import log
from .state import IDLE_SNAPSHOT, Snapshot, sanitized_preview, snapshot_for_hook


class BuddyDaemon:
    def __init__(self, publisher: Publisher) -> None:
        self.publisher = publisher
        self._current: Snapshot = IDLE_SNAPSHOT
        self._idle_timer: Optional[threading.Timer] = None
        self._keepalive_stop = threading.Event()
        self._keepalive_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    @property
    def current(self) -> Snapshot:
        with self._lock:
            return self._current

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
        self.publish(snapshot)
        if idle_delay is not None:
            self._schedule_idle(idle_delay)
        return snapshot

    def publish(self, snapshot: Snapshot) -> None:
        with self._lock:
            if self._idle_timer:
                self._idle_timer.cancel()
                self._idle_timer = None
            self._current = snapshot
        self.publisher.publish(snapshot.to_wire())
        log(f"[codex-buddy] {sanitized_preview(snapshot)}")

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
            body = json.dumps({"ok": True, "current": daemon.current.to_wire()}).encode("utf-8")
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
