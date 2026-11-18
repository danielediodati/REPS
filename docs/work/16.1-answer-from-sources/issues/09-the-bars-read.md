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

## Comments

- The first full reading, 2026-11-18: answer set 3 on corpus version 1 (4750 chunks, index rebuilt), snowflake-arctic-embed2 top 5 with the question also in English, entrance `deepseek/deepseek-v4-flash` high, judged by Haiku 4.5 at 1.00/1.00 on calibration set 2. One rep, nine `--only` blocks added up; $0.546 in all. Three bars missed, so the work stops for the owner.

| Bar | Read | Bar | |
|---|---|---|---|
| Recall@5 | 41 of 61, 67% [55%, 78%]; MRR 0.49 | none | |
| Verbatim and labelled | 42 of 67, 62% [51%, 73%] | 100% | missed |
| Covered answered | 58 of 61, 95% [87%, 98%] | 90% | held |
| Faithful | 36 of 57, 63% [50%, 74%] | 90% | missed |
| Relevant | 53 of 57, 92% [83%, 97%] | 85% | held |
| Not covered | 15 of 19, 78% [57%, 91%] | 90% | missed |
| Triage | 9 of 10, 90% [60%, 98%] | 90% | held |
| Italian on English, 21 rows | recall 61%, answered 90%, faithful 13 of 18, relevant 17 of 18; MRR 0.42 | none | |

- Every quote was word for word: all 25 quote failures are passages the row does not label, none invented.
- Two of the four outside rows answered, `massage-gun` and `ice-bath-minutes`, are `near` rows 16.2.6 already names as gaining a text from 16.2's sources.
- p95 retrieval reached 13 s in the first block, against about 1.3 s in the ladder.
