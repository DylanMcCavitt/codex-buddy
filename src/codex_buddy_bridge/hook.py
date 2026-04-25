from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Mapping, Optional, TextIO


DEFAULT_URL = "http://127.0.0.1:47833/hook"
DEFAULT_TIMEOUT = 0.35
DEFAULT_PERMISSION_TIMEOUT = 12.5


def forward_payload(
    payload: Mapping[str, Any],
    *,
    url: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Mapping[str, Any]:
    envelope = {
        "received_at": time.time(),
        "hook": payload,
    }
    data = json.dumps(envelope, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(
        url or DEFAULT_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout or DEFAULT_TIMEOUT) as response:
        raw = response.read()
    if not raw:
        return {}
    parsed = json.loads(raw.decode("utf-8"))
    return parsed if isinstance(parsed, Mapping) else {}


def main(stdin: Optional[TextIO] = None) -> int:
    try:
        payload = json.load(stdin or sys.stdin)
        if not isinstance(payload, Mapping):
            return 0
    except Exception:
        return 0

    try:
        timeout = _timeout_for_payload(payload)
    except ValueError:
        timeout = DEFAULT_TIMEOUT

    try:
        response = forward_payload(
            payload,
            url=os.environ.get("CODEX_BUDDY_HOOK_URL", DEFAULT_URL),
            timeout=timeout,
        )
        output = response.get("hookSpecificOutput") if isinstance(response, Mapping) else None
        if isinstance(output, Mapping):
            json.dump({"hookSpecificOutput": output}, sys.stdout, separators=(",", ":"))
            sys.stdout.write("\n")
    except (OSError, urllib.error.URLError, TimeoutError, ValueError):
        pass

    return 0


def _timeout_for_payload(payload: Mapping[str, Any]) -> float:
    if payload.get("hook_event_name") == "PermissionRequest":
        return float(os.environ.get("CODEX_BUDDY_PERMISSION_TIMEOUT", str(DEFAULT_PERMISSION_TIMEOUT)))
    return float(os.environ.get("CODEX_BUDDY_HOOK_TIMEOUT", str(DEFAULT_TIMEOUT)))


if __name__ == "__main__":
    raise SystemExit(main())
