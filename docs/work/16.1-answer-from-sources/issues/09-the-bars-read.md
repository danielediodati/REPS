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

| Bar | Set 3, corpus 1 ($0.546) | Set 4, corpus 2 ($0.514) | Set 4, tight prompt ($0.510) | Bar |
|---|---|---|---|---|
| Recall@5 | 41 of 61, 67% [55, 78]; MRR 0.49 | 47 of 62, 75% [64, 85]; MRR 0.58 | 47 of 62, 75% [64, 85]; MRR about 0.57 | none |
| Verbatim and labelled | 42 of 67, 62% [51, 73] | 52 of 67, 77% [66, 86] | 50 of 65, 76% [65, 85] | 100% |
| Covered answered | 58 of 61, 95% [87, 98] | 57 of 62, 91% [82, 97] | 57 of 62, 91% [82, 97] | 90% |
| Faithful | 36 of 57, 63% [50, 74] | 34 of 57, 59% [47, 71] | 31 of 56, 55% [42, 68] | 90% |
| Relevant | 53 of 57, 92% [83, 97] | 52 of 57, 91% [81, 96] | 54 of 56, 96% [88, 99] | 85% |
| Not covered | 15 of 19, 78% [57, 91] | 15 of 18, 83% [61, 94] | 16 of 18, 88% [67, 97] | 90% |
| Triage | 9 of 10, 90% [60, 98] | 10 of 10, 100% [72, 100] | 10 of 10, 100% [72, 100] | 90% |
| Italian on English | 21 rows: recall 61%, faithful 13 of 18; MRR 0.42 | 20 rows: recall 70%, faithful 13 of 18; MRR 0.54 | 20 rows: recall 70%, faithful 11 of 17 | none |

- Every quote is word for word in both readings; the verbatim misses are passages the row does not label.
- Set 4 labels 25 more passages that answer, and `ice-bath-minutes` is covered on English *Ice bath*.
- Passages retrieved for the 62 covered rows on corpus 2, by source: Wikipedia 224, wger 24, US Army 17, SEAL guide 12, HHS 11, Air Force 10, Europe PMC 9, MedlinePlus 3 (310 in all).
- p95 retrieval was 11 to 13 s with three blocks in parallel, against about 1.3 s in the ladder.
- The owner chose to tighten the entrance prompt, bars and set untouched. A screen of the 41 rows that missed on set 4 ($0.31, one rep), before the fix below: faithful 17 of 30 where most had failed; massage-gun and dead-bug-progression now *not covered*; turkish-get-up-steps still answers from a near passage; 7 covered rows now *not covered*, five of them with no labelled passage in the top 5.
- The screen found the cite check refusing quotes typed with `'` where the page has `’`: 8 rows of the set 4 pass lost cites to it (up to 11 in one run). A quote now matches whitespace and typographic quote marks aside, and the passage's own span is what is kept and shown.
- The third reading, tight prompt and the quote-mark fix, 2026-11-18, nine blocks, one rep: faithful does not move (55%, against 59%), not covered misses by one row (16 of 18), verbatim-and-labelled holds at 76%. The work stops for the owner again; the ticket spent $0.82 of the $0.85 agreed.
- Of the 25 unfaithful replies, 15 fail on one statement (0.67 to 0.88), often a paraphrase the passage carries (`belt-what-for`: "exercises where the lower back gets a heavy load"), and the judge counts the *not covered* lines as claims (`hook-grip-small-hands`). At threshold 1.00 one such statement fails the row.
- The owner named the model as the problem. `openai/gpt-6-luna`, default effort, OpenAI, on the same prompt, 2026-11-18: a screen of the 41 rows deepseek missed ($0.10), then a full pass, nine blocks, one rep ($0.17). The ticket has spent $1.09.

| Bar | deepseek-v4-flash high | gpt-6-luna | Bar |
|---|---|---|---|
| Recall@5 | 47 of 62, 75% [64, 85] | 47 of 62, 76% [64, 85] | none |
| Verbatim and labelled | 50 of 65, 76% [65, 85] | 53 of 60, 88% [78, 94] | 100% |
| Covered answered | 57 of 62, 91% [82, 97] | 52 of 62, 84% [73, 91] | 90% |
| Faithful | 31 of 56, 55% [42, 68] | 42 of 52, 81% [68, 89] | 90% |
| Relevant | 54 of 56, 96% [88, 99] | 49 of 52, 94% [84, 98] | 85% |
| Not covered | 16 of 18, 88% [67, 97] | 17 of 18, 94% [74, 99] | 90% |
| Triage | 10 of 10, 100% [72, 100] | 10 of 10, 100% [72, 100] | 90% |
| $ a pass | 0.510 | 0.172 | |

- All ten covered rows luna answered *not covered* had no labelled passage in the top 5: what misses there is retrieval, not the answer.
- Luna is not measured on the entrance's routing (`--suite adapt`, ADR-0011); deepseek is.
- The owner chose luna. Its routing, `--suite adapt`, 1 rep, 2026-11-19 ($0.49): routed 27 of 29 (93%, deepseek's closing pass 88%), plans held 11 of 11. The entrance now runs on `openai/gpt-6-luna` (ADR-0011). The ticket has spent $1.58. Still missing: faithful 81%, verbatim-and-labelled 88%, covered answered 84%, the last on rows whose labelled passage retrieval does not return.
- The last trial, the owner's: luna reading the top 10 and the top 15 passages, 2026-11-19, nine blocks each, one rep ($0.70; the ticket has spent $2.28). Recall@k from one retrieval-only pass at top 20 ($0): 5 77%, 8 82%, 10 84%, 15 90%, 20 92%.

| Bar | Top 5 | Top 10 ($0.355) | Top 15 ($0.340) | Bar |
|---|---|---|---|---|
| Recall | 47 of 62, 76% [64, 85] | 53 of 62, 85% [75, 92] | 56 of 62, 90% [80, 95] | none |
| Verbatim and labelled | 53 of 60, 88% [78, 94] | 42 of 61, 69% [56, 79] | 43 of 58, 74% [62, 84] | 100% |
| Covered answered | 52 of 62, 84% [73, 91] | 56 of 62, 90% [80, 95] | 60 of 62, 97% [89, 99] | 90% |
| Faithful | 42 of 52, 81% [68, 89] | 29 of 52, 56% [42, 68] | 30 of 50, 60% [46, 72] | 90% |
| Relevant | 49 of 52, 94% [84, 98] | 52 of 52, 100% [93, 100] | 49 of 50, 98% [90, 100] | 85% |
| Not covered | 17 of 18, 94% [74, 99] | 14 of 18, 78% [55, 91] | 16 of 18, 89% [67, 97] | 90% |
| Triage | 10 of 10 | 10 of 10 | 10 of 10 | 90% |

- More passages let the entrance answer more rows and hold to them less: no top clears every bar.
