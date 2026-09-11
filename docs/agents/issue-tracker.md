# Issue tracker: local markdown

The tracker is `docs/work/`, versioned with the code, never GitHub Issues; never add it to `.gitignore`.

## Conventions

- **One feature per directory**: `docs/work/<feature-slug>/`, with its spec at `spec.md`.
- **One file per ticket**: `docs/work/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01`.
- **Triage state**: a `Status:` line near the top of the ticket (see `triage-labels.md`).
- **Comments**: appended under a `## Comments` heading.
- **Closing**: a closed ticket is deleted, following CLAUDE.md § Closing a ticket. ROADMAP.md marks it done, with the commit hash.
- **Mapping to the roadmap**: a feature directory is a roadmap session. Each ticket must stand alone in a clean context and point at the TRAINER.md sections and ADRs it needs.

## Skill operations

- **Publish to the tracker**: create a file under `docs/work/<feature-slug>/`.
- **Fetch a ticket**: read the file at the path you were given.

## Wayfinding (`/wayfinder`)

- **Map**: `docs/work/<effort>/map.md`, with the sections Notes, Decisions-so-far and Fog.
- **Child ticket**: `docs/work/<effort>/issues/NN-<slug>.md`. It carries a `Type:` line (`research`, `prototype`, `grilling` or `task`) and a `Status:` line (`claimed` or `resolved`).
- **Blocking**: a `Blocked by: NN, NN` line. The ticket is unblocked once every listed file is `resolved`.
- **Frontier**: the tickets that are open, unblocked and unclaimed, lowest number first.
- **Claim**: set `Status: claimed` before starting any work.
- **Resolve**: append the answer under `## Answer`, set `Status: resolved`, and add a one-line gist with a link to the map's Decisions-so-far.
