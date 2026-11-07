# Map: answer from sources

## Destination

Decisions enough to run `/to-spec` on this outcome: the entrance answers questions on technique and injury prevention from a corpus of openly licensed texts, cites the passage it used, and says so when the corpus does not cover the question. An eval measures retrieval, faithfulness and refusal.

## Notes

- **Why a RAG**: ADR-0006 item 4 already bars the entrance from stating a training fact no tool gave it. Retrieval is the tool that makes a technique answer legal, with its source.
- **Roadmap**: milestone 16, before 17. Exercise photos, the old 16, are parked under *Later*.
- **Who reads the corpus**: the entrance only. The planner is unchanged.
- **The boundary**: technique and general prevention, never a diagnosis. A current pain goes to triage as today.
- **The eval, in three layers**, with the RAGAS library for the judged ones:
  - retrieval: Recall@5 and MRR, in code, $0;
  - faithfulness and answer relevance: an LLM judge through OpenRouter (ADR-0015), the cheapest that clears its bar (ADR-0011), calibrated on a sample the owner reads;
  - negative rejection: rows outside the corpus.
- **Techniques earn their place**: start from the simplest retrieval; hybrid search, a reranker or query rewriting go in only if they raise a metric.
- **Costs**: anything that spends credits is asked for first, with an estimate. Measurements run against a fixture named in `TRAINER_DB`.
- **Skills**: `/grilling` and `/domain-modeling` for grilling tickets, `/research` for research tickets, `/prototype` for prototype tickets.

## Decisions so far

- [Sources and licences](issues/01-sources-and-licences.md): English and Italian Wikipedia pinned by revision, free-exercise-db and MedlinePlus as support; OpenStax and WHO out (NonCommercial); chunks committed with a NOTICE, vectors not.

- [Italian questions, English texts](issues/02-italian-questions-english-texts.md): `bge-m3` first, on Ollama or OpenRouter alike; `qwen3-embedding:0.6b` and `snowflake-arctic-embed2` as challengers; query translation as fallback, never the corpus.

- [Where retrieval runs](issues/03-where-retrieval-runs.md): embeddings on the owner's Ollama, the index in a Qdrant server the owner starts, storage in `~/.reps/qdrant/`; ADR-0017 amends ADR-0015; what is missing or down is a state, never a crash.

- [How a citation looks](issues/04-how-a-citation-looks.md): a short answer, then the passage quoted verbatim in an expandable blockquote under a `«Title» § Section` link to the pinned revision; a two-line refusal; replies move to MarkdownV2.

- [The eval set](issues/05-the-eval-set.md): about 90 rows (60 covered, 20 not covered, 10 on the triage boundary), 80% Italian; the agent drafts in other words than the passage, the owner reads the doubtful rows and a random fifth; passages labelled by verbatim quote, not chunk; frozen and versioned against a named corpus version.

- [The judge](issues/07-the-judge.md): a model judges only faithfulness and relevance, code the rest (ADR-0018); gpt-oss-120b, a Qwen, Haiku in that order, never the answering model's family; calibrated on 30 real replies the owner reads plus 15 planted errors, bar 13/15 and 27/30.

## Not yet specified

Nothing: what remains is ticketed.

## Out of scope

- **Diagnosis**: a pain is triage's, and its outcome is an exclusion.
- **The planner reading the corpus**: it keeps its calibrated eval.
- **Exercise photos**: parked.
- [What changes for 17](issues/06-what-changes-for-17.md): milestone 17's to decide when it runs, after 16; its map carries the note.
