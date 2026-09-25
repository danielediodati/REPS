"""The training configuration: the reader, and every way the file can be wrong.

No LLM and no network. Nothing here opens the database either -- ADR-0003's
whole point is that these four values are declared in a file, so a reader that
needed SQLite to validate them would have given the argument away.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import pytest

from trainer.engine import config, home, methodology, muscle_groups

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


def written(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "training.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_a_valid_configuration_reads_back_as_a_typed_shape(tmp_path: Path) -> None:
    parsed = config.load(written(tmp_path, VALID))

    assert parsed.cycle_length == 3
    assert parsed.duration_cap_min == 45
    assert parsed.volume_denominator == "cycle"
    assert parsed.equipment == ("dumbbell", "bands")
    assert parsed.goal == "hypertrophy"
    assert parsed.split == (
        ("chest", "shoulders", "arms"),
        ("back", "arms"),
        ("legs", "core"),
    )


def test_the_committed_example_is_a_valid_configuration() -> None:
    """The file the missing-config state tells the user to copy. If it did not
    parse, the state's own instruction would be a dead end."""
    parsed = config.load(config.EXAMPLE_CONFIG_PATH)

    assert parsed.cycle_length == len(parsed.split)


def test_the_split_is_indexed_by_position_in_the_rotation(tmp_path: Path) -> None:
    parsed = config.load(written(tmp_path, VALID))

    assert parsed.groups_for(1) == ("chest", "shoulders", "arms")
    assert parsed.groups_for(3) == ("legs", "core")


def test_a_workout_outside_the_cycle_says_how_long_the_cycle_is(tmp_path: Path) -> None:
    """`IndexError`, not `ConfigError`: the configuration is fine, the caller
    asked for a workout the cycle does not hold. Reported as a config error it
    would send the user to edit a file with nothing wrong with it."""
    parsed = config.load(written(tmp_path, VALID))

    with pytest.raises(IndexError, match="outside a cycle of 3"):
        parsed.groups_for(4)

    assert not isinstance(IndexError(), config.ConfigError)


# -- the ways it can be wrong -------------------------------------------------


def test_a_missing_file_is_a_state_and_not_a_field_error(tmp_path: Path) -> None:
    """CLAUDE.md's standing rule, in the case it was written for. The message
    names the state and the way out of it, and mentions no field."""
    absent = tmp_path / "training.toml"

    with pytest.raises(config.NoTrainingConfig) as raised:
        config.load(absent)

    message = str(raised.value)
    assert "no training configuration yet" in message
    assert str(config.EXAMPLE_CONFIG_PATH) in message
    assert "cycle_length" not in message


def test_the_missing_state_is_its_own_class(tmp_path: Path) -> None:
    """So a caller can tell «nothing declared yet» from «what you declared is
    wrong» without reading the message."""
    assert issubclass(config.NoTrainingConfig, config.ConfigError)

    with pytest.raises(config.NoTrainingConfig):
        config.load(tmp_path / "absent.toml")


def test_a_split_that_does_not_match_the_cycle_says_both_numbers(
    tmp_path: Path,
) -> None:
    text = VALID.replace("cycle_length = 3", "cycle_length = 4")

    with pytest.raises(config.ConfigError) as raised:
        config.load(written(tmp_path, text))

    message = str(raised.value)
    assert "3 workout(s)" in message
    assert "4 workout(s)" in message


def test_an_unknown_group_is_rejected_with_the_valid_ones_listed(
    tmp_path: Path,
) -> None:
    text = VALID.replace('["back", "arms"]', '["Back", "arms"]')

    with pytest.raises(config.ConfigError) as raised:
        config.load(written(tmp_path, text))

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

    assert config.parse(raw, valid_groups=("fins",)).split == (("fins",),)

    with pytest.raises(config.ConfigError, match="not a muscle group"):
        config.parse(raw)


@pytest.mark.parametrize("cap", ["0", "-15"])
def test_a_duration_cap_that_is_not_a_workout_is_refused(
    tmp_path: Path, cap: str
) -> None:
    text = VALID.replace("duration_cap_min = 45", f"duration_cap_min = {cap}")

    with pytest.raises(config.ConfigError, match="duration_cap_min"):
        config.load(written(tmp_path, text))


def test_a_cycle_of_zero_workouts_is_refused(tmp_path: Path) -> None:
    text = (
        "cycle_length = 0\nduration_cap_min = 45\n"
        "volume_denominator = 'cycle'\nsplit = []\nequipment = ['bands']\n"
    )

    with pytest.raises(config.ConfigError, match="cycle_length"):
        config.load(written(tmp_path, text))


def test_a_non_integer_cap_is_refused(tmp_path: Path) -> None:
    text = VALID.replace("duration_cap_min = 45", "duration_cap_min = 45.5")

    with pytest.raises(config.ConfigError, match="whole number of minutes"):
        config.load(written(tmp_path, text))


