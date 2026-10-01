"""The onboarding eval set: what it parses, and what it refuses."""

from __future__ import annotations

from pathlib import Path

import pytest

from trainer import onboarding_set
from trainer.coach import onboarding

SET = """\
today = "2026-10-01"

[bars]
on_time = 80
remembered = 80
routed = 70

[[cases]]
name = "terse"
kind = "interview"
describes = "one field an answer"
opens = "ciao"
replies = [
  { fields = ["goal", "equipment"], says = "forza, con un bilanciere. odio correre" },
  { fields = ["cycle_length", "split", "duration_cap_min"], says = "due, sopra e sotto, un'ora" },
]
otherwise = "no"
remembers = ["odio correre"]
pause_after = 1
back = "eccomi"

[[cases]]
name = "bought"
kind = "change"
describes = "equipment bought"
opens = "ho preso i manubri"
before = { cycle_length = 1, duration_cap_min = 45, split = [["legs"]], equipment = ["body only"], goal = "hypertrophy" }
changes = ["equipment"]
open = ["keep", "rewrite"]
otherwise = "si"

[[cases]]
name = "short"
kind = "route"
describes = "today only"
opens = "oggi ho 20 minuti"
routed = "adapt_today"
"""


def test_a_set_parses_into_its_cases_and_bars() -> None:
    parsed = onboarding_set.parse(SET)

    assert (parsed.today, parsed.bar_on_time, parsed.bar_remembered, parsed.bar_routed) == (
        "2026-10-01", 80, 80, 70
    )
    terse, bought, short = parsed.cases
    assert terse.kind == onboarding_set.INTERVIEW
    assert terse.replies[0].fields == ("goal", "equipment")
    assert (terse.pause_after, terse.back, terse.remembers) == (1, "eccomi", ("odio correre",))
    assert bought.before["equipment"] == ["body only"]
    assert (bought.changes, bought.open) == (("equipment",), ("keep", "rewrite"))
    assert short.routed == "adapt_today"


def test_the_set_says_which_cases_are_held_and_which_are_routes() -> None:
    parsed = onboarding_set.parse(SET)

    assert [case.name for case in parsed.held] == ["terse", "bought"]
    assert [case.name for case in parsed.routes] == ["short"]


@pytest.mark.parametrize(
    ("old", "new", "said"),
    [
        ("[bars]\non_time = 80\nremembered = 80\nrouted = 70\n", "", "bars"),
        ("on_time = 80\n", "", "on_time"),
        ('kind = "route"', 'kind = "chat"', "kind"),
        ('fields = ["goal", "equipment"]', 'fields = ["goal", "gear"]', "gear"),
        ('{ fields = ["cycle_length", "split", "duration_cap_min"], says = "due, sopra e sotto, un\'ora" },\n', "", "duration_cap_min"),
        ('open = ["keep", "rewrite"]', 'open = ["keep", "later"]', "later"),
        ('routed = "adapt_today"', 'routed = "log_workout"', "log_workout"),
        ('name = "short"', 'name = "terse"', "terse"),
        ("pause_after = 1", "pause_after = 2", "pause_after"),
        ('changes = ["equipment"]', "changes = []", "changes"),
    ],
)
def test_a_set_that_cannot_be_run_as_written_is_refused_by_name(
    old: str, new: str, said: str
) -> None:
    assert old in SET

    with pytest.raises(onboarding_set.OnboardSetError, match=said):
        onboarding_set.parse(SET.replace(old, new))


def test_the_committed_set_parses_and_every_interview_covers_every_field() -> None:
    committed = onboarding_set.load(Path.cwd().joinpath(*onboarding_set.DEFAULT_PARTS))

    for case in committed.cases:
        if case.kind == onboarding_set.INTERVIEW:
            covered = {field for reply in case.replies for field in reply.fields}
            assert covered == set(onboarding.FIELDS), case.name
    assert committed.routes and committed.held


def test_a_missing_set_is_refused_naming_the_file(tmp_path: Path) -> None:
    with pytest.raises(onboarding_set.OnboardSetError, match="nowhere.toml"):
        onboarding_set.load(tmp_path / "nowhere.toml")
