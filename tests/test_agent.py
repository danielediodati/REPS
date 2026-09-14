"""The loop, against a stand-in model.

One loop is left, the logger's: the planner moved onto the graph in session 6
and `test_planner.py` is where its surface, prompt and brief are now covered.
Session 8 moves this one too.

`conftest.py` removes sockets and credentials from every test on purpose, so
nothing here reaches a provider. What is covered is everything that is this
project's: the tools offered, the call budget, emitting on exhaustion, the way
out through the validator, and the run record the log eval measures on.
`agent.Groq` is covered too, against a stand-in client that records the
request it was handed: the request *shape* is where the one bug that would
have failed every real run lived, and no socket is needed to assert on it.
"""

from __future__ import annotations

import ast
import enum
import inspect
import json
import sqlite3
import textwrap
from collections.abc import Callable, Iterator, Sequence
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from typing import Any, NamedTuple

import pytest

from conftest import enrich, make_exercise
from pydantic import BaseModel

from trainer import agent, log as logs, plan as plans, tools
from trainer.engine import (
    catalog,
    database,
    duration,
    exclusions,
    migrations,
    workouts,
)

CATALOG = (
    make_exercise(id="Barbell_Squat", name="Barbell Squat", primary_muscles=("quadriceps",)),
    make_exercise(
        id="Dumbbell_Bench_Press",
        name="Dumbbell Bench Press",
        equipment="dumbbell",
        primary_muscles=("chest",),
    ),
    make_exercise(
        id="Standing_Military_Press", name="Standing Military Press", equipment="barbell"
    ),
)

_PATTERNS = {
    "Barbell_Squat": ("squat", "hip, knee, ankle", "yes", "high", 3),
    "Dumbbell_Bench_Press": ("horizontal push", "shoulder, elbow", "no", "medium", 1),
    "Standing_Military_Press": ("vertical push", "shoulder, elbow", "yes", "medium", 3),
}

@pytest.fixture()
def connection(database_file: Path) -> Iterator[sqlite3.Connection]:
    with closing(database.connect(database_file)) as opened:
        migrations.migrate(opened, migrations.discover())
        catalog.import_exercises(opened, CATALOG)
        enrich(opened, _PATTERNS)
        yield opened


# -- the stand-in -------------------------------------------------------------


def good_plan(*exercise_ids: str) -> plans.WorkoutPlan:
    return plans.WorkoutPlan(
        blocks=[
            plans.PlanBlock(
                items=[plans.PlanItem(exercise_id=exercise_id, prescription=plans.Prescription(unit="reps", amount=8))],
                rounds=3,
                rest=120,
                reason="because it is a squat and squats are good",
            )
            for exercise_id in exercise_ids or ("Barbell_Squat",)
        ]
    )


class Scripted:
    """A model whose turns were written in advance.

    `turns` is what it replies with, one per `respond`, each a `Turn` -- or the
    shorthand for one: a tuple of calls, or a string, which is prose with no
    tool calls in it. Prose is a clarifying question on the logging door and
    the end of the loop on the planning one. When the turns run out it keeps
    replying with nothing, which is a model that has stopped asking. `emitted`
    is what it hands over when asked for the document, and it counts the asks,
    because *emitted exactly once* is how this suite states that a refused
    document is never re-asked.
    """

    def __init__(
        self,
        turns: Sequence[Turn | tuple[agent.Call, ...] | str] | None = None,
        emitted: BaseModel | None = None,
    ) -> None:
        self.turns = list(turns or [])
        self.emitted = emitted if emitted is not None else good_plan()
        self.name = "a-stand-in"
        self.offers: list[list[dict[str, Any]] | None] = []
        self.emissions = 0
        self.seen: list[Any] = []
        self.briefs: list[str] = []

    def respond(
        self,
        brief: str,
        exchanges: Sequence[agent.Exchange],
        offered: Sequence[dict[str, Any]] | None,
    ) -> agent.Reply:
        self.offers.append(list(offered) if offered is not None else None)
        self.seen = list(exchanges)
        self.briefs.append(brief)
        turn = _turn(self.turns.pop(0) if self.turns else ())
        return agent.Reply(
            content={"role": "assistant", "content": "thinking"},
            calls=turn.calls,
            text=turn.text,
            input_tokens=100,
            output_tokens=20,
        )

    def emit(
        self,
        brief: str,
        exchanges: Sequence[agent.Exchange],
        shape: type[Any],
    ) -> agent.Emission[Any]:
        self.emissions += 1
        self.seen = list(exchanges)
        self.briefs.append(brief)
        assert isinstance(self.emitted, shape), (
            f"the loop asked for a {shape.__name__} and the script holds a "
            f"{type(self.emitted).__name__}"
        )
        return agent.Emission(document=self.emitted, input_tokens=200, output_tokens=50)


def call(name: str, **arguments: Any) -> agent.Call:
    return agent.Call(id=f"toolu_{name}", name=name, arguments=arguments)


class Turn(NamedTuple):
    """One scripted reply: what it called, and what it wrote.

    Both at once is a real turn and not a contrivance -- a model that searches
    the catalog and asks which of two benches it was is doing both things it
    is supposed to do -- so the stand-in has to be able to produce one.
    """

    calls: tuple[agent.Call, ...] = ()
    text: str = ""


def _turn(scripted: Any) -> Turn:
    """A scripted turn, out of `Turn` or either shorthand for one."""
    if isinstance(scripted, Turn):
        return scripted
    if isinstance(scripted, str):
        return Turn(text=scripted)
    return Turn(calls=tuple(scripted))


def executed(one: agent.Call, door: agent.Door = agent.LOGGER) -> agent.Result:
    """One call, through the door that offered it -- which is what decides
    both whether the tool exists and what its answer carries back."""
    return agent.execute(one, agent.registered(door.name, door.tools), door.keeps)


# -- the tools this door offers -----------------------------------------------


def test_the_tools_offered_are_the_shared_surface_and_nothing_else() -> None:
    """No second definition: a door registers names out of `tools.TOOLS`, the
    same tuple `trainer mcp` registers."""
    offered = agent.surface(agent.LOGGER)
    defined = {tool.__name__ for tool in tools.TOOLS}

    assert [tool["name"] for tool in offered] == list(agent.LOGGER.tools)
    assert set(agent.LOGGER.tools) <= defined, "a door named a tool nobody defined"


def test_every_tool_reaches_the_model_with_a_description_and_arguments() -> None:
    """A tool the model cannot fill the arguments in for is a tool it cannot
    call, and a tool with no description is one it cannot choose."""
    for offered in agent.surface(agent.LOGGER):
        assert offered["description"], f"{offered['name']} has no description"
        assert offered["parameters"]["type"] == "object"
        if offered["name"] == "unreported_workouts":
            # The one question with nothing to ask about: *today* is the
            # door's to supply, never the model's, because nothing in
            # `engine/` reads the clock.
            assert offered["parameters"]["properties"] == {}
            continue
        assert offered["parameters"]["properties"], f"{offered['name']} takes nothing"