def test_a_boolean_is_not_a_number(tmp_path: Path) -> None:
    """`True` is an `int` in Python and would otherwise pass as one minute."""
    text = VALID.replace("duration_cap_min = 45", "duration_cap_min = true")

    with pytest.raises(config.ConfigError, match="whole number of minutes"):
        config.load(written(tmp_path, text))


def test_an_unknown_denominator_lists_the_ones_that_exist(tmp_path: Path) -> None:
    text = VALID.replace('volume_denominator = "cycle"', 'volume_denominator = "week"')

    with pytest.raises(config.ConfigError) as raised:
        config.load(written(tmp_path, text))

    assert "'cycle'" in str(raised.value)


def test_a_workout_training_nothing_is_refused(tmp_path: Path) -> None:
    text = VALID.replace('["back", "arms"]', "[]")

    with pytest.raises(config.ConfigError, match="trains nothing"):
        config.load(written(tmp_path, text))


def test_a_group_named_twice_in_one_workout_is_refused(tmp_path: Path) -> None:
    text = VALID.replace('["back", "arms"]', '["back", "back"]')

    with pytest.raises(config.ConfigError, match="more than once"):
        config.load(written(tmp_path, text))


def test_an_unknown_goal_is_rejected_naming_the_ones_the_methodology_has(
    tmp_path: Path,
) -> None:
    text = VALID.replace('goal = "hypertrophy"', 'goal = "toning"')

    with pytest.raises(config.ConfigError) as raised:
        config.load(written(tmp_path, text))

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


def test_a_missing_goal_is_a_state_with_its_fix(tmp_path: Path) -> None:
    """A file written before the goal existed is not wrong: it predates the declaration."""
    text = VALID.replace('goal = "hypertrophy"\n', "")

    with pytest.raises(config.NoGoal) as raised:
        config.load(written(tmp_path, text))

    message = str(raised.value)
    assert "no goal declared yet" in message
    assert 'goal = "' in message
    for goal in methodology.goals():
        assert goal in message
    assert issubclass(config.NoGoal, config.ConfigError)


def test_a_goal_that_is_not_a_string_is_refused(tmp_path: Path) -> None:
    text = VALID.replace('goal = "hypertrophy"', "goal = 3")

    with pytest.raises(config.ConfigError, match="goal"):
        config.load(written(tmp_path, text))


def test_a_misspelled_setting_is_refused_rather_than_ignored(tmp_path: Path) -> None:
    """A key that is silently skipped is a setting the user believes they
    changed and did not."""
    text = VALID.replace("cycle_length = 3", "cycle_lenght = 3\ncycle_length = 3")

    with pytest.raises(config.ConfigError, match="cycle_lenght"):
        config.load(written(tmp_path, text))


def test_a_missing_setting_names_it(tmp_path: Path) -> None:
    text = VALID.replace('volume_denominator = "cycle"\n', "")

    with pytest.raises(config.ConfigError, match="volume_denominator"):
        config.load(written(tmp_path, text))


def test_a_split_that_is_not_a_list_of_lists_is_refused(tmp_path: Path) -> None:
    text = (
        "cycle_length = 1\nduration_cap_min = 45\n"
        "volume_denominator = 'cycle'\nsplit = ['chest']\nequipment = ['bands']\n"
    )

    with pytest.raises(config.ConfigError, match="list of one group list"):
        config.load(written(tmp_path, text))


def test_broken_toml_fails_as_broken_toml(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError, match="not valid TOML"):
        config.load(written(tmp_path, "cycle_length = = 3\n"))


# -- where the file lives -----------------------------------------------------


def test_the_environment_variable_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    elsewhere = written(tmp_path, VALID)
    monkeypatch.setenv(config.CONFIG_ENV_VAR, str(elsewhere))

    assert config.config_path() == elsewhere
    assert config.load().cycle_length == 3


def test_without_the_variable_it_is_in_the_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """And the directory the command was launched from does not reach it."""
    monkeypatch.delenv(config.CONFIG_ENV_VAR, raising=False)
    monkeypatch.setenv(home.HOME_ENV_VAR, str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)

    assert config.config_path() == tmp_path / "home" / config.DEFAULT_CONFIG_NAME


# -- the engine reads it and nothing else -------------------------------------

ENGINE_ROOT = Path(__file__).resolve().parents[1] / "src" / "trainer" / "engine"

_WRITE_METHODS = frozenset(
    {"write", "write_text", "write_bytes", "writelines", "unlink", "mkdir", "touch", "rename", "replace"}
)
"""Every way a `Path` or a file object commits something to disk."""

_WRITE_MODES = frozenset("wax+")


def writes(module: Path) -> list[str]:
    """Calls in `module` that put bytes on disk, found in the parse tree.

    Not a substring search. Matching on text would trip on the word `shutil`
    in a comment and, worse, on `open(` -- which would forbid the read-mode
    `open(path, "rb")` that `tomllib` documents as the way to load a file.
    """
    found: list[str] = []
    for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Attribute) and function.attr in _WRITE_METHODS:
            found.append(function.attr)
        if isinstance(function, ast.Name) and function.id == "open":
            mode = next(
                (
                    argument.value
                    for argument in [*node.args[1:2], *(k.value for k in node.keywords if k.arg == "mode")]
                    if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
                ),
                "r",
            )
            if set(mode) & _WRITE_MODES:
                found.append(f"open(..., {mode!r})")
    return found


