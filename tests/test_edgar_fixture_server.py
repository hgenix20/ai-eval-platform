"""The EDGAR fixture retriever: its index functions, and the same server
started for real over stdio as an MCP target."""

import json
import sys
from pathlib import Path

import pytest

from eval_platform.retrievers.edgar_fixture_server import (
    MAX_K,
    MAX_TEXT_CHARS,
    FixtureIndex,
    default_fixtures_dir,
    load_fixtures,
)
from eval_platform.targets import MCPTarget

SERVER = "eval_platform.retrievers.edgar_fixture_server"

ALPHA = {
    "accession": "0000000000-25-000001",
    "company": "Alpha Corp.",
    "form": "10-K",
    "item": "1A",
    "filing_date": "2025-01-31",
    "document_url": "https://www.sec.gov/Archives/edgar/data/1/alpha.htm",
    "golden_id": "alpha-0000000000-25-000001-1A",
    "window_paragraphs": 40,
    "paragraphs": [
        {"id": 0, "text": "Item 1A. Risk Factors"},
        {"id": 1, "text": "Supply chain disruption could reduce manufacturing output."},
        {"id": 2, "text": "Currency movement affects reported revenue in every region."},
        {"id": 3, "text": "Supply chain and currency movement together shape gross margin."},
        {"id": 4, "text": "x" * (MAX_TEXT_CHARS + 500)},
    ],
    "anchors": [
        {
            "phrase": "supply chain disruption",
            "paragraph_id": 1,
            "sentence": "Supply chain disruption could reduce manufacturing output.",
        }
    ],
}

BETA = {
    "accession": "0000000000-25-000002",
    "company": "Beta Ltd.",
    "form": "10-Q",
    "item": "2",
    "filing_date": "2025-05-02",
    "document_url": "https://www.sec.gov/Archives/edgar/data/2/beta.htm",
    "golden_id": "beta-0000000000-25-000002-2",
    "window_paragraphs": 40,
    "paragraphs": [{"id": 7, "text": "Revenue grew on higher unit volume."}],
    "anchors": [
        {
            "phrase": "higher unit volume",
            "paragraph_id": 7,
            "sentence": "Revenue grew on higher unit volume.",
        }
    ],
}


@pytest.fixture
def fixtures_dir(tmp_path: Path) -> Path:
    d = tmp_path / "fixtures"
    d.mkdir()
    for f in (ALPHA, BETA):
        (d / f"{f['accession']}-{f['item']}.json").write_text(json.dumps(f), encoding="utf-8")
    return d


@pytest.fixture
def index(fixtures_dir: Path) -> FixtureIndex:
    return FixtureIndex(load_fixtures(fixtures_dir))


def test_load_fixtures_reads_every_json_file(fixtures_dir: Path):
    assert sorted(load_fixtures(fixtures_dir)) == [
        ("0000000000-25-000001", "1A"),
        ("0000000000-25-000002", "2"),
    ]


def test_load_fixtures_of_a_missing_directory_is_empty(tmp_path: Path):
    assert load_fixtures(tmp_path / "nope") == {}


def test_default_fixtures_dir_is_the_repo_suite(tmp_path: Path, monkeypatch):
    """Resolved from the module's own location, so any working directory works."""
    monkeypatch.chdir(tmp_path)
    d = default_fixtures_dir()
    assert d.is_absolute() and d.parts[-2:] == ("groundedness", "fixtures")


def test_list_filings_describes_every_fixture_sorted(index: FixtureIndex):
    rows = index.list_filings()
    assert [r["accession"] for r in rows] == ["0000000000-25-000001", "0000000000-25-000002"]
    assert rows[0] == {
        "accession": "0000000000-25-000001",
        "company": "Alpha Corp.",
        "form": "10-K",
        "item": "1A",
        "filing_date": "2025-01-31",
    }


def test_search_ranks_by_the_count_of_distinct_query_terms(index: FixtureIndex):
    hits = index.search_filing("0000000000-25-000001", "1A", "supply chain currency movement")
    assert [h["paragraph_id"] for h in hits] == [3, 1, 2]


