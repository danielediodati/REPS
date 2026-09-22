# The plan eval suite on a mesocycle

Status: ready-for-agent

Blocked by: 01.

`trainer eval --suite plan` runs six adverse situations against one workout. After 01 what is planned is a mesocycle, and a mesocycle is several plans' worth of model minutes: the risk this session carries.

## What to build

- **The six situations asked as a mesocycle**, the six invariants checked on every workout in it.
- **Wall time per run on the local model**, reported beside attempts and tool calls, as the plan suite already reports them.
- **It runs against a fixture named in `TRAINER_DB`** (CLAUDE.md standing rule).

## References

- TRAINER.md § Evaluation; ADR-0008
- `src/trainer/evaluation.py`, `src/trainer/cli.py` (`eval`)

## Acceptance criteria

- [ ] `trainer eval --suite plan` asks for a mesocycle and checks the six invariants per workout.
- [ ] Run on Groq and on the local model; the numbers and the wall time are written here.
- [ ] Full test suite and mypy green.
