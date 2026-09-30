"""Onboarding: the interview that fills `training.toml`, led by the agent in its own words."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Annotated, Any, Literal, TypedDict, cast

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolCall,
    ToolMessage,
)
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import REMOVE_ALL_MESSAGES, add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore
from langgraph.types import interrupt

from trainer import tools
from trainer.coach import conclusions, models
from trainer.coach import record as records
from trainer.coach.calls import answered
from trainer.coach.logger import CLARIFY, EXCLUSION
from trainer.engine import catalog, config, exclusions, methodology, muscle_groups

FIELDS = ("cycle_length", "duration_cap_min", "split", "equipment", "goal")
"""The declarations the interview settles; `volume_denominator` has one value, so nothing to ask."""


def declare(
    cycle_length: int | None = None,
    duration_cap_min: int | None = None,
    split: list[list[str]] | None = None,
    equipment: list[str] | None = None,
    goal: str | None = None,
) -> str:
    """Write down what their answers have settled. A field you leave out stays as it was.

    - `cycle_length`: how many workouts one full rotation holds.
    - `duration_cap_min`: the minutes a workout is built to.
    - `split`: one list of groups or muscles per workout of the rotation,
      exactly `cycle_length` long.
    - `equipment`: what they have to train with, as the catalog names it.
    - `goal`: one of the methodology's goals.

    What comes back says which fields are still to settle.

    The body is never run. The graph answers this call by keeping the values.
    """
    raise AssertionError("the graph answers declare; nothing calls it")


def propose_exclusion(value: str, retest_date: str, why: str) -> str:
    """Propose keeping a movement pattern or a loaded joint out of their plans until a date.

    - `value`: a movement pattern or a loaded joint, as the catalog names it;
      never an exercise.
    - `retest_date`: when to try it again, as YYYY-MM-DD, after today.
    - `why`: one sentence to them, in Italian, saying what you heard.

    They are asked to confirm it; what comes back says whether they did.

    The body is never run. The graph answers this call by asking them.
    """
    raise AssertionError("the graph answers propose_exclusion; nothing calls it")


def finish() -> str:
    """End the interview, once every field is declared.

    Refused, with what is missing or wrong, while anything is.

    The body is never run. The graph answers this call by checking the declarations.
    """
    raise AssertionError("the graph answers finish; nothing calls it")


DECLARE = declare.__name__
PROPOSE_EXCLUSION = propose_exclusion.__name__
FINISH = finish.__name__

INTERVIEWING = """\
You are setting up a training system for the person you are talking to, in a
conversation you lead. You write in Italian, the way a coach texting would:
short, warm, one question per message, never a form or a list of questions.

By the end you must know, and have written down with `declare`:

- **goal**: what they train for, one of: {goals}. If they want several,
  agree with them on the one that comes first.
- **cycle_length**: how many different workouts one rotation holds. They train
  when they can, so this is a rotation of workouts, not days of the week.
- **split**: what each workout of the rotation trains, one entry per workout.
  An entry names muscle groups or single muscles from: {names}.
  Propose a split from what they tell you rather than asking them to design it.
- **duration_cap_min**: how many minutes a workout usually lasts.
- **equipment**: what they have to train with, as the catalog names it: {equipment}.
  «body only» is having nothing.

Asking:

- The goal first and their aches last is a good order, not a rule.
- One question per message. Your message is the question: write it, and call no
  tool in the same turn.
- An answer can settle several things at once: declare all of them, and never
  ask again about something already settled.
- Call `declare` as soon as an answer settles something; it tells you what is
  still missing.

Aches, near the end:

- Ask whether some movement bothers them: pushing overhead, squatting, a joint
  that complains. Ask about movements, never about symptoms, never a pain scale,
  never a diagnosis.
- When a movement should stay out of their plans for a while, call
  `propose_exclusion` with a movement pattern ({patterns}) or a loaded joint
  ({joints}), a retest date after today and a why. They confirm it or not.

Remembering, when `remember` is offered:

- Something lasting they tell you about themselves -- what they like, what they
  cannot stand, what their day allows -- is worth keeping: «odio le distensioni».
- `quote` is their sentence exactly as they typed it; anything else is refused.

When everything is declared, call `finish`. It refuses while something is
missing or wrong and says what; ask them about it and declare it again.

