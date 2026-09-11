"""The planner and logger tool loops on Groq, which ADR-0004's graph replaces."""

from __future__ import annotations

import inspect
import json
import os
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, fields
from typing import Any, Generic, Protocol, TypeVar, get_type_hints

from pydantic import BaseModel, TypeAdapter

from trainer import log as logs
from trainer import plan as plans
from trainer import tools
from trainer.engine import catalog

BACKEND_ENV = "LLM_BACKEND"
MODEL_ENV = "GROQ_MODEL"
API_KEY_ENV = "GROQ_API_KEY"

GROQ = "groq"
BACKENDS = (GROQ,)
"""What `LLM_BACKEND` may name; any other value is refused by name rather than ignored."""

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
"""Tool calls one run may make before the loop stops offering tools; `--call-budget` overrides it."""

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
    request is built.

    `text` is the same turn's prose, pulled out where the loop can read it.
    The planner never looks at it -- a turn with no tool calls is a planner
    that has finished -- but the logger's clarifying question arrives this
    way, because a question to the user is not a tool call and the six tools
    are all reads. Two fields rather than one because the adapter has to hand
    `content` back verbatim: rebuilt from `text`, the history sent on the next
    request would disagree with the history the provider recorded.
    """

    content: Any
    calls: tuple[Call, ...] = ()
    text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class Exchange:
    """One round: what the model said, what the tools answered, and -- when
    the model asked the user something instead of calling a tool -- what they
    said back.

    `answer` is the clarifying turn, and it lives here rather than in a store
    of its own because that is what makes it impossible to persist: a round
    of this conversation exists for as long as one invocation of the loop
    does, and Ctrl-C leaves no rubble because there is nowhere for rubble to
    be left.
    """

    reply: Reply
    results: tuple[Result, ...] = field(default_factory=tuple)
    answer: str | None = None


Document = TypeVar("Document", bound=BaseModel)
"""What a given agent emits. `plan.WorkoutPlan` for the planner,
`log.PerformedWorkout` for the logger -- and the loop below never names
either, which is what lets both run through one seam."""


@dataclass(frozen=True)
class Emission(Generic[Document]):
    """The final turn: the document, in the shape the door asked for."""

    document: Document
    input_tokens: int = 0
    output_tokens: int = 0


class Model(Protocol):
    """Two methods and a name, because the loop has two phases and a record.

    Narrow on purpose. A stand-in that satisfies this exercises the whole loop
    -- the calls, the budget, the emission, the way out through the validator
    -- without a socket, which is the only way the suite can cover any of it.

    **One seam for both agents**, which is why `emit` takes the shape it is to
    produce rather than knowing it. A second protocol for the logger would be
    a second adapter, a second set of provider-failure translations and a
    second place to get the message shapes wrong -- the same argument
    `tools.TOOLS` makes about doors, one level up.
    """

    @property
    def name(self) -> str:
        """What ran, for the record: asked of the model, never read back from the environment."""
        ...

    def respond(
        self,
        brief: str,
        exchanges: Sequence[Exchange],
        offered: Sequence[dict[str, Any]] | None,
    ) -> Reply:
        """One turn, with `offered` tools or with none at all."""
        ...

    def emit(
        self, brief: str, exchanges: Sequence[Exchange], shape: type[Document]
    ) -> Emission[Document]:
        """The document, structured, with no tools on the table."""
        ...


# -- the run record -----------------------------------------------------------
#
# An artifact, not a log. `trainer eval` decides its invariants by reading this
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


class RecordedQuestion(BaseModel):
    """One clarifying turn: what the agent asked, and what the user said.

    Recorded because *it asked instead of filling the field in* is the
    property the log eval scores twelve of its reports on, and a run that guessed
    confidently and a run that checked are indistinguishable from the document
    alone.
    """

    asked: str
    answered: str


class Run(BaseModel):
    """What the model called, what it cost, and how it left the loop.

    Shared by both agents because every field of it is about the *loop*, and
    there is one loop. What differs is the document that came out, and that is
    what each subclass adds.
    """

    model: str
    budget: int
    spent: int
    emitted_on_exhaustion: bool
    calls: list[RecordedCall]
    input_tokens: int
    output_tokens: int
    refused: str | None = None
    """What refused the document, or `None` when it passed. A document that is
    refused is still recorded whole: the point of the record is to be able to
    go and read what the model actually emitted."""


class RunRecord(Run):
    """One planning run, and the plan it emitted."""

    plan: plans.WorkoutPlan


class LogRecord(Run):
    """One logging run: the document it emitted, and anything it had to ask.

    `refused` here is `log.validate`'s sentence -- an exercise id the catalog
    does not have, a re-test date that has already passed. Never a statement
    about what the user did: a report is a fact, and the flags are where
    everything about the training is said.
    """

    questions: list[RecordedQuestion] = []
    document: logs.PerformedWorkout


# -- the tools, as this door registers them -----------------------------------


def schema(tool: Callable[..., Any]) -> dict[str, Any]:
    """One tool definition, derived from the function rather than restated.

    `mcp_server.py` gets its schemas from the SDK reading the same signatures;
    this is the same derivation for the other door. Hand-written schemas here
    would be a second definition -- and the one
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


