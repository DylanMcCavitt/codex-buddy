# Codex Buddy Handoff

Date: 2026-04-24
Current issue: AGE-274
Branch: `feat/age-274-serial-bridge-resilience`
PR: https://github.com/DylanMcCavitt/codex-buddy/pull/2

## Status

AGE-274 is implemented and PR-ready.

- Added `make bridge-serial`, `make bridge-dry-run`, and `make test`.
- Added explicit serial mode: `--serial` auto-discovers likely M5/ESP32 USB
  serial devices; `--serial-port <path>` still forces a known path.
- Serial bridge startup no longer fails when the M5StickC Plus is unplugged.
- Reconnect happens on later publishes/keepalives after the device is plugged
  back in.
- Auto-discovery rejects unrelated ports such as `/dev/cu.Audioengine2`.
- `/healthz` now includes safe serial diagnostics:
  `selected_port`, `connection_state`, `last_publish_time`, and
  `last_serial_error`.

Expected unplug behavior: USB serial cannot remain physically connected while
the device is unplugged. The correct state is `connection_state: disconnected`,
`selected_port: null`, and retrying until the M5 returns.

## Next

Review and merge PR #2. After merge, sync `main` and move AGE-274 to Done.

## Risks

- BLE is still not revisited; USB serial remains the validated path.
- Firmware is still upstream-branded as Claude Buddy.
- Hardware approval/deny remains out of scope and disabled.

## Files

- `Makefile`
- `README.md`
- `pyproject.toml`
- `src/codex_buddy_bridge/ble.py`
- `src/codex_buddy_bridge/cli.py`
- `src/codex_buddy_bridge/server.py`
- `tests/test_serial_bridge.py`
- `tests/test_server.py`

## Checks

- `make test` passed: 23 tests.
- `python3 -m py_compile src/codex_buddy_bridge/*.py .codex/hooks/codex_buddy_hook.py tests/*.py`
- `python3 -m json.tool .codex/hooks.json >/dev/null`
- `git diff --check`
- Manual hardware reconnect passed:
  - unplugged: `/healthz` reported `selected_port: null`,
    `connection_state: disconnected`, and no likely M5/ESP32 serial port
  - plugged back in: bridge reconnected to `/dev/cu.usbserial-7552A41038` and
    resumed heartbeats

## Commands

```bash
make bridge-serial
SERIAL_PORT=/dev/cu.usbserial-7552A41038 make bridge-serial
make bridge-dry-run
make test
```
