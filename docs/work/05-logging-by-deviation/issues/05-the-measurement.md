# 05 — The measurement

**Status:** ready-for-human — the thirty reports are hand-written, and written
blind. The command around them is agent work; the rows are not, and they come
first. Flip this line to `ready-for-agent` once the rows exist.

**Blocked by:** 04.

## What to build

About thirty reports with their expected outcomes, and the command that scores
them. This is what the session ships beyond a write path: without it, session 5
is persistence with a model attached.

**The set is in Italian** — the first Italian in the repo, and deliberately so.
These are fixtures, not documentation, and CLAUDE.md's English rule covers
documents, code, identifiers and commit messages. An eval over English sentences
would measure a system nobody uses, since the person writing these reports
writes them in Italian in twenty seconds after training. Field names, comments
and everything around the strings stay English.

**Written before seeing what the agent produces.** Same discipline as session
2's reference set, and the same reason: a set written afterwards measures how
well you rationalise the output you already got.

**Two halves, and the second is the one that matters.**

*Eighteen unambiguous.* The report determines the answer. Scored by field-by-
field equality on the emitted document: the exercise ids, the rounds, the loads,
and the volume the workout produces on both axes.

*Twelve that must make it ask.* The report does **not** determine the answer,
and filling it is wrong however plausible the fill — *«ho fatto un po' meno»*
(how much less?), *«ho cambiato il secondo esercizio»* (for what?), a bare
number that is effort or discomfort and the sentence does not say which. Scored
binary: did it ask, or did it write a value the row declares unknowable?
**False confidence weighted double**, the same shape as session 10's golden set.

An example you cannot label does not go in — session 10's rule, and it applies
here first.

**Both halves decided by code** reading the run record. No model judges another
model's output, anywhere; that is `evaluation.py`'s standing rule and it does
not bend for a labelled set.

**What it reuses and what it does not.** It reuses `Outcome`, `Report`, `render`
and — this is the part that matters — `REPETITIONS`: a model is a distribution,
and one green run measures nothing for a labelled row just as it measures
nothing for a situation. It does **not** reuse `INVARIANTS`, which are
properties that must hold always with no expected output. This is a labelled set
with expected answers: different structure, same discipline. Adding a suite
selector is what keeps both under one command without forcing either into the
other's shape.

**What ticket 04 built that this one scores.** Four things, by the names it
built them under:

- `agent.log_workout(connection, said, today, *, ask, awaiting, prescribed_on,
  model, budget)` is the entry point, and `ask` is a `Callable[[str], str]`.
  That parameter is what makes the must-ask half measurable at all: pass an
  answerer scripted per row, and *did it ask* is a field rather than something
  read out of a terminal.
- `agent.LogRecord` is what the scoring reads. `questions` holds every
  clarifying turn as `{asked, answered}`, `document` is the emitted
  `log.PerformedWorkout`, and `refused` is `log.validate`'s sentence or
  `None`. **A must-ask row is scored on `questions` being non-empty**, and an
  unambiguous row on `document` — no terminal, no model judging a model.
- **A question is marked, not inferred.** The agent asks by writing a line
  starting with `agent.QUESTION_MARKER`, because the default model hands its
  reasoning back as ordinary message content and there is no way to tell prose
  that thinks from prose that asks. A row whose expected outcome is *«it
  asks»* is testing that the model emitted that marker.
- `agent.ASK_BUDGET` bounds the asking at three. A row that would need a
  fourth question is a row to reword, not a failure to record.

**The eval never writes.** `log_workout` takes a connection and reads through
it; the write is `trainer log`'s, in the CLI. So thirty rows can run against
the project database without leaving thirty performed workouts in the state the
measurement is taken from — which is the mistake session 5's issue 1 moved plan
persistence into the CLI to avoid, and it holds here for free.

**Read first:** `evaluation.py` in full, and `agent.py`'s logging door --
`LOGGER`, `log_workout`, `LogRecord`. ROADMAP.md § Session 5, the notes on the
eval set and on what to cut if ticket 04 overruns. TRAINER.md § Level 1 and the
golden-set rules. CLAUDE.md § Standing rules.

## If this ticket is squeezed

The cut is **thirty rows to twenty, keeping both halves** — never the second
half. The twelve that must make it ask are what measures whether the system
knows that it does not know, and a suite of only the easy rows rewards a model
that guesses confidently, which is the failure being tested for.

## Acceptance criteria

- [ ] The suite selector runs the log set and leaves session 4's six situations reachable and unchanged.
- [ ] Thirty rows exist, eighteen unambiguous and twelve must-ask, each with the expected outcome written beside it.
- [ ] Every must-ask row states, in one line, what makes it unknowable — a row nobody can label is not in the set.
- [ ] The unambiguous half is scored by equality on the emitted document, including the volume produced on both axes.
- [ ] The must-ask half is scored binary, read off `LogRecord.questions`, and a filled value where the row expects a question counts double against.
- [ ] Each row runs the declared number of repetitions and the report shows the distribution, not a single pass.
- [ ] No model judges another model's output anywhere in the scoring path.
- [ ] The command exits non-zero below the declared bar, the way `trainer eval` already does.
- [ ] The report is ASCII.
