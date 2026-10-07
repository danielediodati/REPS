# What the chat shows is Italian

Status: ready-for-agent

Read first: `spec.md`; ADR-0004.

## Where it stands

Found using `1.0.0rc1`, 2026-10-07: the user asked what *the press*, *the row* and *the pull* were. A block's `reason` is shown in the chat under it (`bot.WHY`), and it is English from two sources:

| Source | Example |
|---|---|
| `docs/demo/history.toml`, every block and direction | `reason = "the press"`, `theme = "the main lifts, heavy"` |
| the planner's prompts, which give the reason no language | *"the incline press—upper chest angle"* in tonight's adaptation |

The entrance and onboarding prompts already say *in Italian*.

## What to build

- Every model-written line the chat shows is Italian: a block's reason, a plan's note, a mesocycle's cycles sentence, a direction as the proposal says it. One rule, stated once and read by every prompt that writes one.
- The demo's history is rewritten in Italian, and a reason says why the block is there, not its name.
- Code, identifiers and prompts stay English (CLAUDE.md).

## Acceptance criteria

- [ ] `trainer demo` builds a home whose workouts, as the chat renders them, have no English line.
- [ ] On scripted models: a test that the rule reaches every prompt that writes a shown line.
- [ ] A paid pass, estimated and approved first: one adapted workout and one mesocycle, read by the user.
