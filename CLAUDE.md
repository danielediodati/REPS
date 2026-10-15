# REPS

*Reasoning Engine for Personal Strength.* [TRAINER.md](TRAINER.md) is the design, [ROADMAP.md](ROADMAP.md) the order it is built in, [ADR-0004](docs/adr/0004-an-agent-graph-over-the-engine-reached-through-telegram.md) the architecture.

Docs, code, identifiers and commits are in **English**. Conversation with the user (grilling, interviews, design discussion) and the closing report are in **Italian**.

## Agent skills

- **Issue tracker**: markdown files under `docs/work/<feature-slug>/`, one per ticket, never GitHub Issues. See `docs/agents/issue-tracker.md`.
- **Triage labels**: the five canonical roles, written as a `Status:` line in the ticket. See `docs/agents/triage-labels.md`.
- **Domain docs**: single context, with `CONTEXT.md` and `docs/adr/` at the root. See `docs/agents/domain.md`.

## Writing

- **Docstrings are one line**, saying what the thing does. Add a comment only where the reason is not obvious from the code.
- **Reasoning lives in one place.** A decision goes in an ADR; why the code is shaped the way it is goes in the commit message. Do not restate it in docstrings, the README and the roadmap as well.
- **Markdown stays short.** Prefer tables and lists to paragraphs, and leave out how a decision was reached (git has that). Trim any prose you touch.

## Standing rules

Each of these was learned by getting it wrong once.

- **Anything the CLI prints is ASCII.** An em dash shows as a replacement character in the Windows console. Documents keep their typography.
- **Vocabulary that exists in the data is read from the data**, never copied into a constant. A hand-copied equipment list was wrong in three places.
- **A missing precondition is reported as a state, not as a user error.** Check the state and name the fix, e.g. *run `trainer db import` first*. Against an empty catalog, a correct `--equipment dumbbell` was once rejected as a typo.
- **Tests derive the expected schema version from the migration set**, never from a hardcoded number.
- **A text the user reads is never in the code.** It lives in one catalog per language, read through a factory. Making the bot bilingual once put an English twin beside every Italian constant in `bot.py`.
- **Nothing that spends credits runs without the user's approval.** Every call to a paid model and every test or eval run that reaches one is asked for first, with an estimate of its cost; run it only once approved.
- **Every agent measurement runs against a fixture named in the environment (`TRAINER_DB`).** The tools open their own connection, so a fixture that nothing points at is invisible to the agent.

## Closing

A ticket closes with `/dd:close-ticket S.N`, a session with `/dd:close-session N`.
