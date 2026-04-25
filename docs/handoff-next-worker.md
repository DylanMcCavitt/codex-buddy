# Codex Buddy Handoff

Date: 2026-04-25
Current issue: AGE-278 implemented locally
Branch: `feat/age-278-device-input-diagnostics`
PR: not opened yet

## Status

AGE-278 adds device-originated input capture without routing decisions back to
Codex.

- Added a shared sanitized device-input monitor for newline-delimited JSON.
- Serial mode now starts a reader for the connected USB serial device and keeps
  heartbeat publishing behavior unchanged.
- BLE mode now subscribes to Nordic UART TX notifications and feeds the same
  parser.
- `permission`, `status`, `ack`, and unknown command inputs are counted without
  storing prompt details.
- Malformed and oversized input is ignored safely and counted.
- `/healthz` now reports device-input diagnostics under publisher diagnostics
  for serial and BLE transports.

## Prior Context

- AGE-276 is merged to `main` at
  `daee79f8a9692315463b9df55656dd119b18915a`.
- AGE-272 added the workflow playbook docs and issue-packet conventions.
- AGE-275 added the opt-in LaunchAgent flow and remains the operational basis
  for background serial bridge installs.

## Next

- Review the AGE-278 diff and open a PR if acceptable.
- Do not route device decisions into Codex until AGE-280 or a later approval
  issue owns that behavior.

## Risks

- Hardware approval/deny remains out of scope and disabled.
- BLE transport remains less validated than USB serial.

## Files

- `src/codex_buddy_bridge/device_input.py`
- `src/codex_buddy_bridge/ble.py`
- `tests/test_device_input.py`
- `tests/test_serial_bridge.py`
- `tests/test_ble_discovery.py`
- `README.md`
- `docs/handoff-next-worker.md`

## Checks

- `python3 -m py_compile src/codex_buddy_bridge/device_input.py src/codex_buddy_bridge/ble.py tests/test_device_input.py tests/test_serial_bridge.py tests/test_ble_discovery.py` passed.
- `PYTHONPATH=src python3 -m unittest discover -s tests -v` passed: 36 tests.
- Manual serial button-input verification passed on `/dev/cu.usbserial-7552A41038`:
  after a forced `PermissionRequest`, pressing the device button updated
  `/healthz` with `device_input.last_command_type == "permission"` and
  `command_counts.permission == 1`.

## Commands

```bash
make bridge-serial
SERIAL_PORT=/dev/cu.usbserial-7552A41038 make bridge-serial
make bridge-dry-run
make test
curl -fsS http://127.0.0.1:47833/healthz
```
