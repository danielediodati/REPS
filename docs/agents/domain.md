# Domain docs

This is a single-context repo: `CONTEXT.md` and `docs/adr/` sit at the root.

- **Before exploring**, read `CONTEXT.md` and the ADRs that touch the area. If one of them does not exist, carry on without mentioning it.
- **Use the glossary's terms** in issue titles, proposals and test names. Never use a synonym the glossary tells you to avoid.
  - A concept missing from the glossary means one of two things: you are inventing language (reconsider), or there is a real gap (note it for `/domain-modeling`).
  - Keep three words distinct: a *workout* is training, a *session* is development work, a *plan* is what the agent emits for one workout.
- **Flag ADR conflicts** explicitly instead of silently overriding them, for example: *Contradicts ADR-0004 (…), but worth reopening because…*. TRAINER.md's principles count as decisions too, e.g. no LLM in the engine, writes are never tools, and a validator is preferred over a judge for decidable constraints.
