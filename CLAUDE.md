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
5. **Write the user a detailed report** — what was delivered, what the review found, what surprised you, what you decided and why. In the conversation, not in a file.
6. **Delete the ticket file.** A finished ticket is a work item, not an archive: git still has it, and the durable record is the commit plus whatever step 4 moved. Delete the feature directory too when its last ticket goes.
7. **Commit.**

Step 4 is the one that costs you if you skip it. Steps 1-3 fail loudly; a decision buried in a deleted file fails silently, weeks later, when someone rebuilds the reasoning from scratch.
