from __future__ import annotations

import hashlib
import os
import shlex
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple


APPROVE_DECISIONS = {"accept", "approve", "once", "acceptForSession"}
DENY_DECISIONS = {"decline", "deny", "cancel", "reject"}

DEFAULT_READ_ONLY_COMMANDS = (
    ("cat",),
    ("date",),
    ("git", "diff"),
    ("git", "log"),
    ("git", "show"),
    ("git", "status"),
    ("ls",),
    ("pwd",),
    ("rg",),
    ("sed",),
    ("wc",),
)

HIGH_RISK_COMMAND_WORDS = {
    "chmod",
    "chown",
    "curl",
    "dd",
    "mv",
    "rm",
    "rsync",
    "scp",
    "sh",
    "sudo",
    "tee",
}

HIGH_RISK_SHELL_TOKENS = {
    ">",
    ">>",
    "|",
    "&&",
    "||",
    ";",
    "$(",
    "`",
}


class PolicyOutcome(str, Enum):
    ALLOW_APPROVE = "allow_approve"
    ALLOW_DENY = "allow_deny"
    REJECT_HARDWARE_APPROVE = "reject_hardware_approve"
    IGNORE_STALE_OR_UNKNOWN_PROMPT = "ignore_stale_or_unknown_prompt"


class PromptKind(str, Enum):
    COMMAND = "command"
    FILE_CHANGE = "file_change"
    NETWORK = "network"
    GENERIC = "generic"


@dataclass(frozen=True)
class ApprovalPrompt:
    prompt_id: str
    kind: PromptKind = PromptKind.GENERIC
    command: Optional[str] = None


@dataclass(frozen=True)
class PolicyConfig:
    hardware_approve_enabled: bool = False
    allowed_command_prefixes: Tuple[Tuple[str, ...], ...] = DEFAULT_READ_ONLY_COMMANDS

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "PolicyConfig":
        values = os.environ if env is None else env
        approve_enabled = values.get("CODEX_BUDDY_HARDWARE_APPROVE", "").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        configured_commands = _parse_command_list(values.get("CODEX_BUDDY_APPROVE_COMMANDS", ""))
        return cls(
            hardware_approve_enabled=approve_enabled,
            allowed_command_prefixes=DEFAULT_READ_ONLY_COMMANDS + configured_commands,
        )


