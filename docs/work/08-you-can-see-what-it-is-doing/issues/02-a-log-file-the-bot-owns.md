# A log file the bot owns, rotated

Status: ready-for-agent

Blocked by: 01 -- the log is born in `TRAINER_HOME` rather than moved there later.

`coach/bot.py` logs, and nothing configures logging: there is no handler, so the only record of a run is whatever stderr was attached to when the bot started. Close the terminal and the evening is gone. Meanwhile `BLOCKED` and `FAILED` tell the user the reason is *«dove gira il bot»*, which names no file.

**Nothing raised leaves the machine.** Those two lines are generic on purpose: the engine's states carry absolute paths -- the file to copy, the directory to copy it into -- and quoted into Telegram they leave this installation's account name and disk layout on a third party's servers, for a path nobody can act on from a phone. This ticket is where that detail goes instead.

## What to build

- **A rotating log file under `TRAINER_HOME`**, configured once where the bot starts and nowhere else: a library that configures logging on import steals it from every other caller.
- **Every state and every exception in it**, with a traceback, at the moment the chat is told `BLOCKED` or `FAILED`. A state that reaches the user as one line is a full sentence in the log, with the path and the command that fixes it.
- **The token and the owner id are never written**, whatever is being logged -- including when the failure is an HTTP error whose URL carries the token.
- **`BLOCKED` and `FAILED` name the log** instead of *«dove gira il bot»*. They say which file, in the same way for both, and still without an absolute path: the user reading them is the person sitting at that machine.

## Acceptance criteria

- [ ] Starting the bot creates the log in the home; a run's states and exceptions are in it afterwards.
- [ ] The file rotates: the number and size of the kept files are declared, and a test drives the rotation rather than reading the configuration back.
- [ ] A test asserts the token and the owner id appear nowhere in the file, for a failure that carries both.
- [ ] The two chat lines name the log, and neither prints an absolute path.
- [ ] The full test suite and mypy are green.
