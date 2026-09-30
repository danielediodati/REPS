"""The declarations: every way one can be wrong, and the versions they are kept in (ADR-0013)."""

from __future__ import annotations

import sqlite3
import tomllib
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from trainer.engine import config, database, methodology, migrations, muscle_groups

VALID = """\
cycle_length = 3
duration_cap_min = 45
volume_denominator = "cycle"
equipment = ["dumbbell", "bands"]
goal = "hypertrophy"
split = [
    ["chest", "shoulders", "arms"],
    ["back", "arms"],
    ["legs", "core"],
]
"""


def parsed(text: str) -> config.TrainingConfig:
    return config.parse(tomllib.loads(text))


def test_a_valid_configuration_reads_back_as_a_typed_shape() -> None:
    read = parsed(VALID)

    assert read.cycle_length == 3
    assert read.duration_cap_min == 45
    assert read.volume_denominator == "cycle"
    assert read.equipment == ("dumbbell", "bands")
    assert read.goal == "hypertrophy"
    assert read.split == (
        ("chest", "shoulders", "arms"),
        ("back", "arms"),
        ("legs", "core"),
    )


def test_the_split_is_indexed_by_position_in_the_rotation() -> None:
    read = parsed(VALID)

    assert read.groups_for(1) == ("chest", "shoulders", "arms")
    assert read.groups_for(3) == ("legs", "core")


def test_a_workout_outside_the_cycle_says_how_long_the_cycle_is() -> None:
    """`IndexError`, not `ConfigError`: the configuration is fine, the caller
    asked for a workout the cycle does not hold. Reported as a config error it
    would send the user to edit a file with nothing wrong with it."""
    read = parsed(VALID)

    with pytest.raises(IndexError, match="outside a cycle of 3"):
        read.groups_for(4)

    assert not isinstance(IndexError(), config.ConfigError)


# -- the ways it can be wrong -------------------------------------------------


def test_a_missing_goal_is_named_like_any_missing_setting() -> None:
    with pytest.raises(config.ConfigError, match="goal"):
        parsed(VALID.replace('goal = "hypertrophy"\n', ""))


def test_a_split_that_does_not_match_the_cycle_says_both_numbers() -> None:
    text = VALID.replace("cycle_length = 3", "cycle_length = 4")

    with pytest.raises(config.ConfigError) as raised:
        parsed(text)

    message = str(raised.value)
    assert "3 workout(s)" in message
    assert "4 workout(s)" in message


def test_an_unknown_group_is_rejected_with_the_valid_ones_listed() -> None:
    text = VALID.replace('["back", "arms"]', '["Back", "arms"]')

    with pytest.raises(config.ConfigError) as raised:
        parsed(text)

    message = str(raised.value)
    assert "'Back'" in message
    assert "workout 2" in message
    for group in muscle_groups.groups():
        assert group in message


def test_the_valid_groups_come_from_the_mapping_and_not_from_a_copy() -> None:
    """Hand a different vocabulary in and the reader validates against it --
    proof the six are read rather than spelled out in this module."""
    raw = {
        "cycle_length": 1,
        "duration_cap_min": 30,
        "volume_denominator": "cycle",
        "split": [["fins"]],
        "equipment": ["dumbbell"],
        "goal": "hypertrophy",
    }
    fish = muscle_groups.parse(
        "| muscle | group | why |\n|---|---|---|\n| `pectoral fin` | `fins` | swims |\n"
    )

    assert config.parse(raw, mapping=fish).split == (("fins",),)

    with pytest.raises(config.ConfigError, match="not a muscle group"):
        config.parse(raw)


def _one_slot(*names: str) -> dict[str, object]:
    return {
        "cycle_length": 1,
        "duration_cap_min": 30,
        "volume_denominator": "cycle",
        "split": [list(names)],
        "equipment": ["dumbbell"],
        "goal": "hypertrophy",
    }


def test_a_slot_may_name_muscles_beside_groups() -> None:
    assert config.parse(_one_slot("chest", "biceps")).split == (("chest", "biceps"),)


def test_a_misspelt_muscle_is_refused_naming_the_valid_ones() -> None:
    with pytest.raises(config.ConfigError, match="workout 1 of the split") as raised:
        config.parse(_one_slot("chest", "bicep"))

    for name in muscle_groups.committed().names:
        assert name in str(raised.value)


