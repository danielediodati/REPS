"""The first model in the project: a node that loops over the tool surface.

`trainer plan` without `--from` asks a model for a workout. It gets the tools
`trainer.tools` defines -- the same ones `trainer mcp` serves -- calls them
until it has what it needs, and emits a plan in `trainer.plan`'s shape. The
plan goes out through that module's validator and **does not come back in**.

**A node, not a graph.** TRAINER.md is explicit that the workout loop *"is a
node looping over a tool surface, and a graph adds nothing to a node that
loops"*. So this is the provider SDK and a `while`, and LangGraph arrives in
session 6 for onboarding, where checkpointing and resume are the point.

**The call budget.** Tool calls are local Python: zero network, zero tokens to
execute. What they cost is the context round-trip, and that is bounded
(TRAINER.md § The tool surface). When the budget runs out the loop does not
fail -- it stops offering tools and asks for the plan with what it has. That
is invariant 1 of § Level 1: the agent, and it is behaviour rather than an
error path.

**No way back in.** A plan the validator refuses is recorded as refused, with
the rule that refused it. It is not trimmed, and it is not handed back to the
model to fix: *propose -> check -> correct* is the loop TRAINER.md
deliberately does not have, because the constraints are applied upstream, in
the request. A refusal here is a bug to go and read, and ticket 05 counts
them.

**Two phases, one emission.** The model is asked for the plan in a final call
of its own, with no tools offered and the structured shape required. Running
out of budget and finishing early therefore take the *same* path out, which is
what makes "it emits anyway" a property of the loop rather than a branch in
it.

**The seam.** Everything above talks to a `Model`, two methods wide. `Claude`
implements it against the SDK; the suite implements it with scripted replies.
`conftest.py` takes sockets and credentials away from every test on purpose,
and that guarantee is worth more than the convenience of one runner -- so the
loop is exercised offline here, and the real model runs only under ticket 05's
`trainer eval`.
"""

from __future__ import annotations

import inspect
import json
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, get_type_hints

from pydantic import BaseModel, TypeAdapter

from trainer import plan as plans
from trainer import tools

MODEL = "claude-opus-5"
"""The model, named once. A second spelling at a call site is a run that is
measured on one model and shipped on another."""

CALL_BUDGET = 12
"""Tool calls one run may make before the loop stops offering tools.

A starting value, not a measurement: ticket 05 is what says whether a workout
needs more or fewer, and until it has run this is the number that keeps a
runaway loop from costing a fortune. `--call-budget` overrides it."""

MAX_TOKENS = 16000

API_KEY_ENV = "ANTHROPIC_API_KEY"

NO_CREDENTIALS = (
    f"no Anthropic credentials: set {API_KEY_ENV}, or run `ant auth login` "
    "once and the SDK reads the profile it writes"
)
"""A state with the way out, checked before any request goes out.

Left to the SDK this arrives as a 401 after a network round-trip, or as a
connection error on a machine that is offline -- neither of which names the
thing that is actually missing.
"""


class AgentError(RuntimeError):
    """The run could not be made: no credentials, or the provider refused."""


# -- what the loop talks to ---------------------------------------------------


