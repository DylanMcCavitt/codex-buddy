# Codex Buddy Delivery Workflow

This playbook documents the delivery conventions used for Codex Buddy issues so
workers can continue from any handoff without re-learning process details.

## Core Conventions

- One issue per branch and one PR per issue.
- Keep branch names tied to the issue id (example: `feat/age-272-workflow-docs`).
- Scope each PR to a single risk domain. Split follow-up work instead of
  broadening a PR mid-flight.
- Keep an issue packet under `docs/workflow-playbook/issues/` before coding.
- Keep `docs/handoff-next-worker.md` current after each merged issue.

## Issue Packet Standard

Issue packets live in `docs/workflow-playbook/issues/` and should include:

1. Metadata (issue id, title, risk tier, dependencies)
2. Scope budget and split triggers
3. Objective, scope, non-goals, and constraints
4. Acceptance criteria with explicit verification commands
5. Stop/split rule and definition of done

Use the existing packet format from
`docs/workflow-playbook/issues/CB-001-codex-desktop-hook-discovery.md` as the
baseline template.

## Execution Checklist

1. Pull latest `main`.
2. Create issue branch from `main`.
3. Implement only the packet scope.
4. Run the issue verification commands locally.
5. Update docs and handoff with exact checks and residual risks.
6. Open PR with issue id in title and include test evidence.
7. After merge, reset `docs/handoff-next-worker.md` to the next ready issue.

## Documentation Alignment Rules

- `README.md` should only describe workflows that are currently supported.
- `docs/handoff-next-worker.md` is the source of truth for current status,
  next issue, risks, and replayable commands.
- `docs/workflow-playbook/issues/` is immutable historical issue context; add
  new packets instead of mutating old acceptance criteria post-merge.
