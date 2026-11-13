# A model judges only what code cannot read

Until milestone 16 no model judged another model's output: every check in the suites was code (ADR-0010). Milestone 16's answers quote a passage, and code can tell whether the quote is verbatim, but not whether the answer above it says what the passage says.

## Decision

1. **Code checks everything it can**, at $0: the quote is verbatim in a retrieved passage, that passage is one the row labels, a row outside the corpus gets *not covered*, a current pain goes to triage.
2. **A model judges two things only**: faithfulness (the answer says what its passage says) and answer relevance (it answers the question). Faithfulness is read the RAGAS way, as the share of the answer's statements its passages support; relevance is asked outright, yes or no.
3. **The judge is chosen by ADR-0011's rule**, cheapest first, from a family other than the model that answers.
4. **The judge clears its own bar before it judges anything**: 13 of 15 planted errors caught, and 27 of 30 real replies agreeing with the owner's reading. The 45 replies are frozen with the eval set and versioned with it.

## Consequences

- ADR-0010 still holds: legality at 100% by code, judgement at a declared bar. The judge is one more judgement, itself measured.
- A judge of the answering model's family is excluded, so the judge's choice moves when the entrance's model does.
- The judge is recalibrated on the same 45 replies only when its model or prompt changes.

## Amended in ticket 16.1.8

| Rejected | Why |
|---|---|
| The RAGAS package | 0.4.3 does not install on Python 3.14; older builds import a LangChain module that no longer exists. Its two prompts are reimplemented in `answer_judge`. |
| RAGAS answer relevancy (questions generated from the answer, compared by cosine) | Missed every reply rewritten to answer another question, on all three candidates: a reply on the same exercise sits close to the question whatever it answers. |
| `openai/gpt-oss-120b`, `qwen/qwen3-32b` | Did not clear: 24 and 27 of 30 agreed, 13 and 8 of 15 caught. |

`anthropic/claude-haiku-4.5` clears on calibration set 2: 28 of 30 agreed, 15 of 15 caught, both thresholds at 1.0, about $0.14 a calibration.
