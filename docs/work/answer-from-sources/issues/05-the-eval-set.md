# The eval set

Type: grilling
Status: resolved
Blocked by: 01

## Question

How many questions, who drafts them and who reads them, how the passages that answer each are labelled, how many rows fall outside the corpus, and which rows probe the boundary with triage. How does the set freeze and version, as the suites of milestone 17 do?

## Answer

**About 90 rows**

| Kind | Rows | Expected |
|---|---|---|
| Covered by the corpus | 60 | an answer quoting a labelled passage |
| Not covered: on topic, or near a covered one | 16 | the *not covered* reply |
| Not covered: off topic | 4 | the *not covered* reply |
| Current pain alone | 3 | triage, no answer, no source |
| Technique plus a current pain | 4 | the technique answered and cited, the pain to triage in its own sentence |
| General prevention | 3 | answered and cited, never triage |

- **Language**: about 80% Italian, 20% English. Half the Italian covered rows have their passage only in an English text, to measure the gap decided in [Italian questions, English texts](02-italian-questions-english-texts.md).

**Who writes and reads them**

- The agent drafts every row with no model run, in the owner's voice, in words other than the passage's (*"non voglio ingobbirmi"*, not *"colonna neutra"*), so retrieval is not handed the answer.
- The owner reads the rows the agent flags as doubtful, plus a fifth of the rest drawn at random. More than one wrong among the random ones draws another fifth. A row that leaves the owner in doubt is dropped.

**How a passage is labelled**

- By its title, revision, section and a verbatim quote, never by a chunk id. A retrieved chunk counts as a hit when it contains the quote, however the corpus is cut.
- A row may label several passages; one hit is enough.

**Freezing and versioning**

- As in milestone 17: frozen before any model runs, versioned, and every pass's record names the version. A row is corrected afterwards only where it misstates a fact about the corpus.
- The set names the corpus version it was labelled on. A pass against another corpus is refused as a state, naming the mismatch. What happens when the corpus is refreshed stays with *The corpus over time*.

Glossary: *corpus*, *passage* and *not covered* added to `CONTEXT.md`.
