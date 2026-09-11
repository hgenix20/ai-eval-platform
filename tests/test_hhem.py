import pytest

from eval_platform.graders.hhem import (
    HHEM_SNAPSHOT,
    HHEMGrader,
    HHEMScorer,
    split_sentences,
    unsupported_share,
)
from eval_platform.types import Case, Expect, Step, Trajectory


class StubScorer:
    """Scores 0.9 when the hypothesis appears in the premise, else 0.1."""

    version = "stub"

    def __init__(self):
        self.calls = 0

    def score(self, pairs):
        self.calls += 1
        return [0.9 if h.strip(". ") in p else 0.1 for p, h in pairs]


def test_split_sentences_drops_fragments_and_keeps_order():
    text = "Revenue rose 5%. Costs fell. This is a long enough sentence to keep! Short? Ok."
    assert split_sentences(text) == [
        "Revenue rose 5%.",
        "This is a long enough sentence to keep!",
    ]


def test_unsupported_share_counts_only_low_scores():
    ctx = "Revenue rose 5% in 2025. Margins were flat."
    share, detail = unsupported_share(
        ctx, "Revenue rose 5% in 2025. Margins doubled in 2025.", StubScorer()
    )
    assert share == 0.5
    assert [round(s, 1) for _, s in detail] == [0.9, 0.1]


def test_unsupported_share_empty_context_is_all_unsupported():
    s = StubScorer()
    share, detail = unsupported_share("", "A claim that is long enough.", s)
    assert share == 1.0 and s.calls == 0 and detail[0][1] == 0.0


def test_unsupported_share_no_sentences_is_zero():
    share, detail = unsupported_share("ctx", "", StubScorer())
    assert share == 0.0 and detail == []


def test_unsupported_share_empty_context_and_empty_answer_is_zero():
    """Nothing was claimed, so nothing is unsupported; the answer is read
    before the context."""
    s = StubScorer()
    share, detail = unsupported_share("", "", s)
    assert share == 0.0 and detail == [] and s.calls == 0


def test_grader_grade_shape():
    t = Trajectory(
        target="t",
        goal="g",
        status="completed",
        answer="Revenue rose 5% in 2025. Margins doubled in 2025.",
        steps=(Step("tool", "search", {}, "Revenue rose 5% in 2025."),),
        side_effects=(),
        cost_usd=0.0,
        wall_ms=0.0,
    )
    g = HHEMGrader(scorer=StubScorer())
    grade = g.grade(Case(name="c", goal="g", expect=Expect()), t)
    assert grade.dimension == "unsupported_claims"
    assert grade.value == 0.5 and grade.passed is False
    assert "Margins doubled" in grade.explanation
    assert g.kind == "semantic" and g.version == HHEM_SNAPSHOT


@pytest.mark.gpu
@pytest.mark.network
def test_hhem_reproduces_model_card_examples():
    pairs = [
        ("The capital of France is Berlin.", "The capital of France is Paris."),
        ("I am in California", "I am in United States."),
        ("I am in United States", "I am in California."),
        (
            "A person on a horse jumps over a broken down airplane.",
            "A person is outdoors, on a horse.",
        ),
        (
            "A boy is jumping on skateboard in the middle of a red bridge.",
            "The boy skates down the sidewalk on a red bridge",
        ),
        (
            "A man with blond-hair, and a brown shirt drinking out of a public water fountain.",
            "A blond man wearing a brown shirt is reading a book.",
        ),
        ("Mark Wahlberg was a fan of Manny.", "Manny was a fan of Mark Wahlberg."),
    ]
    # Published on the model card, read 2026-09-11:
    # https://huggingface.co/vectara/hallucination_evaluation_model
    expected = [0.0111, 0.6474, 0.1290, 0.8969, 0.1846, 0.0050, 0.0543]
    got = HHEMScorer().score(pairs)
    assert [round(x, 4) for x in got] == expected
