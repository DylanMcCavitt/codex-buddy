# AGE-272: Align Codex Buddy Workflow Docs With Delivery Conventions

## Metadata

- Issue ID: AGE-272
- Title: Align Codex Buddy repo workflow docs with delivery conventions
- Track/Phase: Foundation / workflow hygiene
- Owner Model: Codex
- Risk Tier: low
- Blocking: no
- Depends on: AGE-273, AGE-274, AGE-275 (already merged)

## Objective

Document and align the repository workflow guidance with the process already
used for recent delivery (single-issue scope, issue packets, and handoff-first
continuity).

## Scope

- Add a canonical workflow playbook for this repository.
- Add packet folder conventions and naming guidance.
- Update root README to reference the canonical workflow docs.
- Update current handoff with completed status and next issue.

## Non-Goals

- No runtime bridge/firmware behavior changes.
- No CI pipeline or lint rule changes.
- No release process automation.

## Acceptance Criteria

1. `docs/workflow-playbook/README.md` exists and defines core conventions.
2. `docs/workflow-playbook/issues/README.md` exists and defines packet format.
3. Root `README.md` links to the workflow playbook.
4. `docs/handoff-next-worker.md` reflects AGE-272 completion and next issue.

## Verification Commands

```bash
make test
python3 -m py_compile src/codex_buddy_bridge/*.py tests/*.py
```

## Definition Of Done

- Documentation updates merged.
- Verification commands pass.
- Next worker can identify the next issue and workflow expectations from repo
  docs alone.
