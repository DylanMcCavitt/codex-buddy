# CB-001: Verify Codex Desktop Hook Discovery And Firing

## Metadata

- Issue ID: CB-001
- Title: Verify Codex Desktop hook discovery and firing for Codex Buddy
- Track/Phase: MVP follow-up / Codex integration reliability
- Owner Model: Codex
- Risk Tier: medium
- Blocking: yes
- Depends on: MVP bridge commit `039c120`

## Scope Budget

- Estimated files touched: 3-5
- Risk domain (pick one): infra

## Split Triggers (If Any = Yes, Split Before Dispatch)

- Estimated files touched >8: no
- More than one risk domain touched: no
- More than one user-visible deliverable: no

## Objective

Make repo-local Codex Desktop hooks reliably discover and fire for the Codex
Buddy MVP, or document the exact current blocker and supported fallback if
Codex Desktop cannot load repo-local hooks in this setup.

The end state is that a worker can start the dry-run or serial bridge, submit a
real Codex prompt in this repo, and see sanitized device-state updates reach the
bridge without manually posting test payloads.

## Current Starting State

- `.codex/hooks.json` exists and registers `SessionStart`, `UserPromptSubmit`,
  `PreToolUse`, `PermissionRequest`, `PostToolUse`, and `Stop`.
- `.codex/hooks/codex_buddy_hook.py` forwards hook payloads to
  `http://127.0.0.1:47833/hook` and exits `0` if the bridge is unavailable.
- `~/.codex/config.toml` has `codex_hooks = true`.
- Manual HTTP posting to `/hook` works.
- Unit tests pass.
- `codex` is not available on the shell `PATH` in this worktree, so Desktop
  hook behavior must be verified from the running app session or by locating
  the actual Codex binary used by Desktop.

## Evidence Captured

- Official Codex hooks docs confirm `<repo>/.codex/hooks.json` is a supported
  discovery location when the project config layer is active.
- With the dry-run bridge running in this Codex Desktop session, real shell
  tool calls reached the bridge as `PreToolUse` and `PostToolUse`.
- An explicitly simulated `PermissionRequest` payload reached the bridge as
  `approval needed` and did not leak raw command text into the heartbeat or
  diagnostics.
- With the dry-run bridge already running, a fresh Codex Desktop user prompt
  reached the bridge as `UserPromptSubmit` and updated the snapshot to
  `Codex working`.
- A nested `/opt/homebrew/bin/codex exec` probe was not usable for
  `UserPromptSubmit`: the CLI is `codex-cli 0.36.0`, needed a
  `model_reasoning_effort` compatibility override, and then failed on the
  configured `gpt-5.5` model before emitting that hook. The successful prompt
  evidence came from Codex Desktop instead.

## Scope

- Reproduce whether Codex Desktop discovers this repo's `.codex/hooks.json`.
- Verify at least one real `UserPromptSubmit` hook reaches the bridge from a
  Codex Desktop session running in this repo.
- Verify the approval/waiting path with a real approval-gated action if
  possible.
- If repo-local discovery does not work, implement the smallest reliable
  registration/config change that keeps this repo self-contained.
- Add or update focused tests for any changed hook command, hook forwarder, or
  diagnostics behavior.
- Update `README.md` and `docs/handoff-next-worker.md` with the exact verified
  run/check steps.

## Non-Goals

- Do not add hardware approve/deny support.
- Do not change BLE behavior or debug macOS CoreBluetooth crashes.
- Do not rebrand firmware strings from Claude to Codex.
- Do not alter upstream firmware unless hook verification proves a bridge-side
  contract is wrong.
- Do not forward raw prompts, command strings, file paths, transcript text, or
  approval details to the bridge/device.
- Do not make Codex work fail when the bridge is down.

## Constraints

- Hook forwarding must remain best-effort and return exit code `0` on bridge
  failures.