@dataclass(frozen=True)
class Call:
    """One tool call the model asked for."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Reply:
    """One turn from the model.

    `content` is opaque and handed straight back on the next turn -- the
    provider's own blocks, which the loop has no business reading. `calls` is
    the part the loop acts on, pulled out by whoever implements `Model`.
    """

    content: Any
    calls: tuple[Call, ...] = ()
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class Emission:
    """The final turn: a plan in the shape `trainer.plan` defines."""

    plan: plans.WorkoutPlan
    input_tokens: int = 0
    output_tokens: int = 0


class Model(Protocol):
    """Two methods, because the loop has two phases.

    Narrow on purpose. A stand-in that satisfies this exercises the whole loop
    -- the calls, the budget, the emission, the way out through the validator
    -- without a socket, which is the only way the suite can cover any of it.
    """

    def respond(self, messages: list[Any], offered: list[dict[str, Any]] | None) -> Reply:
        """One turn, with `offered` tools or with none at all."""
        ...

    def emit(self, messages: list[Any]) -> Emission:
        """The plan, structured, with no tools on the table."""
        ...


# -- the run record -----------------------------------------------------------
#
# An artifact, not a log. Ticket 05 decides its six invariants by reading this
# rather than by asking the model what it did, so everything a check needs is
# a field: pydantic models, so the whole thing writes out as JSON.


class RecordedCall(BaseModel):
    name: str
    arguments: dict[str, Any]
    failed: bool = False
    detail: str | None = None
    """The tool's own sentence, when the call failed. Kept because a run that
    spent its budget on rejected calls and a run that spent it on answers look
    identical from the count alone."""


class RunRecord(BaseModel):
    """What the model called, what it cost, and what came out."""

    model: str
    budget: int
    spent: int
    emitted_on_exhaustion: bool
    calls: list[RecordedCall]
    input_tokens: int
    output_tokens: int
    plan: plans.WorkoutPlan
    refused: str | None = None
    """The rule that refused the plan, or `None` when it passed. A plan that
    is refused is still recorded whole: the point of the record is to be able
    to go and read what the model actually emitted."""


# -- the tools, as this door registers them -----------------------------------


def schema(tool: Callable[..., Any]) -> dict[str, Any]:
    """One tool definition, derived from the function rather than restated.

    `mcp_server.py` gets its schemas from the SDK reading the same signatures;
    this is the same derivation for the other door. Hand-written schemas here
    would be the second definition ticket 01 exists to prevent -- and the one
    that drifts, because nothing would fail when it did.

    The docstring is the description, which is what the model reads to decide
    whether a tool answers its question.
    """
    hints = get_type_hints(tool)
    properties: dict[str, Any] = {}
    required: list[str] = []
    definitions: dict[str, Any] = {}
    for name, parameter in inspect.signature(tool).parameters.items():
        built = TypeAdapter(hints[name]).json_schema()
        # A `$ref` resolves from the root of the schema document, and the root
        # here is `input_schema`. Left where pydantic puts them -- inside the
        # property -- the definitions an enum or a model-typed parameter needs
        # sit one level too deep and every reference to them dangles. No
        # parameter is typed that way today; the day one is, the provider
        # rejects the definition with nothing in this file to explain it.
        definitions.update(built.pop("$defs", {}))
        properties[name] = built
        if parameter.default is inspect.Parameter.empty:
            required.append(name)

    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "required": required,
    }
    if definitions:
        input_schema["$defs"] = definitions
    return {
        "name": tool.__name__,
        "description": inspect.getdoc(tool) or "",
        "input_schema": input_schema,
    }


def surface() -> list[dict[str, Any]]:
    """Every tool in `tools.TOOLS`, and nothing else."""
    return [schema(tool) for tool in tools.TOOLS]


def _execute(call: Call) -> tuple[str, bool]:
    """Run one call. The sentence to hand back, and whether it failed.

    Everything the *model* can get wrong -- a tool that does not exist,
    arguments that do not fit the schema, a question the engine states it
    cannot answer -- comes back as a result it can act on next turn. Anything
    else is a bug in this project and is left to propagate: reported to the
    model as a tool error it would come back as an evaluation failure with no
    signal in it, days later, with the traceback long gone.
    """
    import pydantic

    found = next((tool for tool in tools.TOOLS if tool.__name__ == call.name), None)
    if found is None:
        # The model asked for a tool nobody offered. Its mistake, not ours, so
        # it goes back as a result it can recover from.
        offered = ", ".join(tool.__name__ for tool in tools.TOOLS)
        return f"there is no tool called {call.name!r}; the tools are {offered}", True

    try:
        arguments = _fitted(found, call.arguments)
    except pydantic.ValidationError as error:
        return f"{call.name} was given arguments that do not fit: {error}", True
    except KeyError as error:
        return f"{call.name} takes no argument called {error}", True

    try:
        answer = found(**arguments)
    except tools.ToolFailure as error:
        return str(error), True
    except TypeError as error:
        # An argument left out, or given twice. The shapes are checked above,
        # so what is left is the call itself not fitting the signature.
        return f"{call.name} cannot be called that way: {error}", True
    return _serialised(answer), False


def _fitted(tool: Callable[..., Any], arguments: Mapping[str, Any]) -> dict[str, Any]:
    """The model's arguments, against the types the schema was derived from.

    Reached by exactly the mistake a model makes: `exclusions` given as a list
    of strings rather than of `{granularity, value}` objects satisfies the
    signature and reaches the tool body, where it comes apart as an
    `AttributeError` on a string -- a traceback, no record, and a paid-for run
    thrown away over something the model could have corrected next turn.

    Checked against `get_type_hints`, which is what `schema()` derives the
    definitions from, so what is enforced here and what the model was told are
    the same declaration read twice rather than two declarations.
    """
    hints = get_type_hints(tool)
    fitted: dict[str, Any] = {}
    for name, value in arguments.items():
        if name not in hints:
            raise KeyError(name)
        fitted[name] = TypeAdapter(hints[name]).validate_python(value)
    return fitted


NOT_FOR_CONTEXT = ("instructions", "images")
"""Fields dropped on the way to the model, and only on the way to the model.

