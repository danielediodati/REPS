# The corpus over time

Type: grilling
Status: resolved

## Question

The corpus is pinned by revision ([Sources and licences](01-sources-and-licences.md)) and the eval set names the corpus version it was labelled on ([The eval set](05-the-eval-set.md)). How is the corpus versioned, who refreshes it and when, and what happens to the frozen set when it moves: relabel the rows whose quote no longer appears, bump the set's version, or freeze the corpus for the life of the milestone?

## Answer

Grilled 2026-11-07.

- **Frozen for milestone 16.** The owner refreshes it by hand, with a command, when they choose; nothing refreshes on its own.
- **Versioned** by a manifest beside the chunks; every refresh bumps it.
- **On a refresh**, every labelled quote is checked against the new corpus. Rows that still find their quote carry over unchanged; rows that lost it are listed, and the owner relabels or drops them. The set's version then bumps and names the new corpus version. Until then, a pass against the new corpus is refused as a state.
