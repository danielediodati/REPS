"""The six muscle groups, read from the committed mapping.

`src/trainer/data/muscle-groups.md` assigns each of the catalog's seventeen
`primary_muscles` values to one of six groups -- or to none, in `neck`'s case.
This module reads that file. It decides nothing: the groupings are curated, the
reasoning for each one is in the file's own `why` column, and the six names
exist nowhere else in the project.

**Read from the mapping, never copied.** A list of the six spelled out in code
is the hand-copied vocabulary CLAUDE.md's standing rule was written about --
the catalog's equipment list was transcribed once from a partial read and was
wrong in three places. `budget.allocate` checks its group names against
`groups()` for exactly that reason.

The file ships inside the package rather than under `docs/`, resolved against
`__file__` the way `catalog.DATASET_PATH` is: `allocate` is arithmetic called
from inside an agent loop, and a vocabulary that resolves against the current
working directory would answer differently depending on where the process was
started.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path

MUSCLE_GROUPS_PATH = Path(__file__).resolve().parent.parent / "data" / "muscle-groups.md"

_COLUMNS = ("muscle", "group", "why")
"""`| muscle | group | why |`. `why` is read by a person and not by this
parser; it is the reason the file is markdown rather than a dict literal, and
a row missing it is a row whose decision has lost its reasoning."""

NO_GROUP = "-"
"""The `group` cell for a muscle no split ever asks for.

Spelled rather than left blank: an empty cell is indistinguishable from a row
somebody started and did not finish, and this mapping's whole promise is that
every one of the seventeen was decided.
"""


class MuscleGroupError(RuntimeError):
    """The mapping file on disk is not usable."""


@dataclass(frozen=True)
class MuscleGroups:
    """The mapping, whole: every muscle the file names, and its group.

    `groups` is derived rather than stored, so the vocabulary cannot drift from
    the assignments it is the set of.
    """

    by_muscle: tuple[tuple[str, str | None], ...]

    @property
    def muscles(self) -> tuple[str, ...]:
        return tuple(muscle for muscle, _ in self.by_muscle)

    @property
    def groups(self) -> tuple[str, ...]:
        """The distinct groups, alphabetically -- the project's vocabulary.

        Alphabetical because it has to be the same order twice: this tuple is
        what an error message lists, and a listing whose order depends on the
        order rows happen to sit in the file is a diff nobody asked for.
        """
        return tuple(sorted({group for _, group in self.by_muscle if group is not None}))

    @property
    def names(self) -> tuple[str, ...]:
        """What a slot of the split may name: the groups and every muscle that is in one, alphabetically."""
        grouped = {muscle for muscle, group in self.by_muscle if group is not None}
        return tuple(sorted(set(self.groups) | grouped))

    def muscles_in(self, names: Sequence[str]) -> tuple[str, ...]:
        """The muscles a slot's names cover, in mapping order; `ValueError` for a name no slot may hold."""
        covered: dict[str, str] = {}
        for name in dict.fromkeys(names):
            if name in self.groups:
                muscles = [m for m, group in self.by_muscle if group == name]
            elif name in self.names:
                muscles = [name]
            elif name in self.muscles:
                raise ValueError(
                    f"{name!r} is a muscle in no group; {MUSCLE_GROUPS_PATH.name} "
                    "keeps it out of every split"
                )
            else:
                raise ValueError(
                    f"{name!r} is not a muscle group or a muscle; the groups are "
                    f"{', '.join(self.groups)}, and a muscle is any of "
                    f"{', '.join(n for n in self.names if n not in self.groups)}"
                )
            for muscle in muscles:
                if muscle in covered:
                    # `chest` is a group and its own muscle; the pair is one name, never an overlap.
                    raise ValueError(
                        f"{covered[muscle]!r} and {name!r} both train {muscle!r}; "
                        "name the group or the muscle, not both"
                    )
                covered[muscle] = name
        return tuple(m for m in self.muscles if m in covered)

    def group_of(self, muscle: str) -> str | None:
        """The group this muscle is allocated under, or `None` for one that is
        deliberately in no group.

        A muscle the file does not name raises `KeyError`, not
        `MuscleGroupError`: the mapping is fine, the caller asked about
        something that is not in it, and reporting that as *«the muscle group
        mapping is unusable»* points at a committed file that has nothing
        wrong with it. Never confused with a muscle mapped to no group, which
        is a decision and returns `None`.
        """
        for name, group in self.by_muscle:
            if name == muscle:
                return group
        raise KeyError(
            f"the mapping does not name the muscle {muscle!r}; "
            f"add it to {MUSCLE_GROUPS_PATH.name}"
        )


def parse(text: str) -> MuscleGroups:
    """Read the mapping's data rows -- `| muscle | group | why |`.

    The `why` column is read by a person and not by this parser; it is the
    reason the file exists in markdown rather than as a dictionary literal.
    """
    rows: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        muscle = cells[0].strip("`").strip()
        # The header row and the separator row, neither of which claims to be
        # a muscle. Everything else does.
        if muscle.lower() == "muscle" or (muscle and set(muscle) <= {"-", ":"}):
            continue
        if not muscle:
            # A blank first cell is prose that happens to start with a pipe --
            # unless the rest of the row is filled in, in which case it is a
            # hand-edit that blanked the muscle and the row would otherwise
            # vanish from the mapping without a word. Blanking `biceps`,
            # `triceps` and `forearms` would take `arms` out of the vocabulary
            # and make `allocate` start refusing it as a typo.
            if any(cell.strip("`").strip() for cell in cells[1:]):
                raise MuscleGroupError(
                    f"a row names no muscle but says {' | '.join(cells[1:])!r}; "
                    "every one of the catalog's muscles is decided here"
                )
            continue
        # Checked *after* that, never before: a row short of a cell is a
        # hand-edit that dropped the `why` column, and skipping it on its
        # length would take the muscle out of the mapping altogether -- time
        # allocated to its group would silently stop covering it.
        if len(cells) < len(_COLUMNS):
            raise MuscleGroupError(
                f"the row for {muscle!r} has {len(cells)} cell(s); a row is "
                f"{' | '.join(_COLUMNS)}"
            )
        group_cell = cells[1].strip("`").strip()

        if muscle in seen:
            raise MuscleGroupError(f"the mapping names {muscle!r} twice")
        seen.add(muscle)

        if not group_cell:
            raise MuscleGroupError(
                f"{muscle!r} has an empty group cell; write {NO_GROUP!r} to say "
                "it belongs to no group, so a blank is never mistaken for a "
                "row somebody left unfinished"
            )
        rows.append((muscle, None if group_cell == NO_GROUP else group_cell))

    if not rows:
        raise MuscleGroupError("the mapping has no data rows")
    return MuscleGroups(tuple(rows))


def load(path: Path = MUSCLE_GROUPS_PATH) -> MuscleGroups:
    if not path.is_file():
        raise MuscleGroupError(f"no muscle group mapping at {path}")
    return parse(path.read_text(encoding="utf-8"))


@cache
def committed() -> MuscleGroups:
    """The mapping that ships with the package.

    Cached: it is read on every `allocate` call, it cannot change while the
    process runs, and parsing seventeen rows again each time buys nothing.
    Tests that want a different mapping call `parse` or `load` with their own
    path rather than going through here.
    """
    return load()


def groups() -> tuple[str, ...]:
    """The six, read from the committed mapping."""
    return committed().groups