An admissible set of 75 exercises carries some 18,000 tokens of instruction
prose and image paths, and the loop re-sends it on every later turn. The call
budget rests on a round-trip whose cost is bounded (TRAINER.md § The tool
surface), and it is not bounded while one answer can be larger than the whole
output budget. The inspector behind the MCP door pays none of that and keeps
the record whole; nothing in planning reads either field, and `catalog.py`
already says they are fetched by id when something needs to *show* an
exercise rather than choose one.
"""


def _serialised(answer: Any) -> str:
    """The engine's answer, in the dialect the tool definitions promised.

    JSON rather than `repr`: the docstrings the model reads describe
    `known: false` and `{"granularity": "pattern"}`, and Python would hand
    back `'known': False`. A model translating between two dialects mid-loop
    is one more thing that can go wrong for no reason at all.
    """
    return json.dumps(_trimmed(answer), default=str)


def _trimmed(answer: Any) -> Any:
    if isinstance(answer, list):
        return [_trimmed(item) for item in answer]
    if isinstance(answer, dict):
        return {key: value for key, value in answer.items() if key not in NOT_FOR_CONTEXT}
    return answer


# -- the prompt ---------------------------------------------------------------

SYSTEM = f"""\
You plan one strength workout, for one person, today.

{tools.INSTRUCTIONS}
The rules you are working inside, none of which you can talk your way around:

- Every exercise you prescribe must be in what `admissible_set` returns for
  today's request. Anything else is rejected by a deterministic check after
  you emit, and the workout does not happen.
- The plan must fit the time declared. It is never trimmed to fit: a plan that
  runs over is rejected whole, so ask `remaining_budget` before you commit to
  a block rather than after.
- An exercise appears at most once in the whole plan. One line per exercise,
  with the rounds and reps it needs.
- Rest is yours to prescribe and travels with the block. There are reference
  bands -- around 3 min for heavy low-rep work, 90-120 s for hypertrophy, 60 s
  for isolation -- and they are a reference, not a rule.
- Every block carries the reason it is there, in one short sentence. That is
  the part of the plan only you can supply.

You have a budget of tool calls. When it runs out you will be asked for the
plan with whatever you know at that point, so spend the calls on what you
actually need and do not explore for its own sake.
"""


def brief(request: plans.Request) -> str:
    """Today's request, in words, for the model to plan against."""
    lines = [
        f"Equipment available today: {', '.join(request.equipment)}.",
        f"Time available: {request.budget_min} minutes.",
    ]
    if request.exclusions:
        lines.append(
            "Excluded, and already filtered out of the admissible set: "
            + ", ".join(f"{e.granularity} {e.value}" for e in request.exclusions)
            + "."
        )
    lines.append("Plan the workout.")
    return "\n".join(lines)


