# AGE-280: Route device deny and policy-approved approvals through Codex hooks

## Metadata

- Issue: AGE-280
- Title: Route device deny and policy-approved approvals through Codex hooks
- Priority: High
- Risk tier: approval safety
- Dependency: AGE-279 local safety policy

## Objective

Route hardware-originated permission decisions back to Codex for supported
`PermissionRequest` hooks while keeping all approvals behind the local safety
policy.

## Scope

- Track the active sanitized permission request id sent to the device.
- Return Codex hook `deny` decisions for matching hardware deny/decline/cancel.
- Return Codex hook `allow` decisions only when the policy allows hardware
  approval.
- Leave rejected hardware approvals in the normal Codex UI approval flow.
- Ignore stale or unknown device decisions safely.
- Document supported hook decision behavior and hardware validation.

## Non-Goals

- Do not bypass Codex approval rules.
- Do not route decisions for hook events other than `PermissionRequest`.
- Do not log raw prompt text, full command strings, file paths, or transcript
  text.

## Acceptance Criteria

- Bridge tracks active sanitized permission requests by id.
- Device deny routes back to supported Codex `PermissionRequest` hooks.
- Device approve routes back only when policy allows it.
- Policy-rejected approve publishes a clear display-only state and returns no
  hook decision.
- Stale decisions remain ignored.
- README documents supported prompt types and manual hardware tests.

## Verification

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m py_compile src/codex_buddy_bridge/*.py .codex/hooks/codex_buddy_hook.py tests/*.py
python3 -m json.tool .codex/hooks.json >/dev/null
git diff --check
```
