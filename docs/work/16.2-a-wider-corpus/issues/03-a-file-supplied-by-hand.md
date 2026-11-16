# 03: A file supplied by hand

Status: ready-for-agent

**What to build:** a source whose publisher refuses scripts is read from a local folder the owner fills, checked by its hash; the first is the Air Force's *Warfighter's Fitness Playbook 2.0* (Feb 2026).

Source: [more corpus sources](../../../research/more-corpus-sources.md). Glossary: `CONTEXT.md` (*Corpus*, *Passage*). Retrieval: [ADR-0017](../../../adr/0017-retrieval-runs-on-the-laptop.md). The file, its hash and its contents are in section 6 of the note. A missing precondition is reported as a state (`AGENTS.md`).

**Blocked by:** 01.

- [ ] A pin marked as supplied by hand is read from the local folder and never requested from the network
- [ ] With the file absent, the fetch reports it as a state: which file, where to put it, where it is published
- [ ] A file with the wrong hash is refused as in 01
- [ ] The playbook's chunks read as clean prose: no page header, appendix label or stray step number inside a sentence
- [ ] Each entry of the exercise library is a passage under the exercise's own name
- [ ] The notice says the playbook is a US government work by authorship, inferred, and that only its text was taken
