"""The model: a node that loops over the tool surface, inside a call budget.

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

**Two phases, and on Groq that is not a choice.** The plan is asked for in a
final call of its own, with the tools off the table and the structured shape
required. Groq does not allow structured outputs and tool use in the same
request at all, so the separation the loop was built with is the only shape
that works -- and it has the property that mattered anyway: running out of
budget and finishing early leave by the *same* door, which is what makes "it
emits anyway" a property of the loop rather than a branch inside it.

**The seam.** Everything above talks to a `Model`, two methods wide, over a
conversation described in this project's own terms -- a brief, and the
exchanges that followed. No provider's message shape reaches the loop: that
lives in the adapter, which is the whole reason swapping providers touched
one class and not the loop.
"""

from __future__ import annotations

import inspect
import json
import os
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, get_type_hints

from pydantic import BaseModel, TypeAdapter

from trainer import plan as plans
from trainer import tools

BACKEND_ENV = "LLM_BACKEND"
MODEL_ENV = "GROQ_MODEL"
API_KEY_ENV = "GROQ_API_KEY"

GROQ = "groq"
BACKENDS = (GROQ,)
"""What `LLM_BACKEND` may name today.

`ollama` is the value this will grow next -- the local backend, free and
offline. It is read and refused by name rather than ignored, so a `.env` that
asks for it gets told it is not built yet instead of quietly getting Groq.
"""

DEFAULT_MODEL = "qwen/qwen3.8-27b"
"""The model, when `GROQ_MODEL` does not name one.

Qwen 3.8 27B rather than 3.6: both are preview models on Groq, and this is the
one whose structured output runs in **strict** mode, where constrained
decoding makes the emitted plan conform to the schema by construction rather
than by luck. A plan that comes back as malformed JSON is a whole run thrown
away, and the loop has no way to ask again.
"""

STRICT_OUTPUT = "structured outputs in strict mode"

MAX_TOKENS_ENV = "GROQ_MAX_TOKENS"

CALL_BUDGET = 12
"""Tool calls one run may make before the loop stops offering tools.

A starting value, not a measurement: ticket 05 is what says whether a workout
needs more or fewer, and until it has run this is the number that keeps a
runaway loop from spending an afternoon. `--call-budget` overrides it."""

DEFAULT_MAX_TOKENS = 1000
"""How much the model may write in one turn, by default.

One thousand because that is Groq's free-tier ceiling on output tokens per
minute, and a request whose declared `max_tokens` exceeds it is refused before
any of it runs -- a 429 about a limit nobody has reached yet.

**It is shared with reasoning.** The default model reasons before it answers
and `max_tokens` caps the completion, thinking included, so the plan is
written out of whatever is left. An observed run emitted a six-block plan in
676 tokens all in, so this fits -- but not by much, and a run that reasons
harder loses the plan to truncation rather than to a rule. That is why the
truncation state names `GROQ_MAX_TOKENS`: on a paid tier it is the number to
raise first.
"""


def max_tokens() -> int:
    """How much the model may write, from the environment or the default.

    Checked rather than trusted, because this value is interpolated into the
    rate-limit and truncation messages: `GROQ_MAX_TOKENS=2k` would raise a
    `ValueError` *while handling* the 429 it was meant to explain, and the
    user would get a traceback about a codec-shaped mistake instead of the
    state with its way out.
    """
    declared = os.environ.get(MAX_TOKENS_ENV)
    if not declared:
        return DEFAULT_MAX_TOKENS
    try:
        asked = int(declared)
    except ValueError:
        raise AgentError(
            f"{MAX_TOKENS_ENV} is {declared!r}; it is a whole number of tokens"
        ) from None
    if asked < 1:
        raise AgentError(f"{MAX_TOKENS_ENV} is {asked}; it is at least one token")
    return asked


NO_CREDENTIALS = (
    f"no Groq credentials: set {API_KEY_ENV} in .env (copy .env.example) or in "
    "the environment"
)
"""A state with the way out, checked before any request goes out.

Left to the SDK this arrives as a 401 after a network round-trip, or as a
connection error on a machine that is offline -- neither of which names the
thing that is actually missing.
"""


class AgentError(RuntimeError):
    """The run could not be made: no credentials, a backend that is not built,
    or the provider refusing."""


