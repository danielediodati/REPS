# REPS

*Reasoning Engine for Personal Strength.* See [TRAINER.md](TRAINER.md) for what gets built and why, and [ROADMAP.md](ROADMAP.md) for the order it gets built in.

All documentation, code, identifiers and commit messages are written in **English**.

## Agent skills

### Issue tracker

Issues live as markdown files under `docs/work/<feature-slug>/`, one file per ticket — this repo has no remote. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical roles, unchanged, recorded as a `Status:` line in each issue file. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Standing rules

Each of these was learned by getting it wrong once. They are cheap to follow and expensive to rediscover.

- **Anything the CLI prints is ASCII.** An em dash renders as a replacement character in the Windows console. The documents keep their typography; output does not.
- **Vocabulary that exists in the data is read from the data**, never restated as a constant in code. The catalog's equipment list was hand-copied once from a partial read of the file and was wrong in three places; a CLI holding that copy would have rejected a real value as a typo.
- **A missing precondition is reported as a state, never as a user error.** Against a database with no catalog in it, `catalog --equipment dumbbell` rejected a correct value as a typo, because the vocabulary read from an empty table is empty. Check the state first and name it: *run `trainer db import` first*.
- **Tests derive the expected schema version from the migration set.** Two tests hardcoded version 1 and broke the moment a second migration existed. An assertion about today's schema is not an assertion about behaviour.

## Closing a ticket

Run through this every time, in order. A ticket is not done because the code works.

1. **Verify every acceptance criterion by running it**, not by reading the code. Tick a box only for something you have watched happen.
2. **Full test suite and type check, both green.** Report the numbers.
3. **Run `/code-review`.** Every finding is either fixed — with a test that would have caught it — or declined in writing, with the reason. A finding you could not reproduce still gets a line saying so.
4. **Move anything that outlives the ticket somewhere it will be read.** The ticket file is about to be deleted, so a decision left only in it is a decision lost:
   - it contradicts TRAINER.md or ROADMAP.md → correct those
   - it constrains a later ticket → write it into that ticket
   - it changes how the project is used → README
   - it is the reasoning behind what you built → the commit message, which is permanent and greppable
5. **Write the user a report, in Italian** — the one artefact of this project that is not in English, because it is written for the user to read rather than for the repo to keep. In the conversation, never in a file. Use these headings, in this order, and keep it factual — a reader who was not here has to be able to follow it:

   - **Cosa è stato costruito** — two or three sentences. What the code now does, in plain terms, before any detail.
   - **Cosa puoi lanciare** — the commands, with their real output pasted in.
   - **File** — a table: path, lines, what it does.
   - **Cosa si è rotto rispetto a prima** — **regressions only**: something that worked before this ticket and does not now, or an existing test that failed. A bug you wrote and fixed inside the ticket is not a regression, it is development, and it does not belong here. If nothing broke, say so in one line.
   - **Dove siamo** — test count, type check, what is now unblocked.

   Anything genuinely surprising goes in one short paragraph at the end. Not an essay: no aphorisms, no narrative, no sentence that exists because it sounds good. If a line would not help someone decide what to do next, cut it.
6. **Mark the issue done in ROADMAP.md**, with the short hash of the commit that closed it:

   ```markdown
   2. Import free-exercise-db into `exercises` — native fields, instructions and
      images included, retrievable by id. — **done** `c6f11f3`
   ```

   That is where finished work stays visible. The roadmap already lists every session's issues in order, so someone opening the repo sees what is built and what is not without reading git history, and the hash puts the full record one `git show` away.

7. **Delete the ticket file.** A finished ticket is a work item, not an archive: the roadmap carries the status, the commit carries the record, and git still has the file. Delete the feature directory too when its last ticket goes.
8. **Commit.**

Step 4 is the one that costs you if you skip it. Steps 1-3 fail loudly; a decision buried in a deleted file fails silently, weeks later, when someone rebuilds the reasoning from scratch.

## Closing a session

A session closes when its last ticket does — every issue under that heading in ROADMAP.md marked **done**. It ships a version. Three more steps, after the closing commit:

1. **Bump the minor version in `pyproject.toml`** — session N ends at `0.N.0`, which is what the roadmap's table already promises. That file is the only place the number lives: `trainer.__version__` reads the installed package metadata, so run `uv sync` afterwards or `trainer --version` goes on reporting the old one. Commit it on its own, `Release 0.N.0`.
2. **Tag that commit**, annotated, `v0.N.0`. The subject is the line the roadmap's table gives for the session — *what you can do at the end* — and the body says what actually shipped, in two or three lines.
3. **Point README's Status at the new version** and at what the next session opens with.

The tag is what answers *«it used to work»* when a later session breaks something the roadmap says was finished. `git diff v0.1.0..v0.2.0` is the only view of the project that is neither one commit nor all of them.
