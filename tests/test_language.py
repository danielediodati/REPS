"""The chat's language: read off Telegram, carried by a run, and said from one catalog per language."""

from __future__ import annotations

import string
from collections.abc import Mapping
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from trainer.coach import language


def _placeholders(table: Mapping[str, Any], prefix: str = "") -> dict[str, set[str]]:
    """Every line of a catalog, by its dotted key, with the names it is filled with."""
    found: dict[str, set[str]] = {}
    for key, value in table.items():
        if isinstance(value, Mapping):
            found |= _placeholders(value, f"{prefix}{key}.")
        else:
            found[f"{prefix}{key}"] = {name for _, name, _, _ in string.Formatter().parse(value) if name}
    return found


def test_every_language_has_every_line_with_the_same_placeholders() -> None:
    italian = _placeholders(language.catalog(language.ITALIAN))
    for spoken in language.LANGUAGES:
        assert _placeholders(language.catalog(spoken)) == italian, spoken


def test_every_catalog_loads_whole() -> None:
    for spoken in language.LANGUAGES:
        said = language.texts(spoken)
        assert "{log}" not in said.chat.failed and "trainer.log" in said.chat.failed


def test_an_app_set_to_italian_is_answered_in_italian_and_any_other_in_english() -> None:
    assert language.of("it") == language.ITALIAN
    assert language.of("it-IT") == language.ITALIAN
    assert language.of("en-GB") == language.ENGLISH
    assert language.of("de") == language.ENGLISH
    assert language.of(None) == language.ENGLISH


class _State(TypedDict):
    told: str


def _told(config: RunnableConfig) -> str:
    graph = StateGraph(_State)
    graph.add_node("tell", lambda state: {"told": language.told()})
    graph.add_edge(START, "tell")
    graph.add_edge("tell", END)
    return str(graph.compile().invoke({"told": ""}, config)["told"])


def test_a_run_writes_in_the_language_its_config_carries_and_in_italian_without_one() -> None:
    assert _told({"configurable": {language.KEY: language.ENGLISH}}).endswith("in English.")
    assert _told({"configurable": {language.KEY: language.ITALIAN}}).endswith("in Italian.")
    assert _told({}).endswith("in Italian.")
