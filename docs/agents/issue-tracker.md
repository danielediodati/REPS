# Issue tracker: Local Markdown

Issues and specs for this repo live as markdown files in `.scratch/`.

This repo has no git remote, so there is no GitHub/GitLab issue tracker to talk to. The files under `.scratch/` **are** the tracker, and they are versioned along with the code — do not add `.scratch/` to `.gitignore`.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`
- The spec is `.scratch/<feature-slug>/spec.md`
- Implementation issues are one file per ticket at `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01` — never a single combined tickets file
- Triage state is recorded as a `Status:` line near the top of each issue file (see `triage-labels.md` for the role strings)
- Comments and conversation history append to the bottom of the file under a `## Comments` heading

## Mapping onto the roadmap

[ROADMAP.md](../../ROADMAP.md) is already sliced into numbered sessions of no more than five issues each. A feature directory is a session:

```
.scratch/
└── 01-raw-catalog/
    ├── spec.md
    └── issues/
        ├── 01-skeleton.md
        ├── 02-import-free-exercise-db.md
        ├── 03-catalog-command.md
        └── 04-markdown-dump.md
```

Each issue has to stand on its own in a clean context and point at the sections of [TRAINER.md](../../TRAINER.md) it needs — that is the roadmap's slicing rule, and it is what makes a ticket closable with `/implement`.

## When a skill says "publish to the issue tracker"

Create a new file under `.scratch/<feature-slug>/` (creating the directory if needed).

## When a skill says "fetch the relevant ticket"

Read the file at the referenced path. The user will normally pass the path or the issue number directly.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a file with one **child** file per ticket.

- **Map**: `.scratch/<effort>/map.md` — the Notes / Decisions-so-far / Fog body.
- **Child ticket**: `.scratch/<effort>/issues/NN-<slug>.md`, numbered from `01`, with the question in the body. A `Type:` line records the ticket type (`research`/`prototype`/`grilling`/`task`); a `Status:` line records `claimed`/`resolved`.
- **Blocking**: a `Blocked by: NN, NN` line near the top. A ticket is unblocked when every file it lists is `resolved`.
- **Frontier**: scan `.scratch/<effort>/issues/` for files that are open, unblocked, and unclaimed; first by number wins.
- **Claim**: set `Status: claimed` and save before any work.
- **Resolve**: append the answer under an `## Answer` heading, set `Status: resolved`, then append a context pointer (gist + link) to the map's Decisions-so-far in `map.md`.
