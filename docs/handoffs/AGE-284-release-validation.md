# AGE-284 Release Validation Handoff

Date: 2026-04-27
Branch: `feat/age-284-release-validation`
Issue: AGE-284

## Status

End-to-end validation was run from the current Codex Buddy repo state. The
serial, hook, LaunchAgent, setup, test, firmware build, and firmware upload
paths passed. The port should not be called fully release-complete yet because
AGE-281, AGE-282, and AGE-283 are still open in Linear, and this thread could
not visually confirm the device screen, press hardware buttons, or perform a
physical unplug/replug cycle.

## Evidence

- Clean setup path:
  - A clean copy at `/tmp/codex-buddy-clean-copy.GzENE6/codex-buddy` followed
    the README setup path with a venv, `pip` upgrade, `python3 -m pip install
    -e .`, and `make PYTHON=.venv/bin/python test`.
  - Result: editable install succeeded, `pyserial` installed, and 54 tests
    passed.
- Foreground serial bridge:
  - Device was present at `/dev/cu.usbserial-7552A41038`.
  - `PYTHONPATH=src python3 -u -m codex_buddy_bridge bridge --serial-port
    /dev/cu.usbserial-7552A41038 --port 47833` connected to serial and wrote
    heartbeats.
  - Non-repo hook payloads from `/tmp` updated `/healthz` for
    `UserPromptSubmit`, `Stop`, and `PermissionRequest`.
  - `/healthz` showed `connection_state: "connected"`, `selected_port:
    "/dev/cu.usbserial-7552A41038"`, sanitized project/thread identity, and
    no raw prompt or command in the device snapshot.
- Background LaunchAgent:
  - `PYTHONPATH=src python3 -m codex_buddy_bridge launch-agent install
    --source-dir /Users/dylanmccavitt/.codex/worktrees/1ec3/codex-buddy/src
    --serial-port /dev/cu.usbserial-7552A41038` installed and loaded
    `com.codex-buddy.bridge`.
  - `launch-agent status` showed the service running.
  - A non-repo `UserPromptSubmit` hook payload reached the background service
    and `/healthz` reflected the running snapshot.
  - `launch-agent uninstall` stopped the service and removed the plist.
- User-level hooks:
  - Real `~/.codex/hooks.json` was backed up before the test.
  - `hooks install --source-dir .../src` installed four managed events:
    `SessionStart`, `UserPromptSubmit`, `PermissionRequest`, and `Stop`.
  - `hooks uninstall` removed the managed entries.
  - The original `~/.codex/hooks.json` was restored and validated with
    `python3 -m json.tool`.
- Firmware:
  - `python3 -m platformio run` passed.
  - `python3 -m platformio run -t upload --upload-port
    /dev/cu.usbserial-7552A41038` flashed successfully.
  - Upload target reported ESP32-PICO-D4, MAC `00:4b:12:a0:f0:3c`, verified
    written data, and hard reset via RTS.
- BLE:
  - `bleak` is installed, but BLE validation is blocked.
  - Running the BLE bridge exited during scan startup after `scanning for
    Codex*, Claude*`.
  - A direct `BleakScanner.discover(...)` with `PYTHONFAULTHANDLER=1` aborted
    inside `bleak/backends/corebluetooth/CentralManagerDelegate.py`.
  - Treat this as AGE-281 remaining open, with serial as the supported path.
- Approval behavior:
  - Unit tests cover default approve rejection, deny routing, configured safe
    approve, high-risk rejection, stale ids, and sanitized decision logs.
  - Runtime `PermissionRequest` payload in serial mode published the
    display-only approval snapshot and returned no hook decision without a
    hardware response.
  - Physical button deny/approve was not performed in this thread.

## Checks

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m py_compile setup.py src/codex_buddy_bridge/*.py .codex/hooks/codex_buddy_hook.py tests/*.py
python3 -m json.tool .codex/hooks.json >/dev/null
python3 -m json.tool ~/.codex/hooks.json >/dev/null
python3 -m platformio run
python3 -m platformio run -t upload --upload-port /dev/cu.usbserial-7552A41038
```

## Known Limits

- AGE-281 is still the BLE blocker.
- AGE-282 is still the app-server parity blocker.
- AGE-283 is still the character/status UX blocker.
- Manual visual confirmation of flashed on-device copy was not performed by
  this thread.
- Manual physical button deny/approve and physical unplug/replug were not
  performed by this thread.
- Serial startup currently records firmware boot chatter as sanitized malformed
  device input; the bridge ignores it and continues.

## Next

1. Have the user confirm the flashed device display after a Codex event if
   visual proof is required for AGE-284 closure.
2. Run a physical unplug/replug cycle while `make bridge-serial` is active and
   verify `/healthz` records disconnect/reconnect.
3. Press the device deny button on a real `PermissionRequest`; optionally test
   safe approve with `CODEX_BUDDY_HARDWARE_APPROVE=1` and an allow-listed
   command.
4. Keep AGE-281, AGE-282, and AGE-283 open unless they are handled in separate
   issue branches.
