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

## Milestone.feature.ticket

Work lives in `docs/work/`: every feature's spec and tickets, and every wayfinder map. To move it, change this line and every path in this file that names it.

Every piece of work has an address, `<milestone>.<feature>.<ticket>`: ticket 2.1.3 is the third ticket of feature 2.1, in milestone 2. Ticket numbers restart in every feature, and feature numbers in every milestone. `ROADMAP.md` at the repo root holds the plan; `/roadmap` shows what is open in it.

### `ROADMAP.md`

```markdown
# Roadmap

## Done

| milestone | version | shipped |
| --- | --- | --- |
| 1 - First light | `0.1.0` | the app starts |

## Milestone 2 - Users sign in

**Goal**: a user signs in with email and password.

- **done** 2.1 `login-form`: a user signs in from the login form

### Feature 2.2 - Sessions that expire

Spec: [spec](docs/work/2.2-sessions/spec.md)

1. **Expire them** - [ticket](docs/work/2.2-sessions/issues/01-expire.md)
2. **Warn before** - [ticket](docs/work/2.2-sessions/issues/02-warn.md)
```

- **Milestone:** `## Milestone <n> - <title>`, numbered in order, then its `**Goal**:` line. It names no version: the version is chosen when the milestone closes, which is its release.
- **Feature:** `### Feature <n>.<f> - <title>` under its milestone, then a `Spec:` line linking its spec, then its tickets.
- **Ticket:** a numbered line under its feature, opening with its `**title**` and linking its file.
- **Closed:** a closed ticket's line is removed, except the feature's last, kept and marked `**done** `<commit>``. A closed feature leaves one line, `- **done** <n>.<f> `<slug>`: <what it shows>`. A closed milestone leaves one row in the *Done* table.

### Where a feature lives

A feature's directory is `docs/work/<m>.<f>-<slug>/`: the feature slug of the conventions above, prefixed with the feature's number. Its spec and `issues/` follow those conventions unchanged.

### Where a milestone is built

Each milestone is built on its own branch, `milestone/<n>-<slug>`, opened from main by the first commit that adds the milestone to `ROADMAP.md`: its heading, its map or its first spec. Its features and tickets close on that branch. `/ae:close-milestone` merges it into main and tags the merge, so main holds closed milestones and fixes only.

### When a skill publishes a spec

Ask which milestone the feature belongs to when the conversation does not make it clear, and give it the next feature number in that milestone. Write the spec to `docs/work/<m>.<f>-<slug>/spec.md`, then add its `### Feature` heading and `Spec:` line under the milestone in `ROADMAP.md`.

### When a skill publishes tickets

Write each ticket to the feature's `issues/`, then add one numbered line per ticket under the feature in `ROADMAP.md`, in the same order: the file `issues/03-<slug>.md` is ticket `<m>.<f>.3`. A bare number in a ticket's `Blocked by:` is a ticket of the same feature; a ticket of another feature is named by its full address.

### When a skill closes work

A ticket is closed by `/ae:close-ticket <m>.<f>.<t>`: that is the way this tracker closes work.

### Bugs

A bug is fixed outside the triple: no spec, no ticket, no number. The fix is a commit on main whose subject starts `Fix:`, and ships with the next milestone or a patch. A bug that needs real work becomes a feature.
