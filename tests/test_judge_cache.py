from pathlib import Path
from typing import Any

import pytest

from eval_platform.graders.judge_cache import JudgeCache, cache_key, model_version


def _key(**over: Any) -> str:
    base: dict[str, Any] = dict(
        case_id="c1",
        output="the answer",
        judge_model="mockllm/model",
        judge_version="mock",
        rubric_id="faithfulness",
        rubric_version="1",
        params={"max_tokens": 256},
    )
    base.update(over)
    return cache_key(**base)


def test_key_is_stable_and_sensitive():
    assert _key() == _key()
    assert len(_key()) == 64
    assert _key(output="other") != _key()
    assert _key(judge_version="v2") != _key()
    assert _key(rubric_version="2") != _key()
    assert _key(params={"max_tokens": 128}) != _key()
    # dict key order must not matter
    assert _key(params={"a": 1, "b": 2}) == _key(params={"b": 2, "a": 1})


def test_cache_round_trip(tmp_path: Path):
    c = JudgeCache(tmp_path / "judge")
    assert c.get("a" * 64) is None
    c.put("a" * 64, {"label": "SUPPORTED", "raw": "VERDICT: SUPPORTED"})
    assert c.get("a" * 64) == {"label": "SUPPORTED", "raw": "VERDICT: SUPPORTED"}
    assert (tmp_path / "judge" / ("a" * 64 + ".json")).exists()


def test_cache_treats_a_truncated_entry_as_a_miss(tmp_path: Path):
    c = JudgeCache(tmp_path / "judge")
    (tmp_path / "judge").mkdir()
    cut_short = tmp_path / "judge" / ("b" * 64 + ".json")
    cut_short.write_text('{"label": "SUPPORTED", "ra', encoding="utf-8")
    assert c.get("b" * 64) is None
    no_raw = tmp_path / "judge" / ("c" * 64 + ".json")
    no_raw.write_text('{"label": "SUPPORTED"}', encoding="utf-8")
    assert c.get("c" * 64) is None


def test_cache_rejects_bad_key(tmp_path: Path):
    c = JudgeCache(tmp_path)
    with pytest.raises(ValueError):
        c.get("../escape")


def test_model_version_for_mock_and_hosted():
    assert model_version("mockllm/model") == "mock"
    assert (
        model_version("anthropic/claude-haiku-4-5-20251001")
        == "anthropic/claude-haiku-4-5-20251001"
    )


def test_model_version_reads_hf_ref(tmp_path: Path, monkeypatch):
    hub = tmp_path / "hub" / "models--Org--Name" / "refs"
    hub.mkdir(parents=True)
    (hub / "main").write_text("abc123\n", encoding="utf-8")
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hub"))
    assert model_version("hf/Org/Name") == "abc123"


def test_model_version_hf_missing_ref_raises(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "empty"))
    with pytest.raises(FileNotFoundError):
        model_version("hf/Org/Missing")
