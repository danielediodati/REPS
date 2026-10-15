# What the chat shows while it works

Status: ready-for-agent

Blocked by: 03.

Read first: `src/trainer/coach/progress.py`; `bot.drafting`; ADR-0006 (the entrance's words are the model's).

## What to build

Found rehearsing the demo in English, 2026-10-15.

- **Progress is one line that changes**, not a log: the phase the run is in (looking at the catalog, writing the plan, the validator sent it back and it is rewritten, checking it), and for a mesocycle which workout of how many. The draft shows only the current line, so what outlives the plan by Telegram's 30 seconds is one line. The tool-by-tool detail stays in the run record.
- **A tool call written as text never reaches the chat.** DeepSeek on the entrance once answered a speak-only turn with its own call markup (`<｜DSML｜tool_calls>…`). Such a reply is asked again once; a second one is answered with the failed line.
- The lines come from the catalogs (`src/trainer/data/chat/`), in both languages.

## Acceptance criteria

- [ ] A streamed plan shows one line at a time in the draft, naming the workout for a mesocycle; a refusal shows as a line of its own phase.
- [ ] A test feeds the entrance a reply that is call markup, and the chat gets neither it nor silence.
- [ ] Rehearsed once in Telegram on the user's go, with its cost estimated first.
