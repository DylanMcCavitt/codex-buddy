# Codex Buddy Handoff

Date: 2026-04-27
Current issue: AGE-284
Branch: `feat/age-284-release-validation`
Last merged PR: https://github.com/DylanMcCavitt/codex-buddy/pull/9

## Status

AGE-284 end-to-end validation has been run and documented in
`docs/handoffs/AGE-284-release-validation.md`.

What passed:

- Fresh setup path now works from README when using a venv, upgrading `pip`,
  installing editable mode, and running tests.
- `setup.py` was added so legacy editable-install tooling has a setuptools
  fallback.
- `PYTHONPATH=src python3 -m unittest discover -s tests -v` passed: 54 tests.
- `python3 -m py_compile setup.py src/codex_buddy_bridge/*.py
  .codex/hooks/codex_buddy_hook.py tests/*.py` passed.
- `.codex/hooks.json` and `~/.codex/hooks.json` validate as JSON.
- Real `~/.codex/hooks.json` install/uninstall was verified with backup and
  restore.
- Foreground serial bridge connected to `/dev/cu.usbserial-7552A41038` and
  accepted non-repo hook payloads from `/tmp`.
- Background LaunchAgent install/status/hook/uninstall passed.
- `python3 -m platformio run` passed.
- Firmware upload to `/dev/cu.usbserial-7552A41038` passed.
- User-confirmed manual physical checks passed: unplug/replug recovery,
  hardware deny, and safe approve with an allow-listed command.

Release limits:

- AGE-281, AGE-282, and AGE-283 are still `Todo` in Linear.
- BLE is not validated: `BleakScanner.discover(...)` aborts inside the
  CoreBluetooth scanner on this machine.
- Manual physical checks were confirmed by the user, not directly observed by
  this thread.

## Next

- Review the AGE-284 branch and decide whether the validation handoff is enough
  to close AGE-284 as "validated with known limits."
- If closing AGE-284, leave AGE-281, AGE-282, and AGE-283 open as separate
  blockers/follow-ups rather than folding them into this validation branch.
- If continuing validation, only repeat the physical checks when direct
  observer evidence is required; the user already reported they pass.

## Risks

- The bridge ignores firmware boot chatter on serial as sanitized malformed
  device input; this is handled, but it means `parse_errors` can be non-zero at
  startup.
- The user-level hooks were restored after validation, but long-lived Codex
  sessions may still cache old hook state until a new session starts.
- BLE needs AGE-281 before it can be called release-ready.

## Files

- `README.md`
- `setup.py`
- `docs/workflow-playbook/issues/AGE-284-end-to-end-release-validation.md`
- `docs/handoffs/AGE-284-release-validation.md`
- `docs/handoff-next-worker.md`

## Checks

- `PYTHONPATH=src python3 -m unittest discover -s tests -v` passed: 54 tests.
- `python3 -m py_compile setup.py src/codex_buddy_bridge/*.py .codex/hooks/codex_buddy_hook.py tests/*.py` passed.
- `python3 -m json.tool .codex/hooks.json >/dev/null` passed.
- `python3 -m json.tool ~/.codex/hooks.json >/dev/null` passed.
- Clean copy setup passed: venv, `pip` upgrade, editable install, and 54 tests.
- Real global hook install/uninstall passed and original config was restored.
- Foreground serial bridge passed on `/dev/cu.usbserial-7552A41038`.
- LaunchAgent install/status/non-repo hook/uninstall passed.
- `python3 -m platformio run` passed.
- `python3 -m platformio run -t upload --upload-port /dev/cu.usbserial-7552A41038` passed.
- User-confirmed manual physical unplug/replug, hardware deny, and safe approve
  checks passed.
- BLE scan failed with a CoreBluetooth `bleak` abort; see AGE-281.
