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

## Comments

- Owner's decision, 2026-11-16: the sources of 01 to 05 enter the committed corpus as each ticket closes, under version 1. The version 1 reading this ticket compares against is therefore whatever 16.1.9 reads on the corpus as it stands then; a reading of the original 3868 chunks needs the corpus at `25d8247`.
- The index is built per corpus version: after a ticket adds chunks under version 1, run `trainer corpus build` again before a pass.
- `near` rows whose topic gained a text in 01 to 05, to look at first when relabelling: `ice-bath-minutes` (English *Ice bath*), `monster-walk` and `dead-bug-progression` (the Air Force playbook's library entries *Mini-band Monster Walk* and *Deadbug*, execution only), `massage-gun` (the foam rolling meta-analysis, on the roller alone).
- The corpus grew from 3868 to 4750 chunks under version 1: HHS 157, SEAL guide 101, Air Force playbook 116, Europe PMC articles 331, six more Wikipedia pages 177.
- The refresh is `trainer corpus refresh` (16.1.10): it bumps the version and lists only the rows that lost their quote. Listing `near` rows that now find a passage is this ticket's to add. `trainer corpus settle` then bumps the set onto the new corpus, refused while a row is lost.
