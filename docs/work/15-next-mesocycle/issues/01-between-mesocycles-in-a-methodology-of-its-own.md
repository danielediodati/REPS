# Between mesocycles, in a methodology of its own

Status: ready-for-agent

Read first: ADR-0014 item 7; `src/trainer/data/methodology.md`, its style and its sources; TRAINER.md § Data model (a human writes the methodology).

## What to build

- **`src/trainer/data/variation.md`**, a document of its own, read by the supervisor and never by the planner: going from one mesocycle to the next, varying exercises, reps and rest, alone or together, and what the literature says each buys. Ranges and principles, never a template.
- **The goal's ranges are not copied into it**: the supervisor reads them from `methodology.md`.
- **Primary sources only**, with a list of its own in the same form.
- `methodology.md` is untouched, so the planner's prompt does not change.
- Loads and progression stay out (after 1.0.0).

## Acceptance criteria

- [ ] Every claim in it cites a source in its list.
- [ ] The planner's prompt is byte-identical before and after (a test).
- [ ] Nothing in it is a fixed rule a model could apply without the person (e.g. "change half the exercises").
- [ ] The user has read it: a human writes the methodology.
