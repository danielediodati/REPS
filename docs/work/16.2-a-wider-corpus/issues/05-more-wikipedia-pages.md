# 05: More Wikipedia pages

Status: ready-for-agent

**What to build:** the pinned list grows by the English and Italian Wikipedia pages that answer what the eval set marks as nearly covered: named accessory exercises (gap G3) and technique in Italian (gap G2).

Source: [more corpus sources](../../../research/more-corpus-sources.md). Glossary: `CONTEXT.md` (*Corpus*, *Passage*). Retrieval: [ADR-0017](../../../adr/0017-retrieval-runs-on-the-laptop.md). The gaps and the rows that show them are in section 1 of the note.

**Blocked by:** None (can start immediately).

- [ ] Every `near` row of the eval set is checked for an English and an Italian page that answers it; a page that exists is pinned by revision
- [ ] Every English technique page already pinned is checked for its Italian counterpart; one that exists and holds technique text is pinned
- [ ] A page that is a stub, a disambiguation or off topic is not pinned
- [ ] The rows still without a page are listed for the owner, by gap