Today is {today}.
"""

KEPT = "Written down. {missing}"
STILL = "Still to settle: {fields}."
SETTLED = "Everything is declared: call `finish` once they have nothing to add."
UNKNOWN_FIELD = "Not written: {keys} is not a declaration. The declarations are {fields}."
MISSING = "Not finished: {fields} still to settle. Ask them."
WRONG = "Not finished: {error}. Put it right with them and declare it again."
UNKNOWN_EQUIPMENT = (
    "Not finished: the catalog has no equipment called {names}. It has {valid}."
)
FINISHED = "The interview is over. Their first mesocycle is planned next."

NOT_EXCLUDABLE = "Not proposed: {error}"
BAD_RETEST = "Not proposed: retest_date {given!r} is not a date after {today}, as YYYY-MM-DD."
CONFIRMED = "They confirmed it: it is kept out until {retest_date}."
DECLINED = "They declined it: nothing is kept out."
ANSWERED_IN_WORDS = (
    "They answered in words instead of yes or no: {said!r}. Nothing is kept "
    "out. Propose it again only if they meant yes."
)

SILENT = "You wrote nothing. Ask them your next question, or call `finish`."
SPENT = "No tool calls left before their next answer. Ask them your question."


class OnboardingState(TypedDict, total=False):
    said: list[str]
    """What the user wrote in this interview, in order: what `remember` checks a quote against."""

    today: str
    vocabulary: dict[str, list[str]]
    """The words the declarations are spelled in, read from the data by the door that starts it."""

    messages: Annotated[list[AnyMessage], add_messages]
    declared: dict[str, Any]
    """What `declare` has written so far, as the model gave it."""

    exclusions: list[dict[str, str]]
    """The exclusions the user confirmed, as `granularity`, `value`, `retest_date`."""

    finished: bool
    spent: int
    """Tool calls since the user's last answer, bounded by the budget."""

    budget: int
    negotiation: str
    run: str
    follows: str | None
    began: str
    ended: str
    ending: str
    timings: list[tuple[str, str, str, float, str, str]]


def vocabulary(connection: sqlite3.Connection) -> dict[str, list[str]]:
    """The words each declaration and exclusion may use, read from the catalog, the mapping and the methodology."""
    return {
        "goals": list(methodology.goals()),
        "names": list(muscle_groups.committed().names),
        "equipment": list(catalog.values(connection, "equipment")),
        "patterns": list(catalog.values(connection, "movement_pattern")),
        "joints": list(catalog.joint_values(connection)),
    }


def starting(said: str, today: str, words: dict[str, list[str]]) -> OnboardingState:
    """The input that starts an interview: the message that asked for it, and nothing left from the last."""
    return {
        "said": [said],
        "today": today,
        "vocabulary": words,
        **records.identity(records.negotiation_id(), None),  # type: ignore[typeddict-item]
        "messages": [cast(AnyMessage, RemoveMessage(REMOVE_ALL_MESSAGES))],
        "declared": {},
        "exclusions": [],
        "finished": False,
        "spent": 0,
        "timings": [],
    }


Onboarding = CompiledStateGraph[OnboardingState, None, OnboardingState, OnboardingState]


