# The repository made public

Status: ready-for-agent

Blocked by: 05.

Read first: `spec.md` (Carried from 15b.5).

## What to build

- The whole history checked for what must not be published: keys, `.env`, a Telegram owner id, a home's databases, personal paths. Anything found is reported to the user before any rewrite of history.
- The repository's visibility changed to public on the user's go: it is outward-facing and not undone by turning it back.
- The badges checked logged out: tests, coverage and release, the release blue for `v1.0.0`.

## Acceptance criteria

- [ ] The history check's findings, each fixed or declined in writing.
- [ ] The README, opened logged out on GitHub, has every badge, link and image rendering.
