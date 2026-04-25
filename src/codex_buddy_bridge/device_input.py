from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from .policy import ApprovalPrompt, HardwareApprovalPolicy, PolicyDecision


MAX_DEVICE_INPUT_BYTES = 4096
KNOWN_DEVICE_COMMANDS = {"permission", "status", "ack"}


class DeviceInputMonitor:
    def __init__(
        self,
        max_line_bytes: int = MAX_DEVICE_INPUT_BYTES,
        logger: Optional[Callable[[str], None]] = None,
        policy: Optional[HardwareApprovalPolicy] = None,
        active_prompt: Optional[Callable[[], Optional[ApprovalPrompt]]] = None,
    ) -> None:
        self.max_line_bytes = max_line_bytes
        self._logger = logger
        self._policy = policy
        self._active_prompt = active_prompt
        self._buffer = bytearray()
        self._lock = threading.Lock()
        self._last_command_type: Optional[str] = None
        self._last_received_time: Optional[str] = None
        self._last_policy_decision: Optional[Dict[str, Optional[str]]] = None
        self._command_counts: Dict[str, int] = {}
        self._parse_errors = 0
        self._oversized_inputs = 0
        self._bytes_dropped = 0
        self._dropping_oversized = False

    def feed_bytes(self, data: bytes) -> None:
        if not data:
            return
        with self._lock:
            for byte in data:
                if byte == 10:
                    if self._dropping_oversized:
                        self._dropping_oversized = False
                        self._buffer.clear()
                        continue
                    line = bytes(self._buffer)
                    self._buffer.clear()
                    self._handle_line_locked(line)
                    continue
                if byte == 13:
                    continue
                if self._dropping_oversized:
                    self._bytes_dropped += 1
                    continue
                if len(self._buffer) >= self.max_line_bytes:
                    self._buffer.clear()
                    self._oversized_inputs += 1
                    self._bytes_dropped += 1
                    self._dropping_oversized = True
                    self._log("[codex-buddy] ignored oversized device input")
                    continue
                self._buffer.append(byte)

    def feed_line(self, data: bytes) -> None:
        line = data.rstrip(b"\r\n")
        with self._lock:
            if len(line) > self.max_line_bytes:
                self._oversized_inputs += 1
                self._log("[codex-buddy] ignored oversized device input")
                return
            self._handle_line_locked(line)

    def diagnostics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "last_command_type": self._last_command_type,
                "last_received_time": self._last_received_time,
                "last_policy_decision": (
                    dict(self._last_policy_decision) if self._last_policy_decision else None
                ),
                "command_counts": dict(self._command_counts),
                "parse_errors": self._parse_errors,
                "oversized_inputs": self._oversized_inputs,
                "bytes_dropped": self._bytes_dropped,
                "buffered_bytes": len(self._buffer),
                "dropping_oversized": self._dropping_oversized,
            }

    def _handle_line_locked(self, line: bytes) -> None:
        if not line.strip():
            return
        if len(line) > self.max_line_bytes:
            self._oversized_inputs += 1
            self._log("[codex-buddy] ignored oversized device input")
            return
        try:
            payload = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._parse_errors += 1
            self._log("[codex-buddy] ignored malformed device input")
            return
        if not isinstance(payload, dict):
            self._parse_errors += 1
            self._log("[codex-buddy] ignored non-object device input")
            return

        command = payload.get("cmd")
        command_type = command if isinstance(command, str) else "unknown"
        if command_type not in KNOWN_DEVICE_COMMANDS:
            command_type = "unknown"

        self._last_command_type = command_type
        self._last_received_time = datetime.now().isoformat(timespec="seconds")
        self._command_counts[command_type] = self._command_counts.get(command_type, 0) + 1
        if command_type == "permission":
            self._record_policy_decision_locked(payload)
        self._log(f"[codex-buddy] received device input cmd={command_type}")

    def _record_policy_decision_locked(self, payload: Dict[str, Any]) -> None:
        if self._policy is None:
            return
        prompt_id = payload.get("id")
        decision = payload.get("decision")
        active_prompt = self._active_prompt() if self._active_prompt is not None else None
        result: PolicyDecision = self._policy.evaluate(
            prompt_id=prompt_id if isinstance(prompt_id, str) else None,
            decision=decision if isinstance(decision, str) else None,
            active_prompt=active_prompt,
        )
        self._last_policy_decision = result.log_entry.to_dict()

    def _log(self, message: str) -> None:
        if self._logger is not None:
            self._logger(message)
