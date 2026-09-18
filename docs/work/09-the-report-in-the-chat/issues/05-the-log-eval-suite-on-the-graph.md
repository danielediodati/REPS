# The log eval suite runs against the graph

Status: ready-for-agent

Blocked by: nothing now. 02 pointed the suite at the graph; what is left is a pass against a real provider, and 03 does not change what it measures.

**02 did most of this, because it had to**: a module cannot be deleted while something imports it, so `log_evaluation.py` moved onto the graph with the loop. It enters at `logger.build`, answers the `interrupt()` with `UNANSWERED` and declines every proposed exclusion, scores a `Read` whose `questions` are a field rather than a reading of prose, and writes the ADR-0007 document into the eval runs directory. No marker is left anywhere in it.

What is left is the half 02 could not do: **running it**. Thirty reports against a real provider, at the rate the set declares, with the drop reported per row -- and the suite has not been run against the graph even once.

## What to build

- **A pass against a real provider**, on both, and the number it comes to. The set declares its own bar; a drop is reported per row rather than as one figure.
- **Whatever that pass says about the prompt.** The loop's prompt moved into `coach/logger.py` with one section rewritten -- asking is a tool call now -- and nobody has measured what that did. If the rate moved, the prompt is where to look first.
- **The invariants are the log set's own rows**, unchanged: the suite measures a different implementation of the same thing, not a different standard. U7 still checks only that nothing is invented.
- **It runs against a fixture named in `TRAINER_DB`.** The tools open their own connection, so a fixture nothing points at is invisible to the graph under measurement.

## Acceptance criteria

- [ ] `trainer eval --suite log` has been **run** against a real provider, and the number is written down here.
- [ ] The suite passes at the rate the set declares, and a drop is reported per row rather than as one number.
- [ ] A report whose expectation is a clarifying question is measured on the `interrupt()` -- verified by a pass, not by reading the code (02 wired it).
- [ ] The full test suite and mypy are green.
