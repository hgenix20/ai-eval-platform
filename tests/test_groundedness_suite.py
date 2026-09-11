"""The groundedness suite: the generated cases agree with the committed
fixtures, and one case runs end to end against the retriever server."""

import json
import re
import sys
from pathlib import Path

import pytest
from inspect_ai.model import ModelOutput

from eval_platform.retrievers.edgar_fixture_server import FixtureIndex, load_fixtures
from eval_platform.suites import load_cases, run_case
from eval_platform.targets import MCPTarget
from eval_platform.types import Case

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "suites" / "groundedness"
FIXTURES = SUITE / "fixtures"
SERVER = "eval_platform.retrievers.edgar_fixture_server"
MIN_CASES = 40


@pytest.fixture(scope="module")
def cases() -> list[Case]:
    return load_cases(SUITE)


@pytest.fixture(scope="module")
def index() -> FixtureIndex:
    return FixtureIndex(load_fixtures(FIXTURES))


CASE_NAME = re.compile(r"^.+-(\d{10}-\d{2}-\d{6})-([0-9A-Z]+)-a\d+$")


def _fixture_for(case: Case, index: FixtureIndex) -> dict:
    """The fixture a case name points at. A case is named
    `<ticker>-<accession>-<item>-a<n>`, so its own name resolves its filing."""
    parsed = CASE_NAME.match(case.name)
    assert parsed is not None, f"{case.name} is not <ticker>-<accession>-<item>-a<n>"
    accession, item = parsed.group(1), parsed.group(2)
    fixture = index.fixtures.get((accession, item))
    assert fixture is not None, f"{case.name} has no fixture {accession}-{item}.json"
    return fixture


def test_the_golden_set_is_committed_with_its_provenance():
    golden = json.loads((SUITE / "golden.json").read_text(encoding="utf-8"))
    assert len(golden["cases"]) == 88
    provenance = golden["provenance"]
    assert provenance["commit"] == "97b928b"
    assert provenance["license"] == "MIT"
    assert provenance["source_repo"] == "https://github.com/hgenix20/signalnodus"
    assert provenance["path"] == "eval/golden.json"


def test_every_case_file_loads_and_names_are_unique(cases: list[Case]):
    assert len(cases) >= MIN_CASES
    names = [c.name for c in cases]
    assert len(set(names)) == len(names)
    assert [c.name for c in cases] == sorted(names)


def test_every_case_asks_for_an_agent_and_expects_grounding(cases: list[Case]):
    for c in cases:
        assert c.expect.grounded is True, c.name
        assert c.expect.answer_contains, c.name
        assert c.target_requirements == ["agent"], c.name
        assert c.max_steps >= 4, c.name


def test_every_case_points_at_a_committed_fixture(cases: list[Case], index: FixtureIndex):
    for c in cases:
        _fixture_for(c, index)


def test_every_expected_phrase_is_in_its_fixtures_paragraphs(
    cases: list[Case], index: FixtureIndex
):
    """`answer_contains` is a case-sensitive check, so the phrase has to be
    present in the filing's own casing, inside the window that was kept."""
    for c in cases:
        fixture = _fixture_for(c, index)
        phrase = c.expect.answer_contains or ""
        assert any(phrase in p["text"] for p in fixture["paragraphs"]), c.name


def test_every_fixture_anchor_sentence_sits_in_its_own_paragraph(index: FixtureIndex):
    assert index.fixtures
    for (accession, item), fixture in index.fixtures.items():
        by_id = {p["id"]: p["text"] for p in fixture["paragraphs"]}
        assert fixture["accession"] == accession and fixture["item"] == item
        assert fixture["paragraphs"] == sorted(fixture["paragraphs"], key=lambda p: p["id"])
        for anchor in fixture["anchors"]:
            text = by_id[anchor["paragraph_id"]]
            assert anchor["sentence"] in text, fixture["golden_id"]
            assert anchor["phrase"].lower() in anchor["sentence"].lower(), fixture["golden_id"]


def test_every_fixture_has_a_case(cases: list[Case], index: FixtureIndex):
    covered = {_fixture_for(c, index)["golden_id"] for c in cases}
    assert covered == {f["golden_id"] for f in index.fixtures.values()}


def _quotable(cases: list[Case], index: FixtureIndex) -> tuple[Case, dict, list[dict]]:
    """The first case whose anchor sentence survives the server's own text
    cap, with the search call and results that carry it. Choosing the case
    from the committed data keeps the scripted run honest: the quoted span
    below really is what the tool returned."""
    for case in cases:
        fixture = _fixture_for(case, index)
        phrase = case.expect.answer_contains or ""
        anchor = next(
            (a for a in fixture["anchors"] if a["phrase"].lower() in phrase.lower()), None
        )
        if anchor is None:
            continue
        hits = index.search_filing(fixture["accession"], fixture["item"], anchor["sentence"], k=5)
        if any(anchor["sentence"] in h.get("text", "") for h in hits):
            return case, anchor, hits
    pytest.fail("no committed case carries its anchor sentence through search_filing")


def test_a_scripted_run_over_the_server_passes_both_grounded_dimensions(
    cases: list[Case], index: FixtureIndex, tmp_path: Path
):
    pytest.importorskip("mcp")
    case, anchor, _ = _quotable(cases, index)
    fixture = _fixture_for(case, index)
    answer = (
        f'The filing says "{anchor["sentence"]}" '
        "The passage describes a risk the company reports to its investors."
    )
    target = MCPTarget.stdio(
        command=sys.executable,
        args=["-m", SERVER, "--fixtures", str(FIXTURES)],
        model="mockllm/model",
        model_args={
            "custom_outputs": [
                ModelOutput.for_tool_call(
                    "mockllm",
                    "search_filing",
                    {
                        "accession": fixture["accession"],
                        "item": fixture["item"],
                        "query": anchor["sentence"],
                        "k": 5,
                    },
                ),
                ModelOutput.from_content("mockllm", answer),
            ]
        },
        log_dir=tmp_path,
        server_name="edgar-fixture",
    )
    result = run_case(case, target)
    grades = {g.dimension: g for g in result.grades}
    assert grades["answer_contains"].passed, grades["answer_contains"].explanation
    assert grades["quotes_in_source"].passed, grades["quotes_in_source"].explanation
    assert result.passed


def test_a_fabricated_quote_fails_the_grounded_dimension(
    cases: list[Case], index: FixtureIndex, tmp_path: Path
):
    pytest.importorskip("mcp")
    case, anchor, _ = _quotable(cases, index)
    fixture = _fixture_for(case, index)
    answer = (
        f"{case.expect.answer_contains} appears here. The filing also says "
        '"the board approved a special dividend of four dollars per share."'
    )
    target = MCPTarget.stdio(
        command=sys.executable,
        args=["-m", SERVER, "--fixtures", str(FIXTURES)],
        model="mockllm/model",
        model_args={
            "custom_outputs": [
                ModelOutput.for_tool_call(
                    "mockllm",
                    "search_filing",
                    {
                        "accession": fixture["accession"],
                        "item": fixture["item"],
                        "query": anchor["sentence"],
                        "k": 5,
                    },
                ),
                ModelOutput.from_content("mockllm", answer),
            ]
        },
        log_dir=tmp_path,
        server_name="edgar-fixture",
    )
    result = run_case(case, target)
    grades = {g.dimension: g for g in result.grades}
    assert grades["answer_contains"].passed
    assert not grades["quotes_in_source"].passed
    assert not result.passed
