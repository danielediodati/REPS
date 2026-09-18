# The log eval suite runs against the graph

Status: ready-for-agent

Blocked by: 02, 03 -- it measures the subgraph, through the door the entrance adds.

`log_evaluation.py` runs the 30-report set against `agent.py`, which 02 deletes, and reads `agent.QUESTION_MARKER` as a field. The suite is the only thing that says whether the logger got worse, and it must point at the graph before the loop goes.

## What to build

- **The suite enters at the logger subgraph**, the way the plan suite enters at the planner, and the question it used to read off a marked line is the `interrupt()` the subgraph raises.
- **The invariants are the log set's own rows**, unchanged: the suite measures a different implementation of the same thing, not a different standard. U7 still checks only that nothing is invented.
- **Each run reports what it cost**, like the plan suite: the model, the attempts, the wall time. It writes the same record document as everything else (01).
- **It runs against a fixture named in `TRAINER_DB`.** The tools open their own connection, so a fixture nothing points at is invisible to the agent under measurement.

## Acceptance criteria

- [ ] `trainer eval --suite log` runs the 30 reports against the subgraph and reports the same invariants.
- [ ] A report whose expectation is a clarifying question is measured on the `interrupt()`, with no marker anywhere in the suite.
- [ ] The records it writes are the documents 01 defines, in the eval runs directory.
- [ ] The suite passes at the rate the set declares, and a drop is reported per row rather than as one number.
- [ ] The full test suite and mypy are green.
