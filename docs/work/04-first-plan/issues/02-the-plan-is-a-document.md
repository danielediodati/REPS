# 02 — The plan is a document: schema, validator, renderer

**Status:** ready-for-agent

**Blocked by:** None — can start immediately. Independent of 01; both gate 03.

## What to build

The door the agent's output will come through, built and testable **before**
there is an agent. `trainer plan --from FILE`, given the same request options
`trainer admissible` already takes, reads a plan someone wrote by hand,
validates it deterministically, and either renders the workout or names exactly
which rule rejected it.

Three parts, no model and no network anywhere in them.

**The schema.** A plan is a sequence of blocks; a block is one or more
exercises, a number of rounds, and the rest taken after each round (ADR-0002).
An item names an exercise and either its reps or its seconds. Each block carries
the reason it is there — the agent gives its reasons, and a plan that cannot
hold them has nowhere to put them. Structured, never prose (TRAINER.md §
*Technical architecture*).

The schema is the **wire shape** and lives beside the tool surface. The engine
keeps its own frozen `Block` / `BlockItem`, and the schema converts into them:
the engine grows no new types and learns nothing about how a plan arrives.

**The validator.** Ten lines, three rules, and it **rejects** — it never trims,
never repairs, never re-asks (ADR-0001, TRAINER.md § *The agent cannot route
around the constraints*):

1. every id is inside `admissible_set` for the request this plan was made
   against;
2. the plan's duration is inside the declared budget;
3. no exercise appears twice — `duration.check_plan` already is this rule.

**The renderer.** ASCII only. Blocks in order, each with its exercises, rounds,
reps or seconds, the prescribed rest, what the block costs, and the plan's total
against the budget it was given.

**Read first:** TRAINER.md § *The agent cannot route around the constraints, by
construction*, § *Engine — analytic / derived* (duration). ADR-0001 (rejected,
never repaired), ADR-0002 (blocks, and one line per exercise). CLAUDE.md §
Standing rules — anything the CLI prints is ASCII.

## Acceptance criteria

- [ ] `trainer plan --from FILE --equipment dumbbell --time 45` renders a valid plan: blocks, exercises, rounds and reps or seconds, prescribed rest, cost per block, total against the budget.
- [ ] An id outside the admissible set for that request is rejected naming the id **and** why it is out — equipment, an exclusion, or setup cost over the budget.
- [ ] A plan over the declared budget is rejected with both numbers, and nothing is cut. No option exists to make it fit.
- [ ] An exercise appearing twice anywhere in the plan is rejected, with the sentence `check_plan` already gives.
- [ ] A rejected plan is never partially rendered: it is valid or it is not.
- [ ] A file that is not a plan fails as a shape error naming the field it choked on, never as a traceback.
- [ ] Against a database with no catalog, or a catalog that is not enriched, the answer names that state and the command that fixes it — not a plan that validates against an empty set.
- [ ] The rendered output is ASCII.
- [ ] The engine gains no new type and no import of the schema library.
