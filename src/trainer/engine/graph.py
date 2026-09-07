"""Loading the `variant_of` / `regression_of` graph from `docs/enrichment/graph.md`.

Recognising that two named movements are the same, or that one is easier than
the other, needs reading a movement's own name and instructions -- a single
row's columns cannot supply it, and `enrichment.derive()` never writes either
field. `docs/enrichment/definitions.md` says so explicitly. This module does
not decide anything: it reads what a person decided and writes it, and it
refuses the two shapes that would make the graph unusable before anything
touches the database -- a chain where `variant_of` should be a group of one
representative and its members, and a cycle where `regression_of` should be a
strict "easier points at harder".

It also reads the graph back: `compare()` answers, for one pair of ids, what
each row carries and whether the two are the same movement or one a regression
of the other. That read lives here rather than beside the catalog because the
answer is about the edges this module wrote, and a query that outlived its
writer's rules would be the first thing to disagree with them.
"""

from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from trainer.engine import catalog
from trainer.engine.catalog import Enrichment, known_ids

GRAPH_ENV_VAR = "TRAINER_GRAPH"
"""Environment variable that overrides the graph file location, the same way
`TRAINER_REFERENCE_SET` and `TRAINER_RESIDUE` do for their own files."""

DEFAULT_GRAPH_PARTS = ("docs", "enrichment", "graph.md")


class GraphError(RuntimeError):
    """The graph file, or the graph it describes, is not usable."""


@dataclass(frozen=True)
class VariantGroup:
    """One movement, the same across equipment or a minor stance change.

    `representative` is what every `member` points at -- a star, never a
    chain, so a query never has to follow `variant_of` more than one hop.
    """

    representative: str
    members: tuple[str, ...]


@dataclass(frozen=True)
class Regression:
    """`easier` is a `regression_of` `harder` -- directional, never the reverse."""

    easier: str
    harder: str