@dataclass(frozen=True)
class Door:
    """Which agent is asking, and everything that answer changes.

    Four things vary between the planner and the logger and they vary
    together: the tools it may call, the fields its results keep on the way
    into the context, the prompt it works under, and the sentence that asks
    it to emit. Held as one object because a run is one of these end to end
    -- four parallel constants would let a caller build a logger offered the
    planner's tools, which is exactly the mistake nothing downstream would
    catch.

    What may exist at all is `tools.TOOLS`'s decision. This says which of it
    a given agent sees, from the one definition per tool: a copy diverges at
    the first tool added to one door and not the other.
    """

    name: str
    tools: tuple[str, ...]
    keeps: tuple[str, ...]
    system: str
    emit: str


def registered(door: Door) -> tuple[Callable[..., Any], ...]:
    """The tool functions one door offers, out of the shared surface.

    A name this door asks for that `tools.TOOLS` does not have is an
    `AgentError` rather than a silently shorter surface: the door constants
    are the one place a tool can be misspelled, and a logger quietly missing
    the tool it resolves substitutions with would look like a model that
    chose not to search.
    """
    defined = {tool.__name__: tool for tool in tools.TOOLS}
    missing = [name for name in door.tools if name not in defined]
    if missing:
        raise AgentError(
            f"the {door.name} door asks for {', '.join(missing)}, and the "
            f"tools defined are {', '.join(defined)}"
        )
    return tuple(defined[name] for name in door.tools)


def surface(door: Door) -> list[dict[str, Any]]:
    """The tool definitions one door puts on the table."""
    return [schema(tool) for tool in registered(door)]


def execute(
    call: Call, offered: Sequence[Callable[..., Any]], keeps: Sequence[str]
) -> Result:
    """Run one call: what the model got wrong comes back as a failed result, anything else propagates."""
    import pydantic

    def failed(sentence: str) -> Result:
        return Result(call_id=call.id, name=call.name, content=sentence, failed=True)

    found = next((tool for tool in offered if tool.__name__ == call.name), None)
    if found is None:
        # The model asked for a tool nobody offered *it* -- which includes a
        # tool that exists on the other door. Its mistake, not ours, so it goes
        # back as a result it can recover from.
        named = ", ".join(tool.__name__ for tool in offered)
        return failed(f"there is no tool called {call.name!r}; the tools are {named}")

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
    return Result(call_id=call.id, name=call.name, content=_serialised(answer, keeps))


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


EXERCISE_FIELDS = frozenset(declared.name for declared in fields(catalog.Exercise))
"""Every field of a catalog record, read from the dataclass rather than listed a second time."""

FOR_PLANNING = ("id", "equipment", "primary_muscles")
"""What a plan is written from: the id it names, whether today's equipment reaches it, and the muscles its time is divided over."""

