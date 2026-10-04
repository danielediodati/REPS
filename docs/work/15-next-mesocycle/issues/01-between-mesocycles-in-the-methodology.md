# Between mesocycles, in the methodology

Status: ready-for-agent

Read first: ADR-0014; `src/trainer/data/methodology.md`; TRAINER.md § Data model (a human writes the methodology).

## What to build

- **A section in `methodology.md`** on going from one mesocycle to the next: varying exercises, reps and rest, alone or together, and what the literature says each buys. Ranges and principles, never a template.
- **Primary sources only**, numbered into the file's existing list, as the rest of it is.
- Loads and progression stay out (after 1.0.0).

## Acceptance criteria

- [ ] Every claim in the section cites a source in the list.
- [ ] Nothing in it is a fixed rule a model could apply without the person (e.g. "change half the exercises").
- [ ] The user has read it: a human writes the methodology.
