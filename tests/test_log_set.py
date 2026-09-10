"""The log set, read out of markdown.

Written against a miniature set rather than against the committed thirty rows:
the parser's contract is the *shape* of the document, and a suite that asserted
against the real file would fail the day a row is reworded -- which is a thing
the author is meant to be able to do without asking a test's permission.

The committed file is still exercised, once, by `test_the_committed_set_parses`
-- guarded so it says nothing on a checkout where the document has been moved.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from conftest import make_exercise
from trainer import log_set
from trainer.engine import catalog, database, migrations

SET = """\
# A log set, in miniature

## What the runner has to set up

- **`today` is `2026-09-10`** for every row.
- **One prior performed workout supplies the load history** row U2 needs:
  `Barbell_Squat` last recorded at **80 kg**.

## 1. The prescriptions

### P1 — push day

| block | rounds | rest | exercise id | prescribed | movement pattern | primary muscles |
|---|---|---|---|---|---|---|
| 1 | 4 | 150 | `Bench_Press` | 8 reps | horizontal push | chest |
| 2 | 3 | 60 | `Plank` | 45 seconds | core anti-extension | abdominals |
| 2 | 3 | 60 | `Barbell_Squat` | 5 reps | squat | quadriceps |

Prescribed volume — pattern: horizontal push 4.

## 2. Two unambiguous reports

### U1 — perfect adherence — P1

> tutto liscio

```json
{
  "workout_id": 1,
  "blocks": [],
  "proposed_exclusion": null
}
```

- **volume (pattern):** horizontal push 4, core anti-extension 3
- **volume (muscle):** chest 4, abdominals 3

*Note.* Nothing deviated, so the document says nothing.

### U2 — a load — P1 `?`

> panca con 70 kg

```json
{
  "workout_id": 1,
  "blocks": [
    {
      "items": [
        {
          "exercise_id": "Bench_Press",
          "unit": "reps",
          "amount": 8,
          "amount_source": "assumed",
          "load_kg": 70,
          "load_kg_source": "reported"
        }
      ],
      "rounds": 4,
      "rounds_source": "assumed",
      "rest": 150,
      "rest_source": "assumed"
    }
  ],
  "proposed_exclusion": {
    "value": "shoulder",
    "retest_date": "<any date after 2026-09-10>",
    "why": "the shoulder was pulling"
  }
}
```

- **volume (pattern):** horizontal push 4
- **volume (muscle):** chest 4

## 3. One report that must make it ask

### A1 — how many rounds — P1

> in panca ho tolto qualche serie

- **unknowable:** "qualche serie" gives a direction and no number — the rounds
  performed are anywhere from 1 to 3.
- **wrong answer:** `rounds: 3` on the bench block.

*Note.* The deviation is stated and its size is not.

## 4. Confirmation

Written blind.
"""


def test_the_two_halves_are_read_off_the_sections() -> None:
    holds = log_set.parse(SET)

    assert [row.name for row in holds.unambiguous] == ["U1", "U2"]
    assert [row.name for row in holds.must_ask] == ["A1"]
    assert holds.today == "2026-09-10"
    assert (holds.history_exercise, holds.history_load_kg) == ("Barbell_Squat", 80.0)


def test_a_row_carries_its_report_and_what_it_is_about() -> None:
    row = log_set.parse(SET).rows[0]

    assert row.report == "tutto liscio"
    assert row.describes == "perfect adherence"
    assert row.prescription == "P1"
    assert row.uncertain is False


def test_the_expected_document_is_the_json_and_the_blockquote() -> None:
    row = log_set.parse(SET).unambiguous[1]

    assert row.expects is not None
    # The report is never repeated inside the JSON: one copy of the sentence,
    # and it is the one the reader sees.
    assert row.expects.report == "panca con 70 kg"
    assert row.expects.blocks[0].items[0].load_kg == 70
    assert row.pattern_volume == {"horizontal push": 4}
    assert row.muscle_volume == {"chest": 4}


def test_the_marker_is_read_after_the_prescription() -> None:
    row = log_set.parse(SET).unambiguous[1]

    assert row.name == "U2"
    assert row.uncertain is True
    assert row.prescription == "P1"


def test_a_re_test_date_the_document_leaves_open_becomes_one_after_today() -> None:
    """`<any date after 2026-09-10>` is prose, and the schema refuses prose.

    Filled in so the expected outcome is a document at all. Which day it holds
    means nothing: the scorer checks that field against `today` and never
    against this one.
    """
    row = log_set.parse(SET).unambiguous[1]

    assert row.expects is not None
    assert row.expects.proposed_exclusion is not None
    assert row.expects.proposed_exclusion.retest_date > "2026-09-10"


def test_a_must_ask_row_carries_no_document_and_says_what_is_open() -> None:
    row = log_set.parse(SET).must_ask[0]

    assert row.expects is None and row.must_ask
    assert row.unknowable is not None and row.unknowable.startswith('"qualche serie"')
    # The bullet wraps at 79 columns and the whole sentence is kept.
    assert row.unknowable.endswith("anywhere from 1 to 3.")
    assert row.wrong_answer is not None


def test_a_superset_is_the_rows_that_share_a_block_number() -> None:
    prescription = log_set.parse(SET).prescription("P1")

    assert [block.block.rounds for block in prescription.blocks] == [4, 3]
    assert [item.exercise_id for item in prescription.blocks[1].block.items] == [
        "Plank",
        "Barbell_Squat",
    ]
    # Seconds and reps are the units the table gives, not a default.
    assert prescription.blocks[1].block.items[0].seconds == 45
    assert prescription.blocks[1].block.items[1].reps == 5


def test_a_volume_line_that_wraps_is_read_whole() -> None:
    """The document wraps at 79 columns, and a four-bucket volume line is
    already near it. Read off the first line alone, a wrapped one ends in a
    comma and the row is refused for the author's own formatting."""
    wrapped = SET.replace(
        "- **volume (pattern):** horizontal push 4, core anti-extension 3",
        "- **volume (pattern):** horizontal push 4,\n  core anti-extension 3",
    )

    row = log_set.parse(wrapped).unambiguous[0]

    assert row.pattern_volume == {"horizontal push": 4, "core anti-extension": 3}


