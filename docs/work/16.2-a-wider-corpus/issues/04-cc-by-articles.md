# 04: CC BY articles

Status: ready-for-agent

**What to build:** open-access articles enter the corpus pinned by identifier, fetched through Europe PMC, and only while their own licence reads CC BY or CC0; the first are the nine in section 2 of the note whose licence was read on the publisher's page.

Source: [more corpus sources](../../../research/more-corpus-sources.md). Glossary: `CONTEXT.md` (*Corpus*, *Passage*). Retrieval: [ADR-0017](../../../adr/0017-retrieval-runs-on-the-laptop.md). The fetch route PMC allows and the licence rules are in section 2 of the note.

**Blocked by:** None (can start immediately).

- [ ] An article pinned in the manifest is fetched as full text and cut into chunks, each naming its article section
- [ ] The licence is read from the article at every fetch; anything but CC BY or CC0 (NC, ND, missing) stops the fetch and names the article
- [ ] References, tables, figures, acknowledgements and supplementary sections are left out
- [ ] Each chunk carries the article's title, authors, DOI link and licence, and the notice lists every article with them
- [ ] The two articles whose licence rests only on Europe PMC's field are not pinned