FOR_THE_LOG = ("id", "name", "equipment", "mechanic", "primary_muscles")
"""What reading a report needs. `name` is here and not above, because a report says *"the bench"* and a plan is written in ids."""


def _serialised(answer: Any, keeps: Sequence[str]) -> str:
    """The engine's answer, in the dialect the tool definitions promised.

    JSON rather than `repr`: the docstrings the model reads describe
    `known: false` and `{"granularity": "pattern"}`, and Python would hand
    back `'known': False`. A model translating between two dialects mid-loop
    is one more thing that can go wrong for no reason at all.
    """
    return json.dumps(_trimmed(answer, keeps), default=str)


def _trimmed(answer: Any, keeps: Sequence[str]) -> Any:
    """Every exercise record, cut to the fields this door reads; every envelope around one, left whole.

    A catalog field the door does not keep -- `name` above all, which a model
    shown both strings copied into `exercise_id` -- reaches it under no key at
    all. A key that is not a catalog field is nobody's to drop.
    """
    return _cut(answer, tuple(keeps), EXERCISE_FIELDS - set(keeps))


def _cut(answer: Any, keeps: tuple[str, ...], hidden: frozenset[str]) -> Any:
    if isinstance(answer, list):
        return [_cut(item, keeps, hidden) for item in answer]
    if isinstance(answer, dict):
        if _an_exercise(answer):
            return {key: value for key, value in answer.items() if key in keeps}
        return {
            key: _cut(value, keeps, hidden)
            for key, value in answer.items()
            if key not in hidden
        }
    return answer


def _an_exercise(answer: Mapping[str, Any]) -> bool:
    """A catalog record, and not an envelope that happens to share a field name with one."""
    return "id" in answer and set(answer) <= EXERCISE_FIELDS


# -- the prompts -------------------------------------------------------------

PLANNING = f"""\
You plan one strength workout, for one person, today.

{tools.INSTRUCTIONS}
The rules you are working inside, none of which you can talk your way around:

- Every exercise you prescribe must be in what `admissible_set` returns for
  today's request, written as the `id` that came back, character for
  character. Anything else is rejected by a deterministic check after you
  emit.
- The plan must fit the time declared. It is never trimmed to fit: a plan that
  runs over is rejected whole, so ask `remaining_budget` before you commit to
  a block rather than after.
- An exercise appears at most once in the whole plan. One line per exercise,
  with the rounds and reps it needs.
- Each exercise is prescribed in reps or in seconds: its `prescription` gives
  the `unit` and the `amount`. A plank is seconds; a push-up is reps.
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
    if request.allocation:
        divided = ", ".join(
            f"{group} {minutes} min" for group, minutes in request.allocation
        )
        lines.append(
            f"The time divides over them as {divided}. That is a starting "
            "point and not an instruction: `allocate` will divide it on any "
            "proportions you think are better."
        )
    if request.exclusions:
        lines.append(
            "Excluded, and already filtered out of the admissible set: "
            + ", ".join(f"{e.granularity} {e.value}" for e in request.exclusions)
            + "."
        )
    if request.preferences:
        lines.append(
            "The user has said they would rather not do: "
            + ", ".join(request.preferences)
            + ". These are preferences, not exclusions, so they are still in "
            "the admissible set. Leave them out, or propose one and add a row "
            "to the plan's `despite` saying why -- proposing one silently is "
            "rejected."
        )
    if request.refused is not None:
        lines.append(
            "You proposed this workout and the user turned it down:\n"
            + request.refused.model_dump_json(indent=1)
        )
        if request.because:
            lines.append(f"They said: {request.because}")
        lines.append(
            "Propose a different one. Do not argue it, do not hand back the "
            "same plan, and do not give up and offer something token: they "
            "still want to train today."
        )
    lines.append("Plan the workout.")
    return "\n".join(lines)


EMIT_PLAN = "Emit the plan now, in the required shape."


QUESTION_MARKER = "QUESTION:"
"""How the logging agent says that a turn is a question for the user.

