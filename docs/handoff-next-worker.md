# Codex Buddy Handoff

Date: 2026-04-27
Current issue: none active
Branch: `feat/quiet-codex-buddy-hooks`
Last merged PR: https://github.com/DylanMcCavitt/codex-buddy/pull/9

## Status

AGE-302 is merged into `main` via PR #9.

- `Stop` publishes a `completed` snapshot with sanitized `identity.project` and
  hashed `identity.thread` when Codex supplies workspace/session fields.
- Project identity uses only a cleaned workspace basename; thread identity is a
  short hash. Full paths, transcript paths, prompts, commands, and raw session
  ids stay off the device payload.
- Permission prompts retain AGE-280 behavior while also carrying sanitized
  identity when available.
- Firmware parses identity, shows it on the Codex info page, treats `msg:
  "completed"` as a completion state, and chirps once on a new completion
  transition when sound is enabled.
- Manual hardware verification passed on `/dev/cu.usbserial-7552A41038`:
  `Stop` count reached 3, `/healthz` showed `msg: "completed"` with identity,
  then returned to idle, and the device visibly showed the completion state.
- README and a repo-local AGE-302 packet now document the behavior and checks.
- Quiet hook side fix is committed on this branch: Codex Buddy no longer
  installs managed `PreToolUse` or `PostToolUse` hooks by default, and the live
  `~/.codex/hooks.json` on this machine was reinstalled with the quiet profile.

## Next

- Merge or otherwise reconcile the quiet hook side fix if you want it durable.
- Start AGE-284: end-to-end release validation for Codex Buddy.
- Begin from the canonical checkout on `main` after branch state is clean.
- Before coding, verify Linear state. AGE-277 still appeared as `Todo` in
  Linear even though prior repo history says the prompt-alias work landed; treat
  that as status cleanup unless code review proves otherwise.

## Risks

- Identity depends on Codex hook payloads including workspace/session fields;
  tests cover the supported fields, and snapshots remain safe when fields are
  absent.
- Already-open Codex sessions may cache hook configuration. If quiet-hook
  testing still shows `PreToolUse` or `PostToolUse` rows, start a new Codex
  session after the `~/.codex/hooks.json` update.

## Files

- `src/codex_buddy_bridge/state.py`
- `src/codex_buddy_bridge/server.py`
- `firmware/claude-desktop-buddy/src/data.h`
- `firmware/claude-desktop-buddy/src/main.cpp`
- `tests/test_state.py`
- `tests/test_server.py`
- `README.md`
- `docs/workflow-playbook/issues/AGE-302-completion-alerts-project-identity.md`
- `.codex/hooks.json`
- `src/codex_buddy_bridge/hooks_config.py`
- `tests/test_hooks_config.py`
- `docs/handoff-next-worker.md`

## Checks

- `PYTHONPATH=src python3 -m unittest tests.test_hooks_config -v` passed: 8 tests.
- `PYTHONPATH=src python3 -m unittest discover -s tests -v` passed: 54 tests.
- `python3 -m py_compile src/codex_buddy_bridge/*.py .codex/hooks/codex_buddy_hook.py tests/*.py` passed.
- `python3 -m json.tool .codex/hooks.json >/dev/null` passed.
- `python3 -m json.tool ~/.codex/hooks.json >/dev/null` passed.
- `git diff --check` passed.
- `PYTHONPATH=src python3 -m codex_buddy_bridge hooks install --dry-run --config /tmp/codex-buddy-quiet-hooks.json` showed only `SessionStart`, `UserPromptSubmit`, `PermissionRequest`, and `Stop`.
- `PYTHONPATH=src python3 -m codex_buddy_bridge hooks install --source-dir /Users/dylanmccavitt/codex-buddy/src` updated `~/.codex/hooks.json`, removed old managed entries, and left no `PreToolUse`/`PostToolUse` entries.
- `python3 -m platformio run` passed in `firmware/claude-desktop-buddy` during AGE-302.
- Manual hardware completion check passed during AGE-302: bridge connected over
  serial, lifecycle hooks reached the bridge, `Stop` incremented, `/healthz`
  captured `completed` with identity, and hardware displayed the completion
  state.
