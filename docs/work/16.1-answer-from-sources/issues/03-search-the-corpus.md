# 03: Search the corpus, and its states

Status: ready-for-agent

**What to build:** `trainer corpus build` embeds the committed chunks with `bge-m3` on the owner's Ollama into a Qdrant server whose storage is under the home directory, at $0. The corpus has one interface: a question in, the top passages out with their metadata. Its backends are Qdrant with Ollama in production and an in-memory index in tests. What is missing is a state naming its fix, at the command and at the bot's start check. Decided in [where retrieval runs](../../answer-from-sources/issues/03-where-retrieval-runs.md) and [ADR-0017](../../../adr/0017-retrieval-runs-on-the-laptop.md).

Spec: [16.1](../spec.md). Map: [answer from sources](../../answer-from-sources/map.md).

**Blocked by:** 02.

- [ ] Build embeds every chunk and records the corpus version it built
- [ ] Search returns the top 5 passages with title, section, language and revision link
- [ ] Ollama down, the model not pulled, Qdrant down and the corpus not built (or built at another version) are each a state naming its fix
- [ ] The bot starts with retrieval not ready and names what is missing, as it does for the provider
- [ ] Tests use the in-memory backend; none reaches Ollama or Qdrant
