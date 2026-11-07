# The bars

Type: grilling
Status: resolved
Blocked by: 07

## Question

What must each layer clear for the first version to ship: Recall@5 and MRR on the covered rows, faithfulness and answer relevance as the judge reads them, the *not covered* reply on the 20 rows outside the corpus, and the triage-boundary rows? Is a bar read on the observed score or on an interval, as milestone 17 does, and is the Italian-question-on-English-passage half reported apart? See [the eval set](05-the-eval-set.md).

## Answer

Grilled 2026-11-07.

| Layer | Bar | Checked by |
|---|---|---|
| Retrieval | Recall@5 at least 80% on the 60 covered rows; MRR reported, no bar | code |
| Verbatim quote | 100%: a quote not found in a retrieved chunk is a bug (ADR-0010) | code |
| Faithfulness | at least 90% of covered rows | judge |
| Answer relevance | at least 85% of covered rows | judge |
| *Not covered* on the 20 rows outside the corpus | at least 90% | code |
| Covered rows answered *not covered* by mistake | at most 10% | code |
| Triage boundary, 10 rows | at least 90% | code |

- The judge's score becomes a yes or no at a threshold fixed during calibration, on the owner's 30 readings.
- A bar is read on the observed score, with the 95% interval reported beside it. Intervals become the rule in [the ladder](09-the-retrieval-ladder.md), where one rung is compared with another.
- The Italian-question-on-English-passage rows (about 24) are reported apart, with no bar of their own. A large lag is the signal for the query-translation rung.
- One rep per row, on screens and full passes alike. Three reps only if two identical passes swing across a bar.
