# One suite runner

Status: ready-for-agent

Read first: `spec.md`; ADR-0010 (bars), ADR-0011 (each node measured at its bar); CONTEXT.md (Run, Run record).

## Where it stands

| Shared today, in `evaluation.py` | Copied per suite |
|---|---|
| `measured` (:779): every case, every repetition, the stop on a spent quota | `prepared()` in log (:158), adapt (:74), onboarding (:61), supervise (:74): temp dir, `source.backup`, `DELETE FROM` a list, `TRAINER_DB` set and restored, cleanup. `pointed_at_the_database` (:711) does the env part and none of them uses it |
| `Outcome`, `Half`, `Report`, the `Costed` protocol | `_once` / `_routed` / `_planned` / `_scored`: graph with `InMemorySaver(serde=checkpoints.Declared())`, uuid thread, timing, `run_record.of`, re-raise of a spent quota, any other error as `Outcome(error=…)`, `evaluation.write` |
| `write`, `matrix`, `failures`, `totals` | `barred()` in each suite, hand-building its `Half`s from the set |
| | `_plan/_log/_onboard/_adapt/_supervise_suite` in `cli.py:749-920`, and the `_Named` TypeVar (:928) naming all five case types |

Leaks to close on the way:

- A second graph's outcomes: adapt (:168-186) and supervise (:209-230) pass a mutable list into the lambda; onboarding calls `measured` twice and copies the skip logic by hand (:138-185).
- `Talked` lives in `onboarding_evaluation.py:102`; adapt and supervise import it from there.
- `demo.py:18` imports `prescribed` and `as_performed` from `supervise_evaluation`; the fake-history loop exists in both `supervise_evaluation.staged` (:100) and `demo._performed`.
- `adapt_set`, `onboarding_set`, `supervise_set` are one template (`ENV_VAR`, `DEFAULT_PARTS`, `path`, `load`, `parse`, an error class). `log_set` parses Markdown and stays as it is.

## What to build

- A runner module that owns everything in the right-hand column, reached through one call per suite.
- Each suite reduced to its set, its fixture's contents, how one run is scored, its bars and columns.
- Writing a performed history in one place, used by `demo` and the supervise suite.

## Acceptance criteria

- [ ] Before any change, each suite's rendered output and exit code on scripted models are captured as a test; after it, they are unchanged.
- [ ] No `prepared()`, `_once` or `barred()` copy is left in a suite module; `InMemorySaver(` and the spent-quota re-raise appear once in the eval family.
- [ ] `cli.py` has no per-suite `_X_suite` function.
- [ ] `demo.py` imports nothing from an eval module.
- [ ] The runner is tested once, with a fake suite: quota stop mid-run, an erroring run, a second graph's outcomes, `TRAINER_DB` restored after a failure.
- [ ] No paid model is called to close this ticket.
