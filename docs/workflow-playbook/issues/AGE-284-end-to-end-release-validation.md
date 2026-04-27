# AGE-284: Run end-to-end release validation for Codex Buddy

## Metadata

- Issue: AGE-284
- Title: Run end-to-end release validation for Codex Buddy
- Priority: Medium
- Risk tier: release validation and hardware readiness
- Dependencies: AGE-272 through AGE-280, AGE-302; AGE-281, AGE-282, and
  AGE-283 remain open validation blockers for BLE, app-server parity, and
  character/status UX.

## Objective

Run a release-style pass from clean setup through hooks, bridge modes, firmware
build, and physical device behavior, then record whether Codex Buddy is ready
for normal use or still blocked by explicit follow-up issues.

## Scope

- Validate the README setup path from a fresh checkout.
- Verify user-level hook install and uninstall behavior without losing unrelated
  user hook entries.
- Verify foreground bridge behavior and LaunchAgent background management.
- Verify serial hardware behavior with the attached buddy.
- Attempt BLE validation only if the local environment and open blocker state
  make it available; otherwise document the blocker.
- Build firmware with PlatformIO and record whether flash/upload was performed
  or blocked.
- Verify the final supported approval scope: display, hardware deny, and
  policy-approved hardware approve only for explicitly allow-listed commands.
- Write a release handoff under `docs/handoffs/` and refresh the next-worker
  handoff.

## Non-Goals

- Do not complete AGE-281 BLE remediation inside this issue.
- Do not implement AGE-282 app-server parity inside this issue.
- Do not implement AGE-283 character install/status UX inside this issue.
- Do not enable high-risk hardware approvals by default.
- Do not mark the port complete based only on unit tests.

## Acceptance Criteria

- Fresh-checkout setup from README installs and runs tests.
- Global hook install and uninstall are verified.
- Bridge foreground and background modes are verified.
- Hardware is verified in serial mode; BLE is verified only if available, with
  exact blocker evidence otherwise.
- Firmware build/flash evidence is recorded.
- Approval behavior is verified against the supported scope.
- `docs/handoffs/` contains a release validation handoff with checks run, known
  limits, and future work.

## Verification

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m py_compile setup.py src/codex_buddy_bridge/*.py .codex/hooks/codex_buddy_hook.py tests/*.py
python3 -m json.tool .codex/hooks.json >/dev/null
git diff --check
python3 -m platformio run
```

Manual validation:

- Non-repo hook payload reaches the bridge through managed user hooks.
- Serial bridge updates the attached buddy and records unplug/replug behavior or
  documents the physical-action blocker.
- Permission prompt flow keeps default approve disabled, allows deny, and allows
  approve only for a configured safe command.
