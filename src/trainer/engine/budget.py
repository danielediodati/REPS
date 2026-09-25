"""The arithmetic of the time available.

Two functions, both arithmetic. `remaining_budget` answers *how much room is
left* so a plan can be built against a budget instead of trimmed to one;
`allocate` divides a workout's minutes among the muscle groups it trains, on
proportions it is handed.

**Neither decides how to train.** There is no cut in this module and there is
not going to be one: a plan that does not fit is rejected by the validator,
never silently repaired, because repairing it hides from whoever built it that
the arithmetic was wrong. And there is no table of proportions here -- *60-40
on two groups* is what one workout might look like, not a law, and it means
nothing the moment a workout holds three. ADR-0001.
"""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Mapping

from trainer.engine import muscle_groups
from trainer.engine.duration import Plan, plan_duration

PROPORTION_TOLERANCE = 1e-9
"""How far the proportions may sum from 1 and still be accepted.

Not zero, because a caller who *computes* proportions rather than typing them
can land a bit short: normalising a 1:6:15 ratio gives three floats that sum
to `0.9999999999999999`, and refusing that would reject a split that is
correct by construction. Typed proportions are mostly exact -- three equal
thirds do sum to 1.0 -- so this is insurance against arithmetic upstream, not
against the ordinary case.

Wide enough for that and far too narrow for what the check exists to catch:
0.6 and 0.3 is ten percent of the workout gone, seven orders of magnitude
outside this.
"""


class BudgetError(RuntimeError):
    """Arithmetic that cannot be done honestly: a budget that is not a whole
    number of minutes, or proportions that do not describe a whole workout."""


def _whole(what: str, value: int) -> None:
    """Minutes are whole and not negative.

    The type check is not redundant with the annotation. mypy stops a typed
    caller; ticket 05's MCP wrapper is the untyped one, and a JSON number
    decoded through a float path arrives as `40.0`. Left alone that reaches
    `math.floor` and a list slice, and comes back as `TypeError: slice
    indices must be integers` -- a stack trace instead of a sentence, for
    what is really a caller passing the right number in the wrong type.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise BudgetError(f"{what} is a whole number of minutes, got {value!r}")
    if value < 0:
        raise BudgetError(f"{what} cannot be negative, got {value}")


def remaining_budget(
    connection: sqlite3.Connection, partial_plan: Plan, budget: int
) -> int:
    """How many minutes are left once `partial_plan` is committed.

    Negative when the plan is already over, and deliberately not clamped at
    zero: *how far over* is what the caller has to act on, and a floor would
    hide the size of the miss behind the same answer as an exact fit.

    Whole minutes, because that is what a budget is spoken in. `plan_duration`
    rounds up, so the room reported is never more than the room there is --
    the error, where there is one, is always towards saying there is less
    time, never more.

    The plan's own errors travel: an exercise the catalog does not have fails
    as itself rather than being absorbed into a budget that happens to look
    full.
    """
    _whole("a budget", budget)
    return budget - plan_duration(connection, partial_plan)


def allocate(minutes: int, proportions: Mapping[str, float]) -> dict[str, int]:
    """Divide `minutes` among the groups, on the proportions given.

    The proportions are the caller's, over any number of groups; this function
    carries none of its own and never invents one for a group that was left
    out. The *names* are not the caller's: each has to be a name a slot of the
    split may hold -- one of the six groups or a muscle in one -- read from the
    mapping that ships with the package (`muscle_groups.MUSCLE_GROUPS_PATH`)
    rather than from a copy kept here. Ticket 02 shipped without this check because the
    vocabulary did not exist anywhere a function could read it, and a mapping
    keyed by a typo returns minutes nobody can look up -- the caller who wrote
    `Chest` gets a `KeyError` on `allocated["chest"]` a long way from the
    mistake.

    They must describe a whole workout. Proportions summing to anything but 1
    are refused rather than normalised: a caller who typed 0.6 and 0.3 meant
    something, and quietly scaling it to 0.67 and 0.33 would turn their typo
    into a different plan that runs the full time and trains something else.

    A group may come out at zero minutes -- at two percent of ten there is no
    minute to give. That is honest arithmetic, and the caller who chose the
    proportions can see it. A group asking for *nothing at all* is a different
    thing and is refused: it is not being trained, and it belongs out of the
    mapping rather than in it at zero.
    """
    _whole("minutes", minutes)
    if not proportions:
        raise BudgetError("allocate needs at least one group")

    # Re-raised as a `BudgetError`, so reading the vocabulary does not widen
    # this function's failure vocabulary: a caller wrapping the arithmetic in
    # `except BudgetError` -- ticket 05's MCP wrapper among them -- would
    # otherwise be handed an uncaught `MuscleGroupError` the day the packaged
    # mapping cannot be read.
    try:
        muscle_groups.committed().muscles_in(list(proportions))
    except muscle_groups.MuscleGroupError as error:
        raise BudgetError(f"the muscle groups cannot be read: {error}") from error
    except ValueError as error:
        raise BudgetError(str(error)) from error

    for group, proportion in proportions.items():
        if proportion <= 0:
            raise BudgetError(
                f"{group!r} is allocated {proportion}; a group that is not "
                "being trained belongs out of the mapping, not in it at zero"
            )

    total = math.fsum(proportions.values())
    if not math.isclose(total, 1.0, rel_tol=PROPORTION_TOLERANCE):
        # A percentage with significant digits rather than whole points.
        # `:.0%` reports 0.5 and 0.4999 as "0% of the workout unaccounted
        # for", which reads like the check misfired and names nothing the
        # caller can go and fix; `:.3g` says 0.01%. `:g` on the total also
        # keeps 0.6 + 0.3 from printing as 0.8999999999999999.
        side = "unaccounted for" if total < 1 else "over-committed"
        raise BudgetError(
            f"the proportions sum to {total:g}, not 1 -- "
            f"{abs(1 - total) * 100:.3g}% of the workout is {side}"
        )

    # Floor first, then hand out what floor left over. Largest remainder: the
    # spare minutes go to the groups rounding stripped the most from, not to
    # the largest proportion -- at 11 minutes split 55/45 the shares are 6.05
    # and 4.95, and giving the minute to the larger proportion would hand it
    # to the group that was five hundredths short instead of the one that was
    # nearly a whole minute short. (The ticket's prose said largest
    # proportion; this is the same idea done correctly, and it is the
    # apportionment method the name comes from.)
    exact = {group: minutes * proportion for group, proportion in proportions.items()}
    allocated = {group: math.floor(share) for group, share in exact.items()}

    # Sorted by shortfall descending, then by name, so two callers passing the
    # same groups in a different order get the same answer.
    order = sorted(
        proportions,
        key=lambda group: (-(exact[group] - allocated[group]), group),
    )
    for group in order[: minutes - sum(allocated.values())]:
        allocated[group] += 1
    return allocated
