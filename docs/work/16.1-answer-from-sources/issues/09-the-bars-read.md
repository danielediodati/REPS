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

- Two full readings, 2026-11-18, one rep each, nine `--only` blocks added up: snowflake-arctic-embed2 top 5 with the question also in English, entrance `deepseek/deepseek-v4-flash` high, judged by Haiku 4.5 at 1.00/1.00 on calibration set 2. The bars are now read on set 4 and corpus 2; three miss, so the work stops for the owner.

| Bar | Set 3, corpus 1 ($0.546) | Set 4, corpus 2 ($0.514) | Bar |
|---|---|---|---|
| Recall@5 | 41 of 61, 67% [55, 78]; MRR 0.49 | 47 of 62, 75% [64, 85]; MRR 0.58 | none |
| Verbatim and labelled | 42 of 67, 62% [51, 73] | 52 of 67, 77% [66, 86] | 100% |
| Covered answered | 58 of 61, 95% [87, 98] | 57 of 62, 91% [82, 97] | 90% |
| Faithful | 36 of 57, 63% [50, 74] | 34 of 57, 59% [47, 71] | 90% |
| Relevant | 53 of 57, 92% [83, 97] | 52 of 57, 91% [81, 96] | 85% |
| Not covered | 15 of 19, 78% [57, 91] | 15 of 18, 83% [61, 94] | 90% |
| Triage | 9 of 10, 90% [60, 98] | 10 of 10, 100% [72, 100] | 90% |
| Italian on English | 21 rows: recall 61%, faithful 13 of 18; MRR 0.42 | 20 rows: recall 70%, faithful 13 of 18; MRR 0.54 | none |

- Every quote is word for word in both readings; the verbatim misses are passages the row does not label.
- Set 4 labels 25 more passages that answer, and `ice-bath-minutes` is covered on English *Ice bath*.
- Passages retrieved for the 62 covered rows on corpus 2, by source: Wikipedia 224, wger 24, US Army 17, SEAL guide 12, HHS 11, Air Force 10, Europe PMC 9, MedlinePlus 3 (310 in all).
- p95 retrieval was 11 to 13 s with three blocks in parallel, against about 1.3 s in the ladder.
- The owner chose to tighten the entrance prompt, bars and set untouched. A screen of the 41 rows that missed on set 4 ($0.31, one rep), before the fix below: faithful 17 of 30 where most had failed; massage-gun and dead-bug-progression now *not covered*; turkish-get-up-steps still answers from a near passage; 7 covered rows now *not covered*, five of them with no labelled passage in the top 5.
- The screen found the cite check refusing quotes typed with `'` where the page has `’`: 8 rows of the set 4 pass lost cites to it (up to 11 in one run). A quote now matches whitespace and typographic quote marks aside, and the passage's own span is what is kept and shown.