def backend() -> str:
    """Which provider this run talks to, and a state for one nobody built."""
    named = os.environ.get(BACKEND_ENV) or GROQ
    if named not in BACKENDS:
        raise AgentError(
            f"{BACKEND_ENV} names {named!r}, and the backends built are "
            f"{', '.join(BACKENDS)}"
        )
    return named


def model_name() -> str:
    return os.environ.get(MODEL_ENV) or DEFAULT_MODEL


# -- the conversation, in this project's own terms ----------------------------
#
# Not the provider's. Groq wants an assistant message carrying `tool_calls` and
# one `{"role": "tool"}` message per result; Anthropic wanted content blocks in
# a user turn. The loop below describes what happened -- the model replied, the
# tools answered -- and the adapter renders that into whichever shape its
# provider reads. Swapping providers cost one class, and this is why.


@dataclass(frozen=True)
class Call:
    """One tool call the model asked for."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Result:
    """What one tool answered, on its way back to the model."""

    call_id: str
    name: str
    content: str
    failed: bool = False


@dataclass(frozen=True)
class Reply:
    """One turn from the model.

    `content` is opaque and belongs to the adapter that produced it: the
    provider's own assistant message, handed straight back when the next
    request is built. The loop reads `calls` and nothing else.
    """

    content: Any
    calls: tuple[Call, ...] = ()
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class Exchange:
    """One round: what the model said, and what the tools answered."""

    reply: Reply
    results: tuple[Result, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Emission:
    """The final turn: a plan in the shape `trainer.plan` defines."""

    plan: plans.WorkoutPlan
    input_tokens: int = 0
    output_tokens: int = 0


class Model(Protocol):
    """Two methods and a name, because the loop has two phases and a record.

    Narrow on purpose. A stand-in that satisfies this exercises the whole loop
    -- the calls, the budget, the emission, the way out through the validator
    -- without a socket, which is the only way the suite can cover any of it.
    """

    @property
    def name(self) -> str:
        """What ran, for the record.

        Asked of the model rather than read back out of the environment.
        Ticket 05 compares invariants across models by constructing one per
        run, and a record that re-read `GROQ_MODEL` afterwards would stamp
        every one of them with whatever the environment happened to say --
        unattributable, and passing every test that compares the two.
        """
        ...

    def respond(
        self,
        brief: str,
        exchanges: Sequence[Exchange],
        offered: Sequence[dict[str, Any]] | None,
    ) -> Reply:
        """One turn, with `offered` tools or with none at all."""
        ...

    def emit(self, brief: str, exchanges: Sequence[Exchange]) -> Emission:
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

    Provider-neutral: name, description, parameters. The envelope a given API
    wants around that is the adapter's business.
    """
    hints = get_type_hints(tool)
    properties: dict[str, Any] = {}
    required: list[str] = []
    definitions: dict[str, Any] = {}
    for name, parameter in inspect.signature(tool).parameters.items():
        built = TypeAdapter(hints[name]).json_schema()
        # A `$ref` resolves from the root of the schema document, and the root
        # here is `parameters`. Left where pydantic puts them -- inside the
        # property -- the definitions an enum or a model-typed parameter needs
        # sit one level too deep and every reference to them dangles. No
        # parameter is typed that way today; the day one is, the provider
        # rejects the definition with nothing in this file to explain it.
        definitions.update(built.pop("$defs", {}))
        properties[name] = built
        if parameter.default is inspect.Parameter.empty:
            required.append(name)

    parameters: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "required": required,
    }
    if definitions:
        parameters["$defs"] = definitions
    return {
        "name": tool.__name__,
        "description": inspect.getdoc(tool) or "",
        "parameters": parameters,
    }


def surface() -> list[dict[str, Any]]:
    """Every tool in `tools.TOOLS`, and nothing else."""
    return [schema(tool) for tool in tools.TOOLS]


