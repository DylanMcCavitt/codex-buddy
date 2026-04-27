# Codex Buddy

Repo-local Codex status bridge for Anthropic's Claude Desktop Buddy hardware
reference project.

The MVP keeps the upstream M5StickC Plus firmware protocol mostly unchanged and
adds a small Python bridge. Repo-local Codex hooks post lifecycle events to the
bridge, and the bridge sends compatible heartbeat JSON to the device over USB
serial or BLE.

The device can show idle, working, waiting for approval, and completed states.
For supported Codex `PermissionRequest` hooks, the buddy can deny from hardware
and can approve only when the local hardware approval policy explicitly allows
the request. When Codex emits `Stop`, the bridge publishes a short completed
state with a sanitized project/worktree label and hashed thread label so the
device can show which task finished and play a completion chirp.

## Layout

- `firmware/claude-desktop-buddy/` - upstream firmware baseline.
- `src/codex_buddy_bridge/` - bridge daemon.
- `.codex/hooks.json` - repo-local Codex hook registration for development.
- `.codex/hooks/codex_buddy_hook.py` - repo-local best-effort hook forwarder.
- `src/codex_buddy_bridge/hook.py` - user-level hook forwarder module.
- `tests/` - bridge and hook safety tests.

## Setup

Use a virtual environment for a fresh checkout, then install the bridge:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install --upgrade pip
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

Foreground mode is the best debugging path because logs stream to the terminal
and also append to `~/.codex-buddy/bridge.log`.

To run BLE mode directly:

```bash
python3 -m codex_buddy_bridge bridge --device-prefix Claude --device-prefix Codex --port 47833
```

The default BLE bridge scan includes both `Codex-*` and `Claude-*` device names
so reflashed Codex Buddy firmware and older upstream-branded firmware both
remain discoverable during the transition.

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
publish time, and last serial error. Serial and BLE publisher diagnostics also
include sanitized device-input counters for newline-delimited JSON sent back by
the buddy, including the last command type, command counts, parse errors, and
oversized input drops. These diagnostics are local to the HTTP health check;
they are not added to the device heartbeat payload.

Completion snapshots include an `identity` object when Codex supplies workspace
or session fields. The `project` value is the sanitized basename of the
workspace path, and the `thread` value is a short hash such as
`thread-1a2b3c4d`. Full paths, transcript paths, raw prompts, session ids, and
commands are not sent to the device.

Codex hooks are repo-local in `.codex/hooks.json` for development. The default
hook profile keeps high-frequency tool lifecycle hooks disabled, so Codex does
not add `PreToolUse` and `PostToolUse` rows around every Bash tool call. The
hook script exits successfully if the bridge is not running, so normal Codex
work is not blocked.

## Hardware Approval Policy

The bridge includes a local safety policy for hardware-originated approval
decisions. The policy gates every hardware decision before the bridge returns a
Codex hook response.

Default behavior:

- deny/decline/cancel is allowed for the active prompt
- approve/accept/once is rejected unless hardware approve is explicitly enabled
- high-risk commands and non-command prompts stay in the Codex UI
- decision logs are sanitized and include only timestamp, prompt id hash, prompt
  kind, normalized decision, outcome, and reason

Hardware approve can be enabled for policy tests or future integration by
setting:

```bash
CODEX_BUDDY_HARDWARE_APPROVE=1
CODEX_BUDDY_APPROVE_COMMANDS="python3 -m unittest,make test"
```

The built-in allow-list is conservative and read-only. Configured commands are
matched as command prefixes. Raw prompt text, full command strings, file paths,
and transcript text are not written to the decision log.

## Hardware Permission Decisions

Codex Buddy returns hook decisions only for Codex `PermissionRequest` events.
The current hook matcher is `Bash`; Codex documentation also supports
`PermissionRequest` matchers for `apply_patch` and MCP tool names, but this repo
only installs the Bash matcher today.

Supported behavior:

- hardware deny/decline/cancel returns Codex `behavior: deny` for the matching
  active permission request
- hardware approve/accept/once returns Codex `behavior: allow` only when
  `CODEX_BUDDY_HARDWARE_APPROVE=1` is set and the command is allow-listed by the
  local policy
- policy-rejected hardware approve returns no hook decision, so the normal Codex
  approval UI remains the source of truth
- stale ids, unknown decisions, malformed input, and decisions after the active
  hook wait expires are ignored

The device receives only a sanitized prompt id, a coarse tool label, and a short
hint. Raw commands, prompt text, file paths, transcript paths, and approval
reasons stay local to the bridge for policy evaluation.

Manual hardware test path:

1. Start the bridge with USB serial:

   ```bash
   make bridge-serial
   ```

2. In another Codex session with hooks enabled, trigger a harmless Bash approval
   such as an escalated read-only command. Press the buddy deny button. Codex
   should receive a denied `PermissionRequest`.
