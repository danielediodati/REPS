# 01: Entrance replies in MarkdownV2

Status: ready-for-agent

**What to build:** a prefactor. Every reply the entrance writes is sent in MarkdownV2 with everything escaped, as `offer()` already does, so a cited answer can later add quotes and links without a dot or hyphen breaking the message. Nothing the owner sees changes. Decided in [how a citation looks](../../answer-from-sources/issues/04-how-a-citation-looks.md).

Spec: [16.1](../spec.md). Map: [answer from sources](../../answer-from-sources/map.md).

**Blocked by:** None (can start immediately).

- [ ] Every entrance reply goes out with the MarkdownV2 parse mode
- [ ] Text from the model or the catalog is escaped, dots, hyphens and parentheses included
- [ ] Existing bot tests pass unchanged in what they assert the owner reads