def test_neck_is_refused_with_the_reason() -> None:
    with pytest.raises(config.ConfigError, match="'neck' is a muscle in no group"):
        config.parse(_one_slot("neck"))


def test_a_group_beside_one_of_its_own_muscles_is_refused() -> None:
    with pytest.raises(config.ConfigError, match="'arms' and 'biceps' both train 'biceps'"):
        config.parse(_one_slot("arms", "biceps"))


@pytest.mark.parametrize("cap", ["0", "-15"])
def test_a_duration_cap_that_is_not_a_workout_is_refused(
    cap: str
) -> None:
    text = VALID.replace("duration_cap_min = 45", f"duration_cap_min = {cap}")

    with pytest.raises(config.ConfigError, match="duration_cap_min"):
        parsed(text)


def test_a_cycle_of_zero_workouts_is_refused() -> None:
    text = (
        "cycle_length = 0\nduration_cap_min = 45\n"
        "volume_denominator = 'cycle'\nsplit = []\nequipment = ['bands']\ngoal = 'hypertrophy'\n"
    )

    with pytest.raises(config.ConfigError, match="cycle_length"):
        parsed(text)


def test_a_non_integer_cap_is_refused() -> None:
    text = VALID.replace("duration_cap_min = 45", "duration_cap_min = 45.5")

    with pytest.raises(config.ConfigError, match="whole number of minutes"):
        parsed(text)


def test_a_boolean_is_not_a_number() -> None:
    """`True` is an `int` in Python and would otherwise pass as one minute."""
    text = VALID.replace("duration_cap_min = 45", "duration_cap_min = true")

    with pytest.raises(config.ConfigError, match="whole number of minutes"):
        parsed(text)


def test_an_unknown_denominator_lists_the_ones_that_exist() -> None:
    text = VALID.replace('volume_denominator = "cycle"', 'volume_denominator = "week"')

    with pytest.raises(config.ConfigError) as raised:
        parsed(text)

    assert "'cycle'" in str(raised.value)


def test_a_workout_training_nothing_is_refused() -> None:
    text = VALID.replace('["back", "arms"]', "[]")

    with pytest.raises(config.ConfigError, match="trains nothing"):
        parsed(text)


def test_a_group_named_twice_in_one_workout_is_refused() -> None:
    text = VALID.replace('["back", "arms"]', '["back", "back"]')

    with pytest.raises(config.ConfigError, match="more than once"):
        parsed(text)


def test_an_unknown_goal_is_rejected_naming_the_ones_the_methodology_has() -> None:
    text = VALID.replace('goal = "hypertrophy"', 'goal = "toning"')

    with pytest.raises(config.ConfigError) as raised:
        parsed(text)

    message = str(raised.value)
    assert "'toning'" in message
    for goal in methodology.goals():
        assert goal in message


def test_the_goals_come_from_the_methodology_and_not_from_a_copy() -> None:
    raw = {
        "cycle_length": 1,
        "duration_cap_min": 30,
        "volume_denominator": "cycle",
        "split": [["chest"]],
        "equipment": ["dumbbell"],
        "goal": "power",
    }

    assert config.parse(raw, valid_goals=("power",)).goal == "power"

    with pytest.raises(config.ConfigError, match="not a goal"):
        config.parse(raw)


def test_a_goal_that_is_not_a_string_is_refused() -> None:
    text = VALID.replace('goal = "hypertrophy"', "goal = 3")

    with pytest.raises(config.ConfigError, match="goal"):
        parsed(text)


def test_a_misspelled_setting_is_refused_rather_than_ignored() -> None:
    """A key that is silently skipped is a setting the user believes they
    changed and did not."""
    text = VALID.replace("cycle_length = 3", "cycle_lenght = 3\ncycle_length = 3")

    with pytest.raises(config.ConfigError, match="cycle_lenght"):
        parsed(text)


def test_a_missing_setting_names_it() -> None:
    text = VALID.replace('volume_denominator = "cycle"\n', "")

    with pytest.raises(config.ConfigError, match="volume_denominator"):
        parsed(text)