def test_search_breaks_ties_by_paragraph_id(index: FixtureIndex):
    """Paragraphs 1 and 3 both carry "supply" and "chain", so id orders them."""
    hits = index.search_filing("0000000000-25-000001", "1A", "supply chain")
    assert [h["paragraph_id"] for h in hits] == [1, 3]


def test_search_drops_short_terms_and_stop_words(index: FixtureIndex):
    """Only "movement" carries any signal, so only the movement paragraphs match."""
    hits = index.search_filing("0000000000-25-000001", "1A", "the of a in movement")
    assert [h["paragraph_id"] for h in hits] == [2, 3]


def test_search_matches_across_the_two_apostrophes():
    """The filing writes U+2019, the question is typed with U+0027, and the
    term is the same word either way."""
    curly = chr(0x2019)
    fixture = {
        **ALPHA,
        "accession": "0000000000-25-000003",
        "paragraphs": [{"id": 0, "text": f"The company{curly}s liquidity depends on credit."}],
    }
    one = FixtureIndex({("0000000000-25-000003", "1A"): fixture})
    hits = one.search_filing("0000000000-25-000003", "1A", "company's liquidity")
    assert [h["paragraph_id"] for h in hits] == [0]
    assert curly in hits[0]["text"]
    assert one.search_filing("0000000000-25-000003", "1A", f"company{curly}s liquidity") == hits


def test_search_returns_nothing_when_no_term_matches(index: FixtureIndex):
    assert index.search_filing("0000000000-25-000001", "1A", "cryptocurrency mining") == []


def test_search_honours_k_and_caps_it(index: FixtureIndex):
    assert len(index.search_filing("0000000000-25-000001", "1A", "supply currency", k=1)) == 1
    hits = index.search_filing("0000000000-25-000001", "1A", "supply currency", k=999)
    assert len(hits) <= MAX_K


def test_search_caps_the_returned_text(index: FixtureIndex):
    hits = index.search_filing("0000000000-25-000001", "1A", "xxxx")
    assert hits and len(hits[0]["text"]) <= MAX_TEXT_CHARS


def test_search_of_an_unknown_filing_returns_an_error_row(index: FixtureIndex):
    hits = index.search_filing("9999999999-99-999999", "1A", "supply")
    assert len(hits) == 1 and "error" in hits[0]
    hits = index.search_filing("0000000000-25-000001", "99", "supply")
    assert len(hits) == 1 and "error" in hits[0]


def test_get_paragraph_returns_the_paragraph_by_its_original_id(index: FixtureIndex):
    got = index.get_paragraph("0000000000-25-000002", "2", 7)
    assert got == {"paragraph_id": 7, "text": "Revenue grew on higher unit volume."}


def test_get_paragraph_errors_on_an_unknown_filing_or_paragraph(index: FixtureIndex):
    assert "error" in index.get_paragraph("9999999999-99-999999", "1A", 0)
    assert "error" in index.get_paragraph("0000000000-25-000001", "1A", 4242)


def test_the_tools_never_raise_on_junk_arguments(index: FixtureIndex):
    assert "error" in index.search_filing("", "", "")[0]
    assert index.search_filing("0000000000-25-000001", "1A", "", k=0) == []
    assert "error" in index.get_paragraph("0000000000-25-000001", "1A", -1)


def test_an_empty_index_answers_without_raising():
    empty = FixtureIndex({})
    assert empty.list_filings() == []
    assert "error" in empty.search_filing("a", "1A", "q")[0]
    assert "error" in empty.get_paragraph("a", "1A", 0)


def test_the_server_starts_over_stdio_and_lists_its_three_tools(fixtures_dir: Path):
    pytest.importorskip("mcp")
    target = MCPTarget.stdio(
        command=sys.executable,
        args=["-m", SERVER, "--fixtures", str(fixtures_dir)],
        model="mockllm/model",
        server_name="edgar-fixture",
    )
    assert sorted(target.list_tools()) == ["get_paragraph", "list_filings", "search_filing"]