def test_a_block_listed_again_after_another_is_refused() -> None:
    """`1, 2, 1` is a superset written apart, and it would silently become two
    blocks with the same number -- volume figures that are right about a
    workout the table does not describe."""
    split = SET.replace(
        "| 2 | 3 | 60 | `Barbell_Squat` | 5 reps | squat | quadriceps |",
        "| 1 | 4 | 150 | `Barbell_Squat` | 5 reps | squat | quadriceps |",
    )

    with pytest.raises(log_set.LogSetError) as raised:
        log_set.parse(split)

    assert "block 1 is listed again after another block" in str(raised.value)


@pytest.mark.parametrize(
    ("broken", "says"),
    [
        (SET.replace("- **unknowable:**", "- **why:**"), "unknowable"),
        (SET.replace("- **wrong answer:**", "- **note:**"), "confident model"),
        (SET.replace("- **volume (muscle):** chest 4, abdominals 3", ""), "both axes"),
        (SET.replace("### U1 — perfect adherence — P1", "### A1 — again — P1"), "two rows"),
        (SET.replace("— P1\n\n> in panca", "— P9\n\n> in panca"), "does not prescribe"),
        (SET.replace("`today` is `2026-09-10`", "today is soon"), "what day it is"),
        (SET.replace("last recorded at **80 kg**", "recorded heavy"), "load history"),
        (SET.replace('"amount": 8,', '"amount": 0,'), "could emit"),
        (SET.replace("| 8 reps |", "| 8 times |"), "reps or seconds"),
    ],
)
def test_a_set_that_cannot_be_scored_is_refused_with_the_row_named(
    broken: str, says: str
) -> None:
    with pytest.raises(log_set.LogSetError) as raised:
        log_set.parse(broken)

    assert says in str(raised.value)


def test_a_must_ask_row_with_a_document_is_a_contradiction() -> None:
    """Both halves are scored differently, and a row cannot be in both."""
    with pytest.raises(log_set.LogSetError) as raised:
        log_set.parse(
            SET.replace(
                "> in panca ho tolto qualche serie\n",
                '> in panca ho tolto qualche serie\n\n```json\n{"blocks": []}\n```\n',
            )
        )

    assert "no document it should have written" in str(raised.value)


def test_the_report_is_not_repeated_inside_the_expected_document() -> None:
    with pytest.raises(log_set.LogSetError) as raised:
        log_set.parse(SET.replace('"workout_id": 1,', '"report": "x", "workout_id": 1,', 1))

    assert "blockquote" in str(raised.value)


@pytest.fixture()
def connection(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(
            opened,
            (
                make_exercise(id="Bench_Press", name="Bench Press"),
                make_exercise(id="Plank", name="Plank"),
                make_exercise(id="Barbell_Squat", name="Barbell Squat"),
            ),
        )
        yield opened


def test_every_id_the_set_names_is_checked_against_this_catalog(
    connection: sqlite3.Connection,
) -> None:
    assert log_set.unknown_exercises(connection, log_set.parse(SET)) == ()

    connection.execute("DELETE FROM exercises WHERE id = 'Plank'")
    assert log_set.unknown_exercises(connection, log_set.parse(SET)) == ("Plank",)


def test_against_an_empty_catalog_every_id_is_missing(
    connection: sqlite3.Connection,
) -> None:
    """The state CLAUDE.md's standing rule is about: an empty vocabulary makes
    every correct value look like a typo, so the caller can say *import the
    catalog first* rather than *no such exercise*."""
    connection.execute("DELETE FROM exercises")

    missing = log_set.unknown_exercises(connection, log_set.parse(SET))
    assert set(missing) == {"Bench_Press", "Plank", "Barbell_Squat"}


def test_the_committed_set_parses() -> None:
    """The real document, if this checkout has it.

    `docs/logging/eval-set.md` is the set the command scores against, and a
    parser that only ever meets the miniature above is a parser nobody has run
    against the thing it was written for. Nothing here asserts about a
    particular row: what is checked is that the file reads, that both halves
    are in it, and that every row is complete enough to score.
    """
    where = Path.cwd().joinpath(*log_set.DEFAULT_LOG_SET_PARTS)
    if not where.exists():
        pytest.skip("the committed log set is not in this checkout")

    holds = log_set.load(where)

    assert len(holds.rows) == len(holds.unambiguous) + len(holds.must_ask)
    assert holds.unambiguous and holds.must_ask
    assert all(row.report for row in holds.rows)
    assert all(row.unknowable for row in holds.must_ask)
    assert all(
        row.pattern_volume is not None and row.muscle_volume is not None
        for row in holds.unambiguous
    )