def test_a_split_that_is_not_a_list_of_lists_is_refused() -> None:
    text = (
        "cycle_length = 1\nduration_cap_min = 45\n"
        "volume_denominator = 'cycle'\nsplit = ['chest']\nequipment = ['bands']\ngoal = 'hypertrophy'\n"
    )

    with pytest.raises(config.ConfigError, match="list of one list of groups or muscles"):
        parsed(text)


# -- the equipment, the fifth declaration -------------------------------------


def test_equipment_that_is_not_a_list_of_names_is_refused() -> None:
    text = VALID.replace('equipment = ["dumbbell", "bands"]', 'equipment = "dumbbell"')

    with pytest.raises(config.ConfigError, match="list of the values"):
        parsed(text)


def test_declaring_nothing_to_train_with_is_refused_naming_body_only() -> None:
    """An empty list is a declaration no plan can be made against, and having
    no equipment is a value the catalog has a word for."""
    text = VALID.replace('equipment = ["dumbbell", "bands"]', "equipment = []")

    with pytest.raises(config.ConfigError, match="body only"):
        parsed(text)


def test_a_blank_equipment_name_is_refused() -> None:
    text = VALID.replace('equipment = ["dumbbell", "bands"]', 'equipment = ["  "]')

    with pytest.raises(config.ConfigError, match="body only"):
        parsed(text)


def test_equipment_named_twice_is_refused() -> None:
    text = VALID.replace(
        'equipment = ["dumbbell", "bands"]', 'equipment = ["dumbbell", "dumbbell"]'
    )

    with pytest.raises(config.ConfigError, match="more than once"):
        parsed(text)


def test_the_equipment_vocabulary_is_not_spelled_out_in_this_module() -> None:
    """The standing rule: the values live in the imported catalog, which
    parsing does not read. A value it does not know is refused where the catalog is open, by `admissible_set`, which names the
    ones that exist -- so a declaration naming one is read, not rejected."""
    text = VALID.replace(
        'equipment = ["dumbbell", "bands"]', 'equipment = ["a trapeze"]'
    )

    assert config.parse(tomllib.loads(text)).equipment == ("a trapeze",)


# -- the versions, in the database ------------------------------------------------


@pytest.fixture()
def connection(database_file: Path, declared_training: Path) -> Iterator[sqlite3.Connection]:
    """A migrated database, with no legacy file to import."""
    declared_training.unlink()
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        yield opened


def test_nothing_declared_is_a_state_naming_the_bot(connection: sqlite3.Connection) -> None:
    with pytest.raises(config.NoTrainingConfig) as raised:
        config.load(connection)

    message = str(raised.value)
    assert "bot" in message and "cycle_length" not in message
    assert config.declared(connection) is None


def test_a_version_recorded_is_the_one_read_back(connection: sqlite3.Connection) -> None:
    config.record(connection, parsed(VALID), "2026-10-01")

    assert config.load(connection) == parsed(VALID)


def test_a_change_adds_a_version_and_the_one_before_stays_with_its_date(
    connection: sqlite3.Connection,
) -> None:
    first = parsed(VALID)
    second = parsed(VALID.replace("duration_cap_min = 45", "duration_cap_min = 30"))
    config.record(connection, first, "2026-09-01")
    config.record(connection, second, "2026-10-01")

    assert config.load(connection) == second
    assert [(v.declared_on, v.declaration) for v in config.versions(connection)] == [
        ("2026-10-01", second),
        ("2026-09-01", first),
    ]


def test_a_legacy_file_is_imported_once_and_then_ignored(
    connection: sqlite3.Connection, machine_home: Path
) -> None:
    legacy = machine_home / config.LEGACY_NAME
    legacy.write_text(VALID, encoding="utf-8-sig")

    assert config.load(connection) == parsed(VALID)
    legacy.write_text(VALID.replace("cycle_length = 3", "cycle_length = 9"), encoding="utf-8")

    assert config.load(connection) == parsed(VALID)
    assert len(config.versions(connection)) == 1


def test_a_legacy_file_that_cannot_be_read_is_nothing_declared_saying_why(
    connection: sqlite3.Connection, machine_home: Path
) -> None:
    legacy = machine_home / config.LEGACY_NAME
    legacy.write_bytes(VALID.encode("utf-8") + "# perchè\n".encode("cp1252"))

    with pytest.raises(config.NoTrainingConfig, match="could not be imported"):
        config.load(connection)
    assert config.versions(connection) == ()
