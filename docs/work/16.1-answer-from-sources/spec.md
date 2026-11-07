# Feature 16.1 - Answer from sources

Status: ready-for-agent

Decided in [the map](../answer-from-sources/map.md); each decision's detail lives in its ticket there.

## Problem Statement

The owner asks the bot how to perform an exercise or how to avoid getting hurt, and the entrance cannot answer: ADR-0006 bars it from stating a training fact no tool gave it, and no tool holds technique or prevention. The question is either deflected or answered from the model's memory, with no source and nothing to check it against. Nobody knows how often such an answer would be right, faithful to a text, or honest about what it does not know.

## Solution

The entrance gets a tool that searches a corpus of openly licensed texts (English and Italian Wikipedia pinned by revision, free-exercise-db's instructions, MedlinePlus). It answers briefly, quotes the passage it stands on verbatim under a link to the pinned revision, and replies *not covered* when the corpus does not hold the answer. A current pain still goes to triage. Embeddings run on the owner's Ollama and the index in a Qdrant server the owner starts (ADR-0017); either missing is a state, never a crash.

A frozen eval set of about 90 rows measures three layers: retrieval in code, faithfulness and relevance by a calibrated judge (ADR-0018), and *not covered* and triage in code.

| Bar | Value |
|---|---|
| Recall@5, covered rows | at least 80%; MRR reported |
| Verbatim quote | 100% |
| Faithful | at least 90% of covered rows |
| Relevant | at least 85% of covered rows |
| *Not covered*, rows outside the corpus | at least 90% |
| Covered rows answered *not covered* | at most 10% |
| Triage boundary | at least 90% |

Bars are read on the observed score, the 95% interval beside it. Retrieval starts as the simplest that could work (`bge-m3`, dense, top 5) and climbs the ladder only while a retrieval bar misses.

## User Stories

1. As the owner, I want to ask the bot how to do an exercise and get a short answer from a text, so that technique advice stands on something I can read.
2. As the owner, I want to ask how to avoid an injury in general and get a cited answer, never triage, so that prevention is not mistaken for a symptom.
3. As the owner, I want the answer to come first, in about 150-250 characters, so that the reply reads in a glance.
4. As the owner, I want each passage the answer uses quoted verbatim in an expandable blockquote, so that I can check the claim without leaving the chat.
5. As the owner, I want a passage quoted in its source's language, an English passage staying English, so that the quote is the text and not a translation of it.
6. As the owner, I want under each quote a link named `Wikipedia (en), «Title» § Section` pointing at the pinned revision, never a raw URL, so that the source is one tap away and the chat stays clean.
7. As the owner, I want a two-line *not covered* reply with no source when the corpus does not hold the answer, saying what the corpus does cover, so that the bot never invents.
8. As the owner, I want a message mentioning a current pain alone to go to triage with no answer and no source, so that a symptom is never handled as a technique question.
9. As the owner, I want a message mixing technique and a current pain answered and cited on the technique, with the pain sent to triage in its own sentence, so that neither half is lost.
10. As the owner, I want to ask in Italian about a passage that exists only in English and still get it, so that the corpus's language does not limit my questions.
11. As the owner, I want entrance replies rendered in MarkdownV2 with everything escaped, so that a quote's dots and hyphens never break a message.
12. As the owner, I want the corpus's chunks committed with a NOTICE carrying their licences and attribution, so that the public repo honours CC BY-SA.
13. As the owner, I want OpenStax, WHO and copyrighted sites kept out of the corpus, so that nothing NonCommercial or unlicensed is redistributed.
14. As the owner, I want every page pinned by revision id, so that the corpus and the eval do not move under me.
15. As the owner, I want each chunk to carry its title, section, language and revision link, so that any retrieved chunk can be cited without looking it up again.
16. As the owner, I want the corpus to carry a version in a manifest beside its chunks, so that a pass and a set can name what they were made on.
17. As the owner, I want a command that embeds the committed chunks into Qdrant at $0, so that a new machine rebuilds the index from the repo.
18. As the owner, I want the vectors never committed, so that changing the embedding model is a rebuild, not a migration.
19. As the owner, I want the bot to check Ollama, the embedding model, Qdrant and the built corpus at start and name what is missing with its fix, so that a missing piece is a state and not a crash.
20. As the owner, I want the bot to start anyway when retrieval is not ready, so that everything else keeps working.
21. As the owner, I want a server that goes down mid-session to make the tool answer that the sources are unavailable, and the entrance to say it cannot answer from sources, so that the conversation goes on.
22. As the owner, I want the corpus refreshed only by hand, with a command that bumps its version, so that nothing changes on its own.
23. As the owner, I want a refresh to check every labelled quote against the new corpus and list the rows that lost theirs, so that I relabel or drop only those.
24. As the owner, I want rows that still find their quote carried over unchanged and the set's version bumped to name the new corpus, so that the set follows the corpus without being redrawn.
25. As the owner, I want a pass against a corpus other than the one the set names refused as a state, naming the mismatch, so that scores are never read across versions.
26. As the owner, I want about 90 frozen rows (60 covered, 16 not covered on or near a topic, 4 off topic, 3 pain alone, 4 technique plus pain, 3 general prevention), about 80% Italian, so that every behaviour has rows.
27. As the owner, I want half the Italian covered rows to have their passage only in English, so that the language gap is measured.
28. As the owner, I want the agent to draft every row in my voice, in words other than the passage's, without running a model, so that retrieval is not handed the answer.
29. As the owner, I want to read the rows the agent flags as doubtful plus a random fifth of the rest, another fifth drawn when more than one is wrong, and a doubtful row dropped, so that the set holds without my reading all of it.
30. As the owner, I want a passage labelled by title, revision, section and verbatim quote, never by chunk id, with one hit among several labels enough, so that re-cutting the corpus does not relabel the set.
31. As the owner, I want the set frozen and versioned before any model runs, corrected only where it misstates a fact about the corpus, and every pass record naming its version, so that every configuration is scored on the same rows.
32. As the owner, I want Recall@5 and MRR computed in code at $0, so that retrieval can be measured as often as needed.
33. As the owner, I want a quote not found verbatim in a retrieved chunk failed by code at 100%, so that an invented citation is a bug.
34. As the owner, I want code to check that the quoted passage is one the row labels, that rows outside the corpus get *not covered*, and that pain rows go to triage, so that only what code cannot read reaches a model.
35. As the owner, I want faithfulness and relevance judged through RAGAS by the cheapest model that clears the judge's bar, never of the answering model's family, so that the judgement is both cheap and independent.
36. As the owner, I want the judge calibrated on 45 frozen replies, 30 real ones I label faithful and answers, and 15 the agent plants with an unsupported claim or an answer to another question, so that the judge is measured before it measures.
37. As the owner, I want the judge to clear 13 of 15 planted and 27 of 30 real, candidates tried in the order gpt-oss-120b, a mid-size Qwen, Haiku 4.5, stopping at the first that clears, so that the cheapest adequate judge is chosen.
38. As the owner, I want the work to stop if no candidate clears, with the bar and the set untouched and no fourth model tried unasked, so that I decide with the numbers.
39. As the owner, I want the judge's score turned into yes or no at a threshold fixed during calibration, so that the bars count rows.
40. As the owner, I want the judge recalibrated only when its model or prompt changes, so that calibration is paid once.
41. As the owner, I want every bar reported with its observed score and 95% interval, so that I see how firm a pass is.
42. As the owner, I want the Italian-on-English rows reported apart with no bar of their own, so that a lag shows without deciding on 24 rows.
43. As the owner, I want one rep per row, three only if two identical passes swing across a bar, so that passes stay cheap.
44. As the owner, I want every paid pass, judge calibration included, asked for first with its estimate, and run against a fixture named in `TRAINER_DB`, so that credits are spent only when I agree.
45. As the owner, I want `bge-m3`, `qwen3-embedding:0.6b` and `snowflake-arctic-embed2` always compared on retrieval at $0, the highest Recall@5 winning and MRR breaking a tie, so that the embedder is a measured choice.
46. As the owner, I want rungs climbed only while a retrieval bar misses, in the order query translation (only if the Italian-on-English rows lag far behind), hybrid search, chunk size, reranker, so that no technique enters without a metric asking for it.
47. As the owner, I want a rung kept only when it raises the missing metric by at least 3 of 60 rows, drops no other bar and keeps retrieval within 2 s at p95 on the laptop, the paired difference reported with its interval, so that each technique earns its place.
48. As the owner, I want climbing to stop at the first configuration that clears every retrieval bar, or to stop and leave the choice to me when the rungs run out, so that the ladder never grows unasked.
49. As the owner, I want answers and the judge rerun only once, on the final retrieval configuration, so that the ladder costs nothing but the translation rung.
50. As a portfolio reader, I want the bars, the judge's calibration and the ladder's numbers recorded, so that the RAG's quality is inspectable rather than claimed.

## Implementation Decisions

- **The corpus**: a new module, one interface over building, versioning, searching and checking quotes. It holds chunks with title, section, language, licence and revision link, plus a manifest carrying the corpus version. Search takes a question and returns the top passages with their metadata. Its backends are Qdrant with Ollama embeddings in production, and an in-memory index in tests. Unavailability (Ollama down, model not pulled, Qdrant down, corpus not built) is a typed state naming its fix.
- **Commands**: one to fetch the pinned revisions and cut them into committed chunks (also the refresh, which bumps the version and rechecks the set's quotes); one to embed the committed chunks into Qdrant. Storage lives under the home directory (`qdrant/`).
- **The entrance**: gains a retrieval tool on the shared tool surface, like its other reads. Its prompt asks it to answer only from what the tool returned, to quote verbatim, to reply *not covered* when nothing fits, and to keep a current pain for triage as today. The planner is unchanged.
- **The reply**: the entrance returns the answer and the passages it quotes as structured data; the bot renders them in MarkdownV2 (short answer, expandable blockquote per passage, a text link per source). Every entrance reply moves to MarkdownV2 with everything escaped.
- **The bot's start check**: extended with the corpus's states, reported like the provider's, the bot still starting.
- **Eval**: a new suite, `answer`, on the shared suite runner. Its set lives beside the other suites' sets and declares its bars, its version and the corpus version it was labelled on. Retrieval metrics, verbatim quote, labelled passage, *not covered* and triage are checked in code; faithfulness and relevance go to the judge.
- **The judge**: a node in the model roster, chosen per ADR-0011 within ADR-0018. Calibration is its own pass over the 45 frozen replies, with its own bars, versioned with the set.
- **The ladder**: retrieval-only passes at $0 compare embedders and rungs, reporting Recall@5, MRR, the paired difference with its interval, and p95 retrieval latency.
- ADR-0006, ADR-0010, ADR-0011, ADR-0015 as amended by ADR-0017, and ADR-0018 hold throughout.

## Testing Decisions

- A good test drives behaviour through a public seam and asserts what the owner or the suite would see, never internals.
- **The entrance graph**, with a scripted model and the in-memory corpus (prior art: `test_entrance`): a technique question calls the tool and the reply quotes a returned passage; nothing fitting yields *not covered*; pain alone goes to triage; technique plus pain does both; sources unavailable yields the stated reply.
- **The corpus**, against its in-memory backend: build, version, search returning metadata, the quote check, each unavailable state naming its fix, a refresh listing lost quotes.
- **The bot's rendering** (prior art: `test_bot`): the blockquote, the named link, escaping, the two-line *not covered*, the start check's states.
- **The `answer` suite** (prior art: `test_eval_suites` and the snapshots in `tests/eval_suites/`): bars, intervals, the Italian-on-English half apart, the corpus-version mismatch refused as a state, a missing bar refused.
- Expected schema and set versions are derived from the data, never hardcoded.
- No test reaches a paid model, Ollama or Qdrant.

## Out of Scope

- Diagnosis: a pain is triage's, its outcome an exclusion.
- The planner reading the corpus.
- Exercise photos (parked).
- What milestone 17 changes because of this tool: its map carries the note.
- Translating the corpus.
- A refresh on a schedule.

## Further Notes

- Sources, embeddings and stores were researched on the branches `research/answer-sources`, `research/answer-embeddings` and `research/vector-stores`; the citation prototype is on `prototype/citation-looks`.
- Every measurement runs against a fixture named in `TRAINER_DB`.