def build(
    on: models.Chat,
    budget: int = tools.CALL_BUDGET,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    archive: Path | None = None,
    store: BaseStore | None = None,
) -> Onboarding:
    """The compiled interview on `on`; `store` is where `remember` keeps a conclusion.

    Nothing here writes the file or an exclusion: `written` does, from the door.
    """
    model = on.model
    offered: list[Callable[..., str]] = [declare, propose_exclusion]
    if store is not None:
        offered.append(conclusions.remember)
    working = [{"type": "function", "function": tools.schema(tool)} for tool in offered]
    ending = {"type": "function", "function": tools.schema(finish)}
    timed = records.timing(on)

    def interview(state: OnboardingState) -> dict[str, Any]:
        born = records.born(state)
        opening: list[AnyMessage] = []
        if not state.get("messages"):
            words = state.get("vocabulary", {})
            opening = [
                SystemMessage(
                    INTERVIEWING.format(
                        today=state.get("today", ""),
                        **{key: ", ".join(value) for key, value in words.items()},
                    )
                ),
                HumanMessage(state.get("said", [""])[0]),
            ]
        definitions = working if state.get("spent", 0) < budget else []
        bound = model.bind_tools([*definitions, ending])
        reply = bound.invoke([*state.get("messages", []), *opening])
        return born | {"budget": budget, "messages": [*opening, reply]}

    def ask(state: OnboardingState) -> dict[str, Any]:
        """The model's message put to the user, and their answer handed back."""
        reply = state["messages"][-1]
        question = reply.text.strip() if isinstance(reply, AIMessage) else ""
        if not question:
            return {
                "messages": [HumanMessage(SILENT, name="machine")],
                "spent": state.get("spent", 0) + 1,
            }
        answer = str(interrupt({"kind": CLARIFY, "ask": question}))
        return {
            "messages": [HumanMessage(answer)],
            "said": [*state.get("said", []), answer],
            "spent": 0,
        }

    def run_tools(state: OnboardingState) -> dict[str, Any]:
        """The turn's calls answered; a proposed exclusion waits on the user.

        Resuming replays this node from the top, so everything before an
        `interrupt` is computed from the state it was given.
        """
        reply = state["messages"][-1]
        assert isinstance(reply, AIMessage)
        declared = dict(state.get("declared", {}))
        confirmed = list(state.get("exclusions", []))
        said = list(state.get("said", []))
        spent = state.get("spent", 0)
        finished = False
        answers: list[AnyMessage] = []
        for call in reply.tool_calls:
            spent += 1
            name = call["name"]
            if spent > budget and name != FINISH:
                text, failed = SPENT, True
            elif name == DECLARE:
                text, failed = _declared(declared, call)
            elif name == PROPOSE_EXCLUSION:
                text, failed = _proposed(state, call, confirmed, said)
            elif name == conclusions.REMEMBER and store is not None:
                text, failed = conclusions.kept(
                    store, conclusions.whose(), call["args"], said, state["today"]
                )
            elif name == FINISH:
                refused = refusal(declared)
                text, failed = (FINISHED, False) if refused is None else (refused, True)
                finished = refused is None
            else:
                text, failed = f"There is no tool called {name}.", True
            answers.append(
                ToolMessage(
                    text,
                    tool_call_id=answered(call),
                    name=name,
                    status="error" if failed else "success",
                )
            )
        decided: dict[str, Any] = {
            "messages": answers,
            "declared": declared,
            "exclusions": confirmed,
            "said": said,
            "spent": spent,
            "finished": finished,
        }
        if finished:
            decided.update(records.closing({**state, **decided}, records.DONE, budget, archive))
        return decided

    def after_interview(state: OnboardingState) -> Literal["tools", "ask"]:
        reply = state["messages"][-1]
        return "tools" if isinstance(reply, AIMessage) and reply.tool_calls else "ask"

    def after_tools(state: OnboardingState) -> Literal["interview", "done"]:
        return "done" if state.get("finished") else "interview"

    graph = StateGraph(OnboardingState)
    graph.add_node("interview", timed("interview", interview))
    graph.add_node("ask", timed("ask", ask))
    graph.add_node("tools", timed("tools", run_tools))
    graph.add_edge(START, "interview")
    graph.add_conditional_edges("interview", after_interview)
    graph.add_edge("ask", "interview")
    graph.add_conditional_edges(
        "tools", after_tools, {"interview": "interview", "done": END}
    )
    return graph.compile(checkpointer=checkpointer)


def _declared(declared: dict[str, Any], call: ToolCall) -> tuple[str, bool]:
    """A `declare` call kept into `declared`, and what the model is told is still missing."""
    given = {key: value for key, value in call["args"].items() if value is not None}
    unknown = sorted(set(given) - set(FIELDS))
    if unknown:
        return UNKNOWN_FIELD.format(keys=", ".join(unknown), fields=", ".join(FIELDS)), True
    declared.update(given)
    missing = [field for field in FIELDS if field not in declared]
    return KEPT.format(missing=STILL.format(fields=", ".join(missing)) if missing else SETTLED), False


