# 08: The judge calibrated

Status: ready-for-agent

**What to build:** faithfulness and answer relevance judged through RAGAS by the cheapest candidate that clears the judge's bar. The first full answer pass runs on the final retrieval configuration; the calibration set is drawn from it, frozen and versioned with the eval set. Decided in [the judge](../../answer-from-sources/issues/07-the-judge.md) and [ADR-0018](../../../adr/0018-a-model-judges-only-what-code-cannot-read.md).

Spec: [16.1](../spec.md). Map: [answer from sources](../../answer-from-sources/map.md).

**Blocked by:** 07.

**Constraint from 06:** a full pass is `trainer eval --suite answer`, one rep per row by default; `--only` names rows. Each row's run is written under `--records` as `<row>-<attempt>.json`, its conversation holding the question, the reply and each quote with its title and section: the replies to draw from.

- [ ] The first full pass on the 60 covered rows, asked for first with its estimate
- [ ] 30 replies drawn at random from it; the owner labels each faithful yes/no and answers yes/no
- [ ] 15 planted: real replies the agent alters with a claim the passage lacks or an answer to another question; the owner may read a random fifth
- [ ] Candidates in order `openai/gpt-oss-120b`, a mid-size Qwen, `anthropic/claude-haiku-4.5`, never the answering model's family; stop at the first that catches 13 of 15 planted and agrees on 27 of 30 real
- [ ] The threshold turning RAGAS's score into yes or no is fixed here, on the owner's 30
- [ ] If none clears, stop with the numbers; bar and set untouched, no fourth model
- [ ] The judge joins the model roster; it is recalibrated only when its model or prompt changes
- [ ] Estimate under $1 for all three candidates, asked for first
