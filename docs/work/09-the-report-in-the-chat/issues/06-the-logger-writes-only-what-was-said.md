# The logger writes only what was said

Status: ready-for-agent

Blocked by: nothing. Blocks 05: its pass measures this contract, not today's.

The first pass of the log suite (05 § Passes, 2026-09-21, `gpt-oss:20b` on Ollama) held 24 of 90. Rescored on the document the engine would write, the same 50 valid determined runs go from **7 to 30** held. Most of the gap is the graph making the model fail, not the model misreading the report.

## What is wrong, measured

| # | Where | What happens | Runs |
|---|---|---|---|
| 1 | `emit`, `log.PerformedItem` / `PerformedBlock` | `amount`, `rounds`, `rest` and their sources are required, and `tools.strict_schema` forces every field, so a value the user never gave cannot be left out. The model must copy it from the prescription and label it. `LOGGING` says *"Never `assumed`"*; `eval-set.md` expects `assumed`. It writes `reported` (false), or copies the whole prescription | 23 of 50 |
| 2 | `validate` | A refusal ends the run. The planner gets its refusal back and retries (`planner.ATTEMPTS`); the logger does not. Refusals seen: an exercise id as an exclusion, `TRACIONE`, a retest date of today | ≥ 8 |
| 3 | `emit` | An exclusion is a movement pattern or a loaded joint, and nothing gives the model the list. It invents `vertical squat` | 6 |
| 4 | `logger` | `LOGGING` is ~70 lines, half describing the rigid form, two of them contradicting each other | – |

In 61 of 81 runs the model made one read, `prescribed_workout`, and nothing else; U8 invented ids instead of calling `search_exercises`.

## What to build

1. **A value the user did not give is `null`.** `amount`, `rounds` and `rest` in the emitted document become nullable, with their sources. `log.to_performed` fills a `null` from the prescription and marks it `assumed`, as it already does for an untouched block. The agent writes `reported` and `asked`; `assumed` stays legal only where the prescription is silent (ADR-0009).
   - A `null` with nothing prescribed behind it (a substitution, an unplanned block) is refused, and the refusal offers asking the user or writing a reading marked `assumed`.
2. **A refusal goes back to the model.** Parse errors and `log.validate` refusals come back as a message naming every rule broken, and the run emits again, within an attempt budget like the planner's. The record counts the attempts.
3. **The exclusion's vocabulary comes from the data.** A refused exclusion lists the movement patterns and loaded joints `exclusions.classify` accepts, read from the catalog; with 2 the model picks one. Not an enum in the schema: the choice stays the model's. Never a constant (CLAUDE.md standing rule).
4. **`LOGGING` rewritten** around the new contract: one rule on provenance, none about the form. Say to search the catalog when a named exercise is not in the prescription.
5. **The set and the scorer follow.**
   - The 18 expected documents in `docs/logging/eval-set.md` lose their `assumed` values, except U6's substitute rest, which nothing prescribes.
   - `log_evaluation._difference` compares the document the engine would write, after `to_performed`, so an untouched block re-emitted as `null` is not a failure.
   - `verify` still recomputes every volume.
6. **`trainer.log.PerformedWorkout` registered** with the checkpoint serializer (`coach/checkpoints.py`). LangGraph warns that deserializing it will be blocked in a future version, which would break resuming the logger after `interrupt()`.
7. **An ADR** (0009): the agent writes what was said, and the engine writes what was assumed. It amends the provenance rule the prompt, the schema and the set disagreed on.

Not in scope: the asking half (A rows) beyond what the prompt rewrite does; the full pass and its bar, which are 05's.

## References

- TRAINER.md § Evaluation, § Agent: the deliberative layer
- CONTEXT.md: Adherence, Deviation, Provenance, Skipped
- ADR-0004 (the graph; the validator feeds back), ADR-0007 (the run record)
- `src/trainer/coach/logger.py`, `src/trainer/log.py`, `src/trainer/log_evaluation.py`, `src/trainer/tools.py` (`strict_schema`), `src/trainer/coach/planner.py` (the refusal loop to copy)

## Acceptance criteria

- [x] A document with `amount: null` on a prescribed exercise resolves to the prescribed amount marked `assumed`; one on an unprescribed exercise is refused with a message that says to ask.
- [x] A refused document reaches the model again, and a run that corrects itself on the second attempt ends `done`, with the attempts in its record.
- [x] A refused exclusion names the catalog's patterns and joints, and a test reads them from a fixture catalog rather than from a list.
- [x] `trainer eval --suite log` refuses to start if `verify` fails; the rewritten set passes it.
- [x] The 2026-09-21 records of U1, U2 and U9 that failed on form alone would be scored as held by the new `_difference`: checked by rescoring them, not by reading the code.
- [ ] `trainer eval --suite log --only U1 U2 U9 U15 A8` on Ollama, run and the number written in 05 next to the first pass.
- [ ] The checkpoint warning is gone from that pass.
- [x] Full test suite and mypy green.

## Comments

- Rescored with the new `_difference`, the 50 valid determined runs of the 2026-09-21 pass hold **12** (7 before). U1 3/3, U2-3 and U9-3 now hold; U2-1 and U2-2 still fail, correctly: they mark 10 reps nobody said as `reported`.
- The checkpoint warning came from the evals' `InMemorySaver()` on LangGraph's default serializer; both evals now use `checkpoints.Declared`, as the bot does.
- `/code-review`: one finding, the expected document resolved unguarded in `_difference`; guarded, with a test.