def test_the_logger_still_sees_the_name_it_resolves_a_report_against(
    connection: sqlite3.Connection,
) -> None:
    """Its task is *"the bench"* against what was prescribed, and an id is not
    a thing anybody says out loud."""
    answered = executed(call("search_exercises", text="squat"))

    record = json.loads(answered.content)["exercises"][0]

    assert sorted(record) == ["equipment", "id", "mechanic", "name", "primary_muscles"]


# -- the loop -----------------------------------------------------------------
#
# The loop itself, rather than the logging in particular, which has a section
# of its own further down. It ran both agents until session 6; what reaches it
# now is the logger's door, and every property below is about the loop.


def test_a_run_calls_tools_and_emits_a_document(
    connection: sqlite3.Connection,
) -> None:
    identifier = prescribe(connection)
    ask, _ = answers()
    model = Scripted(
        turns=[(call("prescribed_workout", workout_id=identifier),), "tutto chiaro"],
        emitted=performed(workout_id=identifier, report="fatto"),
    )

    record = agent.log_workout(
        connection, "fatto", TODAY, ask=ask, awaiting=identifier, model=model
    )

    assert record.spent == 1
    assert record.refused is None
    assert record.emitted_on_exhaustion is False
    assert [c.name for c in record.calls] == ["prescribed_workout"]
    assert record.calls[0].arguments == {"workout_id": identifier}


def test_the_calls_are_recorded_in_the_order_they_were_made(
    connection: sqlite3.Connection,
) -> None:
    identifier = prescribe(connection)
    ask, _ = answers()
    model = Scripted(
        turns=[
            (call("prescribed_workout", workout_id=identifier),),
            (
                call("search_exercises", text="squat"),
                call("pattern_history", pattern="squat", cycles=3),
            ),
            "tutto chiaro",
        ],
        emitted=performed(workout_id=identifier, report="fatto"),
    )

    record = agent.log_workout(
        connection, "fatto", TODAY, ask=ask, awaiting=identifier, model=model
    )

    assert [c.name for c in record.calls] == [
        "prescribed_workout",
        "search_exercises",
        "pattern_history",
    ]
    assert record.spent == 3


def test_the_tools_are_taken_off_the_table_when_the_budget_runs_out(
    connection: sqlite3.Connection,
) -> None:
    """It does not fail and it does not keep going: it stops offering tools
    and asks for the document with what it has."""
    forever = [(call("pattern_history", pattern="squat", cycles=3),)] * 20
    ask, _ = answers()
    model = Scripted(turns=forever, emitted=performed(report="fatto"))

    agent.log_workout(connection, "fatto", TODAY, ask=ask, model=model, budget=2)

    assert all(offer for offer in model.offers), "a turn was offered no tools"
    assert len(model.offers) == 2, "it kept asking after the budget was gone"


def test_a_model_that_stops_asking_early_is_not_charged_the_whole_budget(
    connection: sqlite3.Connection,
) -> None:
    ask, _ = answers()
    model = Scripted(turns=["tutto chiaro"], emitted=performed(report="fatto"))

    record = agent.log_workout(
        connection, "fatto", TODAY, ask=ask, model=model, budget=12
    )

    assert record.spent == 0
    assert record.emitted_on_exhaustion is False


def test_a_budget_under_one_call_is_refused(connection: sqlite3.Connection) -> None:
    ask, _ = answers()
    with pytest.raises(agent.AgentError, match="at least one call"):
        agent.log_workout(
            connection, "fatto", TODAY, ask=ask, model=Scripted(), budget=0
        )


# -- what a tool failure does -------------------------------------------------


def test_a_tool_failure_goes_back_to_the_model_as_a_result(
    connection: sqlite3.Connection,
) -> None:
    """A stated failure is something the model can act on -- it asked for an
    exercise nobody has, and the next turn it can ask for one that exists."""
    ask, _ = answers()
    model = Scripted(
        turns=[(call("last_performed_load", exercise_id="Barbell_Sqvat"),), "fine"],
        emitted=performed(report="fatto", blocks=[done("Barbell_Squat")]),
    )

    record = agent.log_workout(connection, "fatto", TODAY, ask=ask, model=model)

    assert record.calls[0].failed is True
    assert record.calls[0].detail is not None
    assert "Barbell_Sqvat" in record.calls[0].detail
    assert record.refused is None, "the run carried on"


def test_a_tool_the_surface_does_not_have_is_a_result_not_a_crash(
    connection: sqlite3.Connection,
) -> None:
    """The model's mistake, not this project's, so it comes back as something
    it can recover from -- with the real names in it."""
    ask, _ = answers()
    model = Scripted(
        turns=[(call("active_conclusions",),), "fine"],
        emitted=performed(report="fatto"),
    )

    record = agent.log_workout(connection, "fatto", TODAY, ask=ask, model=model)

    assert record.calls[0].failed is True
    assert record.calls[0].detail is not None
    assert "prescribed_workout" in record.calls[0].detail


def test_arguments_that_do_not_fit_the_signature_are_a_result_not_a_crash(
    connection: sqlite3.Connection,
) -> None:
    ask, _ = answers()
    model = Scripted(
        turns=[(call("pattern_history", pattern="squat", rounds=3),), "fine"],
        emitted=performed(report="fatto"),
    )

    record = agent.log_workout(connection, "fatto", TODAY, ask=ask, model=model)

    assert record.calls[0].failed is True


# -- the record ---------------------------------------------------------------


def test_the_record_counts_what_the_run_cost(connection: sqlite3.Connection) -> None:
    """What a pass costs is what the log eval reports, so it is counted here
    rather than estimated there."""
    ask, _ = answers()
    model = Scripted(
        turns=[(call("pattern_history", pattern="squat", cycles=3),), "fine"],
        emitted=performed(report="fatto"),
    )

    record = agent.log_workout(connection, "fatto", TODAY, ask=ask, model=model)

    assert record.input_tokens == 100 + 100 + 200
    assert record.output_tokens == 20 + 20 + 50


def test_the_summary_says_when_the_document_was_emitted_on_exhaustion(
    connection: sqlite3.Connection,
) -> None:
    forever = [(call("pattern_history", pattern="squat", cycles=3),)] * 20
    ask, _ = answers()
    record = agent.log_workout(
        connection,
        "fatto",
        TODAY,
        ask=ask,
        model=Scripted(turns=forever, emitted=performed(report="fatto")),
        budget=2,
    )

    assert "budget spent" in "\n".join(agent.summary(record))


# -- credentials --------------------------------------------------------------


def test_no_credentials_is_a_state_with_the_way_out() -> None:
    """`conftest.py` takes every credential out of the environment, so this is
    the state under test rather than something about this machine. Left to the
    SDK it would be a 401 after a round-trip, or a connection error offline --
    neither of which names what is missing."""
    with pytest.raises(agent.AgentError) as raised:
        agent._client()

    assert agent.API_KEY_ENV in str(raised.value)
    assert ".env" in str(raised.value)


