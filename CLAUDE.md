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
- **Every agent measurement runs against a fixture named in the environment (`TRAINER_DB`).** The tools open their own connection, so a fixture that nothing points at is invisible to the agent.

## Closing a ticket

Follow these steps in order. Working code alone does not close a ticket.

1. **Verify every acceptance criterion by running it**, not by reading the code. Tick only what you watched happen.
2. **Run the full test suite and the type check; both must be green.** Report the numbers.
3. **Run `/code-review`.** Each finding is either fixed, with a test that would have caught it, or declined in writing with the reason. A finding you could not reproduce still gets a line saying so.
4. **Move anything that outlives the ticket** before the file is deleted:
   - it contradicts TRAINER.md, ROADMAP.md or an ADR → correct that document;
   - it constrains a later ticket → write it into that ticket;
   - it changes how the project is used → README;
   - it is the reasoning behind the code → the commit message.
5. **Write the user a report, in Italian**, in the conversation and never in a file. Open with a header block so it can be found by eye in the scrollback:

   ```markdown
   ---

   # ✅ Ticket 3.2 — chiuso
   ### Il piano si costruisce contro il budget invece di essere tagliato dopo
   `00d09c2` · 522 test · mypy pulito · niente rotto

   ---
   ```

   - **The H3** is the headline: the thing that now works and did not before, not *«ticket chiuso»*.
   - **The metrics line** holds four facts and no sentence: commit hash, test count, type check, and whether anything regressed.

   Then these sections, in this order:
   - **Cosa è stato costruito**: two or three plain sentences.
   - **Cosa puoi lanciare**: the commands, with their real output pasted in.
   - **Cosa si è rotto rispetto a prima**: regressions only, meaning something that worked before this ticket, or an existing test that now fails. A bug written and fixed inside the ticket does not belong here. If nothing broke, say so in one line.
   - **Dove siamo**: test count, type check, and what is now unblocked.

   Anything genuinely surprising goes in one short paragraph at the end.
   - **No file list**: `git show --stat` already has it.
   - **Keep it short**: a line either helps decide the next move, or it goes.
6. **Mark the issue done in ROADMAP.md** with the short hash of the closing commit: `… — **done** \`c6f11f3\``.
7. **Delete the ticket file.** When its last ticket goes, delete the feature directory too.
8. **Commit with the subject `Close ticket S.N`**: the session number, then the ticket number within it, as in `Close ticket 4.5`. Ticket numbers restart every session, so the number alone is ambiguous.

Step 4 is the one that fails silently. A decision left only in a deleted ticket is lost.

## Closing a session

A session closes when every issue under its heading in ROADMAP.md is **done**. After the closing commit:

1. **Set `pyproject.toml` to the version the roadmap gives the session**, then run `uv sync`: `trainer --version` reads the installed metadata. Commit it on its own as `Release X.Y.Z`.
2. **Tag that commit**, annotated, as `vX.Y.Z`. The subject is the session's demo line from the roadmap. The body says what shipped, in two or three lines.
3. **Point README's Status** at the new version and at what the next session opens with.
4. **Make the README describe the system as it is now**, not only its Status line. Every sentence in it is a claim about a running program, and a release that changed what the program does and left the README alone has published a false one. This is not the portfolio rewrite — that is its own session, with the GIF — it is the minimum that keeps the file from lying between here and there.
