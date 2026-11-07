# 05: The eval set frozen

Status: ready-for-agent

**What to build:** the `answer` suite's set, about 90 rows, drafted by the agent with no model run, read in part by the owner, then frozen and versioned against the corpus version it was labelled on. Decided in [the eval set](../../answer-from-sources/issues/05-the-eval-set.md).

Spec: [16.1](../spec.md). Map: [answer from sources](../../answer-from-sources/map.md).

**Blocked by:** 02.

- [ ] Rows: 60 covered, 16 not covered on or near a topic, 4 off topic, 3 pain alone, 4 technique plus pain, 3 general prevention
- [ ] About 80% Italian; half the Italian covered rows have their passage only in English
- [ ] Written in the owner's voice, in words other than the passage's
- [ ] Each covered row labels one or more passages by title, revision, section and verbatim quote, never a chunk id; every quote is checked present in the corpus
- [ ] The owner reads the rows flagged doubtful plus a random fifth of the rest; more than one wrong draws another fifth; a doubtful row is dropped
- [ ] The set declares its bars ([the bars](../../answer-from-sources/issues/08-the-bars.md)), its version and its corpus version