def test_the_model_is_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(agent.MODEL_ENV, "qwen/qwen3.6-27b")

    assert agent.model_name() == "qwen/qwen3.6-27b"


def test_the_model_falls_back_to_the_one_that_can_be_held_to_the_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(agent.MODEL_ENV, raising=False)

    assert agent.model_name() == agent.DEFAULT_MODEL


# -- what the model is handed back --------------------------------------------


def test_a_result_reaches_the_model_as_json(connection: sqlite3.Connection) -> None:
    """The tool docstrings describe `known: false`; Python would hand back
    `'known': False`, and a model translating between two dialects mid-loop is
    one more thing that can go wrong for nothing."""
    result = executed(call("pattern_history", pattern="squat", cycles=3))

    assert result.failed is False
    assert json.loads(result.content)["known"] is False


def test_the_shared_surface_still_answers_whole(
    connection: sqlite3.Connection,
) -> None:
    """The trimming belongs to this door, not to the surface: an MCP client is
    not paying for context, and ticket 01's wrapper answers with the record
    the engine returned."""
    (first, *_) = tools.admissible_set(equipment=["barbell"], budget_min=45)

    assert "instructions" in first
    assert "images" in first


# -- the schemas the model is given -------------------------------------------


class Grip(enum.Enum):
    OVERHAND = "overhand"
    UNDERHAND = "underhand"


def a_tool(grips: list[Grip]) -> str:
    """A tool with a parameter pydantic describes by reference."""
    return ", ".join(grip.value for grip in grips)


def test_a_definition_a_parameter_needs_is_hoisted_where_it_resolves() -> None:
    """A `$ref` resolves from the root of the schema document, and the root is
    `parameters`. Left inside the property, the definitions an enum or a
    model-typed parameter needs sit one level too deep and every reference to
    them dangles."""
    built = agent.schema(a_tool)["parameters"]

    assert "$defs" in built, "the definition was left inside the property"
    assert "$defs" not in built["properties"]["grips"]
    referenced = built["properties"]["grips"]["items"]["$ref"].removeprefix("#/$defs/")
    assert referenced in built["$defs"]


# -- the provider adapter, against a stand-in client --------------------------
#
# The one part of the loop the suite could not see before, and where the bug
# that would have failed every real run lived: a request built in a shape the
# API refuses. No socket is opened -- the client is a fake that records what it
# was handed and returns a scripted completion.


class FakeMessage:
    def __init__(self, content: str | None = None, tool_calls: object = None) -> None:
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self, exclude_none: bool = False) -> dict[str, Any]:
        return {"role": "assistant", "content": self.content}


class FakeUsage:
    prompt_tokens = 11
    completion_tokens = 7


class FakeCompletion:
    def __init__(self, message: FakeMessage) -> None:
        self.choices = [SimpleNamespace(message=message)]
        self.usage = FakeUsage()


class FakeGroq:
    """A client that records the request and answers from a script."""

    def __init__(self, *messages: FakeMessage) -> None:
        self.scripted = list(messages)
        self.requests: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **request: Any) -> FakeCompletion:
        self.requests.append(request)
        return FakeCompletion(self.scripted.pop(0))


def a_tool_call(name: str, arguments: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=f"call_{name}", function=SimpleNamespace(name=name, arguments=arguments)
    )


def test_the_tool_phase_offers_the_tools_in_the_envelope_groq_reads() -> None:
    client = FakeGroq(FakeMessage(content="thinking"))

    agent.Groq(agent.LOGGER, client=client, model="qwen/qwen3.8-27b").respond(
        "today", [], agent.surface(agent.LOGGER)
    )

    (request,) = client.requests
    offered = agent.LOGGER.tools
    assert [tool["type"] for tool in request["tools"]] == ["function"] * len(offered)
    assert request["tools"][0]["function"]["name"] == offered[0]
    assert "response_format" not in request


def test_the_emission_offers_no_tools_at_all() -> None:
    """Groq does not allow structured outputs and tool use in one request. This
    is the assertion that would have caught a request built the other way."""
    client = FakeGroq(FakeMessage(content=performed(report="fatto").model_dump_json()))

    agent.Groq(agent.LOGGER, client=client, model="qwen/qwen3.8-27b").emit(
        "today", [], logs.PerformedWorkout
    )

    (request,) = client.requests
    assert "tools" not in request
    assert request["response_format"]["type"] == "json_schema"
    assert request["response_format"]["json_schema"]["strict"] is True


def test_the_conversation_replays_in_the_shape_groq_reads() -> None:
    """An assistant message handed back exactly as it arrived, then one `tool`
    message per result keyed by the id the call came with."""
    reply = agent.Reply(
        content={"role": "assistant", "tool_calls": [{"id": "call_1"}]},
        calls=(agent.Call(id="call_1", name="allocate", arguments={}),),
    )
    exchange = agent.Exchange(
        reply=reply,
        results=(agent.Result(call_id="call_1", name="allocate", content='{"legs": 45}'),),
    )
    client = FakeGroq(FakeMessage(content="thinking"))

    agent.Groq(agent.LOGGER, client=client, model="m").respond("today", [exchange], None)

    (request,) = client.requests
    roles = [message["role"] for message in request["messages"]]
    assert roles == ["system", "user", "assistant", "tool"]
    assert request["messages"][1]["content"] == "today"
    assert request["messages"][2] is reply.content
    assert request["messages"][3]["tool_call_id"] == "call_1"
    assert request["messages"][3]["content"] == '{"legs": 45}'


def test_arguments_arrive_as_a_json_string_and_are_parsed() -> None:
    """Groq sends `function.arguments` as a string. Read as one it would reach
    the tools as a `str`, and every call would come back refused for arguments
    that do not fit -- a whole run spent on a mistake nobody made."""
    client = FakeGroq(
        FakeMessage(
            tool_calls=[a_tool_call("allocate", '{"minutes": 45, "proportions": {"legs": 1.0}}')]
        )
    )

    reply = agent.Groq(agent.LOGGER, client=client, model="m").respond(
        "today", [], agent.surface(agent.LOGGER)
    )

    (call_,) = reply.calls
    assert call_.arguments == {"minutes": 45, "proportions": {"legs": 1.0}}


def test_an_emission_that_is_not_the_document_is_a_state_not_a_traceback() -> None:
    client = FakeGroq(FakeMessage(content='{"blocks": "nonsense"}'))

    with pytest.raises(agent.AgentError, match="did not parse"):
        agent.Groq(agent.LOGGER, client=client, model="m").emit(
            "today", [], logs.PerformedWorkout
        )


def test_an_empty_emission_is_a_state_not_a_traceback() -> None:
    client = FakeGroq(FakeMessage(content=None))

    with pytest.raises(agent.AgentError, match="no performed_workout"):
        agent.Groq(agent.LOGGER, client=client, model="m").emit(
            "today", [], logs.PerformedWorkout
        )


