# Codex Buddy Handoff

Date: 2026-04-24

## Current State

The repo now contains the MVP implementation for a repo-local Codex status
buddy.

- Git repo initialized locally on `main`.
- Upstream Anthropic firmware imported under `firmware/claude-desktop-buddy/`.
- Python bridge package implemented under `src/codex_buddy_bridge/`.
- Repo-local Codex hooks added under `.codex/`.
- User-level Codex feature flag was enabled in `~/.codex/config.toml`:
  `codex_hooks = true`.
- M5StickC Plus has been flashed by the user and shows the upstream Claude
  Buddy UI.
- USB serial bridge mode was added and confirmed working with the plugged-in
  device at `/dev/cu.usbserial-7552A41038`.

No remote is configured yet, so the local commit cannot be pushed until a
remote is added.

## How To Run

From the repo root:

```bash
PYTHONPATH=src python3 -u -m codex_buddy_bridge bridge \
  --serial-port /dev/cu.usbserial-7552A41038 \
  --port 47833
```

Keep that foreground process running while using Codex in this repo.

To manually test the status path:

```bash
curl -X POST http://127.0.0.1:47833/hook \
  -H 'Content-Type: application/json' \
  -d '{"hook":{"hook_event_name":"UserPromptSubmit"}}'
```

Expected behavior: the bridge logs `Codex working` and writes a heartbeat JSON
line over USB serial. The device should stop showing `No Claude connected`
after a keepalive heartbeat if the initial serial write was missed during
device reset.

## Important Implementation Notes

- The MVP is display-only. It does not approve or deny Codex actions.
- The hook forwarder exits `0` even if the bridge daemon is down.
- The bridge sanitizes hook payloads and does not send raw prompts, command
  strings, file paths, transcript text, or approval details to the device.
- BLE mode exists, but on this Mac the process crashed around CoreBluetooth
  scanning. USB serial mode is the validated path for now.
- The firmware is intentionally not rebranded yet; seeing `Claude Buddy` is
  expected.
- The upstream firmware accepts heartbeat JSON over both BLE and USB serial,
  which is why serial mode works.

## Verification So Far

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Result: `7 tests` passed.

Also verified:

- `python3 -m py_compile src/codex_buddy_bridge/*.py .codex/hooks/codex_buddy_hook.py tests/*.py`
- `.codex/hooks.json` parses as JSON.
- `codex features list` reports `codex_hooks` as `true`.

Firmware build/upload was not run by the agent because `pio` was initially not
installed. The user later flashed the device successfully.

## Next Good Tasks

1. Add a remote and push the current commit.
2. Make hook registration work reliably in the actual Codex Desktop session;
   if hooks do not fire, inspect Codex hook config discovery for repo-local
   `.codex/hooks.json`.
3. Revisit BLE mode on macOS:
   - test from a Terminal/Python process with Bluetooth permission
   - capture crash details if CoreBluetooth still exits
   - keep serial mode as the fallback
4. Add a tiny `make` or script wrapper for:
   - `bridge-serial`
   - `bridge-dry-run`
   - tests
5. Later milestone: rebrand firmware strings/device name from Claude to Codex.

## Known Commands

Run bridge over serial:

```bash
PYTHONPATH=src python3 -u -m codex_buddy_bridge bridge --serial-port /dev/cu.usbserial-7552A41038 --port 47833
```

Run dry-run bridge:

```bash
PYTHONPATH=src python3 -u -m codex_buddy_bridge bridge --dry-run
```

Run tests:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```
