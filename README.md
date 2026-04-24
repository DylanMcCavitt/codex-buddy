# Codex Buddy

Repo-local Codex status bridge for Anthropic's Claude Desktop Buddy hardware
reference project.

The MVP keeps the upstream M5StickC Plus firmware mostly unchanged and adds a
small Python bridge. Repo-local Codex hooks post lifecycle events to the bridge,
and the bridge sends Claude-compatible heartbeat JSON to the device over USB
serial or BLE.

This first slice is display-only. The device can show idle, working, waiting
for approval, and completed states, but approvals still happen in the Codex UI.

## Layout

- `firmware/claude-desktop-buddy/` - upstream firmware baseline.
- `src/codex_buddy_bridge/` - bridge daemon.
- `.codex/hooks.json` - repo-local Codex hook registration for development.
- `.codex/hooks/codex_buddy_hook.py` - repo-local best-effort hook forwarder.
- `src/codex_buddy_bridge/hook.py` - user-level hook forwarder module.
- `tests/` - bridge and hook safety tests.

## Setup

Install the bridge:

```bash
python3 -m pip install -e .
```

BLE support is optional:

```bash
python3 -m pip install -e '.[ble]'
```

Run the common USB serial path:

```bash
make bridge-serial
```

Serial mode auto-discovers likely M5/ESP32 USB serial devices and keeps running
if the buddy is unplugged. To force a specific port:

```bash
SERIAL_PORT=/dev/cu.usbserial-7552A41038 make bridge-serial
```

For local testing without hardware:

```bash
make bridge-dry-run
```

To run BLE mode directly:

```bash
python3 -m codex_buddy_bridge bridge --device-prefix Claude --device-prefix Codex --port 47833
```

Run tests:

```bash
make test
```

Check the bridge and hook diagnostics:

```bash
curl -fsS http://127.0.0.1:47833/healthz
```

The `diagnostics` block reports the last sanitized hook event name, event counts,
and publisher diagnostics such as selected serial port, connection state, last
publish time, and last serial error. These diagnostics are local to the HTTP
health check; they are not added to the device heartbeat payload.

Codex hooks are repo-local in `.codex/hooks.json` for development. The hook
script exits successfully if the bridge is not running, so normal Codex work is
not blocked.

## User-level Hooks

User-level hooks are opt-in. Installing them writes Codex Buddy managed entries
to `~/.codex/hooks.json` so Codex lifecycle events from any workspace can reach
the local bridge.

Preview the exact global change first:

```bash
codex-buddy hooks install --dry-run
```

Install or update the managed entries:

```bash
codex-buddy hooks install
```

Disable the global integration:

```bash
codex-buddy hooks uninstall
```

The installer preserves unrelated user hooks and marks Codex Buddy entries in
the installed command with `CODEX_BUDDY_HOOK_MANAGED=1`. Uninstall removes only
entries with that marker.

To verify from another workspace:

1. Start the dry-run bridge from this repo:

   ```bash
   PYTHONPATH=src python3 -m codex_buddy_bridge bridge --dry-run --port 47833
   ```

2. Run a Codex prompt or shell tool call in a different repo or directory.
3. Check diagnostics:

   ```bash
   curl -fsS http://127.0.0.1:47833/healthz
   ```

Expected behavior: `diagnostics.event_counts` increments for a hook such as
`UserPromptSubmit`, `PreToolUse`, or `PostToolUse`, and the published device
snapshot remains sanitized.

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
Unknown or malformed hook event names are recorded as `unknown` in diagnostics
instead of being reflected raw.

The user-level hook installer changes only `~/.codex/hooks.json`, and only when
run without `--dry-run`.

## References

- [anthropics/claude-desktop-buddy](https://github.com/anthropics/claude-desktop-buddy)
- [Codex hooks](https://developers.openai.com/codex/hooks)
- [Port plan](docs/codex-buddy-port-plan.md)
