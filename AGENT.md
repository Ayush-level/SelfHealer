# Agent Instructions

You are implementing this project from `TASKS.md`, using `ARCHITECTURE.md`
as the source of truth for design decisions. Read both before writing any
code, and re-check `ARCHITECTURE.md` any time a task seems ambiguous rather
than guessing.

## Working Loop

For every task, in order:

1. Read the task's description and its **Test** line in `TASKS.md`.
2. Implement only that task — don't jump ahead to later phases, even if the
   code would be convenient to write now.
3. Run the test specified for that task. A task is not complete until its
   test passes — no exceptions, no "should work" without running it.
4. If the test fails: fix it and re-run, don't move on with a failing test.
5. If a task's requirements are genuinely ambiguous or conflict with
   `ARCHITECTURE.md`: stop and ask, don't silently pick an interpretation
   for anything that changes the architecture (storage mode behavior,
   network/volume layout, auth approach). Small implementation details
   (variable names, internal function structure) don't need to be asked
   about.
6. Mark the task's checkbox `- [x]` in `TASKS.md`.
7. Append an entry to `MEMORY.md` for the task — see its template. Do this
   for every task, not just milestones; future sessions rely on this log to
   pick up where you left off without re-reading the whole codebase.

## Non-Negotiables

- **Test every step.** This applies literally — no task is "done" without
  its test passing. If a task has no obvious automated test, write one
  before marking it complete rather than skipping verification.
- **Don't modify `ARCHITECTURE.md` decisions without flagging it.** If
  implementation reveals a decision there doesn't work (e.g., a port
  conflict, a library limitation), stop, explain the conflict, and propose
  the change — don't silently diverge from the documented architecture.
- **Don't re-litigate settled scope.** Auth is intentionally stubbed for
  this phase; SigNoz is intentionally deferred. Don't "improve" these
  without being asked — they're documented decisions, not oversights.
- **Keep `MEMORY.md` honest.** Log what actually happened, including partial
  failures and workarounds — not just the happy path. A future session (or
  a human) needs to trust this log.

## Coding Conventions

- Flask: app factory pattern (`create_app()`), blueprints per route group
  (`routes/health.py`, `routes/correlate.py`, `routes/rca.py`).
- Python: type hints on function signatures, PEP 8, `pytest` for tests.
- Config: all secrets and mode switches (`STORAGE_MODE`, `LLM_API_KEY`,
  Grafana admin creds) come from environment variables via `.env` — never
  hardcoded, never committed.
- One task per commit where practical, imperative commit messages
  ("Add Prometheus metrics adapter", not "adapter stuff").

## Before You Start a Session

1. Read `MEMORY.md`'s most recent entries to know what state the repo is
   actually in.
2. Read `TASKS.md` and find the first unchecked task.
3. Confirm the repo matches what `MEMORY.md` says — if it doesn't, stop and
   flag the mismatch rather than assuming either source is right.
