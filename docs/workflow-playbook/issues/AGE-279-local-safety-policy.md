# AGE-279: Add a local safety policy for hardware approval decisions

## Metadata

- Issue: AGE-279
- Title: Add a local safety policy for hardware approval decisions
- Priority: High
- Risk tier: approval safety
- Dependencies: AGE-278 device input capture
- Follow-up: AGE-280 routes policy-approved decisions through Codex hooks

## Objective

Add a local policy layer that evaluates hardware-originated approval decisions
before any future bridge code can route them back into Codex.

## Scope

- Add explicit policy outcomes for allowed approve, allowed deny, rejected
  hardware approve, and stale or unknown prompt handling.
- Allow deny/decline/cancel for active prompts by default.
- Keep hardware approve disabled by default.
- Add a conservative command approval allow-list that can be configured for
  known read-only or test commands.
- Produce a sanitized local decision log.
- Add fixture coverage for stale ids, unknown decisions, high-risk commands,
  and allow-listed commands.

## Non-Goals

- Do not answer Codex hook permission requests from hardware in this issue.
- Do not enable global hardware approve by default.
- Do not log raw prompts, full command strings, file paths, or transcript text.

## Acceptance Criteria

- Policy module exposes explicit decision outcomes.
- Deny/decline/cancel is allowed for active prompts by default.
- Approve/accept/once is rejected unless hardware approval is explicitly
  enabled and the prompt matches the configured allow-list.
- Decision logs include timestamp, prompt id hash, prompt kind, decision,
  outcome, and reason only.
- Unit tests cover reject/allow/ignore cases.

## Verification

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m py_compile src/codex_buddy_bridge/*.py tests/*.py
git diff --check
```