**Marked rather than inferred, and that is not tidiness.** The default model
reasons before it answers and hands the reasoning back as the assistant
message's own content: an observed run replied with nine paragraphs of *"let
me re-read that -- prescription says 3 rounds, the user did 3 rounds"* and a
loop that read prose as a question put all nine at the user's prompt. There is
no length, tone or punctuation that separates a model thinking out loud from a
model asking, so the model marks it.

Read off the **last** line that carries the marker, because reasoning
rehearses: a turn that talks itself through two candidate questions before
settling on one has both in it, and the one it settled on is the last.

A turn with no marked line at all is a model that has nothing to ask, which is
also what an empty turn and a truncated one are. All three end the loop and
the document is emitted -- the same shape as running out of call budget, and
for the same reason: finishing early and running out leave by one door.
"""

ASK_BUDGET = 3
"""Clarifying questions one report may cost the user.

The person is standing in a terminal after training, and a report that needs
a fourth question is a report the agent has failed to read rather than an
ambiguous one. Like the call budget it is a bound and not a target: running
out stops the asking and the document is emitted with what is known, which
is the same shape as invariant 1 -- it emits anyway.
"""

LOGGING = f"""\
You read one report of one workout that has already happened, and turn it
into the document the engine writes down.

{tools.INSTRUCTIONS}
How you read it:

- Call `prescribed_workout` for the workout the brief names, first. It is what
  the report is a deviation from, and it is the closed set of exercises the
  user is talking about.
- Resolve every exercise they name inside that set, by its name. Only when
  nothing in it can be what they meant -- which is what a substitution looks
  like -- call `search_exercises`, and take the id from what comes back.
  **Never write an id you remember.** An id that does not exist is refused; an
  id that exists and is the wrong exercise files the training under something
  they did not do, and nothing anywhere says so.
- Emit only what deviated. Everything you leave out is filled in from the
  prescription and marked as assumed, which is the whole point of logging by
  deviation -- a workout that went as prescribed is a document with no blocks
  in it at all.
- *Sets*, and Italian *serie*, are **rounds** -- how many times the block was
  performed. They are never the `amount`, which is the reps or the seconds of
  one round. *"Solo 3 serie"* is `rounds: 3` with the prescribed reps
  untouched, not three reps.
- `report` is the user's own words, verbatim and complete, in the language
  they wrote them. Not a summary and not a translation.
- Provenance is `reported` for a value they gave and `asked` for one that came
  back from a question you asked. Never `assumed`: that is the engine's, and
  a document claiming it would be claiming the prescription said something.
- **A value nobody gave is left out, not filled in.** Leaving it out is what
  the prescription is for; writing it marks it `reported`, which is the state
  saying the user said it. That is the one mistake here nothing downstream can
  catch.
- A number marked `assumed` has to be the prescribed one. Where the plan is
  silent -- a substituted exercise, a block nobody prescribed -- `assumed` is
  the honest label for a value the user did not give; where the plan says 10
  and the document says 8, it is refused.
- `rpe` is recorded only if they say how hard it felt. Never ask for it and
  never infer it from how the report reads.
- `load_kg` is null unless they gave a load, and `load_kg_source` is null
  with it: the two are written together or both left empty, and a provenance
  describing nothing is not a provenance. Zero is not *"no load"* either --
  it is a claim that the bar was empty.

Asking:

- When the report does not determine a value, ask instead of filling it in. A
  bare number is the case this exists for: *"4 out of 10"* is effort, or it is
  discomfort, and nothing in the sentence says which.
- To ask, write a line that starts with `{QUESTION_MARKER}` and holds the
  question and nothing else. Only that line reaches the user; anything else
  you write in the turn is yours. You will be given the answer and can carry
  on.
- When you have nothing left to ask, write no such line. That is how you say
  you are finished, and you will then be asked for the document.
- One question per turn, and at most {ASK_BUDGET} in all. Somebody is
  answering them in a terminal after training.
