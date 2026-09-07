"""The loop, against a stand-in model.

`conftest.py` removes sockets and credentials from every test on purpose, so
nothing here reaches a provider. What is covered is everything that is this
project's: the tools offered, the call budget, emitting on exhaustion, the way
out through the validator and the fact that there is no way back in, and the
run record ticket 05 will measure on. `agent.Claude` is the one class the
suite never runs -- it is exercised for the first time under `trainer eval`.
"""

from __future__ import annotations

import enum
import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from conftest import enrich, make_exercise
from trainer import agent, plan as plans, tools
from trainer.engine import catalog, database, migrations

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

BARBELL_45 = plans.Request(equipment=("barbell",), budget_min=45)


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
                items=[plans.PlanItem(exercise_id=exercise_id, reps=8)],
                rounds=3,
                rest=120,
                reason="because it is a squat and squats are good",
            )
            for exercise_id in exercise_ids or ("Barbell_Squat",)
        ]
    )


class Scripted:
    """A model whose turns were written in advance.

    `turns` is what it replies with, one per `respond`; when they run out it
    keeps replying with nothing, which is a model that has stopped asking for
    tools. `emitted` is what it hands over when asked for the plan, and it
    counts the asks, because *emitted exactly once* is how this suite states
    that a refused plan is never re-asked.
    """

    def __init__(
        self,
        turns: Sequence[tuple[agent.Call, ...]] | None = None,
        emitted: plans.WorkoutPlan | None = None,
    ) -> None:
        self.turns = list(turns or [])
        self.emitted = emitted if emitted is not None else good_plan()
        self.name = "a-stand-in"
        self.offers: list[list[dict[str, Any]] | None] = []
        self.emissions = 0
        self.seen: list[Any] = []

    def respond(
        self,
        brief: str,
        exchanges: Sequence[agent.Exchange],
        offered: Sequence[dict[str, Any]] | None,
    ) -> agent.Reply:
        self.offers.append(list(offered) if offered is not None else None)
        self.seen = list(exchanges)
        calls = self.turns.pop(0) if self.turns else ()
        return agent.Reply(
            content={"role": "assistant", "content": "thinking"},
            calls=calls,
            input_tokens=100,
            output_tokens=20,
        )

    def emit(self, brief: str, exchanges: Sequence[agent.Exchange]) -> agent.Emission:
        self.emissions += 1
        self.seen = list(exchanges)
        return agent.Emission(plan=self.emitted, input_tokens=200, output_tokens=50)


def call(name: str, **arguments: Any) -> agent.Call:
    return agent.Call(id=f"toolu_{name}", name=name, arguments=arguments)


# -- the tools this door offers -----------------------------------------------


def test_the_tools_offered_are_the_shared_surface_and_nothing_else() -> None:
    """No second definition: the agent's door registers `tools.TOOLS`, the
    same tuple `trainer mcp` registers."""
    offered = agent.surface()

    assert [tool["name"] for tool in offered] == [tool.__name__ for tool in tools.TOOLS]


def test_every_tool_reaches_the_model_with_a_description_and_arguments() -> None:
    """A tool the model cannot fill the arguments in for is a tool it cannot
    call, and a tool with no description is one it cannot choose."""
    for offered in agent.surface():
        assert offered["description"], f"{offered['name']} has no description"
        assert offered["parameters"]["type"] == "object"
        assert offered["parameters"]["properties"], f"{offered['name']} takes nothing"


def test_an_argument_with_a_default_is_not_required() -> None:
    """`admissible_set`'s exclusions are optional, and a schema that demanded
    them would make the common call the harder one to write."""
    (admissible,) = [t for t in agent.surface() if t["name"] == "admissible_set"]

    assert set(admissible["parameters"]["required"]) == {"equipment", "budget_min"}


# -- the loop -----------------------------------------------------------------


