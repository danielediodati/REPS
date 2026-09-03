# 05 — «What can I do today», answered by a `WHERE`

**What to build:** the state the exclusions live in, the library function that reads it, the command that exposes it, and the tests that hold it. This is the ticket the session is named for: everything before it produces data, this one asks the data a question a person would actually ask.

**This is the sentence the whole architecture rests on.** README's first principle is *«the analytic layer defines the space, the agent moves inside it»*, and `admissible_set` **is** that space. From session 4 onward an agent chooses inside what this function returns and cannot prescribe outside it — not because it is instructed not to, but because the validator rejects an id that is not in the set. So this function being right matters more than anything the agent does later.

**Exclusion has two granularities and no third.** A pattern — *«it hurts when I press overhead»* → `vertical push` out — and a joint — *«the shoulder is bad»* → everything with `shoulder` among its loaded joints out. That is what the triage in session 6 can actually elicit, and it is what replaced `required_rom`'s degree thresholds. Both come with a **re-test date**, because TRAINER.md is explicit that an exclusion that never expires walls off a pattern forever and nobody reopens it.

**A preference is not an exclusion.** TRAINER.md's glossary says so in as many words, and the distinction is not pedantry: exclusions are a hard engine boundary reserved for safety, and if *«I don't like lunges»* enters through the same door then a mood becomes a wall. Preferences are handled by the agent, from session 4. This ticket must make that hard rather than merely documented — nothing in the state should make it easy for a preference to arrive as an exclusion.

**No LLM in the tests, at all.** The three properties are deterministic and cheap: an excluded pattern never appears, absent equipment never appears, an expired exclusion stops excluding. These are the tests that will still be catching regressions at session 10, long after the agent's behaviour has become a distribution rather than a value.

**The empty-state case is not an edge case, it is the first run.** Against a database with a catalog and nothing else — no profile, no exclusions — `admissible_set` has to return the equipment-and-budget answer, not fail and not return nothing. And against a catalog with no enrichment it has to name that state: *run `trainer enrich derive` first*. This project has already been bitten once by a vocabulary read from an empty table rejecting a correct value as a typo.

Reference: TRAINER.md § Persistent state (the `WHERE`), § Glossary (exclusion, admissible set), § Engine — analytic / constrained; ROADMAP.md § Session 2.

**Blocked by:** 01 — The six enrichment fields; 02 — What the eleven patterns mean; 04 — The model reads the instructions

**Status:** ready-for-agent

- [ ] `profile` holds the primary goal, base equipment and permanent constraints; `pattern_state` holds per-pattern volume, trend and the active exclusions with their re-test date
- [ ] An exclusion names a **pattern** or a **joint**, never an exercise id and never a range in degrees
- [ ] Every exclusion carries a re-test date, and one whose date has passed no longer excludes — with a test that moves the clock rather than waiting
- [ ] `admissible_set(exclusions, equipment, budget)` is a library function in `engine/`, returning the exercises compatible with all three
- [ ] `trainer admissible --equipment bodyweight --time 45 --exclude vertical_push` runs and answers
- [ ] Tests with **no LLM at all**: an excluded pattern never shows up, an excluded joint never shows up, absent equipment never shows up, an expired exclusion stops excluding
- [ ] Against an empty profile it answers on equipment and budget rather than failing
- [ ] Against an unenriched catalog it names that state and says what to run, rather than returning an empty set that looks like an answer
- [ ] `--exclude` rejects an unknown pattern with the vocabulary read from the data, and rejects an exercise id outright — the granularity is part of the contract
- [ ] The whole path is a thin wrapper over the library, and the boundary test still passes

## Comments
