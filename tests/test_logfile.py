"""The log the bot owns: where it is born, that it rotates, and what never reaches it.

Driven rather than read back: the rotation is exercised by writing past the
declared size, and the credentials are checked against a file on disk instead
of against the formatter that was supposed to take them out.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from trainer.coach import bot, logfile


def written() -> str:
    """Everything in the live file, as text."""
    return logfile.log_path().read_text(encoding="utf-8")


def test_starting_puts_the_log_in_the_home(machine_home: Path) -> None:
    """Born in `TRAINER_HOME`, with everything else the machine writes."""
    path = logfile.start(())

    assert path == machine_home / logfile.LOG_NAME
    assert path.exists()


def test_nothing_is_configured_until_the_bot_starts() -> None:
    """A library that configures logging on import steals it from every other
    caller, so importing this module must do nothing at all."""
    assert not any(
        isinstance(handler, logfile.Rotating)
        for handler in logging.getLogger().handlers
    )


def test_a_state_is_a_full_sentence_in_the_file() -> None:
    """What the chat gets as one line is the whole thing here, fix included."""
    logfile.start(())

    logging.getLogger("trainer.coach.bot").warning(
        "chat:1 cannot plan: %s", "there is no catalog yet; run trainer db import"
    )

    assert "trainer db import" in written()


def test_an_exception_reaches_the_file_with_its_traceback() -> None:
    logfile.start(())

    try:
        raise RuntimeError("the provider fell over")
    except RuntimeError:
        logging.getLogger("trainer.coach.bot").exception("the run on chat:1 failed")

    text = written()
    assert "Traceback" in text
    assert "RuntimeError: the provider fell over" in text


def test_the_file_rotates_and_keeps_what_it_declares() -> None:
    """Written past the declared size, the oldest lines go and the newest stay.

    The point of the file is the evening it records; a file that grows without
    a bound is one nobody can copy, and one that is truncated is an evening
    lost.
    """
    logfile.start(())
    logger = logging.getLogger("trainer.coach.bot")
    padding = "x" * 900
    for turn in range((logfile.MAX_BYTES * (logfile.KEPT + 1)) // 900):
        logger.info("turn %d %s", turn, padding)
    logger.info("the last line")

    kept = sorted(logfile.log_path().parent.glob(f"{logfile.LOG_NAME}*"))
    assert len(kept) == logfile.KEPT + 1, kept
    assert max(path.stat().st_size for path in kept) <= logfile.MAX_BYTES + 1024
    assert "the last line" in written()


def test_the_token_and_the_owner_id_are_never_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The failure that carries both: an HTTP error whose URL is the token.

    The traceback quotes the source line that raised, so the token is in the
    record twice over -- which is the case a formatter that only looked at the
    message would miss.
    """
    monkeypatch.setenv(bot.TOKEN_ENV, "7891011:AA-the-secret")
    monkeypatch.setenv(bot.OWNER_ENV, "6421")
    logfile.start((bot.TOKEN_ENV, bot.OWNER_ENV))

    try:
        raise RuntimeError(
            "POST https://api.telegram.org/bot7891011:AA-the-secret/sendMessage"
        )
    except RuntimeError:
        logging.getLogger("trainer.coach.bot").exception(
            "could not write to chat:6421"
        )

    text = written()
    assert "AA-the-secret" not in text
    assert "6421" not in text
    assert logfile.HIDDEN in text
    assert "api.telegram.org" in text, "only the credentials go"


def test_a_number_that_merely_contains_the_owner_id_survives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The id is a number, and a blind replacement would eat every longer one
    it happens to sit inside -- starting with the seconds of a plan."""
    monkeypatch.setenv(bot.OWNER_ENV, "642")
    logfile.start((bot.OWNER_ENV,))

    logging.getLogger("trainer.coach.bot").info("the plan took 6421 seconds")

    assert "6421" in written()


def test_the_poll_loop_is_not_what_the_file_fills_up_with() -> None:
    """Long polling is a request every few seconds, and the HTTP client says
    so at INFO. Left alone it is the whole log, and the evening that went
    wrong has rotated out from under it."""
    logfile.start(())

    logging.getLogger("httpx").info(
        'HTTP Request: POST https://api.telegram.org/bot1:x/getUpdates "200 OK"'
    )
    logging.getLogger("httpx").warning("the request timed out")

    text = written()
    assert "getUpdates" not in text
    assert "the request timed out" in text, "a request that failed is still kept"


def test_every_level_the_log_takes_is_given_back() -> None:
    """Quieting a library is a process-wide decision, and the log is the only
    thing that made it: somebody debugging the HTTP client must get their own
    level back rather than the default this happened to assume."""
    httpx = logging.getLogger("httpx")
    httpx.setLevel(logging.DEBUG)
    try:
        logfile.start(())
        assert httpx.level == logging.WARNING

        logfile.stop()

        assert httpx.level == logging.DEBUG
    finally:
        httpx.setLevel(logging.NOTSET)


def test_starting_twice_does_not_double_every_line() -> None:
    """The handler is replaced, not stacked: a second one on the same file
    writes every record again, and the log reads as a run that happened twice."""
    logfile.start(())
    logfile.start(())

    logging.getLogger("trainer.coach.bot").warning("said once")

    assert written().count("said once") == 1
