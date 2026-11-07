# 02: The corpus cut and pinned

Status: ready-for-agent

**What to build:** a command fetches a curated list of pages, each pinned by revision id, and cuts them into chunks committed to the repo. Each chunk carries its title, section, language, licence and revision link. A manifest beside them holds the corpus version, and a NOTICE carries licences and attribution. Decided in [sources and licences](../../answer-from-sources/issues/01-sources-and-licences.md); the research is on branch `research/answer-sources`.

Spec: [16.1](../spec.md). Map: [answer from sources](../../answer-from-sources/map.md).

**Blocked by:** None (can start immediately).

- [ ] Sources: English and Italian Wikipedia pages on technique and prevention, free-exercise-db `instructions`, NLM-written MedlinePlus summaries
- [ ] No OpenStax, WHO, ExRx, NSCA, Mayo Clinic or A.D.A.M. text
- [ ] Every Wikipedia page is fetched at its pinned revision; a second fetch of the same list yields the same chunks
- [ ] The manifest names the corpus version and the pinned list
- [ ] The NOTICE names each source's licence and how to attribute it
- [ ] Vectors are not committed
