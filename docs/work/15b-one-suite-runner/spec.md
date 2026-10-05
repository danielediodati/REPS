# Session 15b — One runner behind every eval suite

**Demo**: `trainer eval --suite <each>` prints what it printed before, and each suite's module is down to its set, its fixture and how it scores one run.

| Question | Answer |
|---|---|
| Why | The five suites each rebuild the fixture, the run, the quota stop, the record and the bars. A fix to one copy stays out of the others, and the copied wiring is the least tested code in the family. |
| What moves | Into one runner module: fixture copy and `TRAINER_DB`, graph and saver per run, spent quota and other errors, run record and `write`, bars from the set, the CLI wiring. |
| What stays per suite | Its set, the tables it clears and what it stages, how one run is scored, its bars and columns. |
| Behaviour | None changes. Same reports, same records, same exit codes. |
| Credits | None. Verified on scripted models; no real `trainer eval` run is needed to close it. |
| Version | `1.0.1`: a refactor, nothing the user sees. |

## Tickets

| # | Ticket | Blocked by |
|---|---|---|
| 01 | One suite runner | — |