def _execute(call: Call) -> Result:
    """Run one call, and say what goes back to the model.

    Everything the *model* can get wrong -- a tool that does not exist,
    arguments that do not fit the schema, a question the engine states it
    cannot answer -- comes back as a result it can act on next turn. Anything
    else is a bug in this project and is left to propagate: reported to the
    model as a tool error it would come back as an evaluation failure with no
    signal in it, days later, with the traceback long gone.
    """
    import pydantic

    def failed(sentence: str) -> Result:
        return Result(call_id=call.id, name=call.name, content=sentence, failed=True)

    found = next((tool for tool in tools.TOOLS if tool.__name__ == call.name), None)
    if found is None:
        # The model asked for a tool nobody offered. Its mistake, not ours, so
        # it goes back as a result it can recover from.
        offered = ", ".join(tool.__name__ for tool in tools.TOOLS)
        return failed(f"there is no tool called {call.name!r}; the tools are {offered}")

    try:
        arguments = _fitted(found, call.arguments)
    except pydantic.ValidationError as error:
        return failed(f"{call.name} was given arguments that do not fit: {error}")
    except KeyError as error:
        return failed(f"{call.name} takes no argument called {error}")

    try:
        answer = found(**arguments)
    except tools.ToolFailure as error:
        return failed(str(error))
    except TypeError as error:
        # An argument left out, or given twice. The shapes are checked above,
        # so what is left is the call itself not fitting the signature.
        return failed(f"{call.name} cannot be called that way: {error}")
    return Result(call_id=call.id, name=call.name, content=_serialised(answer))


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


NOT_FOR_CONTEXT = (
    "instructions",
    "images",
    "force",
    "level",
    "category",
    "secondary_muscles",
    "name",
)
"""Fields dropped on the way to the model, and only on the way to the model.

The admissible set is the largest thing the loop ever carries, and it carries
it again on every later turn: 119 dumbbell exercises came to 31,000 characters
whole, against a free-tier ceiling of 7,000 input tokens a minute. The call
budget rests on a round-trip whose cost is bounded (TRAINER.md § The tool
surface), and it was not bounded.

What is dropped is what nothing in planning reads. `instructions` and `images`
because `catalog.py` already says they are fetched by id when something needs
to *show* an exercise rather than choose one. `force` because TRAINER.md's own
appendix judges it insufficient on its own terms and `movement_pattern`
replaced it. `level` and `category` because the admissible set has already
filtered on what today allows. `secondary_muscles` because allocation is over
the six groups a workout trains, and the primaries are what answer that.

`name` goes for a different reason: not because it is large, but because it
is *the wrong one of two strings*. A plan is written in ids, and a model shown
both fields copied the readable one into `exercise_id` -- five refused plans
across the first runs. No rule recovers the id from the name either: `Butt
Lift (Bridge)` is `Butt_Lift_Bridge`, parentheses dropped rather than
underscored, in 36 of the 876 rows. Removing the field makes the mistake
impossible instead of rare, and costs nothing, because the name was never the
model's to carry: `plan.render` reads it back out of the catalog by id when
the workout is printed.

`mechanic` stays: compound against isolation is the distinction ticket 05's
sixth invariant -- *it does not degenerate* -- is about, and a model that
cannot see it cannot be asked to respect it.

The MCP door pays none of this and keeps the record whole. That is the
difference between an inspector and a context window, not two definitions of
what an exercise is.
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
    """All the way down, not just the top level.

    `compare_variants` already answers `{"a": {...}, "b": {...}}`, and the day
    a tool nests a list of exercises under a key the payload this function
    exists to bound comes back whole, with nothing failing to say so.
    """
    if isinstance(answer, list):
        return [_trimmed(item) for item in answer]
    if isinstance(answer, dict):
        return {
            key: _trimmed(value)
            for key, value in answer.items()
            if key not in NOT_FOR_CONTEXT
        }
    return answer


# -- the prompt ---------------------------------------------------------------

SYSTEM = f"""\
You plan one strength workout, for one person, today.

{tools.INSTRUCTIONS}
The rules you are working inside, none of which you can talk your way around:

- Every exercise you prescribe must be in what `admissible_set` returns for
  today's request, written as the `id` that came back, character for
  character. Anything else is rejected by a deterministic check after you
  emit, and the workout does not happen.
- The plan must fit the time declared. It is never trimmed to fit: a plan that
  runs over is rejected whole, so ask `remaining_budget` before you commit to
  a block rather than after.
- An exercise appears at most once in the whole plan. One line per exercise,
  with the rounds and reps it needs.
