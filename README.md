# Codex Buddy

Repo-local Codex status bridge for Anthropic's Claude Desktop Buddy hardware
reference project.

The MVP keeps the upstream M5StickC Plus firmware mostly unchanged and adds a
small Python bridge. Repo-local Codex hooks post lifecycle events to the bridge,
and the bridge sends Claude-compatible heartbeat JSON to the device over BLE.

This first slice is display-only. The device can show idle, working, waiting
for approval, and completed states, but approvals still happen in the Codex UI.

## Layout

- `firmware/claude-desktop-buddy/` - upstream firmware baseline.
- `src/codex_buddy_bridge/` - BLE bridge daemon.
- `.codex/hooks.json` - repo-local Codex hook registration.
- `.codex/hooks/codex_buddy_hook.py` - best-effort hook forwarder.
- `tests/` - bridge and hook safety tests.

## Setup

Install the bridge with BLE support:

```bash
python3 -m pip install -e '.[ble]'
```

Run the bridge:

```bash
python3 -m codex_buddy_bridge bridge --device-prefix Claude --device-prefix Codex --port 47833
```

If the buddy is plugged in by USB-C, you can bypass BLE and use serial:

```bash
PYTHONPATH=src python3 -m codex_buddy_bridge bridge --serial-port /dev/cu.usbserial-7552A41038 --port 47833
```

For local testing without hardware:

```bash
PYTHONPATH=src python3 -m codex_buddy_bridge bridge --dry-run
```

Codex hooks are repo-local in `.codex/hooks.json`. The hook script exits
successfully if the bridge is not running, so normal Codex work is not blocked.

## Firmware

The upstream firmware targets M5StickC Plus and PlatformIO:

```bash
cd firmware/claude-desktop-buddy
pio run
pio run -t upload
```

If starting from a previously flashed device:

```bash
pio run -t erase && pio run -t upload
```

PlatformIO is not vendored in this repo.

## Safety

The MVP intentionally does not forward raw prompts, transcript snippets, full
commands, file paths, or approval details over BLE. `PermissionRequest` only
sends a display-only prompt that tells you to approve in the Codex app.

## References

- [anthropics/claude-desktop-buddy](https://github.com/anthropics/claude-desktop-buddy)
- [Port plan](docs/codex-buddy-port-plan.md)
