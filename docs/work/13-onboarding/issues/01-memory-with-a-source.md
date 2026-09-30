# Memory with a source

Status: ready-for-agent

Read first: TRAINER.md § Memory; ADR-0004 (the LangGraph store is where memory lives).

## What to build

- **The store**: conclusions in the LangGraph store, persisted under `TRAINER_HOME` next to the checkpointer, one namespace per user.
- **A `remember(conclusion, quote)` tool.** `quote` is the user's sentence verbatim. **Admission is code**: refused, with the reason sent back to the model, unless `quote` appears in one of the user's messages in the thread. Admitted, it enters as *provisional*, with its date and the quote.
- **The tool is given to the entrance and the logger** now, and to onboarding in 02. Their prompts say what is worth keeping (TRAINER.md's table: *"the bike bores me"* yes, *"the bike bored me today"* no).
- **The planner reads the live conclusions** in its brief, each with its quote. No retrieval: they fit in a prompt.
- A conclusion is never an exclusion (CONTEXT.md): it makes the planner prefer, never the engine refuse.

## Acceptance criteria

- [ ] A conclusion whose quote is not in a user message is refused, and the refusal reaches the model (test).
- [ ] A paraphrased quote is refused (test).
- [ ] *"I hate pressing"* said to the entrance is stored with its quote, and the next mesocycle's brief carries it (test with a scripted model).
- [ ] It survives a restart of `trainer bot`.
- [ ] Full test suite and mypy green.
