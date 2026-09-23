# Legality is held at 100%, judgement at a declared bar

Both eval suites shared one bar, 100%, and exited non-zero below it. The plan suite checks six invariants a plan can only break by being illegal. The log suite checks how a model reads Italian sentences, some marked `?` by the author of the set. At 100% the log suite fails on every pass, and a failing exit says nothing.

## Decision

1. **The plan suite stays at 100%.** An invariant broken is a bug.
2. **The log suite is measured against two bars its set declares**, one per half: 80% for the reports that determine the answer, 60% for those that must make it ask, false confidence counted double. Below either, the command exits non-zero.
3. **The bars live in `docs/logging/eval-set.md`**, beside the rows. Raising them is an edit there, made when the model changes.

## Consequences

- `log_set.parse` refuses a set that declares no bar.
- A half with no runs, as under `--only`, is not held against the pass.