- Device payloads must stay sanitized and display-only for approval prompts.
- Prefer repo-local config and scripts over user-global edits. If a user-global
  Codex config change is required, document it explicitly instead of hiding it
  in automation.
- Keep the validated serial bridge path working:
  `/dev/cu.usbserial-7552A41038`.
- Preserve support for dry-run bridge verification without hardware.
- Keep changes within:
  - `.codex/hooks.json`
  - `.codex/hooks/codex_buddy_hook.py`
  - `src/codex_buddy_bridge/`
  - `tests/`
  - `README.md`
  - `docs/handoff-next-worker.md`

## Acceptance Criteria

1. Starting the bridge in dry-run mode and submitting a real Codex Desktop
   prompt in this repo causes a `UserPromptSubmit`-driven `Codex working`
   snapshot to reach the bridge.
2. A real or explicitly simulated approval event reaches the bridge as
   `approval needed`, with a display-only prompt and no raw command or prompt
   details in the published payload.
3. Hook discovery behavior is documented with evidence: repo-local hooks work,
   or the exact blocker and required fallback are recorded.
4. Any hook/config/diagnostic code changes have focused tests.
5. Existing bridge safety behavior remains intact: missing daemon still exits
   `0`, sanitized payload tests pass, and `.codex/hooks.json` remains valid
   JSON.
6. `README.md` and `docs/handoff-next-worker.md` contain the verified command
   path for the next worker.

## Dispatch Gate (Must Be Complete Before Assigning)

- [x] Scope is explicit
- [x] Non-goals are explicit
- [x] Constraints are explicit
- [x] Acceptance criteria are testable
- [x] Verification commands are runnable
- [x] Scope budget is set
- [x] Split triggers reviewed

## Micro-Plan

1. Slice: Reproduce hook discovery
- Deliverable: Dry-run bridge plus real Codex Desktop prompt evidence
- Dependency: MVP bridge running locally
2. Slice: Fix registration if needed
- Deliverable: Smallest repo-local hook/config adjustment, or documented
  Desktop limitation and fallback
- Dependency: Reproduction result
3. Slice: Verify approval/waiting path
- Deliverable: Evidence that waiting snapshot is emitted without leaking raw
  approval details
- Dependency: Hook path firing
4. Slice: Tests and docs
- Deliverable: Updated focused tests, README, and handoff
- Dependency: Final implementation path

## Verification Commands

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m py_compile src/codex_buddy_bridge/*.py .codex/hooks/codex_buddy_hook.py tests/*.py
python3 -m json.tool .codex/hooks.json >/dev/null
PYTHONPATH=src python3 -u -m codex_buddy_bridge bridge --dry-run --port 47833
curl -fsS http://127.0.0.1:47833/healthz
curl -fsS -X POST http://127.0.0.1:47833/hook \
  -H 'Content-Type: application/json' \
  -d '{"hook":{"hook_event_name":"UserPromptSubmit"}}'
```

Manual verification required:

1. Start the dry-run bridge from this repo.
2. In Codex Desktop, run a prompt in this repo.
3. Confirm the bridge logs a sanitized `Codex working` event caused by the real
   hook, not by manual `curl`.
4. Trigger an approval-gated action if possible and confirm the bridge logs
   `approval needed`.

## Stop / Split Rule

If scope expands beyond hook discovery/firing reliability, owned paths,
acceptance criteria, or the infra risk domain:

1. Stop implementation for this issue.
2. Create follow-up issue(s) with full packet and dependencies.
3. Keep the current PR scoped to hook discovery/firing only.

Create a follow-up issue instead of expanding this issue if the fix requires:

- app-server bridge work
- BLE/CoreBluetooth debugging
- firmware changes
- hardware approve/deny support
- broader workflow-kit bootstrapping

## Definition Of Done

- Acceptance criteria satisfied.
- Verification commands pass.
- Manual Codex Desktop hook evidence recorded in the PR or handoff.
- PR opened and linked to the issue packet.
- Handoff summary included in PR.
