# 06: Corpus version 2, measured

Status: ready-for-agent

**What to build:** the sources of 01 to 05 become corpus version 2 through the refresh, the eval set is settled against it, and one pass shows what the wider corpus moved against the version 1 reading.

Source: [more corpus sources](../../../research/more-corpus-sources.md). Glossary: `CONTEXT.md` (*Corpus*, *Passage*). Retrieval: [ADR-0017](../../../adr/0017-retrieval-runs-on-the-laptop.md). The refresh is [16.1.10](../../16.1-answer-from-sources/issues/10-the-corpus-refreshed.md); the version 1 reading is [16.1.9](../../16.1-answer-from-sources/issues/09-the-bars-read.md). Nothing that spends credits runs without the owner's approval (`AGENTS.md`).

**Blocked by:** 01, 02, 03, 04, 05, 16.1.9, 16.1.10.

- [ ] The refresh cuts corpus version 2 from the manifest and the notice names it
- [ ] Rows that lost their quote, and `near` rows that now find a passage, are listed for the owner to relabel
- [ ] Once they are settled the set's version bumps and names corpus version 2
- [ ] The pass is asked for first, with its estimated cost, and run only once approved
- [ ] The report sets every bar beside its version 1 reading, and counts the retrieved passages by source
