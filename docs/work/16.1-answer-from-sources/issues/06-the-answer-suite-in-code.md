# 06: The answer suite, in code

Status: ready-for-agent

**What to build:** `trainer eval --suite answer` on the shared suite runner. It checks in code every layer a model need not judge, reports each bar with its observed score and 95% interval, and has a retrieval-only mode at $0. Decided in [the bars](../../answer-from-sources/issues/08-the-bars.md) and [ADR-0018](../../../adr/0018-a-model-judges-only-what-code-cannot-read.md).

Spec: [16.1](../spec.md). Map: [answer from sources](../../answer-from-sources/map.md).

**Blocked by:** 04, 05.

- [ ] Recall@5 (bar 80%) and MRR (reported) on the covered rows; a hit is a retrieved chunk containing a labelled quote
- [ ] Verbatim quote at 100%; the quoted passage is one the row labels
- [ ] *Not covered* at least 90% on rows outside the corpus; at most 10% of covered rows answered *not covered*
- [ ] Triage boundary at least 90%
- [ ] Each bar reported with its 95% interval; the Italian-on-English rows reported apart, with no bar
- [ ] One rep per row
- [ ] A pass against a corpus other than the set's is refused as a state naming the mismatch
- [ ] The retrieval-only mode runs no chat model and reports Recall@5, MRR and p95 retrieval latency
- [ ] Every run is against a fixture named in `TRAINER_DB`; paid passes are asked for first with their estimate
- [ ] A snapshot of the report beside the other suites'