def test_a_run_calls_tools_and_emits_a_plan(connection: sqlite3.Connection) -> None:
    model = Scripted(
        turns=[(call("admissible_set", equipment=["barbell"], budget_min=45),), ()],
    )

    record = agent.plan_workout(connection, BARBELL_45, model=model)

    assert record.spent == 1
    assert record.refused is None
    assert record.emitted_on_exhaustion is False
    assert [c.name for c in record.calls] == ["admissible_set"]
    assert record.calls[0].arguments == {"equipment": ["barbell"], "budget_min": 45}


def test_the_calls_are_recorded_in_the_order_they_were_made(
    connection: sqlite3.Connection,
) -> None:
    model = Scripted(
        turns=[
            (call("allocate", minutes=45, proportions={"legs": 1.0}),),
            (
                call("admissible_set", equipment=["barbell"], budget_min=45),
                call("pattern_history", pattern="squat", cycles=3),
            ),
            (),
        ],
    )

    record = agent.plan_workout(connection, BARBELL_45, model=model)

    assert [c.name for c in record.calls] == [
        "allocate",
        "admissible_set",
        "pattern_history",
    ]
    assert record.spent == 3


def test_a_run_that_spends_its_budget_emits_anyway(
    connection: sqlite3.Connection,
) -> None:
    """Invariant 1 of TRAINER.md's six. Behaviour, not an error path."""
    forever = [(call("pattern_history", pattern="squat", cycles=3),)] * 20
    model = Scripted(turns=forever)

    record = agent.plan_workout(connection, BARBELL_45, model=model, budget=3)

    assert record.spent == 3
    assert record.emitted_on_exhaustion is True
    assert record.refused is None
    assert record.plan.blocks, "it emitted nothing"
    assert model.emissions == 1


def test_the_tools_are_taken_off_the_table_when_the_budget_runs_out(
    connection: sqlite3.Connection,
) -> None:
    """It does not fail and it does not keep going: it stops offering tools
    and asks for the plan with what it has."""
    forever = [(call("pattern_history", pattern="squat", cycles=3),)] * 20
    model = Scripted(turns=forever)

    agent.plan_workout(connection, BARBELL_45, model=model, budget=2)

    assert all(offer for offer in model.offers), "a turn was offered no tools"
    assert len(model.offers) == 2, "it kept asking after the budget was gone"


def test_a_model_that_stops_asking_early_is_not_charged_the_whole_budget(
    connection: sqlite3.Connection,
) -> None:
    model = Scripted(turns=[()])

    record = agent.plan_workout(connection, BARBELL_45, model=model, budget=12)

    assert record.spent == 0
    assert record.emitted_on_exhaustion is False


def test_a_budget_under_one_call_is_refused(connection: sqlite3.Connection) -> None:
    with pytest.raises(agent.AgentError, match="at least one call"):
        agent.plan_workout(connection, BARBELL_45, model=Scripted(), budget=0)


# -- what a tool failure does -------------------------------------------------


def test_a_tool_failure_goes_back_to_the_model_as_a_result(
    connection: sqlite3.Connection,
) -> None:
    """A stated failure is something the model can act on -- it asked for an
    exercise nobody has, and the next turn it can ask for one that exists."""
    model = Scripted(
        turns=[(call("last_performed_load", exercise_id="Barbell_Sqvat"),), ()],
    )

    record = agent.plan_workout(connection, BARBELL_45, model=model)

    assert record.calls[0].failed is True
    assert record.calls[0].detail is not None
    assert "Barbell_Sqvat" in record.calls[0].detail
    assert record.refused is None, "the run carried on"


def test_a_tool_the_surface_does_not_have_is_a_result_not_a_crash(
    connection: sqlite3.Connection,
) -> None:
    """The model's mistake, not this project's, so it comes back as something
    it can recover from -- with the real names in it."""
    model = Scripted(turns=[(call("adherence_history", cycles=3),), ()])

    record = agent.plan_workout(connection, BARBELL_45, model=model)

    assert record.calls[0].failed is True
    assert record.calls[0].detail is not None
    assert "admissible_set" in record.calls[0].detail


