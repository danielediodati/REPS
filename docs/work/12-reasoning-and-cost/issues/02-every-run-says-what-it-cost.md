# Every run says what it cost

Status: ready-for-agent

Blocked by: nothing.

A pass reports tool calls and tokens. What it cost in money was estimated by hand from secondary price pages, and the estimate was off by half. OpenRouter returns the cost of each request in its usage block when asked (`usage: {include: true}`).

## What to build

- **The cost of each model call, from the provider**, kept per node in the run record beside its tokens. No price table in the code (CLAUDE.md: vocabulary that exists in the data is read from the data).
- **The pass reports it**: total dollars, dollars per run, and seconds per run, next to the existing cost line. On a provider that does not report cost, the line says so rather than printing zero.
- **The same in `trainer runs show`**, so a single conversation's cost can be read back.

## References

- ADR-0007 (the run record), ADR-0010
- `src/trainer/evaluation.py` (`totals`), `src/trainer/coach/record.py`

## Acceptance criteria

- [ ] A recorded response with a cost in its usage is summed into the pass; one without prints *not reported*.
- [ ] `trainer eval --suite log --only U1 --repetitions 1` on OpenRouter prints dollars and seconds per run, and the dollars match OpenRouter's activity page.
- [ ] Full test suite and mypy green.
