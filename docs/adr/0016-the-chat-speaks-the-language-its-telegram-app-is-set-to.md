# The chat speaks the language its Telegram app is set to

Until 15c.3 every line the chat showed was Italian, fixed in the prompts and in the bot's own constants. Some lines are written long before they are read: a block's reason is written when the mesocycle is planned and shown days later, with today's workout. So the language cannot be guessed from the last message. It has to be known when the line is written.

## Decision

1. **The language is the sender's Telegram app setting**, read off each update's `language_code`: Italian for `it`, English for anything else.
2. **A run carries it in its config** (`configurable.language`). Every prompt whose words reach the chat ends on a line naming it. The entrance, planner, supervisor, logger and onboarding prompts say *in their language*, not a fixed one.
3. **The chat's own words live in one catalog per language** (`src/trainer/data/chat/<language>.toml`), read through one factory. A test fails the build when the catalogs differ in keys or placeholders.
4. **Outside Telegram the language is Italian**: the CLI and the evals name none, so no eval bar moves.

## Rejected

- **A declared language**: one more declaration, with the interview and its versions to change, for what the phone already says.
- **The language of the message**: a fixed line and a stored reason would have to guess it, and a one-word message (*«ok»*) names none.

## Consequences

- A reason or direction keeps the language it was written in. Switch the app's language and the old mesocycle's reasons stay in the old one.
- The demo's history is in English, because the recording is.
- Exercise names stay the catalog's, in English, in both languages.
