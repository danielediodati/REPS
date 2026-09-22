# The agent writes what was said

The first log pass on the graph held 24 of 90. The document the logger emits required every number in a block, so a number the user never gave had to be copied from the prescription and labelled. The prompt said *never `assumed`*, and the set expected `assumed`. A refused document ended the run, and nothing told the model which patterns or joints an exclusion may name. Rescored on the workout the engine would write, the same runs held 30 of 50 determined reports, where the raw document held 7.

## Decision

1. **A number the user did not give is left out (`null`)**, with its source. `log.to_performed` writes the prescribed one, marked `assumed`, as it already did for an untouched block. The agent writes what the user said (`reported`) or answered (`asked`).
2. **`assumed` stays legal where the prescription is silent**: a substitute's rest nobody mentioned has nothing to be filled from. Whether to ask or to write a reading there is the agent's call, and the validator's refusal of a null with nothing behind it offers both.
3. **A refusal goes back to the model**, which may read, ask and emit again, within `logger.ATTEMPTS`. As in the planner, the record keeps every attempt.
4. **A refused exclusion lists the catalog's patterns and joints.** It is read from the data, never a constant, and the agent picks one rather than being held to an enum.
5. **The log suite scores the resolved workout.** Every number and its provenance are compared after adherence, so the form of the emission is not scored.

## Why

- **Copying a prescribed number is a lookup, and lookups are the engine's.** The model is there to read the sentence (ADR-0001, ADR-0004).
- **Feedback, not more rules in code.** Each failure the validator can name is one the model can fix with a second look, which is what the planner already does.

## Consequences

- `log.PerformedItem` and `log.PerformedBlock` take nulls; a hand-written `trainer log --from FILE` document may leave numbers out the same way.
- `docs/logging/eval-set.md`: the expected documents lose every `assumed` except U6's.
- CONTEXT.md *Adherence* covers a number left out of a block as well as a block left out of the report.