3. Restart the bridge with hardware approve enabled for a safe command:

   ```bash
   CODEX_BUDDY_HARDWARE_APPROVE=1 CODEX_BUDDY_APPROVE_COMMANDS="git status" make bridge-serial
   ```

4. Trigger an approval for `git status --short` and press the buddy approve
   button. Codex should receive an allowed `PermissionRequest`.
5. Trigger a high-risk approval such as a destructive shell command and press
   the buddy approve button. The buddy should show `approve in Codex`, and Codex
   should still require the in-app approval UI.
6. Check local diagnostics:

   ```bash
   curl -fsS http://127.0.0.1:47833/healthz
   ```

   Confirm `diagnostics.last_permission_result` and
   `diagnostics.publisher.device_input.last_policy_decision` show sanitized
   outcomes without raw command or prompt text.

## User-level Hooks

User-level hooks are opt-in. Installing them writes Codex Buddy managed entries
to `~/.codex/hooks.json` so Codex lifecycle events from any workspace can reach
the local bridge.

The managed default is intentionally quiet: `SessionStart`, `UserPromptSubmit`,
`PermissionRequest`, and `Stop`. Re-running install replaces older Codex Buddy
managed `PreToolUse` and `PostToolUse` entries, which were useful for early
debugging but create visible noise in Codex sessions.

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

Expected behavior: `diagnostics.event_counts` increments for a managed hook such
as `UserPromptSubmit`, `PermissionRequest`, or `Stop`, and the published device
snapshot remains sanitized.

To test completion alerts, keep the bridge running and finish a Codex task. The
latest `/healthz` `current` snapshot should show `msg: "completed"` with a
sanitized `identity`, and flashed hardware should briefly celebrate and chirp if
sound is enabled.

## Background LaunchAgent

The macOS LaunchAgent path is opt-in and does not require admin privileges. It
writes `~/Library/LaunchAgents/com.codex-buddy.bridge.plist` and runs the bridge
as a user service with serial auto-discovery enabled.

Preview the plist install first:

```bash
codex-buddy launch-agent install --dry-run
```

Install and start the background bridge:

```bash
codex-buddy launch-agent install
```

Force a known serial port if auto-discovery is not enough:

```bash
codex-buddy launch-agent install --serial-port /dev/cu.usbserial-7552A41038
```

Manage the service:

```bash
codex-buddy launch-agent status
codex-buddy launch-agent restart
codex-buddy launch-agent stop
codex-buddy launch-agent start
codex-buddy launch-agent uninstall
```

The LaunchAgent uses `RunAtLoad` and `KeepAlive`, binds the hook endpoint on
`127.0.0.1:47833`, and writes bridge logs to `~/.codex-buddy/bridge.log`.
Launchd stderr goes to `~/.codex-buddy/bridge.err.log`. The bridge still uses
the same sanitized hook handling as foreground mode; if the service is stopped,
Codex work is not blocked because the hook forwarder remains best-effort.

## Delivery Workflow

Issue execution follows the delivery conventions documented in
`docs/workflow-playbook/README.md`.

- Keep one issue per branch and one PR per issue.
- Track issue packets in `docs/workflow-playbook/issues/`.
- Update `docs/handoff-next-worker.md` at the end of each issue so the next
  worker can continue without rediscovery.

## Firmware

The firmware targets M5StickC Plus and PlatformIO. This port advertises as
`Codex-XXXX` over BLE while preserving the upstream Nordic UART protocol and
attribution files. Firmware-specific build, flash, erase, and on-device copy
notes live in `firmware/claude-desktop-buddy/CODEX_BUDDY.md`.

```bash
cd firmware/claude-desktop-buddy
pio run
pio run -t upload
```

If `pio` is not on the shell `PATH`, use `python3 -m platformio run` from the
firmware directory.

If starting from a previously flashed device:

```bash
pio run -t erase && pio run -t upload
```

PlatformIO is not vendored in this repo.

## Safety

The bridge intentionally does not forward raw prompts, transcript snippets, full
commands, file paths, or approval details over BLE. `PermissionRequest` sends
only a sanitized id, coarse tool label, and short button hint.
Unknown or malformed hook event names are recorded as `unknown` in diagnostics
instead of being reflected raw.

Hardware-originated approval decisions are evaluated by the local safety policy
before any Codex hook decision is returned. If the bridge is stopped or no
hardware decision arrives before the hook wait expires, Codex falls back to the
normal approval UI.

The user-level hook installer changes only `~/.codex/hooks.json`, and only when
run without `--dry-run`.

The LaunchAgent installer changes only
`~/Library/LaunchAgents/com.codex-buddy.bridge.plist`, and only when run without
`--dry-run`.

## References

- [anthropics/claude-desktop-buddy](https://github.com/anthropics/claude-desktop-buddy)
- [Codex hooks](https://developers.openai.com/codex/hooks)
- [Port plan](docs/codex-buddy-port-plan.md)
