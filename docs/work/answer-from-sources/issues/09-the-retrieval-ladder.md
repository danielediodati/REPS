# The retrieval ladder

Type: grilling
Blocked by: 08

## Question

The first version is the simplest retrieval: `bge-m3` dense search, top 5, no rewriting ([Italian questions, English texts](02-italian-questions-english-texts.md), [Where retrieval runs](03-where-retrieval-runs.md)). If it misses a bar, which techniques are climbed, in what order, and when does climbing stop: hybrid search, a reranker, query translation, chunk size? What does each rung cost in latency on the laptop, and which metric must it raise to stay?
