# Codex Buddy Handoff

Date: 2026-04-25
Current issue: AGE-280 complete
Branch: `feat/age-280-hardware-hook-decisions`

## Status

AGE-280 routes hardware permission decisions back through supported Codex
`PermissionRequest` hooks and is ready to merge.

- Permission requests now publish a sanitized prompt id and coarse tool label to
  the device.
- Hardware deny/decline/cancel returns Codex hook `behavior: deny` for the
  matching active request.
- Hardware approve/accept/once returns Codex hook `behavior: allow` only when
  `CODEX_BUDDY_HARDWARE_APPROVE=1` and the command is allow-listed by policy.
- Policy-rejected hardware approve returns no hook decision and publishes an
  `approve in Codex` display state.
- Routed hardware approve/deny now clears the prompt on-device by publishing
  `approved` or `denied`, then idles.
- Stale or unknown device decisions are ignored by the policy.

## Next

- Next product issue: AGE-302, completion alerts and project/thread identity.
- Keep AGE-280 approval routing as a secondary capability for restricted Codex
  sessions.

## Risks

- The installed hook matcher remains Bash-only; README documents that Codex
  supports `apply_patch` and MCP `PermissionRequest` matchers, but this repo
  does not install those yet.
- BLE remains less validated than USB serial.

## Files

- `.codex/hooks.json`
- `src/codex_buddy_bridge/ble.py`
- `src/codex_buddy_bridge/device_input.py`
- `src/codex_buddy_bridge/hook.py`
- `src/codex_buddy_bridge/hooks_config.py`
- `src/codex_buddy_bridge/server.py`
- `tests/test_device_input.py`
- `tests/test_hook_script.py`
- `tests/test_server.py`
- `README.md`
- `docs/workflow-playbook/issues/AGE-280-hardware-hook-decisions.md`
- `docs/handoff-next-worker.md`

## Checks

- `PYTHONPATH=src python3 -m unittest discover -s tests -v` passed: 50 tests.
- `python3 -m py_compile src/codex_buddy_bridge/*.py .codex/hooks/codex_buddy_hook.py tests/*.py` passed.
- `python3 -m json.tool .codex/hooks.json >/dev/null` passed.
- `git diff --check` passed.
- Manual USB serial synthetic `PermissionRequest` reached the M5StickC Plus;
  hardware deny reached the bridge and routed through the policy. The clear
  behavior was fixed afterward and covered by `tests/test_server.py`.