EMIT = "Emit the plan now, in the required shape."


# -- the loop -----------------------------------------------------------------


def plan_workout(
    connection: sqlite3.Connection,
    request: plans.Request,
    *,
    model: Model | None = None,
    budget: int = CALL_BUDGET,
) -> RunRecord:
    """Ask a model for a workout, and record everything it did to get there.

    Returns the record whether the plan passed or was refused. Refusal is an
    outcome of the run, not an exception: ticket 05 counts refusals across
    many runs, and a function that raised on one would make the count the
    caller's job to reassemble.
    """
    if budget < 1:
        raise AgentError(f"a call budget is at least one call, got {budget}")
    if model is None:
        model = claude()

    messages: list[Any] = [{"role": "user", "content": brief(request)}]
    offered = surface()
    recorded: list[RecordedCall] = []
    spent = 0
    input_tokens = 0
    output_tokens = 0

    while spent < budget:
        reply = model.respond(messages, offered)
        input_tokens += reply.input_tokens
        output_tokens += reply.output_tokens
        messages.append({"role": "assistant", "content": reply.content})
        if not reply.calls:
            break

        # Every result from one turn goes back in one message. Split across
        # several, the provider reads it as the calls having been made one at
        # a time, and the model stops asking for them in parallel.
        results = []
        for call in reply.calls:
            answer, failed = _execute(call)
            recorded.append(
                RecordedCall(
                    name=call.name,
                    arguments=call.arguments,
                    failed=failed,
                    detail=answer if failed else None,
                )
            )
            spent += 1
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": answer,
                    "is_error": failed,
                }
            )
        messages.append({"role": "user", "content": results})

    # A turn's calls are executed together, so the last one may carry the
    # count past the budget rather than land on it. The record says what was
    # actually spent; the budget is the point at which tools stop being
    # offered, not a number the loop pretends to hit exactly.
    exhausted = spent >= budget

    messages.append({"role": "user", "content": EMIT})
    emission = model.emit(messages)
    input_tokens += emission.input_tokens
    output_tokens += emission.output_tokens

    return RunRecord(
        model=MODEL,
        budget=budget,
        spent=spent,
        emitted_on_exhaustion=exhausted,
        calls=recorded,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        plan=emission.plan,
        refused=_refusal(connection, emission.plan, request),
    )


def _refusal(
    connection: sqlite3.Connection, emitted: plans.WorkoutPlan, request: plans.Request
) -> str | None:
    """The way out, and there is no way back in.

    Both failures are recorded in one field because from the run's point of
    view they are one outcome: the plan did not get through the door. What
    they are is still legible -- a shape failure names a block, a refusal
    names a rule.
    """
    try:
        plans.validate(connection, plans.to_blocks(emitted), request)
    except (plans.PlanError, plans.PlanRejected) as error:
        return str(error)
    return None


# -- the provider -------------------------------------------------------------