def test_a_provider_that_cannot_be_reached_is_reported_in_words() -> None:
    import groq as sdk
    import httpx

    def unreachable() -> None:
        raise sdk.APIConnectionError(request=httpx.Request("POST", "https://api.groq.com"))

    with pytest.raises(agent.AgentError, match="could not be reached"):
        agent._reported(unreachable)


# -- the shape the model is held to -------------------------------------------


def test_strict_mode_requires_every_property_including_the_defaulted_ones() -> None:
    """Strict mode is constrained decoding, and it demands every property be
    listed in `required`. Pydantic leaves out the ones carrying a default,
    which is the plan's `despite`. That it must be present is exactly why it
    is a list and not a field on every item: the empty answer is `[]`, which a
    model writes without being talked into it."""
    built = agent.strict_schema(plans.WorkoutPlan)
    item = built["$defs"]["PlanItem"]

    assert set(item["required"]) == {"exercise_id", "prescription"}
    assert set(built["$defs"]["Prescription"]["required"]) == {"unit", "amount"}
    assert item["additionalProperties"] is False
    assert set(built["required"]) == {"blocks", "despite"}


def test_the_strict_shape_still_accepts_a_plan_the_project_calls_valid() -> None:
    """The transform above rewrites the schema the model is held to. If it
    drifted from what `WorkoutPlan` actually parses, every run would emit
    something the validator then refuses on shape."""
    import jsonschema

    emitted = json.loads(good_plan("Barbell_Squat").model_dump_json())

    jsonschema.validate(emitted, agent.strict_schema(plans.WorkoutPlan))


