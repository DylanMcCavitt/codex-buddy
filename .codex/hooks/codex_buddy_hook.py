#!/usr/bin/env python3
"""Forward Codex hook events to the local Codex Buddy bridge.

This script is intentionally best-effort. It must never block or alter Codex
behavior if the bridge is not running.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request


DEFAULT_URL = "http://127.0.0.1:47833/hook"


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    envelope = {
        "received_at": time.time(),
        "hook": payload,
    }
    data = json.dumps(envelope, separators=(",", ":")).encode("utf-8")
    url = os.environ.get("CODEX_BUDDY_HOOK_URL", DEFAULT_URL)
    timeout = float(os.environ.get("CODEX_BUDDY_HOOK_TIMEOUT", "0.35"))
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout):
            pass
    except (OSError, urllib.error.URLError, TimeoutError, ValueError):
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
