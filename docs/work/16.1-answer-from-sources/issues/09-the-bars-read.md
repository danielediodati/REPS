# 09: The bars read

Status: ready-for-agent

**What to build:** the calibrated judge scores the full pass, and every bar of the `answer` suite is read together: the milestone's demo. Decided in [the bars](../../answer-from-sources/issues/08-the-bars.md).

Spec: [16.1](../spec.md). Map: [answer from sources](../../answer-from-sources/map.md).

**Blocked by:** 08.

**Constraint from 06:** the suite's bars are `Answer.halves` in `answer_evaluation.py`: recall, verbatim (a quote word for word in a retrieved passage, and from a passage the row labels), not covered, covered answered (the *wrongly not covered* bar held as its complement), and triage over the ten boundary rows (`pain`, `technique_pain` and `prevention`). `faithful` and `relevant` are declared in the set and not yet scored: they join there. The report's header names the set and corpus versions and the embedder; the judge's version is still to add.

**Constraint from 08:** the judge is `models.JUDGE` (`anthropic/claude-haiku-4.5`) through `answer_judge.Judge`, its yes or no at `answer_judge.THRESHOLDS` (both 1.0), fitted on calibration set `FITTED_ON` 2; the judge's version is that pair. About $0.003 a reply. On the first full pass 14 of the 30 real replies read faithful (calibration set 2): the misses are claims a little beyond the passage ("never", "only"), so the entrance prompt may need tightening before this bar can hold. Off-topic rows were refused in the bot's own words, not with the *not covered* reply (`novel-author` answered).

- [ ] Faithful at least 90% and relevant at least 85% of covered rows, as the judge reads them
- [ ] The report shows every bar, code and judge alike, with its interval, and the Italian-on-English rows apart
- [ ] Three reps only if two identical passes swing across a bar
- [ ] The pass's record names the set, corpus and judge versions and its cost
- [ ] A bar missed stops the work with the numbers for the owner; bars and set untouched