- Write the question, and the `why` of any exclusion you propose, in plain
  ASCII -- `perche`, not `perch\u00e9`, and `--` rather than a dash. They are
  printed to a Windows console that has no other alphabet. This applies to
  what **you** write and never to `report`, which is the user's own words and
  is copied exactly as they typed them.

Pain, and the one thing you may propose:

- Pain is prose. There is no scale, no threshold, and nothing accumulates.
- If what they said means a movement should stop being prescribed for a while,
  propose an exclusion: a `value` naming a movement pattern (`vertical push`)
  or a loaded joint (`shoulder`) -- never an exercise id, and never something
  they merely dislike -- a `retest_date` after today, and a `why` saying what
  you are reading. Do not label which of the two it is; the engine decides
  that against the catalog.
- It is a proposal. The user is shown it and confirms it before anything is
  written, because an exclusion on `shoulder` takes 251 of 582 exercises out
  of what may ever be prescribed. Propose one when the report is about pain,
  not when it is about effort.

You have a budget of tool calls. When it runs out you will be asked for the
document with whatever you know at that point.
"""

EMIT_LOG = "Emit the performed workout now, in the required shape."


PLANNER = Door(
    name="planner",
    tools=(
        "admissible_set",
        "remaining_budget",
        "allocate",
        "pattern_history",
        "last_performed_load",
        "search_exercises",
        "adherence_history",
        "volume_deficit",
        "unreported_workouts",
        "compare_variants",
    ),
    keeps=FOR_PLANNING,
    system=PLANNING,
    emit=EMIT_PLAN,
)
"""Everything on the shared surface except the one tool that reads a
prescription back.

`prescribed_workout` answers *what did workout 12 ask for*, and a planner has
no workout 12: it is writing one. What it wants to know about the past is
volume and adherence, and those it already has.

**Named, not derived by subtracting one name from `tools.TOOLS`.** Written that
way this door was the one place a tool could arrive without anybody deciding
it should: rename the excluded tool and the planner silently gains it, with
`registered`'s guard -- which only checks the names a door *asks* for -- unable
to say a word. A door is a decision about which tools an agent gets, and a
decision is written down.
"""

LOGGER = Door(
    name="logger",
    tools=(
        "prescribed_workout",
        "unreported_workouts",
        "last_performed_load",
        "pattern_history",
        "search_exercises",
        "compare_variants",
    ),
    keeps=FOR_THE_LOG,
    system=LOGGING,
    emit=EMIT_LOG,
)
"""Six tools, all reads, and no writer among them.

