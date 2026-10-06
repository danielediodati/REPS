"""Every suite's rendered output and exit code on scripted models, held to a recording."""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from langchain_core.messages import AIMessage

from test_cli import LOG_SET, enriched, runner, stocked  # noqa: F401
from test_planner import Scripted, plan_of
from trainer import plan as plans
from trainer.cli import main
from trainer.coach import entrance, models, onboarding, supervisor

RECORDED = Path(__file__).parent / "eval_suites"
"""One file per suite; `RECORD_EVAL_SUITES=1` writes them instead of comparing."""


def calls(name: str, args: dict[str, Any], n: int) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"c{n}", "type": "tool_call"}])


def says(line: str) -> AIMessage:
    return AIMessage(content=line)


def scripted(monkeypatch: pytest.MonkeyPatch, **script: Any) -> None:
    """One scripted model behind every node, and a clock that stands still."""
    model = Scripted(**script)
    for node in ("planner", "logger", "entrance", "onboarding", "supervisor"):
        monkeypatch.setattr(models, node, lambda: models.Chat(model, "scripted", "a-stand-in"))
    monkeypatch.setattr(time, "monotonic", lambda: 0.0)


def adapted(*ids: str) -> plans.AdaptedPlan:
    return plans.AdaptedPlan.model_validate(
        {
            "counts_as": 1,
            "note": "trenta minuti",
            "blocks": [
                {
                    "items": [{"exercise_id": one, "prescription": {"unit": "reps", "amount": 8}}],
                    "rounds": 3,
                    "rest": 90,
                    "reason": "work",
                }
                for one in ids
            ],
        }
    )


def next_mesocycle() -> plans.Mesocycle:
    return plans.Mesocycle.model_validate(
        {
            "cycles": 3,
            "why": "next",
            "workouts": [
                {
                    "blocks": [
                        {
                            "items": [{"exercise_id": one, "prescription": {"unit": "reps", "amount": 10}}],
                            "rounds": 3,
                            "rest": 90,
                            "reason": "work",
                        }
                        for one in ("Romanian_Deadlift", "Front_Barbell_Squat")
                    ]
                }
            ]
            * 3,
        }
    )


def plan_suite(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
    scripted(monkeypatch, documents=[plan_of("Barbell_Squat")] * 20)
    return ["--only", "no-equipment", "--only", "refused"]


def log_suite(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
    written = tmp_path / "eval-set.md"
    written.write_text(LOG_SET, encoding="utf-8")
    monkeypatch.setenv("TRAINER_LOG_SET", str(written))
    nothing = '{"workout_id": 1, "blocks": [], "proposed_exclusion": null, "report": "tutto liscio, fatto come sta scritto"}'
    scripted(monkeypatch, raw=[nothing, nothing.replace("tutto liscio, fatto come sta scritto", "x")])
    return ["--suite", "log"]


def onboard_suite(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
    scripted(
        monkeypatch,
        turns=[
            calls(onboarding.DECLARE, {"equipment": ["body only", "dumbbell"]}, 1),
            calls(onboarding.FINISH, {}, 2),
            calls(onboarding.CHOOSE, {"path": "keep", "why": "Finisci questo."}, 3),
            calls(entrance.CHANGE_DECLARATION, {"said": "mi sono iscritto in palestra"}, 4),
            says("Aggiorno."),
        ],
    )
    return ["--suite", "onboard", "--only", "bought-dumbbells", "--only", "joined-a-gym"]


def adapt_suite(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
    scripted(
        monkeypatch,
        turns=[
            calls(entrance.CHANGE_DECLARATION, {"said": "ho comprato un bilanciere"}, 1),
            says("Aggiorno quello che hai."),
            calls(entrance.ADAPT_THIS_WORKOUT, {"said": "oggi ho 30 minuti invece di 45"}, 2),
            says("Lo adatto."),
            says("ho quello che serve"),
        ],
        documents=[adapted("Barbell_Squat", "Dumbbell_Lunges")] * 3,
    )
    return ["--suite", "adapt", "--only", "bought-barbell", "--only", "thirty"]


def supervise_suite(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
    written = tmp_path / "supervise-set.toml"
    committed = (Path("docs") / "supervising" / "eval-set.toml").read_text(encoding="utf-8")
    written.write_text(committed.replace("Air_Bike", "Hanging_Leg_Raise"), encoding="utf-8")
    monkeypatch.setenv("TRAINER_SUPERVISE_SET", str(written))
    direction = supervisor.Direction(
        theme="new squat", changes="the squat goes to a front squat", why="two alike", varies=["exercises"]
    )
    scripted(
        monkeypatch,
        turns=[says("enough"), says("ready"), says("enough")],
        documents=[direction, next_mesocycle(), next_mesocycle(), next_mesocycle()],
        raw=[],
    )
    return ["--suite", "supervise", "--only", "loves-the-hinge", "--only", "alike-twice"]


SUITES: dict[str, Callable[[pytest.MonkeyPatch, Path], list[str]]] = {
    "plan": plan_suite,
    "log": log_suite,
    "onboard": onboard_suite,
    "adapt": adapt_suite,
    "supervise": supervise_suite,
}


def normalised(output: str, tmp_path: Path) -> str:
    """The output with what differs between machines and days written as a placeholder."""
    for root in {str(tmp_path), str(tmp_path.resolve())}:
        output = output.replace(root, "<tmp>")
    output = output.replace("\\", "/")
    return re.sub(r"\d{4}-\d{2}-\d{2}", "<date>", output)


@pytest.mark.parametrize("suite", sorted(SUITES))
def test_a_suite_prints_what_it_printed_before_the_runner_was_shared(
    suite: str,
    runner: CliRunner,  # noqa: F811
    enriched: Path,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arguments = SUITES[suite](monkeypatch, tmp_path)

    result = runner.invoke(
        main, ["eval", *arguments, "--repetitions", "1", "--records", str(tmp_path / "records")]
    )

    got = f"exit {result.exit_code}\n{normalised(result.output, tmp_path)}"
    recorded = RECORDED / f"{suite}.txt"
    if os.environ.get("RECORD_EVAL_SUITES"):
        recorded.parent.mkdir(exist_ok=True)
        recorded.write_text(got, encoding="utf-8")
    assert got == recorded.read_text(encoding="utf-8")
