# The checkpoint's types are registered

Status: ready-for-agent

Blocked by: none -- can start immediately.

`plan.Request`, `plan.Violation` and `plan.WorkoutPlan` go into every checkpoint the graph writes. LangGraph's msgpack serializer accepts them today and warns that it will stop reading unregistered types back. The warning is the whole notice: on the next LangGraph upgrade every conversation on disk becomes unreadable, and the first sign of it is a thread that will not resume.

## What to build

- **The three types declared to the serializer**, where the checkpointer is built, so that what is written is what will be read back.
- **Strict serialization on**, so that a type nobody declared fails loudly when it is written rather than quietly when it is read.
- **A test that resumes from disk**: a state carrying all three is written by one saver, read by another, and comes back as those classes with equal fields -- not as dictionaries.

The three are the ones in the state today. If a fourth is found while doing this, declare it and say so in the ticket.

## Acceptance criteria

- [ ] A checkpoint written and reopened returns `plan.Request`, `plan.Violation` and `plan.WorkoutPlan`, equal to what went in.
- [ ] Writing an undeclared type fails at the write, with a message naming the type.
- [ ] The serializer emits no unregistered-type warning during the test suite.
- [ ] A conversation started before this ticket still resumes.
- [ ] The full test suite and mypy are green.
