# The log eval suite runs against the graph

Status: ready-for-agent

Blocked by: nothing. 06 closed on the 2026-09-23 pass; the full pass that closes this one runs on OpenRouter (`LLM_BACKEND=openrouter`, `LOGGER_MODEL`).

**02 did most of this, because it had to**: a module cannot be deleted while something imports it, so `log_evaluation.py` moved onto the graph with the loop. It enters at `logger.build`, answers the `interrupt()` with `UNANSWERED` and declines every proposed exclusion, scores a `Read` whose `questions` are a field rather than a reading of prose, and writes the ADR-0007 document into the eval runs directory. No marker is left anywhere in it.

What is left is the half 02 could not do: **running it**. Thirty reports against a real provider, at the rate the set declares, with the drop reported per row -- and the suite has not been run against the graph even once.

## What to build

- **A pass against a real provider**, on both, and the number it comes to. The set declares its own bar; a drop is reported per row rather than as one figure.
- **Whatever that pass says about the prompt.** The loop's prompt moved into `coach/logger.py` with one section rewritten -- asking is a tool call now -- and nobody has measured what that did. If the rate moved, the prompt is where to look first.
- **The invariants are the log set's own rows**, unchanged: the suite measures a different implementation of the same thing, not a different standard. U7 still checks only that nothing is invented.
- **It runs against a fixture named in `TRAINER_DB`.** The tools open their own connection, so a fixture nothing points at is invisible to the graph under measurement.

## Passes

| Date | Provider | Model | Held | Cost |
|---|---|---|---|---|
| 2026-09-21 | ollama (CPU) | `gpt-oss:20b` | **24 / 90, 25%** (95 with false confidence counted double) | 102 tool calls, 640k tokens in, 52k out, ~2.6 h |
| 2026-09-22 | ollama (CPU) | `gpt-oss:20b` | **3 / 15, 20%** on `--only U1 U2 U9 U15 A8`, after 9.6. 5 not run were a shape refusal 9.6 introduced and then fixed | 16 tool calls, 103k tokens in, 9.5k out |
| 2026-09-22 | groq | `qwen/qwen3.8-27b` | **9 / 12, 75%** on the same rows, A8's 3 not run (daily quota). Asked in 11 of 12 reports that needed no question | 36 tool calls, 161k tokens in, 8k out |
| 2026-09-23 | openrouter | `qwen/qwen3.8-27b:nitro` | **9 / 15, 56%** on the same rows: U 9 / 12, A8 0 / 3. Asked in **0 of 15**, `done_reading` in every run | 31 tool calls, 121k tokens in, 84k out |

What the 2026-09-23 pass leaves for this ticket:

- **A8 never asks** (3 / 3), which failed 3 / 3 on `gpt-oss:20b` too. `done_reading` and the rule *a number not mentioned is not a question* took every unneeded question away; whether they took the needed one with it is what the A rows of the full pass measure.
- **Provenance invented on a value nobody gave**: U2 #2 marks an unsaid rest `asked` with no question asked, U15 #1 marks it `reported`.
- **A block emitted twice**: U9 #2 writes the Pullups block twice and the engine accepts it, doubling vertical pull. A validator gap, not only a model error.
- **Output tokens are ten times Groq's.** Nothing caps them on OpenRouter; Qwen reasons at length.

What the first pass says, by cluster (counted by hand, a run can sit in two):

| Cluster | Runs | Where |
|---|---|---|
| Untouched blocks re-emitted, whole prescription copied | ~22 | U1, U4, U7, U9, U10, U18 |
| Copied value marked `reported`/`asked`, the set expects `assumed` | ~12 | U2, U5, U12, U18 |
| Exclusion names an exercise or an invented pattern, or is missing | ~9 | U7, U13-U16 |
| Did not ask when it had to | 14 of 36 | A3, A8, A12 fail 3/3 |
| Empty or invalid output | ~9 | A1, A11, U3-1, U13-2, U16-3 |
| Unprescribed workout: 0 blocks, or ids invented | 3 of 3 | U8 |

- **The prompt contradicts the set.** `LOGGING` says *"Provenance is `reported` … or `asked`. Never `assumed`"*; the set's own rule (`eval-set.md` § How to read a row, U2's note) is that a value nobody mentioned inside an emitted block is the prescribed one, marked `assumed`. The schema makes `amount`, `rounds`, `rest` and their sources required, so the model cannot leave them out as the prompt also asks. The line dates from 5.4.
- **An exclusion's vocabulary is not in the context.** The prompt asks for a pattern or a loaded joint and names two; nothing lists the rest, so the model invents `vertical squat`.
- **`Deserializing unregistered type trainer.log.PerformedWorkout from checkpoint`**: LangGraph warns it will block this in a future version, which would break resuming the logger after `interrupt()`. Register it in `coach/checkpoints.py`.
- `OLLAMA_CONTEXT_LENGTH=8192` in `.env`; the empty outputs may be truncation. Not verified.

## Acceptance criteria

- [x] `trainer eval --suite log` has been **run** against a real provider, and the number is written down here.
- [ ] The suite passes at the rate the set declares, and a drop is reported per row rather than as one number.
- [x] A report whose expectation is a clarifying question is measured on the `interrupt()` -- verified by a pass, not by reading the code (02 wired it).
- [ ] The full test suite and mypy are green.