- Each exercise is prescribed in **either** reps **or** seconds, never both
  and never neither. Both fields are always present in the shape you emit, so
  put a value in one and null in the other. A plank is seconds; a push-up is
  reps. Filling both is rejected.
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
    if request.groups:
        lines.append(
            f"This workout trains: {', '.join(request.groups)}. Ask "
            "`admissible_set` for those groups; anything else is not today's "
            "workout."
        )
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
        model = groq()

    written = brief(request)
    offered = surface()
    exchanges: list[Exchange] = []
    recorded: list[RecordedCall] = []
    spent = 0
    input_tokens = 0
    output_tokens = 0

    while spent < budget:
        reply = model.respond(written, exchanges, offered)
        input_tokens += reply.input_tokens
        output_tokens += reply.output_tokens
        if not reply.calls:
            exchanges.append(Exchange(reply=reply))
            break

        results = []
        for call in reply.calls:
            result = _execute(call)
            recorded.append(
                RecordedCall(
                    name=call.name,
                    arguments=call.arguments,
                    failed=result.failed,
                    detail=result.content if result.failed else None,
                )
            )
            spent += 1
            results.append(result)
        exchanges.append(Exchange(reply=reply, results=tuple(results)))

    # A turn's calls are executed together, so the last one may carry the
    # count past the budget rather than land on it. The record says what was
    # actually spent; the budget is the point at which tools stop being
    # offered, not a number the loop pretends to hit exactly.
    exhausted = spent >= budget

    emission = model.emit(written, exchanges)
    input_tokens += emission.input_tokens
    output_tokens += emission.output_tokens

    return RunRecord(
        model=model.name,
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


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """A pydantic model's schema, in the shape strict mode will accept.

    Strict mode is constrained decoding: it makes the emitted JSON conform by
    construction rather than by luck, which is what a loop with no way to ask
    again needs. It also demands that **every** property be listed in
    `required`, and pydantic leaves out the ones with defaults -- `reps` and
    `seconds`, which are exactly the pair that carries *either reps or
    seconds*. Their optionality survives as the null in their type; what
    changes here is only that the model must decide about them rather than
    leave them out.

    `additionalProperties: false` is already there, from the wire shape's own
    `extra="forbid"`. Strict mode wants it for its reasons and the plan format
    wants it for the ticket-02 reason -- a misspelled field quietly ignored is
    a prescription the author believes they wrote -- and they agree.
    """
    built = model.model_json_schema()

    def require_everything(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["required"] = list(node["properties"])
                node.setdefault("additionalProperties", False)
            for value in node.values():
                require_everything(value)
        elif isinstance(node, list):
            for item in node:
                require_everything(item)

    require_everything(built)
    return built


class Groq:
    """`Model`, against the Groq API.

    The only part of this file that knows what a provider looks like: the
    message shapes, the tool envelope, the two request forms. Everything above
    talks in exchanges.
    """

    def __init__(self, client: Any | None = None, model: str | None = None) -> None:
        self._model = model or model_name()
        self._client = client if client is not None else _client()

    @property
    def name(self) -> str:
        return self._model

    def _messages(self, written: str, exchanges: Sequence[Exchange]) -> list[Any]:
        """The conversation, in the shape Groq reads.

        An assistant message carrying `tool_calls`, then one `tool` message per
        result, keyed by the id the call came with. The assistant message goes
        back exactly as it arrived: it is the provider's own object, and
        rebuilding it from parts is how a loop starts disagreeing with the
        history it is sending.
        """
        messages: list[Any] = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": written},
        ]
        for exchange in exchanges:
            messages.append(exchange.reply.content)
            for result in exchange.results:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": result.call_id,
                        "name": result.name,
                        "content": result.content,
                    }
                )
        return messages

    def respond(
        self,
        brief: str,
        exchanges: Sequence[Exchange],
        offered: Sequence[dict[str, Any]] | None,
    ) -> Reply:
        request: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens(),
            "messages": self._messages(brief, exchanges),
        }
        if offered:
            request["tools"] = [
                {"type": "function", "function": definition} for definition in offered
            ]
        completion = _reported(lambda: self._client.chat.completions.create(**request))
        message = completion.choices[0].message
        return Reply(
            content=message.model_dump(exclude_none=True),
            calls=tuple(_call(raw) for raw in message.tool_calls or ()),
            input_tokens=completion.usage.prompt_tokens,
            output_tokens=completion.usage.completion_tokens,
        )

    def emit(self, brief: str, exchanges: Sequence[Exchange]) -> Emission:
        """The plan, in `trainer.plan`'s own shape.

        No tools on this request, and not as a nicety: Groq does not allow
        structured outputs and tool use in the same call at all. The shape the
        file format uses, the shape the validator reads and the shape the model
        is held to are one declaration, so a field added to `WorkoutPlan`
        reaches all three.
        """
        import pydantic

        messages = self._messages(brief, exchanges)
        messages.append({"role": "user", "content": EMIT})
        completion = _reported(
            lambda: self._client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens(),
                messages=messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "workout_plan",
                        "strict": True,
                        "schema": strict_schema(plans.WorkoutPlan),
                    },
                },
            )
        )
        body = completion.choices[0].message.content
        if not body:
            raise AgentError("the model returned no plan")
        try:
            emitted = plans.WorkoutPlan.model_validate_json(body)
        except pydantic.ValidationError as error:
            raise AgentError(
                "the model's plan did not parse, which usually means it was cut "
                f"off at {max_tokens()} tokens ({MAX_TOKENS_ENV} raises that): "
                f"{error}"
            ) from error
        return Emission(
            plan=emitted,
            input_tokens=completion.usage.prompt_tokens,
            output_tokens=completion.usage.completion_tokens,
        )


