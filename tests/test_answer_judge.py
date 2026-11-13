"""The judge: statements and relevance read from a model, scored and held to its bar in code."""

from __future__ import annotations

import json


import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from trainer import answer_judge
from trainer.answer_judge import Calibrated, Calibration, Reply, Verdict

REPLY = Reply("r", "Quando inspiro alla panca?", "Inspira mentre scendi. Trattieni il fiato sui carichi pesanti.", ("c",))
TEXTS = {"c": "Bench Press / Cautions\nInhale on the downward movement and exhale on the upward movement."}


def _said(*replies: object, cost: float = 0.001) -> FakeMessagesListChatModel:
    return FakeMessagesListChatModel(
        responses=[AIMessage(r if isinstance(r, str) else json.dumps(r), response_metadata={"cost": cost}) for r in replies]
    )


def test_faithfulness_is_the_share_of_statements_the_passages_support() -> None:
    chat = _said(
        {"statements": ["Inspira mentre scendi.", "Trattieni il fiato sui carichi pesanti."]},
        {"verdicts": [{"statement": "a", "verdict": 1}, {"statement": "b", "verdict": 0}]},
        {"reason": "it says when to inhale", "relevant": 1},
    )

    verdict = answer_judge.Judge(chat).judge(REPLY, TEXTS)

    assert verdict.faithfulness == 0.5
    assert verdict.statements[1] == ("Trattieni il fiato sui carichi pesanti.", False)
    assert verdict.relevance == 1.0 and verdict.reason == "it says when to inhale"
    assert verdict.dollars == pytest.approx(0.003)


def test_an_answer_to_another_question_is_not_relevant() -> None:
    chat = _said({"statements": []}, {"reason": "it names the muscles, not when to breathe", "relevant": 0})

    verdict = answer_judge.Judge(chat).judge(REPLY, TEXTS)

    assert verdict.relevance == 0.0


def test_a_reply_not_json_is_asked_again_once_then_named() -> None:
    chat = _said("```json\n" + json.dumps({"statements": []}) + "\n```", {"relevant": 1})
    assert answer_judge.Judge(chat).judge(REPLY, TEXTS).relevance == 1.0

    with pytest.raises(answer_judge.JudgeError, match="did not reply with JSON"):
        answer_judge.Judge(_said("no", "still no")).judge(REPLY, TEXTS)


def test_the_threshold_agrees_with_the_most_labels_and_reads_a_tie_strictly() -> None:
    assert answer_judge.fitted([0.2, 0.9, 1.0], [False, True, True]) == 0.9
    assert answer_judge.fitted([0.7, 0.8, 0.95], [True, True, True]) == 0.7


def _calibrated(id: str, kind: str, faithful: bool = True, relevant: bool = True) -> Calibrated:
    return Calibrated(Reply(id, "q", "a", ("c",)), kind, faithful, relevant)


def _verdict(faithfulness: float, relevance: float) -> Verdict:
    return Verdict(faithfulness, relevance, (), "", 0.01)


def test_a_judge_clears_its_bar_only_catching_planted_errors_and_agreeing_with_the_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(answer_judge, "CAUGHT_BAR", 2)
    monkeypatch.setattr(answer_judge, "AGREED_BAR", 2)
    calibration = Calibration(
        1,
        3,
        (
            _calibrated("good", answer_judge.REAL),
            _calibrated("loose", answer_judge.REAL, faithful=False),
            _calibrated("added", answer_judge.UNSUPPORTED, relevant=True, faithful=False),
            _calibrated("elsewhere", answer_judge.OFF_QUESTION, relevant=False),
        ),
    )
    verdicts = {
        "good": _verdict(1.0, 0.8),
        "loose": _verdict(0.5, 0.9),
        "added": _verdict(0.6, 0.85),
        "elsewhere": _verdict(1.0, 0.4),
    }

    reading = answer_judge.read(calibration, verdicts)

    assert (reading.agreed, reading.caught) == (2, 2) and reading.clears
    assert reading.thresholds == answer_judge.Thresholds(1.0, 0.8)
    assert reading.dollars == pytest.approx(0.04)

    verdicts["elsewhere"] = _verdict(1.0, 0.85)
    missed = answer_judge.read(calibration, verdicts)
    assert missed.caught == 1 and not missed.clears
    assert "elsewhere: planted off_question not caught" in missed.disagreements


def test_the_committed_calibration_set_holds_30_real_and_15_planted_on_cited_passages() -> None:
    calibration = answer_judge.load()
    kinds = [one.kind for one in calibration.replies]

    assert kinds.count(answer_judge.REAL) == 30
    assert len(kinds) - kinds.count(answer_judge.REAL) == 15
    texts = answer_judge.passages()
    assert all(cited in texts for one in calibration.replies for cited in one.reply.passages)