def test_the_record_names_the_model_that_ran_not_the_environment(
    connection: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The log eval compares outcomes across models by building one per run. A
    record that re-read the environment afterwards would stamp every one of
    them with whatever `GROQ_MODEL` happened to say."""
    monkeypatch.setenv(agent.MODEL_ENV, "a-model-nobody-ran")
    ask, _ = answers()
    model = Scripted(turns=["fine"], emitted=performed(report="fatto"))
    model.name = "the-one-that-ran"

    record = agent.log_workout(connection, "fatto", TODAY, ask=ask, model=model)

    assert record.model == "the-one-that-ran"


def test_the_provider_adapter_reports_the_model_it_was_built_with() -> None:
    assert agent.Groq(agent.LOGGER, client=FakeGroq(), model="qwen/qwen3.8-27b").name == (
        "qwen/qwen3.8-27b"
    )


# -- values a person can get wrong in .env ------------------------------------


def test_a_max_tokens_that_is_not_a_number_is_a_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It is interpolated into the rate-limit message, so left unchecked it
    raises *while handling* the 429 it was meant to explain."""
    monkeypatch.setenv(agent.MAX_TOKENS_ENV, "2k")

    with pytest.raises(agent.AgentError, match="whole number"):
        agent.max_tokens()


def test_a_max_tokens_of_zero_is_a_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(agent.MAX_TOKENS_ENV, "0")

    with pytest.raises(agent.AgentError, match="at least one"):
        agent.max_tokens()


def test_max_tokens_is_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(agent.MAX_TOKENS_ENV, "4096")

    assert agent.max_tokens() == 4096


# -- trimming reaches a nested record -----------------------------------------


def test_trimming_reaches_a_record_nested_under_a_key() -> None:
    """`compare_variants` already answers `{"a": {...}, "b": {...}}`. A tool
    that nests a list of exercises brings back the payload this exists to
    bound, with nothing failing to say so."""
    answer = {"variants": [{"id": "X", "instructions": ["long"], "level": "expert"}]}

    trimmed = agent._trimmed(answer, agent.FOR_THE_LOG)

    assert trimmed == {"variants": [{"id": "X"}]}


def test_an_answer_envelope_is_not_cut_to_an_exercise_record() -> None:
    """`known: false` is the difference between *nobody has trained this* and a
    field that happens to be empty, and it is not a catalog field to drop."""
    answer = {"about": "squat", "known": False, "value": None}

    assert agent._trimmed(answer, agent.FOR_THE_LOG) == answer


def test_a_provider_failure_outside_the_status_hierarchy_is_still_words() -> None:
    """`APIResponseValidationError` inherits from `APIError`, not from
    `APIStatusError`. A chain that ends at the status hierarchy leaves a door
    for a traceback to reach the terminal."""
    import groq as sdk
    import httpx

    def malformed() -> None:
        raise sdk.APIResponseValidationError(
            response=httpx.Response(200, request=httpx.Request("POST", "https://x")),
            body=None,
        )

    with pytest.raises(agent.AgentError, match="the provider failed"):
        agent._reported(malformed)


# -- the agent never writes ---------------------------------------------------
#
# ROADMAP.md § Session 5: writes are never tools. If the model can call the
# write, the model decides when the database changes -- the single door
# disappears, the validator becomes optional, and an interrupted run leaves
# half a workout behind. The agent emits; the engine writes, from the CLI.


def workout_count(connection: sqlite3.Connection) -> int:
    return int(
        connection.execute("SELECT COUNT(*) AS total FROM workouts").fetchone()["total"]
    )


def test_the_loop_leaves_the_workout_count_unchanged(
    connection: sqlite3.Connection,
) -> None:
    identifier = prescribe(connection)
    ask, _ = answers()
    model = Scripted(
        turns=[(call("prescribed_workout", workout_id=identifier),), "fine"],
        emitted=performed(workout_id=identifier, report="fatto"),
    )

    record = agent.log_workout(
        connection, "fatto", TODAY, ask=ask, awaiting=identifier, model=model, budget=4
    )

    assert record.refused is None
    assert workout_count(connection) == 1, "the prescription, and nothing the loop wrote"


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "trainer"
PACKAGE_NAME = "trainer"


def _importers_of(
    name: str, root: Path = PACKAGE_ROOT, package: str = PACKAGE_NAME
) -> set[str]:
    """Every module under `root` whose source imports `name`.

    Every form the import can take, absolute and relative, because a guard
    that catches four of five is a guard that tells you the writer is
    unreachable while somebody is calling it -- and the one it misses is the
    one a future module inside the package is most likely to be written with.
    """
    found: set[str] = set()
    for module in sorted(root.rglob("*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        here = _module_name(module, root, package)
        for node in ast.walk(tree):
            imported: set[str] = set()
            if isinstance(node, ast.Import):
                imported = {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                base = _resolved(node, here)
                if base is not None:
                    imported = {base} | {
                        f"{base}.{alias.name}" for alias in node.names
                    }
            if name in imported:
                found.add(str(module.relative_to(root)).replace("\\", "/"))
    return found


def _module_name(module: Path, root: Path, package: str) -> str:
    """The dotted name of a file, as Python would import it."""
    parts = module.relative_to(root).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join((package, *parts))


def _resolved(node: ast.ImportFrom, here: str) -> str | None:
    """What `from ... import` names, absolute or relative to `here`.

    `node.level` is the number of leading dots: zero is absolute, one means
    the importing module's own package, and each further dot climbs one more.
    """
    if node.level == 0:
        return node.module
    ancestors = here.split(".")[: -node.level]
    if not ancestors:
        return None
    return ".".join((*ancestors, node.module)) if node.module else ".".join(ancestors)


@pytest.mark.parametrize(
    "source",
    [
        "import trainer.engine.workouts",
        "from trainer.engine import workouts",
        "from trainer.engine.workouts import record_prescribed",
        "from .engine import workouts",
        "from .engine.workouts import record_prescribed",
    ],
)
def test_the_writer_guard_catches_every_form_of_the_import(
    source: str, tmp_path: Path
) -> None:
    """The guard is only worth having if it fails on the code it forbids --
    `test_engine_boundary.py` makes the same point about its own. The two
    relative forms are here because the guard once missed both, and a module
    added inside the package is exactly where they would be written."""
    (tmp_path / "offender.py").write_text(source, encoding="utf-8")

    assert _importers_of("trainer.engine.workouts", tmp_path) == {"offender.py"}


def test_the_writer_guard_does_not_fire_on_something_else(tmp_path: Path) -> None:
    """A guard that matched everything would pass this suite while saying
    nothing at all."""
    (tmp_path / "innocent.py").write_text(
        "from trainer.engine import duration\nfrom .engine import catalog\n",
        encoding="utf-8",
    )

    assert _importers_of("trainer.engine.workouts", tmp_path) == set()


def test_only_the_cli_and_the_document_reach_the_writer_module() -> None:
    """A short, explicit list of who may even see the module.

    `log.py` joined it in session 5 and does not write: it reads the
    prescribed phase back, because adherence has to know what was prescribed
    in order to fill in what a report did not mention, and it names the two
    performed dataclasses because those are what a complete block is.
    `tools.py` joined it for `prescribed_workout`, which is the same read
    offered to a model. `log_set.py` names `PrescribedBlock` because a
    prescription in the log set *is* one and there is no second shape for it,
    and `log_evaluation.py` writes those four blocks into the fixture the set
    is measured against -- see the next test, which is the one that matters
    and which says exactly what that exception covers.
    """
    assert _importers_of("trainer.engine.workouts") == {
        "cli.py",
        "log.py",
        "log_evaluation.py",
        "log_set.py",
        "tools.py",
    }


WRITERS = ("record_prescribed", "record_performed")
"""The two functions that change what the database says happened. The guard
below is about these names, not about the module that holds them."""


def _callers_of(
    writers: tuple[str, ...] = WRITERS, root: Path = PACKAGE_ROOT
) -> set[str]:
    """Every module under `root` outside the engine that names one of the
    writers -- called as `workouts.record_performed(...)` or imported bare and
    called by name.

    A call rather than an import, because `log.py` legitimately needs the
    module: it reads the prescribed phase back in order to fill in what a
    report did not mention, and it names the two performed dataclasses because
    those are what a complete block is. Reading is not writing. What must stay
    impossible is the *call*, from anywhere but the command.
    """
    found: set[str] = set()
    for module in sorted(root.rglob("*.py")):
        if module.is_relative_to(root / "engine"):
            # The engine defines them and may call its own; the claim is about
            # everything above it.
            continue
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        for node in ast.walk(tree):
            named = (
                node.attr
                if isinstance(node, ast.Attribute)
                else node.id
                if isinstance(node, ast.Name)
                else None
            )
            if named in writers:
                found.add(str(module.relative_to(root)).replace("\\", "/"))
    return found


def test_only_the_cli_calls_a_writer() -> None:
    """The runtime assertions above say the writer was not called on these
    paths. This says it cannot be, from anywhere but the command -- which is
    the claim that has to survive somebody adding a tool next session.

    It is about the two writer names rather than about the module because
    session 5 gave that module readers as well: `log.py` reads the prescribed
    phase to fill in what a report left out. Written as *nobody but the CLI
    may import `workouts`*, this test would have had to be relaxed to let a
    reader through, and relaxing it is what loses the claim. Written about the
    writers, it says exactly what ROADMAP.md says -- the agent emits, the
    engine writes -- and it stays sharp.

    **`log_evaluation.py` is the one exception, and it is a narrow one.** The
    log set is measured against four prescribed workouts and one performed
    one, and building those means writing them: there is no fixture without a
    writer. What the exception does not cover is the part that would matter --
    **scoring a run writes nothing**, because a document is resolved and
    costed with `workouts.volume`, which reads -- and what the fixture writes
    into is a throwaway copy, deleted with the temp directory it was made in.
    The database the user trains against is opened once, read, and never
    written. `test_log_evaluation.py` holds the runtime guard on that claim,
    and it is what keeps this line from being a hole.
    """
    assert _callers_of() == {"cli.py", "log_evaluation.py"}


@pytest.mark.parametrize(
    "source",
    [
        "workouts.record_prescribed(connection, blocks, on='2026-09-09')",
        "workouts.record_performed(connection, blocks, on='2026-09-09', report='')",
        "record_performed(connection, blocks, on='2026-09-09', report='')",
        "engine.workouts.record_prescribed(connection, blocks, on='2026-09-09')",
    ],
)
def test_the_writer_guard_catches_every_form_of_the_call(
    source: str, tmp_path: Path
) -> None:
    """The guard is only worth having if it fails on the code it forbids --
    `test_engine_boundary.py` makes the same point about its own."""
    (tmp_path / "offender.py").write_text(source, encoding="utf-8")

    assert _callers_of(root=tmp_path) == {"offender.py"}


def test_the_writer_call_guard_does_not_fire_on_a_reader(tmp_path: Path) -> None:
    """Reading the prescribed phase and naming the performed dataclasses is
    what `log.py` does, and it must not read as a write."""
    (tmp_path / "innocent.py").write_text(
        "from trainer.engine import workouts\n"
        "blocks = workouts.prescribed(connection, 1)\n"
        "item = workouts.PerformedItem(exercise_id='x', unit='reps', amount=8,\n"
        "                              amount_source='reported')\n",
        encoding="utf-8",
    )

    assert _callers_of(root=tmp_path) == set()


# -- the logging door ---------------------------------------------------------
#
# The second agent. Same loop, same record, same seam -- what changes is which
# tools are on the table, what its results carry, and that a turn with no tool
# calls in it can be a question to the user rather than the end.

TODAY = "2026-09-10"


def prescribe(connection: sqlite3.Connection, on: str = "2026-09-09") -> int:
    """One prescribed workout on the fixture catalog: squats, four rounds.

    Written straight through the engine. The guard that only the CLI may call
    a writer is about `src/trainer`, and a test that could not set up a
    prescription could not exercise a single thing this door does.
    """
    return workouts.record_prescribed(
        connection,
        (
            workouts.PrescribedBlock(
                block=duration.Block(
                    items=(
                        duration.BlockItem(exercise_id="Barbell_Squat", reps=8),
                        duration.BlockItem(
                            exercise_id="Standing_Military_Press", reps=10
                        ),
                    ),
                    rounds=4,
                    rest=150,
                ),
                reason="legs and a press",
            ),
        ),
        on=on,
    )


def performed(**fields: Any) -> logs.PerformedWorkout:
    """A report in the shape the logging agent emits, deviations only."""
    base: dict[str, Any] = {"report": "tutto come scritto"}
    base.update(fields)
    return logs.PerformedWorkout(**base)


def done(
    exercise_id: str, source: logs.Provenance = "reported", **fields: Any
) -> logs.PerformedBlock:
    """One block as it was performed, with the provenance under test on it."""
    block: dict[str, Any] = {
        "items": [
            logs.PerformedItem(
                exercise_id=exercise_id, unit="reps", amount=8, amount_source=source
            )
        ],
        "rounds": 3,
        "rounds_source": source,
        "rest": 150,
        "rest_source": source,
    }
    block.update(fields)
    return logs.PerformedBlock(**block)


def answers(*given: str) -> tuple[Callable[[str], str], list[str]]:
    """An answerer scripted in advance, and the questions it was put.

    A parameter rather than a call to `click`: the turn belongs to the loop and
    the terminal does not, which is the whole reason it can be measured at all.
    """
    asked: list[str] = []
    remaining = list(given)

    def ask(question: str) -> str:
        asked.append(question)
        return remaining.pop(0) if remaining else "yes"

    return ask, asked


def test_the_logging_door_offers_six_tools_and_none_of_them_writes() -> None:
    """The number is the ticket's, and the claim under it is the session's: if
    the model can call the write, the model decides when the database changes.

    Checked against the functions the door actually registers rather than
    against its list of names -- a name that resolved to something else would
    pass a test written about the constant.
    """
    offered = agent.registered(agent.LOGGER.name, agent.LOGGER.tools)

    assert len(offered) == 6
    for tool in offered:
        source = ast.parse(textwrap.dedent(inspect.getsource(tool)))
        named = {
            node.attr if isinstance(node, ast.Attribute) else node.id
            for node in ast.walk(source)
            if isinstance(node, (ast.Attribute, ast.Name))
        }
        assert not named & set(WRITERS), f"{tool.__name__} reaches a writer"
        assert "add" not in named, f"{tool.__name__} may write an exclusion"


def test_a_door_asking_for_a_tool_nobody_defined_is_a_state() -> None:
    """The door constants are the one place a tool name can be misspelled, and
    a surface quietly one tool short looks like a model that chose not to
    call it."""
    door = agent.Door(
        name="typo", tools=("prescribed_wrokout",), keeps=(), system="", emit=""
    )

    with pytest.raises(agent.AgentError, match="prescribed_wrokout"):
        agent.surface(door)


def test_the_logger_cannot_call_a_tool_the_planner_has(
    connection: sqlite3.Connection,
) -> None:
    """A tool that exists is not a tool this agent was offered. It comes back
    as a result it can recover from, listing what it does have."""
    result = executed(call("admissible_set", equipment=["barbell"], budget_min=45))

    assert result.failed is True
    assert "no tool called 'admissible_set'" in result.content
    assert "prescribed_workout" in result.content


def test_the_logger_is_shown_the_exercise_names_the_user_says_out_loud(
    connection: sqlite3.Connection,
) -> None:
    """The planner drops `name`, because a plan is written in ids and a model
    shown both copied the readable one into `exercise_id`. This door has the
    opposite job: resolving *"the bench"* against the prescribed workout is
    not possible when everything in it is an id nobody says out loud."""
    identifier = prescribe(connection)

    result = executed(call("prescribed_workout", workout_id=identifier))

    assert "Barbell Squat" in result.content
    assert "name" in json.loads(result.content)["blocks"][0]["items"][0]


def test_a_windowed_read_with_no_configuration_is_a_failed_result(
    connection: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`pattern_history` counts in cycles and only `training.toml` says how
    long one is. On a machine that has not declared one it comes back as a
    stated failure naming the file to copy -- not a crash, and not an empty
    history, which would read as *nobody has trained this*."""
    monkeypatch.setenv("TRAINER_CONFIG", str(tmp_path / "absent.toml"))

    result = executed(call("pattern_history", pattern="squat", cycles=1))

    assert result.failed is True
    assert "no training configuration yet" in result.content
    assert "absent.toml" in result.content, "it names the file to write"
    assert ".example.toml" in result.content, "and the one to copy"


def test_a_run_reads_the_prescription_and_emits_a_report(
    connection: sqlite3.Connection,
) -> None:
    identifier = prescribe(connection)
    ask, asked = answers()
    model = Scripted(
        turns=[(call("prescribed_workout", workout_id=identifier),), "tutto chiaro"],
        emitted=performed(
            workout_id=identifier,
            blocks=[done("Barbell_Squat", rounds=3)],
            report="solo tre serie di squat",
        ),
    )

    record = agent.log_workout(
        connection, "solo tre serie di squat", TODAY, ask=ask, awaiting=identifier,
        model=model,
    )

    assert record.refused is None
    assert [c.name for c in record.calls] == ["prescribed_workout"]
    assert record.document.workout_id == identifier
    assert asked == [], "nothing in that sentence needed clarifying"


def test_the_brief_names_the_workout_that_is_open_and_the_words_that_were_said(
    connection: sqlite3.Connection,
) -> None:
    written = agent.log_brief("panca pesante", TODAY, awaiting=12, prescribed_on="2026-09-09")

    assert "prescribed_workout(12)" in written
    assert "2026-09-09" in written
    assert "panca pesante" in written
    assert TODAY in written, "a re-test date has to be after a day it knows"


def test_the_brief_says_when_nothing_is_waiting_for_a_report() -> None:
    """Training nobody planned is training. The state is named rather than
    left for the model to infer from a workout id it was not given."""
    written = agent.log_brief("sono andato a correre", TODAY)

    assert "No prescribed workout is waiting" in written
    assert "null" in written


# -- resolving an exercise: the closed set first -------------------------------


def test_a_substitution_reaches_the_catalog_only_after_the_prescribed_set_fails(
    connection: sqlite3.Connection,
) -> None:
    """The candidates are the exercises of the prescribed workout. Catalog
    search is the fallback, called exactly when the closed set has nothing that
    can be what the user meant -- which is exactly when there was a
    substitution, and that is the interesting case."""
    identifier = prescribe(connection)
    ask, _ = answers()
    model = Scripted(
        turns=[
            (call("prescribed_workout", workout_id=identifier),),
            (call("search_exercises", text="dumbbell bench"),),
            "tutto chiaro",
        ],
        emitted=performed(
            workout_id=identifier,
            blocks=[done("Dumbbell_Bench_Press")],
            report="ho scambiato i military con la panca coi manubri",
        ),
    )

    record = agent.log_workout(
        connection, "ho scambiato i military", TODAY, ask=ask,
        awaiting=identifier, model=model,
    )

    assert [c.name for c in record.calls] == [
        "prescribed_workout",
        "search_exercises",
    ]
    assert record.refused is None
    substituted = record.document.blocks[0].items[0].exercise_id
    assert catalog.exercise(connection, substituted) is not None


def test_an_id_the_model_remembered_rather_than_read_is_refused(
    connection: sqlite3.Connection,
) -> None:
    """A well-formed dead id passes anything that does not check the catalog,
    and the error becomes volume filed under the wrong exercise, silently.

    It is refused rather than made impossible, and that is the trade this door
    makes for showing the model exercise names at all."""
    identifier = prescribe(connection)
    ask, _ = answers()
    model = Scripted(
        turns=["tutto chiaro"],
        emitted=performed(
            workout_id=identifier,
            blocks=[done("Barbell_Bench_Press_Medium_Grip")],
            report="panca",
        ),
    )

    record = agent.log_workout(
        connection, "panca", TODAY, ask=ask, awaiting=identifier, model=model
    )

    assert record.refused is not None
    assert "Barbell_Bench_Press_Medium_Grip" in record.refused
    assert record.document.blocks, "the document is still recorded whole"


# -- the clarifying question ---------------------------------------------------


def test_a_report_that_does_not_determine_a_value_produces_a_question(
    connection: sqlite3.Connection,
) -> None:
    """*"4 out of 10"* is effort **or** discomfort, and TRAINER.md's own
    sentence does not say which. The agent asks rather than filling it in."""
    identifier = prescribe(connection)
    ask, asked = answers("fastidio, non fatica")
    model = Scripted(
        turns=[
            (call("prescribed_workout", workout_id=identifier),),
            "QUESTION: Quel 4 su 10 e' fatica o fastidio?",
            "tutto chiaro",
        ],
        emitted=performed(workout_id=identifier, report="squat, 4 su 10"),
    )

    record = agent.log_workout(
        connection, "squat, 4 su 10", TODAY, ask=ask, awaiting=identifier, model=model
    )

    assert asked == ["Quel 4 su 10 e' fatica o fastidio?"]
    assert [q.answered for q in record.questions] == ["fastidio, non fatica"]
    assert record.spent == 1, "asking is not a tool call"


def test_the_answer_reaches_the_model_as_a_turn_of_its_own(
    connection: sqlite3.Connection,
) -> None:
    """In memory, inside one invocation. It is an exchange like any other, and
    that is what makes it impossible to persist: there is nowhere for it to be
    left when the run is interrupted."""
    ask, _ = answers("fastidio")
    model = Scripted(
        turns=["QUESTION: Fatica o fastidio?", "tutto chiaro"],
        emitted=performed(report="4 su 10", blocks=[done("Barbell_Squat")]),
    )

    agent.log_workout(connection, "4 su 10", TODAY, ask=ask, model=model)

    (asked_turn, *_rest) = model.seen
    assert asked_turn.answer == "fastidio"


@pytest.mark.parametrize(
    "written",
    [
        "QUESTION: Fatica o fastidio?",
        "**QUESTION:** Fatica o fastidio?",
        "- QUESTION: Fatica o fastidio?",
        "### QUESTION: Fatica o fastidio?",
        "Ci penso su.\n\n> QUESTION: Fatica o fastidio?",
    ],
)
def test_the_marker_is_found_behind_whatever_the_model_decorates_it_with(
    connection: sqlite3.Connection, written: str
) -> None:
    """Emphasising or bulleting a labelled line is ordinary model behaviour,
    and a strict prefix match misses every one of these.

    Missing is **silent**, and it lands in exactly the failure the marker
    exists to prevent: the turn reads as *nothing to ask*, the loop ends, and
    the document is emitted carrying the value the model meant to check.
    """
    ask, asked = answers("fastidio")
    model = Scripted(
        turns=[written, "fine"],
        emitted=performed(report="4 su 10", blocks=[done("Barbell_Squat")]),
    )

    record = agent.log_workout(connection, "4 su 10", TODAY, ask=ask, model=model)

    assert asked == ["Fatica o fastidio?"]
    assert record.questions[0].asked == "Fatica o fastidio?"


def test_the_last_marked_line_is_the_question_because_reasoning_rehearses(
    connection: sqlite3.Connection,
) -> None:
    """A turn that talks itself through two candidate questions before
    settling on one has both in it, and the one it settled on is the last."""
    ask, asked = answers("fastidio")
    model = Scripted(
        turns=[
            "QUESTION: Quante serie?\nNo, quello lo so gia.\n"
            "QUESTION: Fatica o fastidio?",
            "fine",
        ],
        emitted=performed(report="4 su 10", blocks=[done("Barbell_Squat")]),
    )

    agent.log_workout(connection, "4 su 10", TODAY, ask=ask, model=model)

    assert asked == ["Fatica o fastidio?"]


def test_a_turn_that_calls_a_tool_and_asks_does_both(
    connection: sqlite3.Connection,
) -> None:
    """Read only on a turn with no tool calls in it, the question is dropped
    silently -- and the run reads, in the record ticket 05 scores, as one that
    never needed to ask."""
    identifier = prescribe(connection)
    ask, asked = answers("quelli coi manubri")
    model = Scripted(
        turns=[
            Turn(
                calls=(call("search_exercises", text="bench"),),
                text="QUESTION: Manubri o bilanciere?",
            ),
            "fine",
        ],
        emitted=performed(workout_id=identifier, report="panca"),
    )

    record = agent.log_workout(
        connection, "panca", TODAY, ask=ask, awaiting=identifier, model=model
    )

    assert record.spent == 1, "the tool still ran"
    assert asked == ["Manubri o bilanciere?"]
    assert [q.answered for q in record.questions] == ["quelli coi manubri"]
    (first, *_) = model.seen
    assert first.results, "the results are on the same exchange"
    assert first.answer == "quelli coi manubri"


def test_the_question_budget_stops_a_model_that_only_asks(
    connection: sqlite3.Connection,
) -> None:
    """It emits with what it has rather than looping -- the same property the
    call budget has, applied to the other thing a turn can be. Somebody is
    answering these in a terminal after training."""
    ask, asked = answers(*["si"] * 10)
    model = Scripted(
        turns=["QUESTION: Prima?",
            "QUESTION: Seconda?",
            "QUESTION: Terza?",
            "QUESTION: Quarta?",
            "QUESTION: Quinta?"],
        emitted=performed(report="4 su 10", blocks=[done("Barbell_Squat")]),
    )

    record = agent.log_workout(connection, "4 su 10", TODAY, ask=ask, model=model)

    assert len(asked) == agent.ASK_BUDGET
    assert len(record.questions) == agent.ASK_BUDGET
    assert model.emissions == 1


def test_a_turn_with_nothing_in_it_ends_the_loop_rather_than_asking_a_blank(
    connection: sqlite3.Connection,
) -> None:
    """A truncated completion looks exactly like a model with nothing to say,
    and handing the user an empty prompt is worse than emitting."""
    ask, asked = answers()
    model = Scripted(
        turns=["   "],
        emitted=performed(report="fatto", blocks=[done("Barbell_Squat")]),
    )

    agent.log_workout(connection, "fatto", TODAY, ask=ask, model=model)

    assert asked == []


# -- the exclusion it may propose ----------------------------------------------


def test_a_proposed_exclusion_travels_in_the_document_and_writes_nothing(
    connection: sqlite3.Connection,
) -> None:
    """The agent emits and the engine writes. Even the one thing in a report
    that changes what may be prescribed tomorrow leaves this function as a
    field on a document, and the confirmation is the command's."""
    identifier = prescribe(connection)
    ask, _ = answers()
    model = Scripted(
        turns=["tutto chiaro"],
        emitted=performed(
            workout_id=identifier,
            report="la spalla tirava sui military",
            proposed_exclusion=logs.ProposedExclusion(
                value="shoulder", retest_date="2026-10-15", why="la spalla tirava"
            ),
        ),
    )

    record = agent.log_workout(
        connection, "la spalla tirava", TODAY, ask=ask, awaiting=identifier, model=model
    )

    assert record.refused is None
    assert record.document.proposed_exclusion is not None
    assert exclusions.active(connection, TODAY) == ()


def test_a_re_test_date_that_has_already_passed_is_refused(
    connection: sqlite3.Connection,
) -> None:
    """A wall that was never a wall is the same failure as a wall with no way
    back, with the sign flipped: nothing re-reads the row, and the render
    prints a confident sentence about a movement that is not excluded."""
    ask, _ = answers()
    model = Scripted(
        turns=["tutto chiaro"],
        emitted=performed(
            report="spalla",
            blocks=[done("Barbell_Squat")],
            proposed_exclusion=logs.ProposedExclusion(
                value="shoulder", retest_date="2026-01-01", why="spalla"
            ),
        ),
    )

    record = agent.log_workout(connection, "spalla", TODAY, ask=ask, model=model)

    assert record.refused is not None
    assert "2026-01-01" in record.refused


# -- the budget, and the record ------------------------------------------------


def test_a_logging_run_that_spends_its_budget_emits_anyway(
    connection: sqlite3.Connection,
) -> None:
    identifier = prescribe(connection)
    ask, _ = answers()
    model = Scripted(
        turns=[(call("prescribed_workout", workout_id=identifier),)] * 6,
        emitted=performed(workout_id=identifier, report="fatto"),
    )

    record = agent.log_workout(
        connection, "fatto", TODAY, ask=ask, awaiting=identifier, model=model, budget=3
    )

    assert record.spent == 3
    assert record.emitted_on_exhaustion is True
    assert model.emissions == 1


def test_the_logging_record_writes_out_as_json(connection: sqlite3.Connection) -> None:
    """Ticket 05 reads this rather than asking the model what it did, so
    everything a check needs is a field."""
    identifier = prescribe(connection)
    ask, _ = answers("fastidio")
    model = Scripted(
        turns=["QUESTION: Fatica o fastidio?", "tutto chiaro"],
        emitted=performed(workout_id=identifier, report="4 su 10"),
    )

    record = agent.log_workout(
        connection, "4 su 10", TODAY, ask=ask, awaiting=identifier, model=model
    )
    written = json.loads(record.model_dump_json())

    assert written["questions"] == [
        {"asked": "Fatica o fastidio?", "answered": "fastidio"}
    ]
    assert written["document"]["report"] == "4 su 10"
    assert written["model"] == "a-stand-in"


def test_the_summary_of_a_logging_run_is_ascii_and_counts_the_questions(
    connection: sqlite3.Connection,
) -> None:
    ask, _ = answers("fastidio")
    model = Scripted(
        turns=["QUESTION: Fatica o fastidio?", "tutto chiaro"],
        emitted=performed(report="4 su 10", blocks=[done("Barbell_Squat")]),
    )

    record = agent.log_workout(connection, "4 su 10", TODAY, ask=ask, model=model)
    lines = agent.summary(record)

    assert all(line.isascii() for line in lines)
    assert any("1 question(s) asked" in line for line in lines)


def test_an_interrupted_conversation_writes_nothing_at_all(
    connection: sqlite3.Connection,
) -> None:
    """Ctrl-C at a question. Nothing about a report reaches the database --
    not the workout, not the exclusion, and not a word of the conversation.

    Session 6's issue 5 is the non-negotiable test that LangGraph never
    persists domain and SQLite never persists conversation; a half-finished
    report parked in a table would make it red before it is written.
    """
    identifier = prescribe(connection)
    said = "la spalla tirava, 4 su 10"

    def interrupt(question: str) -> str:
        raise KeyboardInterrupt

    model = Scripted(turns=["QUESTION: Fatica o fastidio?"], emitted=performed(report=said))

    with pytest.raises(KeyboardInterrupt):
        agent.log_workout(
            connection, said, TODAY, ask=interrupt, awaiting=identifier, model=model
        )

    found = workouts.workout(connection, identifier)
    assert found is not None and found.state == "prescribed"
    assert exclusions.active(connection, TODAY) == ()
    assert said not in _everything_stored(connection)


def _everything_stored(connection: sqlite3.Connection) -> str:
    """Every value in every table this schema has, as one string.

    Blunt on purpose: the claim is that no conversation is persisted anywhere,
    and a test that named the tables it expected to be empty would pass for a
    table added next session to hold exactly that.
    """
    tables = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    found: list[str] = []
    for table in tables:
        for row in connection.execute(f'SELECT * FROM "{table["name"]}"'):  # a name
            found.extend(str(value) for value in tuple(row))
    return "\n".join(found)


# -- what the logging prompt has to say ----------------------------------------


def test_the_logging_prompt_carries_the_rules_this_ticket_decided() -> None:
    """Each of these is a rule with nowhere else to live: no code can make a
    model resolve an id inside a closed set first, and a rule the model was
    never told is a finding that is the prompt's fault."""
    for rule in (
        "prescribed_workout",
        "never write an id you remember",
        "only what deviated",
        "verbatim",
        "never ask for it",
        "at most 3 in all",
        "never an exercise id",
        agent.QUESTION_MARKER.lower(),
    ):
        assert rule.lower() in agent.LOGGING.lower(), rule


def test_a_bare_number_has_no_way_of_becoming_an_rpe_without_being_offered(
    connection: sqlite3.Connection,
) -> None:
    """`rpe` carries no provenance, because it is recorded only when the user
    volunteers it -- so `assumed` and `asked` cannot arise for it. The rule the
    prompt states is the one that keeps a bare number off it, and the shape is
    what stops a filled-in one being dressed as something the user was asked."""
    assert "rpe" not in logs.PerformedItem.model_fields
    assert set(logs.PerformedBlock.model_fields) & {"rpe_source"} == set()
    assert "never ask for it" in agent.LOGGING.lower()
