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
- CB-001 was completed on branch `feat/codex-hooks-discovery-packet`.
  The bridge now records sanitized hook diagnostics in `/healthz` and logs the
  hook event name that produced each snapshot.
- AGE-273 implementation is on branch `feat/age-273-user-level-hooks`.
  The branch adds an explicit `codex-buddy hooks install|uninstall` command for
  opt-in user-level `~/.codex/hooks.json` entries.

Remote `origin` is configured at `git@github.com:DylanMcCavitt/codex-buddy.git`.
At the start of CB-001, `main` and `origin/main` both pointed at MVP commit
`039c120`.

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

To inspect hook diagnostics while the bridge is running:

```bash
curl -fsS http://127.0.0.1:47833/healthz
```

Expected behavior: the response includes `diagnostics.last_hook_event` and
`diagnostics.event_counts`. These fields are local bridge diagnostics and are
not sent to the device heartbeat payload.

To preview the user-level hooks install without changing global config:

```bash
PYTHONPATH=src python3 -m codex_buddy_bridge hooks install --dry-run
```

To opt in globally:

```bash
codex-buddy hooks install
```

To disable the global integration:

```bash
codex-buddy hooks uninstall
```

The installer preserves unrelated user hooks and removes only command entries
marked with `CODEX_BUDDY_HOOK_MANAGED=1`.

## Important Implementation Notes

- The MVP is display-only. It does not approve or deny Codex actions.
- The hook forwarder exits `0` even if the bridge daemon is down.
- The bridge sanitizes hook payloads and does not send raw prompts, command
  strings, file paths, transcript text, or approval details to the device.
- User-level hook installation is explicit. It changes `~/.codex/hooks.json`
  only when `codex-buddy hooks install` is run without `--dry-run`.
- BLE mode exists, but on this Mac the process crashed around CoreBluetooth
  scanning. USB serial mode is the validated path for now.
- The firmware is intentionally not rebranded yet; seeing `Claude Buddy` is
  expected.
- The upstream firmware accepts heartbeat JSON over both BLE and USB serial,
  which is why serial mode works.

## Verification So Far

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m codex_buddy_bridge hooks install --dry-run --config /tmp/codex-buddy-hooks-test.json
```

Result on CB-001 branch: `9 tests` passed.
Current AGE-273 branch result: `16 tests` passed.

Also verified:

- `python3 -m py_compile src/codex_buddy_bridge/*.py .codex/hooks/codex_buddy_hook.py tests/*.py`
- `.codex/hooks.json` parses as JSON.
- `~/.codex/config.toml` has `[features].codex_hooks = true`.
- With `PYTHONPATH=src python3 -u -m codex_buddy_bridge bridge --dry-run --port 47833`
  running in this repo, real Codex Desktop shell tool calls reached the bridge
  as `PreToolUse` and `PostToolUse`.
- With that same dry-run bridge already running, a fresh Codex Desktop user
  prompt reached the bridge as `UserPromptSubmit` and updated the snapshot to
  `Codex working`.
- An explicitly simulated `PermissionRequest` payload reached the bridge as
  `approval needed` with only the display-only approval prompt in the heartbeat.
- User-level hook config install, merge, idempotency, dry-run, invalid-config,
  and uninstall behavior is covered with temp config paths. The real
  `~/.codex/hooks.json` was not modified during automated verification.
- With a dry-run bridge running on port `47833`, the managed hook command was
  invoked from `/tmp` and `/healthz` reported `UserPromptSubmit: 1`, confirming
  the installed command path is not tied to the `codex-buddy` cwd.

Firmware build/upload was not run by the agent because `pio` was initially not
installed. The user later flashed the device successfully.

Nested `/opt/homebrew/bin/codex exec` was not usable as a prompt-hook probe
because that CLI is `codex-cli 0.36.0`, needed a `model_reasoning_effort`
compatibility override, and then failed against the configured `gpt-5.5` model
before producing a `UserPromptSubmit` hook. The verified prompt-hook evidence
came from this Codex Desktop session instead.

## Next Good Tasks

1. Revisit BLE mode on macOS:
   - test from a Terminal/Python process with Bluetooth permission
   - capture crash details if CoreBluetooth still exits
   - keep serial mode as the fallback
2. Add a tiny `make` or script wrapper for:
   - `bridge-serial`
   - `bridge-dry-run`
   - tests
3. Run the manual AGE-273 global-hook check after opting in:
   - start the dry-run bridge
   - run a Codex prompt from a different workspace
   - confirm `/healthz` event counts update
4. Later milestone: rebrand firmware strings/device name from Claude to Codex.

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
