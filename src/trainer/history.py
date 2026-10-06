"""A made-up past: mesocycles recorded, and their workouts performed as prescribed on the days after."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import replace
from datetime import date, timedelta

from trainer import plan as plans
from trainer.engine import mesocycles, workouts


def prescribed(workout: plans.WorkoutPlan) -> tuple[workouts.PrescribedBlock, ...]:
    """A planned workout in the shape the engine records."""
    return tuple(
        workouts.PrescribedBlock(block=costed, reason=shape.reason)
        for shape, costed in zip(workout.blocks, plans.to_blocks(workout), strict=True)
    )


def as_performed(
    prescribed: workouts.PrescribedBlock, loads: Mapping[str, float] | None = None
) -> workouts.PerformedBlock:
    """A block performed exactly as it was prescribed, each exercise `loads` names at its load in kg."""
    block = prescribed.block
    performed = workouts.PerformedBlock(
        items=tuple(
            workouts.PerformedItem(
                exercise_id=item.exercise_id,
                unit="reps" if item.reps is not None else "seconds",
                amount=item.reps if item.reps is not None else int(item.seconds or 0),
                amount_source="reported",
            )
            for item in block.items
        ),
        rounds=block.rounds,
        rounds_source="reported",
        rest=block.rest,
        rest_source="reported",
    )
    if not loads:
        return performed
    return replace(
        performed,
        items=tuple(
            replace(item, load_kg=loads[item.exercise_id], load_kg_source="reported")
            if item.exercise_id in loads
            else item
            for item in performed.items
        ),
    )


def performed_as_prescribed(
    connection: sqlite3.Connection,
    mesocycle: plans.Mesocycle,
    on: date,
    *,
    direction: mesocycles.Direction | None = None,
    left: int = 0,
    loads: Mapping[str, float] | None = None,
) -> date:
    """The mesocycle recorded on `on` and performed a workout a day, but for the last `left`; the last day written."""
    mesocycles.record_mesocycle(
        connection,
        tuple(prescribed(workout) for workout in mesocycle.workouts),
        cycles=mesocycle.cycles,
        why=mesocycle.why,
        on=on.isoformat(),
        direction=direction,
    )
    for _ in range(len(mesocycle.workouts) * mesocycle.cycles - left):
        on += timedelta(days=1)
        served, workout_id = mesocycles.record_served(connection, on.isoformat())
        workouts.record_performed(
            connection,
            tuple(as_performed(block, loads) for block in served.blocks),
            on=on.isoformat(),
            report="as prescribed",
            workout_id=workout_id,
        )
    return on
