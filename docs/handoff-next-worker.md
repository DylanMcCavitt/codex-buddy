# Codex Buddy Handoff

Date: 2026-04-25
Current issue: AGE-279 complete on branch
Branch: `feat/age-279-local-safety-policy`
PR: not opened

## Status

AGE-279 adds the local safety policy that must exist before hardware decisions
can be routed back into Codex.

- Added `HardwareApprovalPolicy` with explicit outcomes for allow approve,
  allow deny, reject hardware approve, and ignore stale/unknown prompt.
- Deny/decline/cancel is allowed for active prompts by default.
- Approve/accept/once is rejected by default unless hardware approve is
  explicitly enabled.
- Added conservative command allow-list support, including environment config
  for future integration:
  - `CODEX_BUDDY_HARDWARE_APPROVE=1`
  - `CODEX_BUDDY_APPROVE_COMMANDS="python3 -m unittest,make test"`
- Added sanitized decision-log entries with timestamp, prompt id hash, prompt
  kind, normalized decision, outcome, and reason only.
- Device permission input can optionally evaluate through the policy and expose
  only the latest sanitized policy decision in diagnostics.

## Next

- Open/review PR for AGE-279.
- After AGE-279 merges, AGE-280 should route device deny and policy-approved
  approvals through Codex hooks.
- Do not route device decisions into Codex before AGE-279 is merged.

## Risks

- Hardware approval/deny routing remains out of scope and disabled.
- Policy has fixture coverage only; manual Codex high-risk prompt validation
  belongs with AGE-280 when routing exists.
- BLE transport remains less validated than USB serial.

## Files

- `src/codex_buddy_bridge/policy.py`
- `src/codex_buddy_bridge/device_input.py`
- `tests/test_policy.py`
- `tests/test_device_input.py`
- `README.md`
- `docs/codex-buddy-port-plan.md`
- `docs/workflow-playbook/issues/AGE-279-local-safety-policy.md`
- `docs/handoff-next-worker.md`

## Checks

- `PYTHONPATH=src python3 -m unittest discover -s tests -v` passed: 45 tests.
- `python3 -m py_compile src/codex_buddy_bridge/*.py .codex/hooks/codex_buddy_hook.py tests/*.py` passed.
- `git diff --check` passed.
