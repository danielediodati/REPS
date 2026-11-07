# 10: The corpus refreshed

Status: ready-for-agent

**What to build:** the owner refreshes the corpus by hand: new pinned revisions, a new corpus version, and the eval set checked against it. Decided in [the corpus over time](../../answer-from-sources/issues/10-the-corpus-over-time.md).

Spec: [16.1](../spec.md). Map: [answer from sources](../../answer-from-sources/map.md).

**Blocked by:** 05.

- [ ] A refresh fetches the revisions it is given and bumps the corpus version; nothing refreshes on its own
- [ ] Every labelled quote is checked against the new corpus; rows still finding theirs carry over unchanged
- [ ] Rows that lost their quote are listed for the owner to relabel or drop
- [ ] Once they are settled, the set's version bumps and names the new corpus version
- [ ] Until then a pass against the new corpus is refused as a state