Named rather than derived by subtraction: `allocate` and `remaining_budget`
are arithmetic for a plan that has not happened, `admissible_set` is the space
a plan is chosen inside, `adherence_history` and `volume_deficit` are what the
*planner* wants to know about what was trained. None of them is a question
about the sentence in front of this agent, and a surface holding tools nobody
needs is context paid for on every turn.
"""


def log_brief(
    said: str,
    today: str,
    awaiting: int | None = None,
    prescribed_on: str | None = None,
) -> str:
    """The report, and what it is probably about, for the model to read.

    `awaiting` is the workout still to do -- resolved by the caller, because
    which prescribed workout is open is a fact and not a judgement. Which
    workout the report is *about* stays the model's call: a user who trained
    something else entirely says so in the sentence, and that sentence is the
    only place the answer is.
    """
    lines = [f"Today is {today}."]
    if awaiting is None:
        lines.append(
            "No prescribed workout is waiting for a report. Unless the user "
            "names one, this is training nobody planned: emit `workout_id` "
            "as null. `unreported_workouts` lists the ones a later workout "
            "overtook."
        )
    else:
        lines.append(
            f"Workout {awaiting}, prescribed on {prescribed_on}, is waiting "
            f"for a report, and this is almost certainly it. Call "
            f"`prescribed_workout({awaiting})` to see what it asked for. If "
            f"what they describe is plainly not that workout, emit "
            f"`workout_id` as null instead."
        )
    lines.append("The user said, in their own words:")
    lines.append(said)
    return "\n".join(lines)


# -- the two agents -----------------------------------------------------------


def plan_workout(
    connection: sqlite3.Connection,
    request: plans.Request,
    *,
    model: Model | None = None,
    budget: int = CALL_BUDGET,
) -> RunRecord:
    """Ask a model for a workout, and record everything it did to get there.

    Returns the record whether the plan passed or was refused. Refusal is an
    outcome of the run, not an exception: the plan eval counts refusals across
    many runs, and a function that raised on one would make the count the
    caller's job to reassemble.
    """
    ran = _ran(PLANNER, model, brief(request), budget)
    emission = ran.model.emit(ran.written, ran.exchanges, plans.WorkoutPlan)

    return RunRecord(
        **ran.fields(emission),
        plan=emission.document,
        refused=_refusal(connection, emission.document, request),
    )


def log_workout(
    connection: sqlite3.Connection,
    said: str,
    today: str,
    *,
    ask: Ask,
    awaiting: int | None = None,
    prescribed_on: str | None = None,
    model: Model | None = None,
    budget: int = CALL_BUDGET,
) -> LogRecord:
    """Read one report against what was prescribed, and record what came of it.

    **Nothing here writes.** The six tools are reads and the document goes
    back to the caller; `workouts.record_performed` is called from the command
    and nowhere else, which is what keeps the single door single and what
    makes an interrupted run leave nothing behind. `test_agent.py::
    test_only_the_cli_calls_a_writer` is the guard on that claim.

    `ask` is how a clarifying question reaches the person who wrote the
    report. It is a parameter rather than a call to `click` because the turn
    belongs to the loop and the terminal does not: the log eval runs thirty
    reports through this function with a scripted answerer, and a loop that
    reached for stdin could not be measured at all.

    Returns the record whether the document passed `log.validate` or was
    refused, for `plan_workout`'s reason.
    """
    ran = _ran(
        LOGGER,
        model,
        log_brief(said, today, awaiting, prescribed_on),
        budget,
        ask=ask,
    )
    emission = ran.model.emit(ran.written, ran.exchanges, logs.PerformedWorkout)

    return LogRecord(
        **ran.fields(emission),
        questions=ran.questions,
        document=emission.document,
        refused=_log_refusal(connection, emission.document, today),
    )


# -- the loop, which is one loop ----------------------------------------------


Ask = Callable[[str], str]
"""How the loop puts a clarifying question to whoever wrote the report."""


@dataclass
class _Ran:
    """What one pass over the tool surface produced, before the emission.

    A mutable holder rather than a tuple of eight things, because the two
    entry points differ only in the document they ask for at the end and the
    fields they keep -- and the loop that fills this in is the same loop.
    """

    model: Model
    written: str
    exchanges: list[Exchange] = field(default_factory=list)
    calls: list[RecordedCall] = field(default_factory=list)
    questions: list[RecordedQuestion] = field(default_factory=list)
    budget: int = CALL_BUDGET
    spent: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def fields(self, emission: Emission[Any]) -> dict[str, Any]:
        """The `Run` fields, with the emission's own cost folded in.

        A turn's calls are executed together, so the last one may carry the
        count past the budget rather than land on it. The record says what was
        actually spent; the budget is the point at which tools stop being
        offered, not a number the loop pretends to hit exactly.
        """
        return {
            "model": self.model.name,
            "budget": self.budget,
            "spent": self.spent,
            "emitted_on_exhaustion": self.spent >= self.budget,
            "calls": self.calls,
            "input_tokens": self.input_tokens + emission.input_tokens,
            "output_tokens": self.output_tokens + emission.output_tokens,
        }


def _ran(
    door: Door,
    model: Model | None,
    written: str,
    budget: int,
    ask: Ask | None = None,
) -> _Ran:
    """Loop over one door's tools until the model stops asking for them.

    One loop for both agents. What a door changes is which tools are on the
    table, what its results carry into the context, and whether a turn with no
    tool calls in it is the end (`ask is None`, the planner: a model that has
    stopped asking is a model that is ready) or possibly a question.
    """
    if budget < 1:
        raise AgentError(f"a call budget is at least one call, got {budget}")
    if model is None:
        model = groq(door)

    offered = registered(door)
    definitions = [schema(tool) for tool in offered]
    ran = _Ran(model=model, written=written, budget=budget)

    while ran.spent < budget:
        reply = model.respond(written, ran.exchanges, definitions)
        ran.input_tokens += reply.input_tokens
        ran.output_tokens += reply.output_tokens

        results = []
        for call in reply.calls:
            result = execute(call, offered, door.keeps)
            ran.calls.append(
                RecordedCall(
                    name=call.name,
                    arguments=call.arguments,
                    failed=result.failed,
                    detail=result.content if result.failed else None,
                )
            )
            ran.spent += 1
            results.append(result)

        # A question is looked for on **every** turn, not only on one with no
        # tool calls in it. A model that searches the catalog and asks which
        # of two benches it was in the same breath is doing both things it is
        # supposed to do, and a loop that read the question only when the turn
        # was otherwise empty would drop it silently -- leaving a run that
        # reads, in the record, as one that never needed to ask.
        question = _question(reply, ask, len(ran.questions))
        answer = None
        if question is not None:
            assert ask is not None  # `_question` answers None without one
            answer = ask(question)
            ran.questions.append(RecordedQuestion(asked=question, answered=answer))

        ran.exchanges.append(
            Exchange(reply=reply, results=tuple(results), answer=answer)
        )
        if not reply.calls and question is None:
            # Nothing asked for and nothing asked: the model is finished.
            break

    return ran


DECORATION = "#>-*_ \t"
"""What a model puts in front of a label, and what the marker is found behind.