def _call(raw: Any) -> Call:
    """One tool call, out of Groq's envelope.

    `function.arguments` arrives as a **JSON string**, not an object. Read as
    one it would reach the tools as a `str`, and every call would come back
    refused for arguments that do not fit -- a whole run spent on a mistake
    nobody made.
    """
    try:
        arguments = json.loads(raw.function.arguments or "{}")
    except json.JSONDecodeError:
        arguments = {}
    return Call(id=raw.id, name=raw.function.name, arguments=arguments)


def groq(client: Any | None = None) -> Groq:
    """The provider-backed model, built lazily.

    A function rather than a constructor call at import: nothing in the suite
    may build a client, and a module that made one on import would break the
    no-credentials guarantee for every test that happens to import it.
    """
    backend()
    return Groq(client)


def _client() -> Any:
    import groq as sdk

    key = os.environ.get(API_KEY_ENV)
    if not key:
        raise AgentError(NO_CREDENTIALS)
    return sdk.Groq(api_key=key)


def _reported(call: Callable[[], Any]) -> Any:
    """The provider's failures, in words, with the ones worth acting on apart."""
    import groq as sdk

    try:
        return call()
    except sdk.AuthenticationError as error:
        raise AgentError(f"{NO_CREDENTIALS} (the provider said: {error})") from error
    except sdk.RateLimitError as error:
        raise AgentError(
            f"the provider is rate limiting this key: {error}\n"
            f"If it is refusing the declared output size rather than actual "
            f"traffic, lower {MAX_TOKENS_ENV} (currently {max_tokens()})."
        ) from error
    except sdk.BadRequestError as error:
        # Where a model that cannot do strict structured output lands: the
        # emission is the only request that asks for it, and the refusal
        # arrives naming the parameter rather than the way out.
        raise AgentError(
            f"the provider refused the request: {error}\n"
            f"If it names response_format, this model does not support "
            f"{STRICT_OUTPUT}; qwen/qwen3.8-27b and the gpt-oss models do, and "
            f"{MODEL_ENV} chooses."
        ) from error
    except sdk.APIConnectionError as error:
        raise AgentError(f"the provider could not be reached: {error}") from error
    except sdk.APIStatusError as error:
        raise AgentError(f"the provider refused the request: {error}") from error
    except sdk.APIError as error:
        # `APIResponseValidationError` and anything else the SDK raises that is
        # not a status error. Last, and deliberately broad: this function's
        # whole job is that no provider failure reaches the terminal as a
        # traceback, and a chain that ends at `APIStatusError` leaves a door.
        raise AgentError(f"the provider failed: {error}") from error


def summary(record: RunRecord) -> list[str]:
    """The run in three lines, for the terminal. ASCII."""
    used = f"{record.spent} of {record.budget} tool calls"
    if record.emitted_on_exhaustion:
        used += " (budget spent; the plan was emitted with what it had)"
    failed = sum(1 for call in record.calls if call.failed)
    lines = [f"{record.model} -- {used}"]
    if failed:
        lines.append(f"  {failed} of those calls came back an error")
    lines.append(f"  {record.input_tokens} tokens in, {record.output_tokens} out")
    return lines