def test_arguments_that_do_not_fit_the_signature_are_a_result_not_a_crash(
    connection: sqlite3.Connection,
) -> None:
    model = Scripted(turns=[(call("allocate", minutes=45, groups={"legs": 1.0}),), ()])

    record = agent.plan_workout(connection, BARBELL_45, model=model)

    assert record.calls[0].failed is True


# -- the way out, and no way back in ------------------------------------------


def test_a_plan_that_breaks_a_rule_is_recorded_as_refused(
    connection: sqlite3.Connection,
) -> None:
    model = Scripted(emitted=good_plan("Dumbbell_Bench_Press"))

    record = agent.plan_workout(connection, BARBELL_45, model=model)

    assert record.refused is not None
    assert "Dumbbell_Bench_Press" in record.refused
    assert "dumbbell" in record.refused


def test_a_refused_plan_is_not_handed_back_to_the_model(
    connection: sqlite3.Connection,
) -> None:
    """*Propose -> check -> correct* is the loop TRAINER.md deliberately does
    not have: the constraints are applied upstream, and a refusal here is a
    bug to go and read rather than a turn to spend."""
    model = Scripted(emitted=good_plan("Dumbbell_Bench_Press"))

    agent.plan_workout(connection, BARBELL_45, model=model)

    assert model.emissions == 1


def test_a_refused_plan_is_still_recorded_whole(
    connection: sqlite3.Connection,
) -> None:
    """The record exists to be read after a refusal; one that dropped the plan
    would answer every question except the one being asked."""
    model = Scripted(emitted=good_plan("Dumbbell_Bench_Press"))

    record = agent.plan_workout(connection, BARBELL_45, model=model)

    assert record.plan.blocks[0].items[0].exercise_id == "Dumbbell_Bench_Press"


def test_a_plan_the_block_vocabulary_cannot_express_is_refused_too(
    connection: sqlite3.Connection,
) -> None:
    """Reps and seconds both given. The structured shape does not carry that
    rule -- `BlockItem` is where it lives -- so it arrives here as a shape
    failure, and from the run's point of view that is the same outcome: the
    plan did not get through the door."""
    emitted = plans.WorkoutPlan(
        blocks=[
            plans.PlanBlock(
                items=[plans.PlanItem(exercise_id="Barbell_Squat", reps=8, seconds=30)],
                rounds=3,
                rest=120,
                reason="both at once",
            )
        ]
    )

    record = agent.plan_workout(connection, BARBELL_45, model=Scripted(emitted=emitted))

    assert record.refused is not None
    assert "block 1" in record.refused


# -- the record ---------------------------------------------------------------


def test_the_record_writes_out_as_json(connection: sqlite3.Connection) -> None:
    """Ticket 05 decides its invariants by reading this rather than by asking
    the model what it did."""
    model = Scripted(turns=[(call("admissible_set", equipment=["barbell"], budget_min=45),), ()])

    record = agent.plan_workout(connection, BARBELL_45, model=model)
    written = json.loads(record.model_dump_json())

    assert written["model"] == "a-stand-in"
    assert written["budget"] == agent.CALL_BUDGET
    assert written["spent"] == 1
    assert written["emitted_on_exhaustion"] is False
    assert written["calls"][0]["arguments"]["equipment"] == ["barbell"]
    assert written["plan"]["blocks"][0]["items"][0]["exercise_id"] == "Barbell_Squat"
    assert written["refused"] is None


def test_the_record_counts_what_the_run_cost(connection: sqlite3.Connection) -> None:
    """What a pass costs is what ticket 05 reports, so it is counted here
    rather than estimated there."""
    model = Scripted(turns=[(call("allocate", minutes=45, proportions={"legs": 1.0}),), ()])

    record = agent.plan_workout(connection, BARBELL_45, model=model)

    assert record.input_tokens == 100 + 100 + 200
    assert record.output_tokens == 20 + 20 + 50


def test_the_summary_is_ascii(connection: sqlite3.Connection) -> None:
    record = agent.plan_workout(connection, BARBELL_45, model=Scripted())

    assert "\n".join(agent.summary(record)).isascii()


