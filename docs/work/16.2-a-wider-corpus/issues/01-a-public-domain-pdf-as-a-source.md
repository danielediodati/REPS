# 01: A public-domain PDF as a source

Status: ready-for-agent

**What to build:** the manifest pins any PDF by URL and SHA-256, where today it knows only the Army publication, and `trainer corpus fetch` cuts the first one: the HHS *Physical Activity Guidelines for Americans*, 2nd edition, whose licence is stated on the publisher's page.

Source: [more corpus sources](../../../research/more-corpus-sources.md). Glossary: `CONTEXT.md` (*Corpus*, *Passage*). Retrieval: [ADR-0017](../../../adr/0017-retrieval-runs-on-the-laptop.md).

**Blocked by:** None (can start immediately).

- [ ] A PDF pinned in the manifest is fetched, checked against its SHA-256 and cut into chunks at paragraph and sentence ends
- [ ] A file whose hash differs from the pin stops the fetch and names both hashes
- [ ] The Army publication is cut through the same path and its chunks are unchanged
- [ ] Each HHS chunk carries its title, section, link, licence and author; front matter, references and tables are left out
- [ ] The notice lists the guidelines with the licence wording read in section 2 of the note