class Claude:
    """`Model`, against the Anthropic SDK.

    The only part of this file that knows what a provider looks like. It is
    also the only part the suite never runs: `conftest.py` removes sockets and
    credentials, so everything above is covered against a stand-in and this
    class is exercised for the first time under ticket 05's `trainer eval`.
    """

    def __init__(self, client: Any | None = None, model: str = MODEL) -> None:
        self._model = model
        self._client = client if client is not None else _client()

    def respond(self, messages: list[Any], offered: list[dict[str, Any]] | None) -> Reply:
        request: dict[str, Any] = {
            "model": self._model,
            "max_tokens": MAX_TOKENS,
            "system": SYSTEM,
            "messages": messages,
        }
        if offered:
            request["tools"] = offered
        response = _reported(lambda: self._client.messages.create(**request))
        calls = tuple(
            Call(id=block.id, name=block.name, arguments=dict(block.input))
            for block in response.content
            if block.type == "tool_use"
        )
        return Reply(
            content=response.content,
            calls=calls,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    def emit(self, messages: list[Any]) -> Emission:
        """The plan, in `trainer.plan`'s own shape.

        `WorkoutPlan` is handed to the provider as the required output format
        rather than described in the prompt: the shape the file format uses,
        the shape the validator reads and the shape the model is held to are
        then one declaration, and a field added to it reaches all three.

        **The tools are still declared, and refused by `tool_choice`.** The
        history at this point holds the `tool_use` and `tool_result` blocks the
        loop appended, and the API rejects a request that carries those while
        defining no tools. Leaving `tools` out is not how you take them off the
        table -- it is how you make every run that used one fail at the last
        step, which is the one step the suite cannot cover.
        """
        import pydantic

        response = _reported(
            lambda: self._client.messages.parse(
                model=self._model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM,
                messages=messages,
                tools=surface(),
                tool_choice={"type": "none"},
                output_format=plans.WorkoutPlan,
            )
        )
        try:
            parsed = response.parsed_output
        except pydantic.ValidationError as error:
            # Truncated JSON, most likely: a long plan against `max_tokens`.
            raise AgentError(
                "the model's plan did not parse, which usually means it was "
                f"cut off at {MAX_TOKENS} tokens: {error}"
            ) from error
        if parsed is None:
            # No text block carried a parsed output: the model answered with
            # something that is not a plan at all.
            raise AgentError("the model returned no plan")
        return Emission(
            plan=parsed,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )


def claude(client: Any | None = None) -> Claude:
    """The provider-backed model, built lazily.

    A function rather than a constructor call at import: nothing in the suite
    may build a client, and a module that made one on import would break the
    no-credentials guarantee for every test that happens to import it.
    """
    return Claude(client)


def _client() -> Any:
    import anthropic

    return authenticated(anthropic.Anthropic())


def authenticated(built: Any) -> Any:
    """The credential check, kept apart from building the client.

    The SDK resolves a key, a token, or an `ant auth login` profile, in that
    order, and comes back with empty auth headers when it finds none of them.
    Checked here rather than left to the request: unauthenticated, the call
    comes back a 401 from the network, and on a machine with no network it
    comes back a connection error -- neither of which names what is missing.

    Its own function so the suite can exercise it. Reaching it through
    `_client` would mean constructing a real SDK client, and what that
    resolves depends on the machine the tests are running on -- which is the
    state under test, not a way to reach it.
    """
    if not built.auth_headers:
        raise AgentError(NO_CREDENTIALS)
    return built


def _reported(call: Callable[[], Any]) -> Any:
    """The provider's failures, in words, with the ones worth acting on apart."""
    import anthropic

    try:
        return call()
    except anthropic.AuthenticationError as error:
        raise AgentError(f"{NO_CREDENTIALS} (the provider said: {error})") from error
    except anthropic.RateLimitError as error:
        raise AgentError(f"the provider is rate limiting this key: {error}") from error
    except anthropic.APIConnectionError as error:
        raise AgentError(f"the provider could not be reached: {error}") from error
    except anthropic.APIStatusError as error:
        raise AgentError(f"the provider refused the request: {error}") from error


def summary(record: RunRecord) -> list[str]:
    """The run in three lines, for the terminal. ASCII."""
    used = f"{record.spent} of {record.budget} tool calls"
    if record.emitted_on_exhaustion:
        used += " (budget spent; the plan was emitted with what it had)"
    failed = sum(1 for call in record.calls if call.failed)
    lines = [f"{record.model} -- {used}"]
    if failed:
        lines.append(f"  {failed} of those calls came back an error")
    lines.append(
        f"  {record.input_tokens} tokens in, {record.output_tokens} out"
    )
    return lines


def called(record: RunRecord) -> Sequence[Mapping[str, Any]]:
    """The calls, in order, as plain data -- what ticket 05 reads."""
    return [call.model_dump() for call in record.calls]
