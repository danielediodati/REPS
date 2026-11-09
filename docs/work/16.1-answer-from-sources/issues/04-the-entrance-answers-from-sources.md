# 04: The entrance answers from sources

Status: ready-for-agent

**What to build:** the entrance gets a retrieval tool on the shared tool surface. Asked how to do an exercise or how to prevent an injury, it answers briefly from what the tool returned. Under the answer, each passage it uses is quoted verbatim in an expandable blockquote, in its source's language, under a `Wikipedia (en), «Title» § Section` text link to the pinned revision. When nothing fits, it gives the two-line *not covered* reply. A current pain still goes to triage. Decided in [how a citation looks](../../answer-from-sources/issues/04-how-a-citation-looks.md); the prototype is on branch `prototype/citation-looks`.

Spec: [16.1](../spec.md). Map: [answer from sources](../../answer-from-sources/map.md).

**Blocked by:** 03.

**Constraint from 01:** `say` escapes the whole line, so a cited reply carries its own markup only through `offer` (text already marked, as `proposal` writes it), never through `say`.

- [ ] A technique question calls the tool, and the reply quotes a returned passage verbatim with its link; the raw URL never shows
- [ ] The answer is about 150-250 characters
- [ ] General prevention is answered and cited, never sent to triage
- [ ] Nothing fitting yields *not covered*: two lines, no source, what the corpus covers
- [ ] A current pain alone goes to triage, with no answer and no source
- [ ] Technique plus a current pain: the technique answered and cited, the pain sent to triage in its own sentence
- [ ] Sources unavailable mid-session: the tool says so, the entrance says it cannot answer from sources, and the conversation goes on
- [ ] A chunk with no section (a page's lead, a wger description) is cited by its title alone, with no `§`; the source name in the link is read from the chunk, not only Wikipedia's
- [ ] The planner is unchanged
- [ ] Tested on the entrance graph with a scripted model and the in-memory corpus, and on the bot's rendering