def graph_path() -> Path:
    override = os.environ.get(GRAPH_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return Path.cwd().joinpath(*DEFAULT_GRAPH_PARTS)


_ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|.*\|$")
"""Two backtick-quoted ids and a note. A header or separator row has no
backticks and never matches, so neither needs to be skipped explicitly."""


def _section(text: str, heading: str) -> str:
    marker = f"## {heading}"
    start = text.find(marker)
    if start == -1:
        raise GraphError(f"no {marker!r} section in the graph file")
    rest = text[start + len(marker) :]
    end = rest.find("\n## ")
    return rest if end == -1 else rest[:end]


def _pairs(text: str, heading: str) -> list[tuple[str, str]]:
    return [
        (match.group(1), match.group(2))
        for line in _section(text, heading).splitlines()
        if (match := _ROW.match(line.strip()))
    ]


def parse(text: str) -> tuple[tuple[VariantGroup, ...], tuple[Regression, ...]]:
    """Both tables at once, since neither is usable without the other having
    been read too: `apply()` needs the complete picture to validate."""
    groups: dict[str, list[str]] = {}
    for representative, member in _pairs(text, "Variant groups"):
        groups.setdefault(representative, []).append(member)
    variants = tuple(
        VariantGroup(representative, tuple(members))
        for representative, members in groups.items()
    )

    regressions = tuple(
        Regression(easier, harder) for easier, harder in _pairs(text, "Regression edges")
    )
    return variants, regressions


def load(
    path: Path | None = None,
) -> tuple[tuple[VariantGroup, ...], tuple[Regression, ...]]:
    target = path if path is not None else graph_path()
    if not target.is_file():
        raise GraphError(f"no graph file at {target}")
    variants, regressions = parse(target.read_text(encoding="utf-8"))
    if not variants and not regressions:
        raise GraphError(f"{target} names no variant group and no regression")
    return variants, regressions


def validate(variants: tuple[VariantGroup, ...], regressions: tuple[Regression, ...]) -> None:
    """Refuse before writing anything: a chain in `variant_of`, an id in two
    variant groups, or a cycle in `regression_of`."""
    representatives = {group.representative for group in variants}
    owner: dict[str, str] = {}
    for group in variants:
        if group.representative in owner:
            raise GraphError(
                f"{group.representative!r} is a representative and also a member of "
                f"{owner[group.representative]!r}'s group -- that is a chain, not a group"
            )
        for member in group.members:
            if member in representatives:
                raise GraphError(
                    f"{member!r} is a member of {group.representative!r}'s group and "
                    "the representative of its own -- that is a chain, not a group"
                )
            if member in owner:
                raise GraphError(
                    f"{member!r} belongs to both {owner[member]!r}'s group and "
                    f"{group.representative!r}'s group"
                )
            owner[member] = group.representative

    edges: dict[str, list[str]] = {}
    for edge in regressions:
        edges.setdefault(edge.easier, []).append(edge.harder)

    visiting: set[str] = set()
    settled: set[str] = set()

    def visit(node: str) -> None:
        if node in settled:
            return
        if node in visiting:
            raise GraphError(f"regression_of has a cycle through {node!r}")
        visiting.add(node)
        for neighbour in edges.get(node, ()):
            visit(neighbour)
        visiting.remove(node)
        settled.add(node)

    for node in edges:
        visit(node)


@dataclass(frozen=True)
class GraphReport:
    variant_groups: int
    variant_rows: tuple[str, ...]
    regression_rows: tuple[str, ...]


def apply(
    connection: sqlite3.Connection,
    variants: tuple[VariantGroup, ...],
    regressions: tuple[Regression, ...],
) -> GraphReport:
    """Validate, then write every edge with `curated` provenance."""
    validate(variants, regressions)

    named = (
        {group.representative for group in variants}
        | {member for group in variants for member in group.members}
        | {edge.easier for edge in regressions}
        | {edge.harder for edge in regressions}
    )
    unknown = sorted(named - known_ids(connection))
    if unknown:
        raise GraphError(f"the graph names ids the catalog does not have: {', '.join(unknown)}")

    variant_rows: list[str] = []
    regression_rows: list[str] = []
    connection.execute("BEGIN IMMEDIATE")
    try:
        for group in variants:
            for member in group.members:
                connection.execute(
                    "UPDATE exercises SET variant_of = ?, variant_of_source = 'curated' "
                    "WHERE id = ?",
                    (group.representative, member),
                )
                variant_rows.append(member)
        for edge in regressions:
            connection.execute(
                "UPDATE exercises SET regression_of = ?, regression_of_source = 'curated' "
                "WHERE id = ?",
                (edge.harder, edge.easier),
            )
            regression_rows.append(edge.easier)
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    connection.execute("COMMIT")

    return GraphReport(
        variant_groups=len(variants),
        variant_rows=tuple(variant_rows),
        regression_rows=tuple(regression_rows),
    )


# --- reading the graph back ----------------------------------------------
#
# Everything above writes the curated file into the table. What follows reads
# the two columns back out for one pair of ids -- the question TRAINER.md's
# `compare_variants` asks, and the reason the tool had nothing to wrap until
# this module existed.


@dataclass(frozen=True)
class Comparison:
    """Two exercises side by side, and what the graph says about the pair.

    The two relations are separate fields rather than one verdict, because
    they are independent facts and a single string would have to rank them:
    a regression is *also* a same-movement pair whenever the curated file says
    both, and a caller looking for a substitution wants to know each.

    `easier` names an id rather than a side, so that reading the answer does
    not depend on remembering which argument was `a`.
    """

    a: Enrichment
    b: Enrichment
    same_movement: bool
    easier: str | None

    @property
    def summary(self) -> str:
        """The pair in one sentence, for whoever is not going to read fields."""
        harder = (
            self.b.exercise_id
            if self.easier == self.a.exercise_id
            else self.a.exercise_id
        )
        if self.a.exercise_id == self.b.exercise_id:
            return "the same exercise"
        if self.same_movement and self.easier:
            return f"the same movement; {self.easier} is the easier of the two"
        if self.same_movement:
            return "the same movement, interchangeable"
        if self.easier:
            return f"{self.easier} is a regression of {harder}"
        return "neither the same movement nor a regression of one another"


def applied_to(connection: sqlite3.Connection) -> bool:
    """Has this graph ever been written into the catalog?

    `trainer enrich curated` is a command of its own, separate from `db
    import` and `enrich derive`, and a database that has had the other two run
    on it looks completely enriched while holding no edges at all. Read from
    the provenance columns rather than the value columns: an exercise in no
    variant group legitimately has `variant_of` null, so the values cannot
    tell *nobody decided* from *decided to be nothing*.
    """
    row = connection.execute(
        "SELECT COUNT(*) AS total FROM exercises WHERE variant_of_source IS NOT NULL "
        "OR regression_of_source IS NOT NULL"
    ).fetchone()
    return int(row["total"]) > 0


def compare(connection: sqlite3.Connection, id_a: str, id_b: str) -> Comparison:
    """What the two rows carry, and the relation the graph holds between them.

    Only the direct edge. `variant_of` is a star by construction, so same-group
    membership is always one hop; `regression_of` may chain, and a chain is
    deliberately not followed -- *A is easier than B, which is easier than C*
    does not make A a usable stand-in for C, and answering as though it did
    would put a substitution in the agent's hands that nobody decided.

    A catalog the graph was never applied to is refused before anything is
    read. Answered on the edges alone it comes back as *neither the same
    movement nor a regression of one another* for TRAINER.md's own running
    example -- a decided **no**, indistinguishable from a real one, off which
    an agent would refuse a legitimate substitution with nothing in the
    output to say why. CLAUDE.md's standing rule, in the case it was written
    for: check the state first and name it.
    """
    if not applied_to(connection):
        raise GraphError(
            "no variant or regression edge has been written into this "
            "catalog, so nothing can be said about how two exercises relate; "
            "run `trainer enrich curated` first"
        )

    a = catalog.enrichment(connection, id_a)
    b = catalog.enrichment(connection, id_b)

    if id_a == id_b:
        # One exercise against itself. Left to the edges it answers *the same
        # movement* for a group member -- both sides carry the same
        # `variant_of` -- and *neither* for a representative or an exercise in
        # no group, which is the same question getting two answers depending
        # on where in the graph the id happens to sit.
        return Comparison(a=a, b=b, same_movement=True, easier=None)

    same_movement = (
        a.variant_of == b.exercise_id
        or b.variant_of == a.exercise_id
        or (a.variant_of is not None and a.variant_of == b.variant_of)
    )
    if a.regression_of == b.exercise_id:
        easier: str | None = a.exercise_id
    elif b.regression_of == a.exercise_id:
        easier = b.exercise_id
    else:
        easier = None

    return Comparison(a=a, b=b, same_movement=same_movement, easier=easier)
