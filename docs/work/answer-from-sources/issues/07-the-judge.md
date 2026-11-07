# The judge

Type: grilling
Status: resolved

## Question

Which model judges faithfulness and answer relevance through RAGAS, and how is it chosen? ADR-0011 picks the cheapest that clears a bar: what is that bar for a judge, on which sample of rows does the owner read the replies to calibrate it, how large is the sample, and what does a calibration pass cost? Rows come from [the eval set](05-the-eval-set.md).

## Answer

**What it judges**: faithfulness and answer relevance only, through RAGAS. Code checks the rest at $0: verbatim quote, labelled passage, *not covered*, triage. See [ADR-0018](../../../adr/0018-a-model-judges-only-what-code-cannot-read.md).

**Candidates**, cheapest first, stopping at the first that clears; never the answering model's family (today DeepSeek):

1. `openai/gpt-oss-120b`
2. a mid-size Qwen
3. `anthropic/claude-haiku-4.5`

Estimate: under $1 for all three on the calibration set.

**Calibration set (45 replies)**

| Part | Rows | Labelled by |
|---|---|---|
| Real | 30, drawn at random from the teacher's first pass on covered rows | the owner: faithful yes/no, answers yes/no |
| Planted | 15, real replies the agent alters: a claim the passage lacks, or an answer to another question | construction; the owner may read a random fifth |

**Bar**: at least 13 of 15 planted caught and 27 of 30 real agreeing with the owner.

**When it runs**: on every full pass over the 60 covered rows, asked for first; never on screens. The 45 are frozen and versioned with the eval set; recalibrated on them only when the judge's model or prompt changes.

**If none clears**: stop; the owner decides with the numbers. Bar and set stay untouched, and no fourth model is tried unasked.