def test_the_summary_says_when_the_plan_was_emitted_on_exhaustion(
    connection: sqlite3.Connection,
) -> None:
    forever = [(call("pattern_history", pattern="squat", cycles=3),)] * 20
    record = agent.plan_workout(
        connection, BARBELL_45, model=Scripted(turns=forever), budget=2
    )

    assert "budget spent" in "\n".join(agent.summary(record))


# -- the request the model is given -------------------------------------------


def test_the_model_is_told_what_it_is_planning_against(
    connection: sqlite3.Connection,
) -> None:
    request = plans.Request(equipment=("barbell", "dumbbell"), budget_min=30)

    written = agent.brief(request)

    assert "barbell, dumbbell" in written
    assert "30 minutes" in written


def test_the_prompt_carries_the_rules_the_validator_will_apply() -> None:
    """A model that is not told the rules is one whose refusals are the
    prompt's fault rather than a finding."""
    for rule in ("admissible_set", "never trimmed to fit", "at most once", "reason"):
        assert rule.lower() in agent.SYSTEM.lower(), rule


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


def test_the_backend_defaults_to_groq_when_nothing_names_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(agent.BACKEND_ENV, raising=False)

    assert agent.backend() == agent.GROQ


def test_a_backend_nobody_built_is_named_rather_than_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`.env.example` offers ollama as the one to come. Falling through to Groq
    would answer a question the user did not ask, with their key."""
    monkeypatch.setenv(agent.BACKEND_ENV, "ollama")

    with pytest.raises(agent.AgentError, match="ollama"):
        agent.backend()


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


# -- what the model can get wrong ---------------------------------------------


def test_an_argument_of_the_wrong_shape_is_a_result_not_a_crash(
    connection: sqlite3.Connection,
) -> None:
    """Exclusions as a list of strings rather than of objects. It satisfies
    the signature, reaches the tool body and comes apart on a string -- a
    traceback, no record, and a paid-for run thrown away over something the
    model could have corrected next turn."""
    model = Scripted(
        turns=[
            (call("admissible_set", equipment=["barbell"], budget_min=45,
                  exclusions=["squat"]),),
            (),
        ],
    )

    record = agent.plan_workout(connection, BARBELL_45, model=model)

    assert record.calls[0].failed is True
    assert record.calls[0].detail is not None
    assert "do not fit" in record.calls[0].detail


def test_a_dict_where_a_list_belongs_is_a_result_not_a_crash(
    connection: sqlite3.Connection,
) -> None:
    model = Scripted(turns=[(call("allocate", minutes=45, proportions=["legs"]),), ()])

    record = agent.plan_workout(connection, BARBELL_45, model=model)

    assert record.calls[0].failed is True


def test_an_argument_nobody_declared_is_a_result_not_a_crash(
    connection: sqlite3.Connection,
) -> None:
    model = Scripted(
        turns=[(call("allocate", minutes=45, proportions={"legs": 1.0}, why="because"),), ()]
    )

    record = agent.plan_workout(connection, BARBELL_45, model=model)

    assert record.calls[0].failed is True
    assert record.calls[0].detail is not None
    assert "why" in record.calls[0].detail


# -- what the model is handed back --------------------------------------------


def test_a_result_reaches_the_model_as_json(connection: sqlite3.Connection) -> None:
    """The tool docstrings describe `known: false`; Python would hand back
    `'known': False`, and a model translating between two dialects mid-loop is
    one more thing that can go wrong for nothing."""
    result = agent._execute(call("pattern_history", pattern="squat", cycles=3))

    assert result.failed is False
    assert json.loads(result.content)["known"] is False


def test_an_admissible_set_reaches_the_model_without_its_prose(
    connection: sqlite3.Connection,
) -> None:
    """One answer must not be larger than the whole output budget. Instructions
    and image paths are most of an exercise record and nothing in planning
    reads either, and the loop re-sends every result on every later turn."""
    result = agent._execute(call("admissible_set", equipment=["barbell"], budget_min=45))
    (first, *_) = json.loads(result.content)

    assert result.failed is False
    assert first["id"] and first["equipment"]
    assert "instructions" not in first
    assert "images" not in first


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

    agent.Groq(client=client, model="qwen/qwen3.8-27b").respond("today", [], agent.surface())

    (request,) = client.requests
    assert [tool["type"] for tool in request["tools"]] == ["function"] * len(tools.TOOLS)
    assert request["tools"][0]["function"]["name"] == tools.TOOLS[0].__name__
    assert "response_format" not in request


def test_the_emission_offers_no_tools_at_all() -> None:
    """Groq does not allow structured outputs and tool use in one request. This
    is the assertion that would have caught a request built the other way."""
    client = FakeGroq(FakeMessage(content=good_plan().model_dump_json()))

    agent.Groq(client=client, model="qwen/qwen3.8-27b").emit("today", [])

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

    agent.Groq(client=client, model="m").respond("today", [exchange], None)

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

    reply = agent.Groq(client=client, model="m").respond("today", [], agent.surface())

    (call_,) = reply.calls
    assert call_.arguments == {"minutes": 45, "proportions": {"legs": 1.0}}


def test_an_emission_that_is_not_a_plan_is_a_state_not_a_traceback() -> None:
    client = FakeGroq(FakeMessage(content='{"blocks": "nonsense"}'))

    with pytest.raises(agent.AgentError, match="did not parse"):
        agent.Groq(client=client, model="m").emit("today", [])


def test_an_empty_emission_is_a_state_not_a_traceback() -> None:
    client = FakeGroq(FakeMessage(content=None))

    with pytest.raises(agent.AgentError, match="no plan"):
        agent.Groq(client=client, model="m").emit("today", [])


def test_a_provider_that_cannot_be_reached_is_reported_in_words() -> None:
    import groq as sdk
    import httpx

    def unreachable() -> None:
        raise sdk.APIConnectionError(request=httpx.Request("POST", "https://api.groq.com"))

    with pytest.raises(agent.AgentError, match="could not be reached"):
        agent._reported(unreachable)


# -- the shape the model is held to -------------------------------------------


def test_strict_mode_requires_every_property_including_the_optional_pair() -> None:
    """Strict mode is constrained decoding, and it demands every property be
    listed in `required`. Pydantic leaves out the ones with defaults, which is
    exactly `reps` and `seconds` -- the pair that carries *either reps or
    seconds*. Their optionality survives as the null in their type."""
    built = agent.strict_schema(plans.WorkoutPlan)
    item = built["$defs"]["PlanItem"]

    assert set(item["required"]) == {"exercise_id", "reps", "seconds"}
    assert item["additionalProperties"] is False
    assert built["required"] == ["blocks"]


def test_the_strict_shape_still_accepts_a_plan_the_project_calls_valid() -> None:
    """The transform above rewrites the schema the model is held to. If it
    drifted from what `WorkoutPlan` actually parses, every run would emit
    something the validator then refuses on shape."""
    import jsonschema

    emitted = json.loads(good_plan("Barbell_Squat").model_dump_json())
    emitted["blocks"][0]["items"][0]["seconds"] = None

    jsonschema.validate(emitted, agent.strict_schema(plans.WorkoutPlan))


def test_the_record_names_the_model_that_ran_not_the_environment(
    connection: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ticket 05 compares invariants across models by building one per run. A
    record that re-read the environment afterwards would stamp every one of
    them with whatever `GROQ_MODEL` happened to say."""
    monkeypatch.setenv(agent.MODEL_ENV, "a-model-nobody-ran")
    model = Scripted()
    model.name = "the-one-that-ran"

    record = agent.plan_workout(connection, BARBELL_45, model=model)

    assert record.model == "the-one-that-ran"


def test_the_provider_adapter_reports_the_model_it_was_built_with() -> None:
    assert agent.Groq(client=FakeGroq(), model="qwen/qwen3.8-27b").name == (
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
    answer = {"variants": [{"id": "X", "name": "X", "instructions": ["long"], "level": "expert"}]}

    trimmed = agent._trimmed(answer)

    assert trimmed == {"variants": [{"id": "X", "name": "X"}]}


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
