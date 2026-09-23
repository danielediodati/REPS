"""The thirty reports, read out of the document that holds them.

`docs/logging/eval-set.md` is thirty hand-written reports with the outcome each
one must produce, written blind -- the file itself says how that was enforced.
This module only reads it. It decides nothing: every expected document, every
volume figure and the fixture the set needs are the author's, and a scorer that
restated any of them in Python would be measuring a copy that nobody maintains.

**The same shape as `engine/reference_set.py`**, and for the same reason. That
module reads session 2's blind reference set out of markdown rather than
holding sixty rows in source, so a disagreement about a row is a diff in a
document a person can read. A labelled set is a document first.

**Two halves, and the parser knows which is which.** A row under *eighteen
unambiguous reports* carries an expected document and the volume it produces on
both axes; a row under *twelve reports that must make it ask* carries the line
saying what makes it unknowable, and no document at all -- there is none to
write, which is the whole point of it. A row missing what its half requires is
a parse error naming the row, because the acceptance criterion *every must-ask
row states, in one line, what makes it unknowable* is a property of the file
and this is the only thing that reads it.

**The expected document is validated as a document.** Each JSON block goes
through `log.PerformedWorkout` with the row's own blockquote as `report`, so an
expected outcome that could not have been emitted at all is refused here rather
than failing thirty runs later against a model that was right.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import date, timedelta
from pathlib import Path

from trainer import log
from trainer.engine import duration, workouts

LOG_SET_ENV_VAR = "TRAINER_LOG_SET"
"""Environment variable that overrides the log set's location, the way
`TRAINER_DB`, `TRAINER_SNAPSHOT` and `TRAINER_REFERENCE_SET` do -- the suite
points it at a small written-out set rather than at the committed thirty."""

DEFAULT_LOG_SET_PARTS = ("docs", "logging", "eval-set.md")


class LogSetError(RuntimeError):
    """The log set on disk is not usable, and the sentence says which row."""


@dataclass(frozen=True)
class Prescription:
    """One of the four workouts the reports are reports *of*.

    `blocks` is the engine's own prescribed shape, so the fixture writes it
    with `workouts.record_prescribed` and nothing here reimplements a plan.
    The movement pattern and primary muscles the table also carries are read
    by a person and never by this parser: they are the catalog's, and the
    catalog is where the volume figures are computed from.
    """

    name: str
    describes: str
    blocks: tuple[workouts.PrescribedBlock, ...]


@dataclass(frozen=True)
class Row:
    """One report, and what it must produce.

    `expects` is the document for a row the sentence determines, and `None`
    for one it does not -- which is what `must_ask` reads. The two halves are
    one class because they are one set and they run through one loop; what
    differs is which fields are filled, and a row that filled neither or both
    never leaves `parse`.
    """

    name: str
    describes: str
    report: str
    prescription: str | None
    expects: log.PerformedWorkout | None = None
    pattern_volume: dict[str, int] | None = None
    muscle_volume: dict[str, int] | None = None
    unknowable: str | None = None
    wrong_answer: str | None = None
    uncertain: bool = False
    """The author marked the row `?`: it is in the set and its expected
    outcome is honestly labelled, but they say so where they doubt it."""

    @property
    def must_ask(self) -> bool:
        return self.expects is None


@dataclass(frozen=True)
class LogSet:
    """The whole file: what the runner has to set up, and the rows.

    `today` and `history` are read out of the document rather than written
    here, because they are what the expected outcomes were computed against. A
    date typed in two places is a set that drifts from its own answers the
    first time one of them is edited.
    """

    today: str
    history_exercise: str
    history_load_kg: float
    prescriptions: tuple[Prescription, ...]
    rows: tuple[Row, ...]
    bar_unambiguous: int
    """The percentage the unambiguous half must hold, as the set declares it."""
    bar_must_ask: int
    """The percentage the must-ask half must hold, false confidence counted double."""

    @property
    def unambiguous(self) -> tuple[Row, ...]:
        return tuple(row for row in self.rows if not row.must_ask)

    @property
    def must_ask(self) -> tuple[Row, ...]:
        return tuple(row for row in self.rows if row.must_ask)

    def prescription(self, name: str) -> Prescription:
        for found in self.prescriptions:
            if found.name == name:
                return found
        raise LogSetError(f"no prescription called {name!r} in the set")


def log_set_path() -> Path:
    override = os.environ.get(LOG_SET_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return Path.cwd().joinpath(*DEFAULT_LOG_SET_PARTS)


def load(path: Path | None = None) -> LogSet:
    """The set, off disk. Raises when the file is not there, naming it."""
    where = path if path is not None else log_set_path()
    try:
        text = where.read_text(encoding="utf-8")
    except OSError as error:
        raise LogSetError(f"cannot read the log set at {where}: {error}") from None
    return parse(text)


# -- reading the document -----------------------------------------------------

_HEADING = re.compile(r"^###\s+(.*?)\s*$")
_SECTION = re.compile(r"^##\s+(\d+)\.")
_UNCERTAIN = re.compile(r"\s*`\?`\s*$")
_NAMES_A_PRESCRIPTION = re.compile(r"^P\d+$")
_TODAY = re.compile(r"`today`\s+is\s+`(\d{4}-\d{2}-\d{2})`")
_HISTORY = re.compile(r"`([A-Za-z0-9_\-']+)`\s+last recorded at\s+\*\*([\d.]+) kg\*\*")
_BAR = re.compile(
    r"unambiguous half holds at (\d+)%,\s+the must-ask half at (\d+)%"
)
_PRESCRIBED = re.compile(r"^(\d+)\s+(reps|seconds)$")
_COUNTED = re.compile(r"^(.*?)\s+(\d+)$")

_PATTERN_VOLUME, _MUSCLE_VOLUME = "volume (pattern)", "volume (muscle)"
_UNKNOWABLE, _WRONG_ANSWER = "unknowable", "wrong answer"
_BULLETS = (_PATTERN_VOLUME, _MUSCLE_VOLUME, _UNKNOWABLE, _WRONG_ANSWER)
"""The bullets a row can carry. Anything else under a heading -- the `*Note.*`
paragraph, which is written for a reader -- is not read."""

_PRESCRIPTIONS, _UNAMBIGUOUS, _MUST_ASK = "1", "2", "3"
"""The numbered sections, as the document numbers them. Which half a row is in
is read off the section it is under and never off its name: `U` and `A` are
how the author writes them, and a row filed under the wrong heading with the
right letter would be scored by the wrong half in silence."""

_EM_DASH = "—"


def parse(text: str) -> LogSet:
    """The whole set, or the first thing wrong with it.

    Line by line rather than by regex over the whole file: a row is a heading
    followed by a blockquote, sometimes a JSON block and some bullets, and the
    thing that decides what a bullet belongs to is the heading above it.
    """
    today = _today(text)
    exercise_id, load_kg = _history(text)
    bar = _bar(text)
    reader = _Reader(today)
    for line in text.splitlines():
        reader.line(line)
    return reader.finished(today, exercise_id, load_kg, bar)


@dataclass
class _Open:
    """The row or prescription currently being read, before it is complete."""

    name: str
    describes: str
    prescription: str | None
    uncertain: bool
    section: str
    report: str | None = None
    fenced: list[str] | None = None
    document: str | None = None
    bullets: dict[str, str] = dataclass_field(default_factory=dict)
    table: list[list[str]] | None = None
    bullet: str | None = None
    """Which bullet a continuation line belongs to: these wrap at 79 columns
    like every other line in the document, and a rule read out of the first
    line alone would stop mid-sentence."""


class _Reader:
    def __init__(self, today: str) -> None:
        self.today = today
        self.section = ""
        self.open: _Open | None = None
        self.prescriptions: list[Prescription] = []
        self.rows: list[Row] = []

    def line(self, line: str) -> None:
        if self.open is not None and self.open.fenced is not None:
            if line.strip().startswith("```"):
                self.open.document = "\n".join(self.open.fenced)
                self.open.fenced = None
            else:
                self.open.fenced.append(line)
            return

        section = _SECTION.match(line)
        if section is not None:
            self._close()
            self.section = section.group(1)
            return

        heading = _HEADING.match(line)
        if heading is not None:
            self._close()
            self.open = _headed(heading.group(1), self.section)
            return

        if self.open is None:
            return
        self._body(self.open, line)

    def _body(self, open: _Open, line: str) -> None:
        stripped = line.strip()
        if stripped.startswith("> "):
            if open.report is not None:
                raise LogSetError(f"{open.name}: two reports under one heading")
            open.report = stripped[2:].strip()
            return
        if stripped.startswith("```"):
            if open.document is not None:
                raise LogSetError(f"{open.name}: two expected documents")
            open.fenced = []
            return
        if stripped.startswith("|"):
            if open.table is None:
                open.table = []
            open.table.append([cell.strip() for cell in stripped.strip("|").split("|")])
            return
        if stripped.startswith("- **"):
            self._bullet(open, stripped)
            return
        if open.bullet is not None and stripped and line.startswith("  "):
            self._continue(open, stripped)
            return
        # A blank line, or the *Note.* paragraph, which is written for a
        # reader and is not scored. Either way the bullet above has ended.
        open.bullet = None

    def _bullet(self, open: _Open, stripped: str) -> None:
        """One `- **label:** ...` line, kept whole and read later.

        Every bullet the set uses is kept as text and parsed when the row
        closes, so all four wrap the same way. Parsing a volume line where it
        starts would read the first line of a bullet that wrapped and refuse
        the row for a trailing comma -- blaming the author for following the
        document's own 79-column habit.
        """
        label, _, rest = stripped[len("- **") :].partition("**")
        name = label.strip().rstrip(":").lower()
        if name in _BULLETS:
            open.bullets[name] = rest.lstrip(": ").strip()
            open.bullet = name
        else:
            open.bullet = None

    def _continue(self, open: _Open, stripped: str) -> None:
        if open.bullet is not None and open.bullet in open.bullets:
            open.bullets[open.bullet] = f"{open.bullets[open.bullet]} {stripped}"

    def _close(self) -> None:
        open, self.open = self.open, None
        if open is None:
            return
        if open.section == _PRESCRIPTIONS:
            self.prescriptions.append(_prescription(open))
        elif open.section in (_UNAMBIGUOUS, _MUST_ASK):
            self.rows.append(_row(open, self.today))

    def finished(
        self, today: str, exercise_id: str, load_kg: float, bar: tuple[int, int]
    ) -> LogSet:
        self._close()
        if not self.prescriptions:
            raise LogSetError("the set holds no prescriptions")
        if not self.rows:
            raise LogSetError("the set holds no reports")

        seen: set[str] = set()
        known = {prescription.name for prescription in self.prescriptions}
        for row in self.rows:
            if row.name in seen:
                raise LogSetError(f"{row.name}: two rows under one name")
            seen.add(row.name)
            if row.prescription is not None and row.prescription not in known:
                raise LogSetError(
                    f"{row.name} is about {row.prescription}, which the set "
                    f"does not prescribe"
                )
        return LogSet(
            today=today,
            history_exercise=exercise_id,
            history_load_kg=load_kg,
            prescriptions=tuple(self.prescriptions),
            rows=tuple(self.rows),
            bar_unambiguous=bar[0],
            bar_must_ask=bar[1],
        )


def _headed(heading: str, section: str) -> _Open:
    """A `### ` line, split into the name, what it is, and what it is about.

    The em dash separates them because that is how the document is written;
    the `?` marker is taken off first, so a row can be marked whether or not
    it names a prescription.
    """
    uncertain = bool(_UNCERTAIN.search(heading))
    parts = [part.strip() for part in _UNCERTAIN.sub("", heading).split(_EM_DASH)]
    name = parts[0]
    prescription = None
    rest = parts[1:]
    if rest and _NAMES_A_PRESCRIPTION.match(rest[-1]):
        prescription = rest[-1]
        rest = rest[:-1]
    return _Open(
        name=name,
        describes=" - ".join(part for part in rest if part),
        prescription=prescription,
        uncertain=uncertain,
        section=section,
    )


def _counts(name: str, said: str) -> dict[str, int]:
    """`horizontal push 4, vertical push 3` as a mapping.

    The bucket names are not checked against anything here: they are the
    catalog's own movement patterns and primary muscles, and this file has
    been wrong once already by keeping a copy of a vocabulary that lives in
    the data. A name nothing in the catalog answers to shows up as a volume
    the run did not produce, which is a failing row and not a parse error.
    """
    counts: dict[str, int] = {}
    for part in said.split(","):
        counted = _COUNTED.match(part.strip())
        if counted is None:
            raise LogSetError(f"{name}: {part.strip()!r} is not a bucket and a count")
        counts[counted.group(1)] = int(counted.group(2))
    return counts


def _row(open: _Open, today: str) -> Row:
    if not open.report:
        raise LogSetError(f"{open.name}: no report under the heading")

    unknowable = open.bullets.get(_UNKNOWABLE)
    wrong_answer = open.bullets.get(_WRONG_ANSWER)
    pattern_said = open.bullets.get(_PATTERN_VOLUME)
    muscle_said = open.bullets.get(_MUSCLE_VOLUME)

    if open.section == _MUST_ASK:
        if open.document is not None:
            raise LogSetError(
                f"{open.name} must make it ask, so there is no document it "
                f"should have written"
            )
        if not unknowable:
            raise LogSetError(
                f"{open.name}: a must-ask row says in one line what makes it "
                f"unknowable, and this one says nothing"
            )
        if not wrong_answer:
            raise LogSetError(
                f"{open.name}: a must-ask row names the value a confident "
                f"model fills in instead"
            )
        return Row(
            name=open.name,
            describes=open.describes,
            report=open.report,
            prescription=open.prescription,
            unknowable=unknowable,
            wrong_answer=wrong_answer,
            uncertain=open.uncertain,
        )

    if open.document is None:
        raise LogSetError(f"{open.name}: no expected document under the heading")
    if pattern_said is None or muscle_said is None:
        raise LogSetError(
            f"{open.name}: an unambiguous row states the volume it produces "
            f"on both axes"
        )
    return Row(
        name=open.name,
        describes=open.describes,
        report=open.report,
        prescription=open.prescription,
        expects=_expected(open.name, open.document, open.report, today),
        pattern_volume=_counts(open.name, pattern_said),
        muscle_volume=_counts(open.name, muscle_said),
        uncertain=open.uncertain,
    )


_PLACEHOLDER = re.compile(r"^<.*>$")
"""A field the document deliberately does not pin down, written as prose
between angle brackets -- `<any date after 2026-09-10>`. The set declares two
of them and `retest_date` is the one that has to survive validation: which day
the agent picks is a judgement the document does not constrain, so it is
scored as *after today* and never by equality. Filled in with a real date here
purely so the expected outcome is a document the schema accepts."""


def _expected(
    name: str, document: str, report: str, today: str
) -> log.PerformedWorkout:
    """The JSON block as a document, with the blockquote as its `report`.

    The document is written without one on purpose -- `report` is the user's
    own words and the blockquote already holds them, and two copies of one
    sentence is one copy that can be edited without the other. It is put back
    here, so what the row expects is a whole document and can be compared
    field by field against a whole document.
    """
    try:
        fields = json.loads(document)
    except json.JSONDecodeError as error:
        raise LogSetError(
            f"{name}: the expected document is not JSON: {error}"
        ) from None
    if not isinstance(fields, dict):
        raise LogSetError(f"{name}: the expected document is not an object")
    if "report" in fields:
        raise LogSetError(
            f"{name}: the expected document carries a `report` of its own; the "
            f"blockquote above it is the one the runner reads"
        )
    fields["report"] = report
    exclusion = fields.get("proposed_exclusion")
    if isinstance(exclusion, dict):
        retest = exclusion.get("retest_date")
        if isinstance(retest, str) and _PLACEHOLDER.match(retest):
            exclusion["retest_date"] = _after(today)
    try:
        return log.PerformedWorkout.model_validate(fields)
    except Exception as error:  # pydantic's own, kept as its sentence
        raise LogSetError(
            f"{name}: the expected document is not one this project could "
            f"emit: {error}"
        ) from None


def _after(today: str) -> str:
    return (date.fromisoformat(today) + timedelta(days=1)).isoformat()


def _prescription(open: _Open) -> Prescription:
    """One of the four workouts, out of its markdown table.

    Rows carrying the same block number are one block -- that is a superset,
    and P4 has one. `rounds` and `rest` belong to the block, so a table that
    gave two different values for one of them is a table nobody can write a
    block from and it is refused here.
    """
    if not open.table:
        raise LogSetError(f"{open.name}: no table under the prescription")

    grouped: list[tuple[int, int, int, list[duration.BlockItem]]] = []
    for cells in open.table:
        if len(cells) < 5 or not cells[0].isdigit():
            continue  # the header and the `|---|` line under it
        position, rounds, rest = int(cells[0]), int(cells[1]), int(cells[2])
        if any(position == seen for seen, _, _, _ in grouped[:-1]):
            # A block's rows go together: that is what makes them one block,
            # and it is how a superset is written. Listed apart -- `1, 2, 1`
            # -- the rows would quietly become two blocks with the same
            # number, and every volume figure computed from them would be
            # right about a workout the table does not describe.
            raise LogSetError(
                f"{open.name}: block {position} is listed again after "
                f"another block; a block's rows go together"
            )
        exercise_id = cells[3].strip("`")
        prescribed = _PRESCRIBED.match(cells[4])
        if prescribed is None:
            raise LogSetError(
                f"{open.name}: {cells[4]!r} is not a number of reps or seconds"
            )
        amount, unit = int(prescribed.group(1)), prescribed.group(2)
        item = duration.BlockItem(
            exercise_id=exercise_id,
            reps=amount if unit == "reps" else None,
            seconds=amount if unit == "seconds" else None,
        )
        if grouped and grouped[-1][0] == position:
            if grouped[-1][1] != rounds or grouped[-1][2] != rest:
                raise LogSetError(
                    f"{open.name}: block {position} gives two different round "
                    f"counts or rests; both belong to the block"
                )
            grouped[-1][3].append(item)
        else:
            grouped.append((position, rounds, rest, [item]))

    if not grouped:
        raise LogSetError(f"{open.name}: the table holds no blocks")
    return Prescription(
        name=open.name,
        describes=open.describes,
        blocks=tuple(
            workouts.PrescribedBlock(
                block=duration.Block(items=tuple(items), rounds=rounds, rest=rest),
                # A prescribed block carries the reason it was prescribed. The
                # fixture's reason is which of the four workouts it is: nobody
                # reads it, and a blank one would print as a plan with nothing
                # behind it the day somebody dumps the fixture to look at it.
                reason=f"{open.name} - {open.describes}",
            )
            for _, rounds, rest, items in grouped
        ),
    )


def _today(text: str) -> str:
    found = _TODAY.search(text)
    if found is None:
        raise LogSetError(
            "the set does not say what day it is run against; the runner's "
            "section states it as `today` is `YYYY-MM-DD`"
        )
    return found.group(1)


def _bar(text: str) -> tuple[int, int]:
    found = _BAR.search(text)
    if found is None:
        raise LogSetError(
            "the set does not say what rate it must hold; the runner's section "
            "states it as the unambiguous half holds at N%, the must-ask half at N%"
        )
    unambiguous, must_ask = int(found.group(1)), int(found.group(2))
    if not (0 < unambiguous <= 100 and 0 < must_ask <= 100):
        raise LogSetError(
            f"the set's bar is {unambiguous}% and {must_ask}%; each is 1 to 100"
        )
    return unambiguous, must_ask


def _history(text: str) -> tuple[str, float]:
    found = _HISTORY.search(text)
    if found is None:
        raise LogSetError(
            "the set does not say what load history it needs; the runner's "
            "section states it as `Exercise_Id` last recorded at **N kg**"
        )
    return found.group(1), float(found.group(2))


def unknown_exercises(
    connection: sqlite3.Connection, holds: LogSet
) -> tuple[str, ...]:
    """Ids the set names that this catalog does not have, in the set's order.

    Checked before anything reaches a provider: a prescription naming an id
    the catalog lost is thirty runs measuring a fixture that could not be
    written, and against an empty database it is every id in the file. The
    caller decides what to say about it -- a missing catalog is a state, not a
    typo, and CLAUDE.md's standing rule is that the state gets named.
    """
    named: list[str] = []
    for prescription in holds.prescriptions:
        for block in prescription.blocks:
            named.extend(item.exercise_id for item in block.block.items)
    for row in holds.rows:
        if row.expects is None:
            continue
        named.extend(
            item.exercise_id for block in row.expects.blocks for item in block.items
        )
    named.append(holds.history_exercise)

    missing: list[str] = []
    for exercise_id in dict.fromkeys(named):
        found = connection.execute(
            "SELECT 1 FROM exercises WHERE id = ?", (exercise_id,)
        ).fetchone()
        if found is None:
            missing.append(exercise_id)
    return tuple(missing)