@dataclass(frozen=True)
class PolicyDecisionLogEntry:
    timestamp: str
    prompt_id_hash: Optional[str]
    prompt_kind: str
    decision: str
    outcome: str
    reason: str

    def to_dict(self) -> dict[str, Optional[str]]:
        return {
            "timestamp": self.timestamp,
            "prompt_id_hash": self.prompt_id_hash,
            "prompt_kind": self.prompt_kind,
            "decision": self.decision,
            "outcome": self.outcome,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PolicyDecision:
    outcome: PolicyOutcome
    reason: str
    log_entry: PolicyDecisionLogEntry

    @property
    def allowed(self) -> bool:
        return self.outcome in {PolicyOutcome.ALLOW_APPROVE, PolicyOutcome.ALLOW_DENY}


class SanitizedDecisionLog:
    def __init__(self, max_entries: int = 50) -> None:
        self.max_entries = max_entries
        self._entries: List[PolicyDecisionLogEntry] = []
        self._lock = threading.Lock()

    def record(self, entry: PolicyDecisionLogEntry) -> None:
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self.max_entries:
                self._entries = self._entries[-self.max_entries :]

    def entries(self) -> List[Dict[str, Optional[str]]]:
        with self._lock:
            return [entry.to_dict() for entry in self._entries]


@dataclass
class HardwareApprovalPolicy:
    config: PolicyConfig = field(default_factory=PolicyConfig)
    decision_log: SanitizedDecisionLog = field(default_factory=SanitizedDecisionLog)

    def evaluate(
        self,
        *,
        prompt_id: Optional[str],
        decision: Optional[str],
        active_prompt: Optional[ApprovalPrompt],
    ) -> PolicyDecision:
        normalized_decision = _normalize_decision(decision)
        if normalized_decision is None:
            return self._result(
                PolicyOutcome.IGNORE_STALE_OR_UNKNOWN_PROMPT,
                prompt=active_prompt,
                prompt_id=prompt_id,
                decision="unknown",
                reason="unknown_decision",
            )

        if active_prompt is None or not prompt_id or active_prompt.prompt_id != prompt_id:
            return self._result(
                PolicyOutcome.IGNORE_STALE_OR_UNKNOWN_PROMPT,
                prompt=active_prompt,
                prompt_id=prompt_id,
                decision=normalized_decision,
                reason="stale_or_unknown_prompt",
            )

        if normalized_decision in DENY_DECISIONS:
            return self._result(
                PolicyOutcome.ALLOW_DENY,
                prompt=active_prompt,
                prompt_id=prompt_id,
                decision=normalized_decision,
                reason="deny_allowed_by_default",
            )

        if normalized_decision not in APPROVE_DECISIONS:
            return self._result(
                PolicyOutcome.IGNORE_STALE_OR_UNKNOWN_PROMPT,
                prompt=active_prompt,
                prompt_id=prompt_id,
                decision="unknown",
                reason="unknown_decision",
            )

        if not self.config.hardware_approve_enabled:
            return self._result(
                PolicyOutcome.REJECT_HARDWARE_APPROVE,
                prompt=active_prompt,
                prompt_id=prompt_id,
                decision=normalized_decision,
                reason="hardware_approve_disabled",
            )

        if active_prompt.kind != PromptKind.COMMAND:
            return self._result(
                PolicyOutcome.REJECT_HARDWARE_APPROVE,
                prompt=active_prompt,
                prompt_id=prompt_id,
                decision=normalized_decision,
                reason="prompt_kind_not_allowlisted",
            )

        if _command_is_allowlisted(active_prompt.command, self.config.allowed_command_prefixes):
            return self._result(
                PolicyOutcome.ALLOW_APPROVE,
                prompt=active_prompt,
                prompt_id=prompt_id,
                decision=normalized_decision,
                reason="command_allowlisted",
            )

        return self._result(
            PolicyOutcome.REJECT_HARDWARE_APPROVE,
            prompt=active_prompt,
            prompt_id=prompt_id,
            decision=normalized_decision,
            reason="command_not_allowlisted",
        )

    def _result(
        self,
        outcome: PolicyOutcome,
        *,
        prompt: Optional[ApprovalPrompt],
        prompt_id: Optional[str],
        decision: str,
        reason: str,
    ) -> PolicyDecision:
        prompt_kind = prompt.kind.value if prompt is not None else "unknown"
        log_entry = PolicyDecisionLogEntry(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            prompt_id_hash=_hash_prompt_id(prompt_id),
            prompt_kind=prompt_kind,
            decision=decision,
            outcome=outcome.value,
            reason=reason,
        )
        self.decision_log.record(log_entry)
        return PolicyDecision(outcome=outcome, reason=reason, log_entry=log_entry)


def prompt_from_hook_payload(payload: Mapping[str, object]) -> ApprovalPrompt:
    prompt_id = _safe_str(payload.get("id")) or _safe_str(payload.get("request_id")) or "display-only"
    tool_input = payload.get("tool_input")
    command = None
    if isinstance(tool_input, Mapping):
        command = _safe_str(tool_input.get("command"))
    return ApprovalPrompt(prompt_id=prompt_id, kind=PromptKind.COMMAND if command else PromptKind.GENERIC, command=command)


def _normalize_decision(decision: Optional[str]) -> Optional[str]:
    if not isinstance(decision, str):
        return None
    value = decision.strip()
    if not value:
        return None
    if value.lower() == "acceptforsession":
        return "acceptForSession"
    lowered = value.lower()
    if lowered in {"accept", "approve", "once", "decline", "deny", "cancel", "reject"}:
        return lowered
    return None


def _command_is_allowlisted(
    command: Optional[str],
    allowed_prefixes: Sequence[Sequence[str]],
) -> bool:
    argv = _split_command(command)
    if not argv:
        return False
    if _looks_high_risk(command or "", argv):
        return False
    return any(_starts_with(argv, prefix) for prefix in allowed_prefixes)


def _split_command(command: Optional[str]) -> Tuple[str, ...]:
    if not command:
        return ()
    try:
        return tuple(shlex.split(command))
    except ValueError:
        return ()


def _looks_high_risk(command: str, argv: Sequence[str]) -> bool:
    first = argv[0].lower()
    if first in HIGH_RISK_COMMAND_WORDS:
        return True
    if first == "sed" and any(arg == "-i" or arg.startswith("-i.") for arg in argv[1:]):
        return True
    if first == "git" and any(arg.startswith("--output") for arg in argv[1:]):
        return True
    return any(token in command for token in HIGH_RISK_SHELL_TOKENS)


def _starts_with(argv: Sequence[str], prefix: Sequence[str]) -> bool:
    if not prefix or len(argv) < len(prefix):
        return False
    return tuple(part.lower() for part in argv[: len(prefix)]) == tuple(part.lower() for part in prefix)


def _parse_command_list(raw: str) -> Tuple[Tuple[str, ...], ...]:
    commands = []
    for value in raw.replace("\n", ",").split(","):
        parts = _split_command(value.strip())
        if parts:
            commands.append(parts)
    return tuple(commands)


def _hash_prompt_id(prompt_id: Optional[str]) -> Optional[str]:
    if not prompt_id:
        return None
    return hashlib.sha256(prompt_id.encode("utf-8")).hexdigest()[:16]


def _safe_str(value: object) -> Optional[str]:
    if isinstance(value, str) and value:
        return value
    return None