def test_the_write_guard_catches_the_forms_it_exists_for(tmp_path: Path) -> None:
    """The guard is only worth having if it fails on the code it forbids --
    and only useful if it passes the read-mode open `tomllib` documents."""
    offender = tmp_path / "offender.py"
    offender.write_text(
        "from pathlib import Path\n"
        'Path("training.toml").write_text("cycle_length = 1")\n',
        encoding="utf-8",
    )
    assert writes(offender) == ["write_text"]

    offender.write_text('open("training.toml", "w").close()\n', encoding="utf-8")
    assert writes(offender)

    innocent = tmp_path / "innocent.py"
    innocent.write_text(
        "# shutil and os.replace are only mentioned here\n"
        "import tomllib\n"
        'tomllib.load(open("training.toml", "rb"))\n',
        encoding="utf-8",
    )
    assert writes(innocent) == []


def test_nothing_in_the_engine_writes_the_configuration() -> None:
    """ADR-0003 leaves writing to session 6's onboarding, outside `engine/`.

    A convention not enforced is a convention forgotten in a month, the same
    reasoning `test_engine_boundary.py` is built on. Any engine module that
    knows where the configuration lives is checked for a write of any kind.
    """
    knows_the_path = [
        module
        for module in sorted(ENGINE_ROOT.rglob("*.py"))
        if any(
            token in module.read_text(encoding="utf-8")
            for token in ("config_path", "CONFIG_ENV_VAR", config.DEFAULT_CONFIG_NAME)
        )
    ]
    assert knows_the_path, "no engine module reads the configuration at all"

    for module in knows_the_path:
        assert not writes(module), f"{module.name} writes: {writes(module)}"


def test_reading_the_configuration_leaves_the_file_untouched(tmp_path: Path) -> None:
    path = written(tmp_path, VALID)
    before = path.read_bytes()

    config.load(path)

    assert path.read_bytes() == before


def test_a_file_that_is_not_utf8_is_a_message_and_not_a_traceback(
    tmp_path: Path,
) -> None:
    """The one file the README tells the user to hand-edit, so the editor that
    saved it is not this project's choice. A Windows editor writing cp1252
    would otherwise reach the terminal as a codec traceback."""
    path = tmp_path / "training.toml"
    path.write_bytes(
        VALID.encode("utf-8") + "# perchè quattro allenamenti\n".encode("cp1252")
    )

    with pytest.raises(config.ConfigError, match="not UTF-8"):
        config.load(path)


def test_a_byte_order_mark_does_not_break_the_file(tmp_path: Path) -> None:
    """Notepad writes UTF-8 with a BOM by default, and TOML reads one as part
    of the first key -- a correct file coming back as «Invalid statement at
    line 1, column 1», which names nothing anyone can act on."""
    path = tmp_path / "training.toml"
    path.write_text(VALID, encoding="utf-8-sig")

    assert config.load(path).cycle_length == 3

# -- the equipment, the fifth declaration -------------------------------------


def test_equipment_that_is_not_a_list_of_names_is_refused(tmp_path: Path) -> None:
    text = VALID.replace('equipment = ["dumbbell", "bands"]', 'equipment = "dumbbell"')

    with pytest.raises(config.ConfigError, match="list of the values"):
        config.load(written(tmp_path, text))


def test_declaring_nothing_to_train_with_is_refused_naming_body_only(
    tmp_path: Path,
) -> None:
    """An empty list is a declaration no plan can be made against, and having
    no equipment is a value the catalog has a word for."""
    text = VALID.replace('equipment = ["dumbbell", "bands"]', "equipment = []")

    with pytest.raises(config.ConfigError, match="body only"):
        config.load(written(tmp_path, text))


def test_a_blank_equipment_name_is_refused(tmp_path: Path) -> None:
    text = VALID.replace('equipment = ["dumbbell", "bands"]', 'equipment = ["  "]')

    with pytest.raises(config.ConfigError, match="body only"):
        config.load(written(tmp_path, text))


def test_equipment_named_twice_is_refused(tmp_path: Path) -> None:
    text = VALID.replace(
        'equipment = ["dumbbell", "bands"]', 'equipment = ["dumbbell", "dumbbell"]'
    )

    with pytest.raises(config.ConfigError, match="more than once"):
        config.load(written(tmp_path, text))


def test_the_equipment_vocabulary_is_not_spelled_out_in_this_module() -> None:
    """The standing rule: the values live in the imported catalog, and this
    module reads no database by design (ADR-0003). A value it does not know is
    refused where the catalog is open, by `admissible_set`, which names the
    ones that exist -- so a declaration naming one is read, not rejected."""
    text = VALID.replace(
        'equipment = ["dumbbell", "bands"]', 'equipment = ["a trapeze"]'
    )

    assert config.parse(tomllib.loads(text)).equipment == ("a trapeze",)
