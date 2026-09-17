# The run record can be read back

Status: ready-for-agent

Blocked by: 03 -- reading a record out of a checkpoint is reading back the types it registers.

Session 6 put the run record in the graph's state, and `coach/record.py` derives it: attempts and the violations each one collected, tool calls with their arguments and whether they came back an error, tokens in and out, seconds per node. Only `trainer plan --record` and the eval suites have ever asked for it. After a run in Telegram there is nothing to ask, and *control* means only *I have logs*.

This is the other half of the demo: pull the plug mid-run, restart, and read back what the bot was doing and why it stopped. The log says why it stopped; this says what it was doing.

## What to build

- **A command that lists the conversations in the checkpointer**, most recent first, each with enough to recognise it: when it last moved, and whether it ended with a plan, a refusal or nothing.
- **A command that prints one conversation's run record**, in the ASCII the terminal already gets from `record.summary`, with the JSON available for the whole thing.
- **A run cut mid-flight reads back**, at the last checkpoint it reached: the calls made so far, the attempts so far, the nodes that finished. An unfinished run is the case this ticket exists for, not an edge of it.
- **One definition of how a record is written**, still. `record.document` is it; a second renderer here would drift from `--record` and the eval files.

## Acceptance criteria

- [ ] A finished run in Telegram can be read back afterwards, with its attempts, calls, tokens and per-node seconds.
- [ ] A run killed mid-flight reads back what it had reached, without an error and without inventing an outcome.
- [ ] The listing names the conversation well enough to pick one without guessing.
- [ ] The record printed matches the one `trainer plan --record` writes for the same state.
- [ ] The full test suite and mypy are green.

## Comments

**A resumed state is not equal to the one that was written**, found closing 8.3.
msgpack has one sequence, so every tuple field of a dataclass comes back a
list: a `Request` read out of a checkpoint holds `['barbell']` where it was
written `('barbell',)`, which makes it unequal to the original and no longer
hashable. Nothing compares or hashes one today. It matters here because this
ticket reads state back and reports on it: the record must not claim two runs
differ because one of them came off disk.