`**QUESTION:** ...`, `- QUESTION: ...`, `### QUESTION: ...` -- emphasising or
bulleting a labelled line is ordinary model behaviour, and matched strictly
every one of them misses. Missing is silent and lands in exactly the failure
the marker exists to prevent: the turn reads as *nothing to ask*, the loop
ends, and the document is emitted carrying the value the model meant to check.
"""


def _question(reply: Reply, ask: Ask | None, asked: int) -> str | None:
    """The clarifying question in this turn, or `None` when the loop is over.

    `None` on a door that cannot ask, on a turn that marks no question, and
    once the ask budget is spent -- which is where *it emits anyway* holds for
    questions the way it holds for tool calls.

    The **last** marked line, because reasoning rehearses: a turn that talks
    itself through two candidate questions before settling on one has both in
    it, and the one it settled on is the last.
    """
    if ask is None or asked >= ASK_BUDGET:
        return None
    for line in reversed(reply.text.splitlines()):
        said = line.strip(DECORATION)
        if said.upper().startswith(QUESTION_MARKER):
            marked = said[len(QUESTION_MARKER) :].strip(DECORATION)
            if marked:
                return marked
    return None


def _refusal(
    connection: sqlite3.Connection, emitted: plans.WorkoutPlan, request: plans.Request
) -> str | None:
    """Why the validator refused the emitted plan, or `None` when it passed."""
    try:
        plans.validate(connection, plans.to_blocks(emitted), request, emitted)
    except (plans.PlanError, plans.PlanRejected) as error:
        return str(error)
    return None


def _log_refusal(
    connection: sqlite3.Connection, emitted: logs.PerformedWorkout, today: str
) -> str | None:
    """The way out for a report, and it is a much narrower door.

    `log.validate` refuses statements about the *document* and nothing else --
    an id the catalog does not have, a provenance that could not be true, a
    re-test date already past. It never refuses a statement about the
    training: a report is a fact, and everything about what the user actually
    did is a flag on the row.
    """
    try:
        logs.validate(connection, emitted, today)
    except (logs.LogError, logs.LogRejected) as error:
        return str(error)
    return None


# -- the provider -------------------------------------------------------------


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """A pydantic model's schema as strict mode accepts it: every property required, no extras."""
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

    def __init__(
        self, door: Door, client: Any | None = None, model: str | None = None
    ) -> None:
        self._door = door
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

        A clarifying question is the same assistant message with no tool calls
        on it, and the user's answer is an ordinary user turn after it. That is
        the whole of the multi-turn machinery here: there is none, because the
        conversation only has to survive one invocation.
        """
        messages: list[Any] = [
            {"role": "system", "content": self._door.system},
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
            if exchange.answer is not None:
                messages.append({"role": "user", "content": exchange.answer})
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
            text=message.content or "",
            input_tokens=completion.usage.prompt_tokens,
            output_tokens=completion.usage.completion_tokens,
        )

    def emit(
        self, brief: str, exchanges: Sequence[Exchange], shape: type[Document]
    ) -> Emission[Document]:
        """The document, in the shape the caller asked for.

        No tools on this request, and not as a nicety: Groq does not allow
        structured outputs and tool use in the same call at all. The shape the
        file format uses, the shape the validator reads and the shape the model
        is held to are one declaration, so a field added to `WorkoutPlan` or to
        `PerformedWorkout` reaches all three.

        `shape` is a parameter rather than a constant because there are two
        agents and one adapter. Everything below this line is about Groq, and
        which document is being asked for is not.
        """
        import pydantic

        messages = self._messages(brief, exchanges)
        messages.append({"role": "user", "content": self._door.emit})
        completion = _reported(
            lambda: self._client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens(),
                messages=messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": _schema_name(shape),
                        "strict": True,
                        "schema": strict_schema(shape),
                    },
                },
            )
        )
        body = completion.choices[0].message.content
        if not body:
            raise AgentError(f"the model returned no {_schema_name(shape)}")
        try:
            emitted = shape.model_validate_json(body)
        except pydantic.ValidationError as error:
            # Two causes, and the message names both because they need
            # opposite responses. A completion cut off at `max_tokens` is a
            # setting to raise; a document that is whole and breaks one of the
            # shape's own rules -- a load with a provenance and no value -- is
            # a sentence to add to the prompt, and telling somebody to raise a
            # token ceiling for it sends them to the wrong file.
            raise AgentError(
                f"the model's {_schema_name(shape)} did not parse. Either it "
                f"was cut off at {max_tokens()} tokens ({MAX_TOKENS_ENV} "
                f"raises that), or it broke a rule of the shape: {error}"
            ) from error
        return Emission(
            document=emitted,
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


def _schema_name(shape: type[BaseModel]) -> str:
    """The document's name, in the dialect a json_schema block is written in.

    Derived from the class rather than given alongside it: a name and a shape
    passed separately are two declarations, and the day they disagree the model
    is told it is emitting a plan and held to a report.
    """
    letters = [
        ("_" + character.lower()) if character.isupper() else character
        for character in shape.__name__
    ]
    return "".join(letters).lstrip("_")


def groq(door: Door, client: Any | None = None) -> Groq:
    """The provider-backed model, built lazily.

    A function rather than a constructor call at import: nothing in the suite
    may build a client, and a module that made one on import would break the
    no-credentials guarantee for every test that happens to import it.
    """
    backend()
    return Groq(door, client)


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


def summary(record: Run) -> list[str]:
    """The run in a few lines, for the terminal. ASCII.

    One function for both agents because every line of it is about the loop.
    The questions are the one thing only a logging run has, and they are said
    out loud: *it asked instead of guessing* is the behaviour the log eval
    measures, and it is the behaviour a user should be able to see happening.
    """
    emitted = "the plan" if isinstance(record, RunRecord) else "the report"
    used = f"{record.spent} of {record.budget} tool calls"
    if record.emitted_on_exhaustion:
        used += f" (budget spent; {emitted} was emitted with what it had)"
    failed = sum(1 for call in record.calls if call.failed)
    lines = [f"{record.model} -- {used}"]
    if failed:
        lines.append(f"  {failed} of those calls came back an error")
    if isinstance(record, LogRecord) and record.questions:
        lines.append(f"  {len(record.questions)} question(s) asked")
    lines.append(f"  {record.input_tokens} tokens in, {record.output_tokens} out")
    return lines