def _proposed(
    state: OnboardingState,
    call: ToolCall,
    confirmed: list[dict[str, str]],
    said: list[str],
) -> tuple[str, bool]:
    """An exclusion checked against the catalog and put to the user, and what they answered."""
    value = str(call["args"].get("value", "")).strip()
    retest_date = str(call["args"].get("retest_date", "")).strip()
    today = state["today"]
    try:
        after = date.fromisoformat(retest_date) > date.fromisoformat(today)
    except ValueError:
        after = False
    if not after:
        return BAD_RETEST.format(given=retest_date, today=today), True
    try:
        with tools.opened() as connection:
            classified = exclusions.classify(connection, value)
    except exclusions.ExclusionError as error:
        return NOT_EXCLUDABLE.format(error=error), True
    answer = interrupt(
        {
            "kind": EXCLUSION,
            "ask": str(call["args"].get("why", "")),
            "granularity": classified.granularity,
            "value": classified.value,
            "retest_date": retest_date,
        }
    )
    if isinstance(answer, bool):
        if not answer:
            return DECLINED, False
        confirmed.append(
            {
                "granularity": classified.granularity,
                "value": classified.value,
                "retest_date": retest_date,
            }
        )
        return CONFIRMED.format(retest_date=retest_date), False
    said.append(str(answer))
    return ANSWERED_IN_WORDS.format(said=str(answer)), False


def refusal(declared: dict[str, Any]) -> str | None:
    """Why the interview cannot end on these declarations, or `None` when it can."""
    missing = [field for field in FIELDS if field not in declared]
    if missing:
        return MISSING.format(fields=", ".join(missing))
    try:
        parsed = settled(declared)
    except config.ConfigError as error:
        return WRONG.format(error=error)
    with tools.opened() as connection:
        valid = catalog.values(connection, "equipment")
    unknown = [name for name in parsed.equipment if name not in valid]
    if unknown:
        return UNKNOWN_EQUIPMENT.format(names=", ".join(unknown), valid=", ".join(valid))
    return None


def settled(declared: dict[str, Any]) -> config.TrainingConfig:
    """The declarations as `config.load` would read them back."""
    return config.parse({**declared, "volume_denominator": config.DENOMINATORS[0]})


HEADER = """\
# The training configuration, written by onboarding on {today}.
#
# Yours to read and edit by hand (ADR-0003).
"""

COMMENTS = {
    "cycle_length": (
        "How many workouts one complete rotation holds. Not days of the week: the\n"
        "rotation advances when a workout is performed, never when a date passes."
    ),
    "duration_cap_min": (
        "The minutes a workout is built to, give or take five, when no other time is\n"
        "asked for; and the most that may be asked for."
    ),
    "volume_denominator": "What volume is counted over.",
    "split": (
        "What each workout of the cycle trains, in order: one entry per workout.\n"
        "`trainer config --muscle-groups` lists the groups and muscles."
    ),
    "equipment": (
        "What you have to train with, as the catalog spells it: run\n"
        "`trainer catalog --values equipment` for the list."
    ),
    "goal": (
        "What this mesocycle trains for: one of the goal columns of the methodology.\n"
        "Changing it is a new mesocycle."
    ),
}


def rendered(declaration: config.TrainingConfig, today: str) -> str:
    """The declarations as TOML, with a comment above each."""
    values = {
        "cycle_length": str(declaration.cycle_length),
        "duration_cap_min": str(declaration.duration_cap_min),
        "volume_denominator": json.dumps(declaration.volume_denominator),
        "split": "[\n"
        + "".join(f"    {_listed(workout)},\n" for workout in declaration.split)
        + "]",
        "equipment": _listed(declaration.equipment),
        "goal": json.dumps(declaration.goal),
    }
    parts = [HEADER.format(today=today)]
    for key, value in values.items():
        comment = "\n".join(f"# {line}" for line in COMMENTS[key].splitlines())
        parts.append(f"{comment}\n{key} = {value}\n")
    return "\n".join(parts)


def _listed(names: tuple[str, ...]) -> str:
    """A list of strings as TOML: a JSON string is a TOML basic string."""
    return "[" + ", ".join(json.dumps(name) for name in names) + "]"


def written(final: dict[str, Any], path: Path | None = None) -> config.TrainingConfig:
    """The interview's declarations written to `training.toml`, and its confirmed exclusions to the database."""
    declaration = settled(final["declared"])
    target = path if path is not None else config.config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered(declaration, str(final["today"])), encoding="utf-8")
    kept = final.get("exclusions", [])
    if kept:
        with tools.opened() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                for one in kept:
                    exclusions.add(
                        connection,
                        exclusions.Exclusion(one["granularity"], one["value"]),
                        one["retest_date"],
                    )
            except BaseException:
                connection.execute("ROLLBACK")
                raise
            connection.execute("COMMIT")
    return declaration


def studio() -> Onboarding:
    """The interview on the entrance's model, as `langgraph dev` serves it."""
    return build(models.entrance(), archive=records.archive())
