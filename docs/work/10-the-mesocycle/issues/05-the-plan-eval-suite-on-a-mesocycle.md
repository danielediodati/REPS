# The plan eval suite on a mesocycle

Status: ready-for-agent

Blocked by: 01.

`trainer eval --suite plan` runs six adverse situations against one workout. After 01 what is planned is a mesocycle, and a mesocycle is several plans' worth of model minutes: the risk this session carries.

## What to build

- **The six situations asked as a mesocycle**, the six invariants checked on every workout in it.
- **Wall time per run on the local model**, reported beside attempts and tool calls, as the plan suite already reports them.
- **It runs against a fixture named in `TRAINER_DB`** (CLAUDE.md standing rule).

## Left by 03

- **Groq's free tier cannot plan a mesocycle.** Its input cap is 7000 tokens a minute, and the first planner turn of a 5-slot mesocycle asks for 8003: `413 rate_limit_exceeded` before any tool call, as a raw traceback from `trainer plan`.
- **One 5-slot mesocycle on `gpt-oss:20b` (CPU) took 585 s** (`trainer plan --change`, 2 attempts, 34.5k tokens in, 2.6k out; planner 427 s, emit 154 s). Six situations are about an hour, and one refused twice will not fit a 10-minute call.

## Left by 01

- **One `trainer plan --mesocycle` on OpenRouter**, 2026-09-24, `openai/gpt-oss-120b:nitro`: 5 workouts, 4 cycles, accepted after 3 attempts. **~17 s** (planner 11.1 s, emit 6.2 s), 93k tokens in, 21k out, 6 of 12 tool calls, one of them an error. Six situations are minutes, not an hour: the risk above belongs to the local model, which the project no longer plans on. Run this suite on OpenRouter with the planner session 12 chooses, and on the local model only if a number is still wanted from it.

## References

- TRAINER.md § Evaluation; ADR-0008
- `src/trainer/evaluation.py`, `src/trainer/cli.py` (`eval`)

## Acceptance criteria

- [ ] `trainer eval --suite plan` asks for a mesocycle and checks the six invariants per workout.
- [ ] Run on OpenRouter with session 12's planner; the numbers and the wall time are written here.
- [ ] Full test suite and mypy green.
