# Codex Buddy Handoff

Date: 2026-04-25
Current issue: AGE-276 complete
Branch: `main`
PR: https://github.com/DylanMcCavitt/codex-buddy/pull/5 (merged)

## Status

AGE-276 is merged to `main` at
`daee79f8a9692315463b9df55656dd119b18915a`.

The issue updated firmware identity from upstream Claude Buddy branding to
Codex Buddy while preserving protocol compatibility and upstream attribution.

- BLE advertisement changed from `Claude-XXXX` to `Codex-XXXX`.
- Normal on-device copy now uses Codex-facing strings:
  `No Codex connected`, `I watch Codex`, `CODEX`, and BLE pairing instructions
  for running `codex-buddy`.
- Added firmware notes at `firmware/claude-desktop-buddy/CODEX_BUDDY.md`.
- Bridge BLE discovery still accepts both `Codex-*` and `Claude-*`; covered by
  a focused test.
- AGE-272 workflow docs are on `main`.

## Prior Context

- AGE-272 added the workflow playbook docs and issue-packet conventions.
- AGE-275 added the opt-in LaunchAgent flow and remains the operational basis
  for background serial bridge installs.

## Next

- Next ready Linear candidate: AGE-277 `Add Codex decision aliases and
  prompt-kind display to firmware`.
- Before starting AGE-277, read this handoff and the live Linear issue.
- If hardware is available, confirm the AGE-276 firmware advertises as
  `Codex-*` before layering additional firmware changes.

## Risks

- BLE advertisement verification is still pending unless the reviewer confirms
  `Codex-*` in a scanner or OS Bluetooth UI.
- Hardware approval/deny remains out of scope and disabled.
- BLE transport remains less validated than USB serial.

## Files

- `firmware/claude-desktop-buddy/src/main.cpp`
- `firmware/claude-desktop-buddy/src/data.h`
- `firmware/claude-desktop-buddy/CODEX_BUDDY.md`
- `tests/test_ble_discovery.py`
- `README.md`
- `docs/handoff-next-worker.md`

## Checks

- `PYTHONPATH=src python3 -m unittest tests.test_ble_discovery -v` passed.
- `python3 -m py_compile src/codex_buddy_bridge/ble.py tests/test_ble_discovery.py` passed.
- `PYTHONPATH=src python3 -m unittest discover -s tests -v` passed: 30 tests.
- `python3 -m platformio run` passed from `firmware/claude-desktop-buddy`.
- `pio run` could not be used directly because `pio` is not on this shell
  `PATH`; PlatformIO Core is available through `python3 -m platformio`.
- User verified `make bridge-serial` against the flashed hardware on
  `/dev/cu.usbserial-7552A41038`; bridge connected and sent a `Codex idle`
  heartbeat over serial.
- Manual BLE advertisement verification still pending.

## Commands

```bash
make bridge-serial
SERIAL_PORT=/dev/cu.usbserial-7552A41038 make bridge-serial
make bridge-dry-run
make test
cd firmware/claude-desktop-buddy && pio run
cd firmware/claude-desktop-buddy && python3 -m platformio run
cd firmware/claude-desktop-buddy && pio run -t upload
```
