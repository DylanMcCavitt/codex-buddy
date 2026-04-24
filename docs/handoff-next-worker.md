# Codex Buddy Handoff

Date: 2026-04-24
Current issue: AGE-272 complete
Branch: `main`
PR: (pending merge from `feat/age-272-workflow-docs`)

## Status

AGE-272 is implemented on branch `feat/age-272-workflow-docs` and aligns repo
workflow docs with the delivery conventions already used in AGE-273/274/275.

- Added `docs/workflow-playbook/README.md` to codify branch/PR/issue packet and
  handoff conventions.
- Added `docs/workflow-playbook/issues/README.md` to define packet naming and
  minimum required sections.
- Added the AGE-272 issue packet:
  `docs/workflow-playbook/issues/AGE-272-workflow-docs-alignment.md`.
- Updated `README.md` with a Delivery Workflow section that points workers to
  the canonical playbook docs.

## Prior Issue Context (AGE-275)

AGE-275 is already merged to `main` at
`8bcc41440d4601b532763e6b46229ae00cf983e8` and remains the operational basis
for AGE-276 work.

- AGE-274 PR #2 was merged to `main` at
  `05048f22cb6ce571c1a4001cc6dc7406b148985d`.
- Added a testable LaunchAgent renderer in
  `src/codex_buddy_bridge/launch_agent.py`.
- Added `codex-buddy launch-agent install/start/stop/restart/status/uninstall`.
- The generated user LaunchAgent writes
  `~/Library/LaunchAgents/com.codex-buddy.bridge.plist`, runs
  `python -m codex_buddy_bridge bridge --serial --port 47833`, and logs to
  `~/.codex-buddy/bridge.log`.
- LaunchAgent install is opt-in and supports `--dry-run`, `--no-start`, and
  `--serial-port /dev/cu.usbserial-7552A41038`.
- Foreground bridge logs still work, and the LaunchAgent path avoids duplicate
  bridge log writes by letting launchd capture stdout into the bridge log.
- Manual launchctl verification loaded the service under
  `gui/501/com.codex-buddy.bridge`, confirmed `state = running`, and confirmed
  `/healthz` through the background bridge.
- A temporary user-level hook install verified a `/tmp` tool call updated
  `/healthz` through global hooks. The temporary global hooks file and
  worktree-pointing LaunchAgent were removed after verification.

## Next

- AGE-272 docs alignment is complete; the next ready Linear candidate is
  AGE-276 `Rebrand firmware from Claude Buddy to Codex Buddy`.
- For a durable local background install after merge, run from the canonical
  checkout or installed package rather than the disposable worktree:

  ```bash
  python3 -m pip install -e .
  codex-buddy hooks install
  codex-buddy launch-agent install
  codex-buddy launch-agent status
  ```

## Risks

- Workflow conventions are now documented, but there is no CI gate yet to
  enforce packet presence or handoff updates.
- BLE is still not revisited; USB serial remains the validated path.
- Firmware is still upstream-branded as Claude Buddy.
- Hardware approval/deny remains out of scope and disabled.
- The manual verification used the issue worktree as `PYTHONPATH`; a durable
  install should be run from the canonical checkout or installed package.

## Files

- `README.md`
- `docs/workflow-playbook/README.md`
- `docs/workflow-playbook/issues/README.md`
- `docs/workflow-playbook/issues/AGE-272-workflow-docs-alignment.md`
- `src/codex_buddy_bridge/ble.py`
- `src/codex_buddy_bridge/cli.py`
- `src/codex_buddy_bridge/launch_agent.py`
- `tests/test_launch_agent.py`
- `docs/handoff-next-worker.md`

## Checks

- `make test` passed: 29 tests.
- `python3 -m py_compile src/codex_buddy_bridge/*.py tests/*.py`
- `PYTHONPATH=src python3 -m codex_buddy_bridge launch-agent install --dry-run --no-start`
- `python3 -m py_compile src/codex_buddy_bridge/*.py .codex/hooks/codex_buddy_hook.py tests/*.py`
- `PYTHONPATH=src python3 -m codex_buddy_bridge launch-agent install`
- `PYTHONPATH=src python3 -m codex_buddy_bridge launch-agent status`
- `PYTHONPATH=src python3 -m codex_buddy_bridge launch-agent restart`
- `PYTHONPATH=src python3 -m codex_buddy_bridge launch-agent stop`
- `PYTHONPATH=src python3 -m codex_buddy_bridge launch-agent start`
- `PYTHONPATH=src python3 -m codex_buddy_bridge hooks install`
- `/tmp` shell tool call increased `/healthz` counts from
  `PreToolUse: 5, PostToolUse: 3` to `PreToolUse: 7, PostToolUse: 6`.
- `PYTHONPATH=src python3 -m codex_buddy_bridge hooks uninstall`
- `PYTHONPATH=src python3 -m codex_buddy_bridge launch-agent uninstall`

## Commands

```bash
make bridge-serial
SERIAL_PORT=/dev/cu.usbserial-7552A41038 make bridge-serial
make bridge-dry-run
make test
codex-buddy launch-agent install --dry-run
codex-buddy launch-agent install
codex-buddy launch-agent status
codex-buddy launch-agent stop
codex-buddy launch-agent uninstall
```
