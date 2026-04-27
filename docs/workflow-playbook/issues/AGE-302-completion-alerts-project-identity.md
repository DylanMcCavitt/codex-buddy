# AGE-302: Add completion alerts and project identity to Codex Buddy

## Metadata

- Issue: AGE-302
- Title: Add completion alerts and project identity to Codex Buddy
- Priority: High
- Risk tier: device status UX and privacy
- Dependency: AGE-280 approval routing remains intact

## Objective

Make full-access Codex sessions useful on the device by showing which sanitized
project/thread completed and chirping on a new completion transition.

## Scope

- Publish a `Stop` completion snapshot with sanitized identity.
- Add basename-only project/worktree identity and hashed thread identity to
  device heartbeat payloads when available.
- Keep raw paths, transcript paths, prompts, commands, and session ids off the
  device.
- Have firmware parse/display sanitized identity and chirp on new completion.
- Preserve existing permission prompt behavior.
- Document manual completion alert testing.

## Non-Goals

- Do not remove AGE-280 hardware permission routing.
- Do not expose full paths, raw prompt text, command strings, transcript text,
  or raw session identifiers.
- Do not make full-access Codex depend on permission requests.

## Acceptance Criteria

- On `Stop`, the bridge publishes a completion snapshot with sanitized identity.
- Device heartbeat includes enough sanitized identity to show the completed
  project/thread.
- Firmware emits a short sound on a new completion transition when sound is on.
- Approval prompt behavior remains intact.
- README documents completion alert behavior and testing.

## Verification

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m py_compile src/codex_buddy_bridge/*.py .codex/hooks/codex_buddy_hook.py tests/*.py
python3 -m json.tool .codex/hooks.json >/dev/null
git diff --check
```
