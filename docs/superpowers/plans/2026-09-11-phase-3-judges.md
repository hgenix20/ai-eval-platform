# AI Eval Platform, Phase 3 (judges, calibration, groundedness) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add model-backed grading to the platform under the spec's calibration rule: judge graders with a content-addressed cache, a semantic (HHEM) grader, a human-labeled calibration set of at least 50 items, `evalplat calibrate` reporting Cohen's kappa per judge and swap agreement between two judge models, a gate that lets only calibrated judges block, and a `groundedness` suite over pinned EDGAR filings from the SignalNodus golden set with a published unsupported-claim rate.

**Architecture:** Model-backed grading is a second pass over a stored run, never part of the run itself: `evalplat run ...` records trajectories (deterministic grades only, as today), and `evalplat judge` re-reads a suite's `latest.json`, adds judge and semantic grades to every scored case, recomputes metrics, and republishes the run. This keeps the answering model and the judge model out of GPU memory at the same time (12 GB fits one 3B model in bf16, not two) and makes judge reruns free through the cache. Judges are Inspect model handles (`get_model`), so the same code runs on `mockllm/model` in tests, on `hf/` locally, and on a hosted provider when credits exist. The gate reads `results/calibration/latest.json` and refuses to let a judge-derived metric pass or fail until that judge's kappa and swap agreement clear the floors; until then the row is `not_measured` with the reason printed. HHEM-2.1-Open is loaded through a plain `T5ForTokenClassification` with the checkpoint's weights renamed, because the model's own `trust_remote_code` class cannot load under transformers 5 (verified 2026-09-11: `AttributeError: all_tied_weights_keys`); the plain loader reproduces the model card's seven published example scores to four decimals. The groundedness suite runs the existing MCP target over a stdio retriever that serves paragraphs of the pinned filings; the fixture is built once from EDGAR and validated against the golden set's own anchor phrases.

**Tech Stack:** as Phase 2 (Python 3.12, inspect-ai 0.3.263, inspect-evals 0.19.0, pydantic 2, PyYAML, mcp 2.x, opentelemetry-api) plus the existing `local` extra (torch 2.6.0+cu124, transformers 5.17, accelerate) for HHEM and the local judges, and `safetensors` (already installed as a transformers dependency; add it to the `local` extra explicitly). No new hosted dependency. Judge models: `hf/Qwen/Qwen2.5-3B-Instruct` (snapshot `aa8e72537993ba99e69dfaafa59ed015b17504d1`, license qwen-research) and `hf/Qwen/Qwen2.5-1.5B-Instruct` (snapshot `989aa7980e4cf806f80c7fef2b1adb7bc71aa306`, Apache-2.0). Classifier: `vectara/hallucination_evaluation_model` snapshot `8e4a2e6e96c708cc76c2344f7e4757df2515292c` (Apache-2.0), foundation `google/flan-t5-base`. Calibration labels: RAGTruth (github.com/ParticleMedia/RAGTruth, MIT, human span annotations).

**Spec:** `docs/superpowers/specs/2026-09-07-ai-eval-platform-design.md` sections 4.4 (`groundedness` and `judge_calibration` rows of the suites table), 4.5 (Grader protocol, judge cache, calibration rule), 4.6 (gate: `groundedness` row, `judge_stability`, the `unstable` verdict), 4.8 (report: judge calibration section), 4.9 (grader-call spans), 5 (rung 3), 8 (Phase 3 acceptance: judge graders with cache · calibration set of at least 50 labeled items · `evalplat calibrate` report with kappa per judge · swap-stability check against a second judge model · `groundedness` suite on the EDGAR golden set with unsupported-claim rate published).

**Spec deviations, decided before execution (the ledger carries each as a ruling):**

1. Judges are local models on the RTX 4080 at $0, because the HF Inference Providers account has no credits (402 on 2026-09-10) and no other hosted key exists. The spec's Phase 3 allocation ($60) stays unspent. A 3B judge is expected to land below the 0.70 kappa floor; that outcome is reported as measured, and the gate then keeps every judge row `not_measured`, which is the calibration rule doing its job. The judge code takes any Inspect model id, so a hosted judge is a command-line change.
2. The calibration set is sampled from RAGTruth's human-annotated test split (MIT), not labeled by hand here: 120 items, balanced 60 supported / 60 unsupported across the QA and Summary task types, seeded. Kameron's own labels can be added later as a second file in the same directory and the calibrate command reads every file there.
3. HHEM runs through the plain-T5 loader described above, pinned to the checkpoint snapshot, instead of `trust_remote_code`.
4. The groundedness retriever is a stdio MCP server over paragraph fixtures built from EDGAR, not the live SignalNodus MCP server, because every SignalNodus tool except `lookup_company` is paid per call and the account has no key. The suite's cases do not name tools, so the same suite runs against `https://mcp.signalnodus.ai/` with `--mcp-url` and a bearer key when one exists; that run is optional and not part of acceptance.
5. Model-backed grades are added by `evalplat judge` as a second pass over a stored run (see Architecture), so `run_suite` and `grade_expect` stay model-free.
6. The `groundedness` gate row has no absolute ceiling (the spec's 0.05) until the rate has been measured, matching the Phase 2 ruling on `faults`: a rise against the target-tied baseline fails; the measured level is the finding.

## Global Constraints

- Everything runs with the venv: `cd /c/Users/Sagac/ai-eval-platform && .venv/Scripts/python ...`; pyright as `.venv/Scripts/pyright --pythonpath .venv/Scripts/python.exe`.
- Gates before every commit: `ruff format .` then `ruff format --check .`, `ruff check .`, pyright, `bandit -q -r eval_platform`, `pytest -m "not network and not live and not gpu"`; `evalplat gate` must print PASS on `main` after each task that touches results, baselines, or `gate.yaml`. A new pytest marker `gpu` (registered in `pyproject.toml`) marks tests that load a real model; CI never runs them.
- Public prose (README, docs, YAML comments, CLI text, gate output, rubric text): no em-dashes, no "not X but Y" or "rather than" stacking, no robust / seamless / delve / surface (verb) / silently / quietly / load-bearing / hard-won / battle-tested, no inline labels.
- Commits: one line starting with a verb, no trailer of any kind. Work on a branch per task (`phase-3/<task>`), merged fast-forward into `main`; the remote is public, so push only when the controller says so, and `git pull --ff-only` first because CI commits baselines back to `main`.
- Never edit `docs/superpowers/` or `docs/research/`. Never edit anything under `C:\Users\Sagac\enterprise-agent-platform` or `C:\signalnodus-site`. Findings about other systems are written down, never patched around.
- No hosted model. Local GPU runs (`hf/` provider) are allowed where a task says so. `mockllm/model` with `custom_outputs` is the test double for every judge test.
- A number is published only from a committed file under `results/` produced by `evalplat`.
- Claims about other people's work (RAGTruth, HHEM, Qwen licenses) are cited to the primary URL and say only what that page says.
- Bound everything: every model call carries `max_tokens`; every retriever result is capped in count and characters; every EDGAR fetch has a timeout and a delay between requests.

---

## File structure

```
eval_platform/graders/base.py              Grader protocol (id, kind, version, grade)
eval_platform/graders/judge.py             JudgeGrader over an Inspect model; rubric registry; verdict parsing
eval_platform/graders/judge_cache.py       content-addressed cache under .cache/judge/
eval_platform/graders/rubrics/faithfulness.py, correctness.py   rubric text, id, version
eval_platform/graders/hhem.py              HHEM-2.1-Open through a plain T5 loader; sentence split; unsupported share
eval_platform/graders/deterministic.py     += quotes_in_source dimension (Expect.grounded)
eval_platform/types.py                     Expect += grounded; compute_metrics += unsupported_rate, judge.* metrics
eval_platform/calibration.py               calibration item schema, kappa, swap agreement, report
eval_platform/judge_pass.py                second-pass grading over a stored run
eval_platform/gate/config.py               += judges (kappa_floor, min_swap_agreement, require_swap_agreement)
eval_platform/gate/compare.py              judge rows need calibration; unstable verdict
eval_platform/retrievers/__init__.py
eval_platform/retrievers/edgar_fixture_server.py   stdio MCP server over suites/groundedness/fixtures
eval_platform/reports/html.py              judge calibration section
eval_platform/cli.py                       evalplat calibrate, evalplat judge
scripts/build_calibration_set.py           RAGTruth -> calibration/faithfulness/ragtruth-120.jsonl
scripts/build_edgar_fixtures.py            golden.json + EDGAR -> suites/groundedness/fixtures/*.json + cases
calibration/faithfulness/ragtruth-120.jsonl, calibration/faithfulness/LICENSE-RAGTruth.txt, calibration/README.md
suites/groundedness/*.yaml, suites/groundedness/fixtures/*.json, suites/groundedness/golden.json, suites/groundedness/README.md
gate.yaml                                  groundedness rows, judges block
results/calibration/latest.json, results/groundedness/latest.json
docs/results.md, docs/adr/0007-*.md, docs/adr/0008-*.md, README.md, .github/workflows/ci.yml
tests/test_judge.py, test_judge_cache.py, test_hhem.py, test_calibration.py, test_judge_pass.py,
tests/test_gate_judges.py, test_edgar_fixture_server.py, test_groundedness_suite.py, test_graders_grounded.py
```

---

### Task 1: Grader protocol, judge cache, judge grader

**Files:**
- Create: `eval_platform/graders/base.py`, `eval_platform/graders/judge_cache.py`, `eval_platform/graders/judge.py`, `eval_platform/graders/rubrics/__init__.py`, `eval_platform/graders/rubrics/faithfulness.py`, `eval_platform/graders/rubrics/correctness.py`
- Modify: `eval_platform/graders/__init__.py` (exports), `eval_platform/telemetry.py` (nothing new; use `span`)
- Test: `tests/test_judge_cache.py`, `tests/test_judge.py`

**Interfaces:**
- Consumes: `Case`, `Trajectory`, `Grade` from `eval_platform.types`; `span`, `set_attributes` from `eval_platform.telemetry`; `inspect_ai.model.get_model`, `GenerateConfig`, `ChatMessageSystem`, `ChatMessageUser`.
- Produces:
  ```python
  class Grader(Protocol):
      id: str
      kind: Literal["deterministic", "semantic", "judge"]
      version: str
      def grade(self, case: Case, trajectory: Trajectory) -> Grade: ...

  @dataclass(frozen=True)
  class Rubric:
      id: str            # "faithfulness" | "correctness"
      version: str       # "1"
      system: str        # the judge's instructions
      def user_prompt(self, case: Case, trajectory: Trajectory) -> str: ...
      labels: tuple[str, ...]   # ("SUPPORTED", "UNSUPPORTED", "UNKNOWN") / ("CORRECT", "INCORRECT", "NOT_ATTEMPTED")
      passing: str              # label that counts as pass

  RUBRICS: dict[str, Rubric]

  Verdict = Literal["pass", "fail", "unknown"]

  @dataclass(frozen=True)
  class JudgeResult:
      verdict: Verdict
      label: str
      raw: str
      cached: bool

  def cache_key(*, case_id: str, output: str, judge_model: str, judge_version: str,
                rubric_id: str, rubric_version: str, params: dict[str, Any]) -> str   # sha256 hex

  class JudgeCache:
      def __init__(self, root: Path) -> None
      def get(self, key: str) -> dict[str, Any] | None
      def put(self, key: str, payload: dict[str, Any]) -> None

  def model_version(model_id: str) -> str
      # hf/<repo>: the snapshot hash in ~/.cache/huggingface/hub/models--<repo>/refs/main
      # mockllm/*: "mock"; anything else: the model id itself (hosted ids carry their date)

  class JudgeGrader:
      kind = "judge"
      def __init__(self, *, model: str, rubric: Rubric, cache: JudgeCache,
                   model_args: dict[str, Any] | None = None, max_tokens: int = 256,
                   model_handle: Model | None = None) -> None
      id: str            # f"{rubric.id}@{rubric.version}:{model}"
      version: str       # model_version(model)
      def judge(self, case: Case, trajectory: Trajectory) -> JudgeResult   # sync; asyncio.run inside
      def grade(self, case: Case, trajectory: Trajectory) -> Grade
          # dimension f"judge:{rubric.id}:{model}", value 1.0 pass / 0.0 fail / 0.5 unknown,
          # passed = verdict == "pass"; explanation = f"{label} ({'cached' if cached else 'called'}): {raw[:200]}"
  ```
  A judge grade's `value` 0.5 marks `unknown`; `compute_metrics` (Task 4) counts it as neither pass nor fail.

- [ ] **Step 1: Write the failing cache tests**

`tests/test_judge_cache.py`:
```python
from pathlib import Path

from eval_platform.graders.judge_cache import JudgeCache, cache_key, model_version


def _key(**over):
    base = dict(case_id="c1", output="the answer", judge_model="mockllm/model", judge_version="mock",
                rubric_id="faithfulness", rubric_version="1", params={"max_tokens": 256})
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
    assert c.get("k" * 64) is None
    c.put("k" * 64, {"label": "SUPPORTED", "raw": "VERDICT: SUPPORTED"})
    assert c.get("k" * 64) == {"label": "SUPPORTED", "raw": "VERDICT: SUPPORTED"}
    assert (tmp_path / "judge" / ("k" * 64 + ".json")).exists()


def test_cache_rejects_bad_key(tmp_path: Path):
    import pytest
    c = JudgeCache(tmp_path)
    with pytest.raises(ValueError):
        c.get("../escape")


def test_model_version_for_mock_and_hosted():
    assert model_version("mockllm/model") == "mock"
    assert model_version("anthropic/claude-haiku-4-5-20251001") == "anthropic/claude-haiku-4-5-20251001"


def test_model_version_reads_hf_ref(tmp_path: Path, monkeypatch):
    hub = tmp_path / "hub" / "models--Org--Name" / "refs"
    hub.mkdir(parents=True)
    (hub / "main").write_text("abc123\n", encoding="utf-8")
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hub"))
    assert model_version("hf/Org/Name") == "abc123"


def test_model_version_hf_missing_ref_raises(tmp_path: Path, monkeypatch):
    import pytest
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "empty"))
    with pytest.raises(FileNotFoundError):
        model_version("hf/Org/Missing")
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_judge_cache.py -q`
Expected: ImportError on `eval_platform.graders.judge_cache`.

- [ ] **Step 3: Implement the cache**

`eval_platform/graders/judge_cache.py`:
```python
"""Content-addressed cache for judge verdicts (design spec 4.5).

Key = SHA-256 over (case id, output text, judge model id and version,
rubric id and version, grader parameters). A hit returns the stored
verdict with zero model calls, so a rerun is byte-identical and free.
The cache root is `.cache/judge/` locally (gitignored).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

_KEY = re.compile(r"^[0-9a-f]{64}$")


def cache_key(
    *,
    case_id: str,
    output: str,
    judge_model: str,
    judge_version: str,
    rubric_id: str,
    rubric_version: str,
    params: dict[str, Any],
) -> str:
    """SHA-256 hex of the canonical JSON of every input. `params` is
    serialized with sorted keys, so insertion order never changes the key."""
    payload = {
        "case_id": case_id,
        "output": output,
        "judge_model": judge_model,
        "judge_version": judge_version,
        "rubric_id": rubric_id,
        "rubric_version": rubric_version,
        "params": params,
    }
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def model_version(model_id: str) -> str:
    """The version string that goes into a cache key for `model_id`.

    `hf/<repo>` resolves to the snapshot hash Hugging Face recorded in
    `<HF_HUB_CACHE>/models--<org>--<name>/refs/main` (default cache
    `~/.cache/huggingface/hub`); raises FileNotFoundError when the weights
    have not been downloaded, since an unversioned judge must not be cached.
    `mockllm/...` is "mock". Any other id is returned unchanged: hosted ids
    carry their release date.
    """
    if model_id.startswith("mockllm/"):
        return "mock"
    if model_id.startswith("hf/"):
        repo = model_id[len("hf/") :].replace("/", "--")
        root = Path(os.environ.get("HF_HUB_CACHE") or Path.home() / ".cache" / "huggingface" / "hub")
        ref = root / f"models--{repo}" / "refs" / "main"
        if not ref.exists():
            raise FileNotFoundError(f"no local snapshot for {model_id}: {ref} is missing")
        return ref.read_text(encoding="utf-8").strip()
    return model_id


class JudgeCache:
    """One JSON file per key under `root`. Keys are validated against the
    64-hex-character shape before they touch the filesystem, so a caller
    cannot turn a key into a path."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, key: str) -> Path:
        if not _KEY.match(key):
            raise ValueError(f"cache key is not a sha256 hex digest: {key!r}")
        return self.root / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        p = self._path(key)
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def put(self, key: str, payload: dict[str, Any]) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
```

- [ ] **Step 4: Run the cache tests**

Run: `.venv/Scripts/python -m pytest tests/test_judge_cache.py -q`
Expected: 6 passed.

- [ ] **Step 5: Write the failing judge tests**

`tests/test_judge.py`:
```python
from pathlib import Path

import pytest
from inspect_ai.model import get_model

from eval_platform.graders.judge import RUBRICS, JudgeGrader, parse_verdict
from eval_platform.graders.judge_cache import JudgeCache
from eval_platform.types import Case, Expect, Step, Trajectory


def _traj(answer: str, context: str = "Paris is the capital of France.") -> Trajectory:
    return Trajectory(
        target="t", goal="capital of France?", status="completed", answer=answer,
        steps=(Step("tool", "search", {"q": "France"}, context),),
        side_effects=(), cost_usd=0.0, wall_ms=1.0,
    )


def _case() -> Case:
    return Case(name="c1", goal="capital of France?", expect=Expect(answer_contains="Paris"))


def _grader(tmp_path: Path, outputs: list[str]) -> JudgeGrader:
    handle = get_model("mockllm/model", custom_outputs=outputs)
    return JudgeGrader(model="mockllm/model", rubric=RUBRICS["faithfulness"],
                       cache=JudgeCache(tmp_path), model_handle=handle)


@pytest.mark.parametrize(
    "text,label",
    [
        ("Reasoning...\nVERDICT: SUPPORTED", "SUPPORTED"),
        ("verdict: unsupported", "UNSUPPORTED"),
        ("VERDICT: UNKNOWN", "UNKNOWN"),
        ("I think it is fine.", "UNKNOWN"),
        ("VERDICT: SUPPORTED\nVERDICT: UNSUPPORTED", "UNSUPPORTED"),  # last line wins
    ],
)
def test_parse_verdict(text, label):
    assert parse_verdict(text, RUBRICS["faithfulness"].labels) == label


def test_judge_pass_fail_unknown(tmp_path: Path):
    g = _grader(tmp_path, ["VERDICT: SUPPORTED", "VERDICT: UNSUPPORTED", "no idea"])
    r1 = g.judge(_case(), _traj("Paris."))
    assert (r1.verdict, r1.label, r1.cached) == ("pass", "SUPPORTED", False)
    r2 = g.judge(_case(), _traj("Berlin."))
    assert (r2.verdict, r2.label) == ("fail", "UNSUPPORTED")
    r3 = g.judge(_case(), _traj("Rome."))
    assert (r3.verdict, r3.label) == ("unknown", "UNKNOWN")


def test_judge_cache_hit_makes_no_call(tmp_path: Path):
    g = _grader(tmp_path, ["VERDICT: SUPPORTED"])  # exactly one scripted output
    first = g.judge(_case(), _traj("Paris."))
    second = g.judge(_case(), _traj("Paris."))  # a second call would exhaust mockllm
    assert first.cached is False and second.cached is True
    assert second.label == "SUPPORTED"


def test_grade_shape(tmp_path: Path):
    g = _grader(tmp_path, ["VERDICT: UNKNOWN"])
    grade = g.grade(_case(), _traj("Paris."))
    assert grade.dimension == "judge:faithfulness:mockllm/model"
    assert grade.value == 0.5 and grade.passed is False
    assert g.id == "faithfulness@1:mockllm/model" and g.version == "mock"


def test_judge_records_span(tmp_path: Path, spans):
    g = _grader(tmp_path, ["VERDICT: SUPPORTED"])
    g.judge(_case(), _traj("Paris."))
    g.judge(_case(), _traj("Paris."))
    names = [s.name for s in spans.get_finished_spans()]
    assert names.count("eval.grader") == 2
    hits = [s.attributes["eval.cache_hit"] for s in spans.get_finished_spans() if s.name == "eval.grader"]
    assert hits == [False, True]
    s = spans.get_finished_spans()[0]
    assert s.attributes["eval.judge"] == "faithfulness@1:mockllm/model"


def test_faithfulness_prompt_carries_context_and_answer():
    text = RUBRICS["faithfulness"].user_prompt(_case(), _traj("Paris.", context="CTX-123"))
    assert "CTX-123" in text and "Paris." in text


def test_correctness_prompt_uses_reference():
    case = Case(name="c", goal="q?", expect=Expect(answer_contains="42"))
    text = RUBRICS["correctness"].user_prompt(case, _traj("It is 42."))
    assert "42" in text and "It is 42." in text


def test_empty_answer_is_unknown_without_a_call(tmp_path: Path):
    g = _grader(tmp_path, [])  # no scripted outputs: any call would fail
    r = g.judge(_case(), _traj(""))
    assert r.verdict == "unknown" and r.cached is False
```

- [ ] **Step 6: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_judge.py -q`
Expected: ImportError on `eval_platform.graders.judge`.

- [ ] **Step 7: Implement the protocol, rubrics, and grader**

`eval_platform/graders/base.py`:
```python
"""The grader contract every grader kind satisfies (design spec 4.5)."""

from __future__ import annotations

from typing import Literal, Protocol

from eval_platform.types import Case, Grade, Trajectory

GraderKind = Literal["deterministic", "semantic", "judge"]


class Grader(Protocol):
    """A grader turns one (case, trajectory) pair into one Grade.

    `kind` says what the grade costs and how much to trust it: a
    deterministic grader never calls a model; a semantic grader runs a
    local classifier or embedder; a judge grader calls a pinned model
    with a rubric. `version` changes whenever the grader's output could
    change for the same input (a rubric edit, a new model snapshot), and
    is part of every judge cache key.
    """

    id: str
    kind: GraderKind
    version: str

    def grade(self, case: Case, trajectory: Trajectory) -> Grade: ...
```

`eval_platform/graders/rubrics/__init__.py`:
```python
"""Judge rubrics: one per dimension, each with an id, a version, the
judge's instructions, and how a (case, trajectory) pair becomes the
user prompt. Edit a rubric's text and bump its version in the same
change; the version is part of the judge cache key."""

from __future__ import annotations

from .base import Rubric
from .correctness import CORRECTNESS
from .faithfulness import FAITHFULNESS

RUBRICS: dict[str, Rubric] = {FAITHFULNESS.id: FAITHFULNESS, CORRECTNESS.id: CORRECTNESS}

__all__ = ["CORRECTNESS", "FAITHFULNESS", "RUBRICS", "Rubric"]
```

`eval_platform/graders/rubrics/base.py`:
```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from eval_platform.types import Case, Trajectory

# Character cap on the context block handed to a judge. Long tool outputs
# are truncated from the end with a marker, so a judge never sees an
# unbounded prompt and a 3B model's context window is respected.
CONTEXT_CHARS = 6000


def context_from(trajectory: Trajectory) -> str:
    """Every tool step's output, in order, joined by blank lines and capped
    at CONTEXT_CHARS. Empty string when the run made no tool call."""
    parts = [str(s.output) for s in trajectory.steps if s.kind == "tool" and s.output is not None]
    text = "\n\n".join(parts)
    if len(text) > CONTEXT_CHARS:
        text = text[:CONTEXT_CHARS] + "\n[truncated]"
    return text


@dataclass(frozen=True)
class Rubric:
    id: str
    version: str
    system: str
    labels: tuple[str, ...]
    passing: str
    failing: str
    build_user_prompt: Callable[[Case, Trajectory], str]

    def user_prompt(self, case: Case, trajectory: Trajectory) -> str:
        return self.build_user_prompt(case, trajectory)
```

`eval_platform/graders/rubrics/faithfulness.py`:
```python
from __future__ import annotations

from eval_platform.types import Case, Trajectory

from .base import Rubric, context_from

_SYSTEM = """You are grading whether an answer is supported by the context it was given.
Read the context, then the answer. Every factual claim in the answer must be stated in or
follow directly from the context. Ignore whether the answer is helpful or complete.
Reply with your reasoning in at most three sentences, then a final line in exactly this form:
VERDICT: SUPPORTED
or
VERDICT: UNSUPPORTED
Use VERDICT: UNKNOWN only when the context is empty or the answer makes no factual claim."""


def _prompt(case: Case, trajectory: Trajectory) -> str:
    return (
        f"Question:\n{case.goal}\n\nContext:\n{context_from(trajectory) or '[no context]'}"
        f"\n\nAnswer:\n{trajectory.answer or ''}"
    )


FAITHFULNESS = Rubric(
    id="faithfulness",
    version="1",
    system=_SYSTEM,
    labels=("SUPPORTED", "UNSUPPORTED", "UNKNOWN"),
    passing="SUPPORTED",
    failing="UNSUPPORTED",
    build_user_prompt=_prompt,
)
```

`eval_platform/graders/rubrics/correctness.py`:
```python
from __future__ import annotations

from eval_platform.types import Case, Trajectory

from .base import Rubric

_SYSTEM = """You are grading a short answer against a reference answer.
CORRECT means the answer states the same fact as the reference, with no contradicting claim.
INCORRECT means the answer states a fact that contradicts the reference.
NOT_ATTEMPTED means the answer declines, hedges without committing, or does not address the question.
Reply with your reasoning in at most three sentences, then a final line in exactly this form:
VERDICT: CORRECT
or
VERDICT: INCORRECT
or
VERDICT: NOT_ATTEMPTED"""


def _prompt(case: Case, trajectory: Trajectory) -> str:
    reference = case.expect.answer_contains or "[no reference]"
    return (
        f"Question:\n{case.goal}\n\nReference answer:\n{reference}"
        f"\n\nAnswer:\n{trajectory.answer or ''}"
    )


CORRECTNESS = Rubric(
    id="correctness",
    version="1",
    system=_SYSTEM,
    labels=("CORRECT", "INCORRECT", "NOT_ATTEMPTED"),
    passing="CORRECT",
    failing="INCORRECT",
    build_user_prompt=_prompt,
)
```

`eval_platform/graders/judge.py`:
```python
"""Judge graders: a pinned model, a rubric, an explicit unknown outcome,
and a content-addressed cache (design spec 4.5).

A judge never runs inside `run_suite`; it is applied by `evalplat judge`
as a second pass over a stored run, so the answering model and the judge
model are never resident together.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any, Literal

from inspect_ai.model import ChatMessageSystem, ChatMessageUser, GenerateConfig, Model, get_model

from eval_platform.graders.judge_cache import JudgeCache, cache_key, model_version
from eval_platform.graders.rubrics import RUBRICS, Rubric
from eval_platform.telemetry import set_attributes, span
from eval_platform.types import Case, Grade, Trajectory

Verdict = Literal["pass", "fail", "unknown"]
_VERDICT_LINE = re.compile(r"verdict\s*:\s*([A-Z_]+)", re.IGNORECASE)


@dataclass(frozen=True)
class JudgeResult:
    verdict: Verdict
    label: str
    raw: str
    cached: bool


def parse_verdict(text: str, labels: tuple[str, ...]) -> str:
    """The label on the LAST `VERDICT: <label>` line in `text`, upper-cased,
    when it is one of `labels`; otherwise the rubric's last label (the
    unknown one). A judge that writes two verdict lines is taken at its
    final word; a judge that writes none is unknown, never a pass."""
    found = [m.group(1).upper() for m in _VERDICT_LINE.finditer(text)]
    if found and found[-1] in labels:
        return found[-1]
    return labels[-1]


class JudgeGrader:
    """One rubric on one model. `model_handle` lets tests inject an Inspect
    `mockllm/model` with scripted outputs; production code passes `model`
    and the handle is created lazily on the first uncached call, so a run
    that hits the cache for every case never loads the judge weights."""

    kind = "judge"

    def __init__(
        self,
        *,
        model: str,
        rubric: Rubric,
        cache: JudgeCache,
        model_args: dict[str, Any] | None = None,
        max_tokens: int = 256,
        model_handle: Model | None = None,
    ) -> None:
        self.model = model
        self.rubric = rubric
        self.cache = cache
        self.model_args = dict(model_args or {})
        self.max_tokens = max_tokens
        self._handle = model_handle
        self.id = f"{rubric.id}@{rubric.version}:{model}"
        self.version = model_version(model)

    def _params(self) -> dict[str, Any]:
        return {"max_tokens": self.max_tokens, "model_args": self.model_args}

    def _handle_or_load(self) -> Model:
        if self._handle is None:
            self._handle = get_model(self.model, **self.model_args)
        return self._handle

    async def _call(self, user: str) -> str:
        out = await self._handle_or_load().generate(
            [ChatMessageSystem(content=self.rubric.system), ChatMessageUser(content=user)],
            config=GenerateConfig(max_tokens=self.max_tokens),
        )
        return out.completion

    def _verdict(self, label: str) -> Verdict:
        if label == self.rubric.passing:
            return "pass"
        if label == self.rubric.failing:
            return "fail"
        return "unknown"

    def judge(self, case: Case, trajectory: Trajectory) -> JudgeResult:
        """Cached verdict for this case's answer. An empty answer is unknown
        with no model call and no cache write. Runs inside an `eval.grader`
        span carrying `eval.judge`, `eval.case`, and `eval.cache_hit`."""
        answer = trajectory.answer or ""
        with span("eval.grader", **{"eval.judge": self.id, "eval.case": case.name}) as s:
            if not answer.strip():
                set_attributes(s, **{"eval.cache_hit": False, "eval.label": self.rubric.labels[-1]})
                return JudgeResult("unknown", self.rubric.labels[-1], "", False)
            user = self.rubric.user_prompt(case, trajectory)
            key = cache_key(
                case_id=case.name,
                output=user,
                judge_model=self.model,
                judge_version=self.version,
                rubric_id=self.rubric.id,
                rubric_version=self.rubric.version,
                params=self._params(),
            )
            hit = self.cache.get(key)
            if hit is not None:
                set_attributes(s, **{"eval.cache_hit": True, "eval.label": hit["label"]})
                return JudgeResult(self._verdict(hit["label"]), hit["label"], hit["raw"], True)
            raw = asyncio.run(self._call(user))
            label = parse_verdict(raw, self.rubric.labels)
            self.cache.put(key, {"label": label, "raw": raw, "judge": self.id, "version": self.version})
            set_attributes(s, **{"eval.cache_hit": False, "eval.label": label})
            return JudgeResult(self._verdict(label), label, raw, False)

    def grade(self, case: Case, trajectory: Trajectory) -> Grade:
        r = self.judge(case, trajectory)
        value = {"pass": 1.0, "fail": 0.0, "unknown": 0.5}[r.verdict]
        return Grade(
            dimension=f"judge:{self.rubric.id}:{self.model}",
            value=value,
            passed=r.verdict == "pass",
            explanation=f"{r.label} ({'cached' if r.cached else 'called'}): {r.raw[:200]}",
        )


__all__ = ["RUBRICS", "JudgeGrader", "JudgeResult", "Verdict", "parse_verdict"]
```

Note on `asyncio.run`: `judge()` is called from synchronous CLI code. If a caller is already inside an event loop (Inspect's own solver), `asyncio.run` raises `RuntimeError`; that is acceptable here because the judge pass is always a top-level command. Document this in the docstring.

Note on `cache_key(output=user)`: the key covers the full user prompt (question, context, answer), so a changed context with the same answer is a different key. The spec's "output text" is satisfied because the prompt contains it.

Update `eval_platform/graders/__init__.py` to export `Grader`, `JudgeGrader`, `RUBRICS` alongside the existing names, and change its docstring to "Graders: deterministic (model-free), semantic (local classifier), and judge (a pinned model with a rubric)."

- [ ] **Step 8: Run the judge tests and the full gate set**

Run: `.venv/Scripts/python -m pytest tests/test_judge.py tests/test_judge_cache.py -q` then the Global Constraints gate commands.
Expected: all pass; pyright 0 errors (the `mockllm` `custom_outputs` kwarg is typed `Any` in Inspect; if pyright complains about `get_model` kwargs in the test, annotate the handle as `Model`).

- [ ] **Step 9: Commit**

```bash
git add eval_platform/graders tests/test_judge.py tests/test_judge_cache.py
git commit -m "Add judge graders with rubrics, an explicit unknown outcome, and a content-addressed cache"
```

---

### Task 2: HHEM semantic grader

**Files:**
- Create: `eval_platform/graders/hhem.py`, `tests/test_hhem.py`
- Modify: `pyproject.toml` (`local` extra adds `safetensors>=0.4`; new `gpu` marker), `eval_platform/graders/__init__.py`

**Interfaces:**
- Produces:
  ```python
  HHEM_REPO = "vectara/hallucination_evaluation_model"
  HHEM_SNAPSHOT = "8e4a2e6e96c708cc76c2344f7e4757df2515292c"
  HHEM_FOUNDATION = "google/flan-t5-base"
  HHEM_PROMPT = "<pad> Determine if the hypothesis is true given the premise?\n\nPremise: {text1}\n\nHypothesis: {text2}"

  def split_sentences(text: str, *, min_chars: int = 15) -> list[str]
  class Scorer(Protocol):
      def score(self, pairs: Sequence[tuple[str, str]]) -> list[float]: ...
  class HHEMScorer:            # implements Scorer; loads weights on first use; CPU
      version: str             # HHEM_SNAPSHOT
      def score(self, pairs) -> list[float]
  def unsupported_share(context: str, answer: str, scorer: Scorer, *, threshold: float = 0.5,
                        max_sentences: int = 40) -> tuple[float, list[tuple[str, float]]]
  class HHEMGrader:            # kind = "semantic"; id "hhem@2.1-open"; version HHEM_SNAPSHOT
      def __init__(self, scorer: Scorer | None = None, threshold: float = 0.5) -> None
      def grade(self, case, trajectory) -> Grade
          # dimension "unsupported_claims"; value = 1 - share; passed = share == 0.0;
          # explanation lists each unsupported sentence's first 60 chars and score
  ```
  `context` for a trajectory is `context_from(trajectory)` (Task 1's rubric base); an empty context makes every sentence unsupported (share 1.0) without calling the scorer, because an answer with nothing retrieved cannot be grounded.

- [ ] **Step 1: Write the failing tests**

`tests/test_hhem.py`:
```python
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
    share, detail = unsupported_share(ctx, "Revenue rose 5% in 2025. Margins doubled in 2025.", StubScorer())
    assert share == 0.5
    assert [round(s, 1) for _, s in detail] == [0.9, 0.1]


def test_unsupported_share_empty_context_is_all_unsupported():
    s = StubScorer()
    share, detail = unsupported_share("", "A claim that is long enough.", s)
    assert share == 1.0 and s.calls == 0 and detail[0][1] == 0.0


def test_unsupported_share_no_sentences_is_zero():
    share, detail = unsupported_share("ctx", "", StubScorer())
    assert share == 0.0 and detail == []


def test_grader_grade_shape():
    t = Trajectory(
        target="t", goal="g", status="completed",
        answer="Revenue rose 5% in 2025. Margins doubled in 2025.",
        steps=(Step("tool", "search", {}, "Revenue rose 5% in 2025."),),
        side_effects=(), cost_usd=0.0, wall_ms=0.0,
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
        ("A person on a horse jumps over a broken down airplane.", "A person is outdoors, on a horse."),
        ("A boy is jumping on skateboard in the middle of a red bridge.", "The boy skates down the sidewalk on a red bridge"),
        ("A man with blond-hair, and a brown shirt drinking out of a public water fountain.", "A blond man wearing a brown shirt is reading a book."),
        ("Mark Wahlberg was a fan of Manny.", "Manny was a fan of Mark Wahlberg."),
    ]
    # Published on the model card, read 2026-09-11:
    # https://huggingface.co/vectara/hallucination_evaluation_model
    expected = [0.0111, 0.6474, 0.1290, 0.8969, 0.1846, 0.0050, 0.0543]
    got = HHEMScorer().score(pairs)
    assert [round(x, 4) for x in got] == expected
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_hhem.py -q -m "not gpu"`
Expected: ImportError.

- [ ] **Step 3: Implement**

`eval_platform/graders/hhem.py`:
```python
"""HHEM-2.1-Open as a semantic grader (design spec 4.4, groundedness row).

The published checkpoint ships a `trust_remote_code` wrapper written for
transformers 4.39 that no longer loads under transformers 5 (verified
2026-09-11: `AttributeError: 'HHEMv2ForSequenceClassification' object has
no attribute 'all_tied_weights_keys'`). The wrapper is small: a
`T5ForTokenClassification` over `google/flan-t5-base` with two labels, a
fixed prompt, the logits of the first token, softmax, and the probability
of class 1 ("consistent"). This module reproduces that directly: it reads
the checkpoint's safetensors, strips the wrapper's `t5.` prefix from every
key, and loads them into a plain `T5ForTokenClassification`. On the model
card's seven example pairs the scores match the card's published tensor
to four decimals (see tests/test_hhem.py). The snapshot is pinned so a
checkpoint update cannot change scores without a version bump here.

Scores are in [0, 1]: 1 means the hypothesis is fully supported by the
premise, 0 means not evidenced at all (model card wording). Runs on CPU.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Protocol

from eval_platform.graders.rubrics.base import context_from
from eval_platform.types import Case, Grade, Trajectory

HHEM_REPO = "vectara/hallucination_evaluation_model"
HHEM_SNAPSHOT = "8e4a2e6e96c708cc76c2344f7e4757df2515292c"
HHEM_FOUNDATION = "google/flan-t5-base"
HHEM_PROMPT = (
    "<pad> Determine if the hypothesis is true given the premise?\n\n"
    "Premise: {text1}\n\nHypothesis: {text2}"
)
# FLAN-T5 was trained at 512 tokens; the premise is capped in characters so a
# long retrieved context cannot push the hypothesis out of the window.
PREMISE_CHARS = 2000
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


class Scorer(Protocol):
    version: str

    def score(self, pairs: Sequence[tuple[str, str]]) -> list[float]: ...


def split_sentences(text: str, *, min_chars: int = 15) -> list[str]:
    """Split on sentence-ending punctuation followed by whitespace and an
    upper-case letter, digit, or quote; drop pieces shorter than
    `min_chars`, which are headings, list markers, and fragments a
    classifier cannot judge. Order is preserved."""
    parts = [p.strip() for p in _SENTENCE_END.split(text.strip()) if p.strip()]
    return [p for p in parts if len(p) >= min_chars]


class HHEMScorer:
    """Lazy-loading CPU scorer. The weights (about 440 MB) come from the
    Hugging Face cache; the first call downloads them if absent."""

    version = HHEM_SNAPSHOT

    def __init__(self) -> None:
        self._model: Any = None
        self._tok: Any = None

    def _load(self) -> None:
        import torch
        from huggingface_hub import hf_hub_download
        from safetensors.torch import load_file
        from transformers import AutoConfig, AutoTokenizer, T5ForTokenClassification

        weights = hf_hub_download(HHEM_REPO, "model.safetensors", revision=HHEM_SNAPSHOT)
        model = T5ForTokenClassification(AutoConfig.from_pretrained(HHEM_FOUNDATION, num_labels=2))
        state = load_file(weights)
        renamed = {k[len("t5.") :]: v for k, v in state.items() if k.startswith("t5.")}
        missing = model.load_state_dict(renamed, strict=False)
        # The encoder's embedding is tied to `shared` in T5, so it is the
        # one key the checkpoint does not carry; anything else missing means
        # the checkpoint changed shape and the pin above must be revisited.
        unexpected = set(missing.missing_keys) - {"transformer.encoder.embed_tokens.weight"}
        if unexpected or missing.unexpected_keys:
            raise RuntimeError(
                f"HHEM checkpoint does not fit T5ForTokenClassification: "
                f"missing={sorted(unexpected)} unexpected={missing.unexpected_keys}"
            )
        model.eval()
        self._model = model
        self._tok = AutoTokenizer.from_pretrained(HHEM_FOUNDATION)
        self._torch = torch

    def score(self, pairs: Sequence[tuple[str, str]]) -> list[float]:
        if not pairs:
            return []
        if self._model is None:
            self._load()
        texts = [HHEM_PROMPT.format(text1=p[:PREMISE_CHARS], text2=h) for p, h in pairs]
        inputs = self._tok(texts, return_tensors="pt", padding=True, truncation=True, max_length=1024)
        with self._torch.no_grad():
            logits = self._model(**inputs).logits[:, 0, :]
        return [float(x) for x in self._torch.softmax(logits, dim=-1)[:, 1].tolist()]


def unsupported_share(
    context: str,
    answer: str,
    scorer: Scorer,
    *,
    threshold: float = 0.5,
    max_sentences: int = 40,
) -> tuple[float, list[tuple[str, float]]]:
    """Share of the answer's sentences (first `max_sentences`) whose HHEM
    score against `context` is below `threshold`, plus every sentence with
    its score. An empty context makes every sentence unsupported (score
    0.0) with no scorer call; an answer with no sentence yields 0.0."""
    sentences = split_sentences(answer)[:max_sentences]
    if not sentences:
        return 0.0, []
    if not context.strip():
        detail = [(s, 0.0) for s in sentences]
        return 1.0, detail
    scores = scorer.score([(context, s) for s in sentences])
    detail = list(zip(sentences, scores, strict=True))
    unsupported = sum(1 for _, sc in detail if sc < threshold)
    return unsupported / len(sentences), detail


class HHEMGrader:
    """The `unsupported_claims` dimension: value is 1 minus the unsupported
    share, so 1.0 is a fully grounded answer; passed only at share 0.0."""

    kind = "semantic"
    id = "hhem@2.1-open"
    version = HHEM_SNAPSHOT

    def __init__(self, scorer: Scorer | None = None, threshold: float = 0.5) -> None:
        self.scorer: Scorer = scorer or HHEMScorer()
        self.threshold = threshold

    def grade(self, case: Case, trajectory: Trajectory) -> Grade:
        del case
        share, detail = unsupported_share(
            context_from(trajectory), trajectory.answer or "", self.scorer, threshold=self.threshold
        )
        bad = [f"{s[:60]!r}={sc:.2f}" for s, sc in detail if sc < self.threshold]
        why = f"{len(bad)}/{len(detail)} sentences unsupported" + (f": {'; '.join(bad)}" if bad else "")
        return Grade("unsupported_claims", 1.0 - share, share == 0.0, why)
```

`pyproject.toml`: `local = ["torch>=2.6", "transformers>=4.45", "accelerate>=1.0", "safetensors>=0.4", "huggingface_hub>=0.25"]`; markers add `"gpu: loads a real model on this machine's GPU or CPU; never in CI"`. Export `HHEMGrader` from `graders/__init__.py`.

- [ ] **Step 4: Run tests, including the real one once**

Run: `.venv/Scripts/python -m pytest tests/test_hhem.py -q` (all markers) once locally.
Expected: 6 passed, the model-card test included. Then the Global Constraints gates.

- [ ] **Step 5: Commit**

```bash
git add eval_platform/graders/hhem.py eval_platform/graders/__init__.py tests/test_hhem.py pyproject.toml
git commit -m "Add the HHEM semantic grader through a plain T5 loader that matches the model card"
```

---

### Task 3: Calibration set and `evalplat calibrate`

**Files:**
- Create: `scripts/build_calibration_set.py`, `calibration/README.md`, `calibration/faithfulness/LICENSE-RAGTruth.txt`, `calibration/faithfulness/ragtruth-120.jsonl` (generated, committed), `eval_platform/calibration.py`, `tests/test_calibration.py`
- Modify: `eval_platform/cli.py` (`calibrate` subcommand), `.gitignore` (nothing), `eval_platform/results.py` (no change; the report is written by `calibration.write_report`)

**Interfaces:**
- Produces:
  ```python
  class CalibrationItem(BaseModel):
      id: str
      context: str
      question: str            # "" for summarization items
      response: str
      label: Literal["supported", "unsupported"]
      provenance: dict[str, str]   # dataset, split, source_id, response_id, task_type, license
  def load_items(directory: Path) -> list[CalibrationItem]      # every *.jsonl, sorted, ids unique
  def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float   # 0.0 when both constant
  def agreement(a: Sequence[str], b: Sequence[str]) -> float
  @dataclass(frozen=True)
  class JudgeCalibration:
      judge: str; version: str; items: int; unknown: int
      kappa: float; accuracy: float; tp: int; fp: int; tn: int; fn: int
  @dataclass(frozen=True)
  class CalibrationReport:
      started_at: str; finished_at: str; items: int
      judges: tuple[JudgeCalibration, ...]
      swap_agreement: float | None      # over items where both judges gave a non-unknown label
      swap_pair: tuple[str, str] | None
      kappa_floor: float; min_swap_agreement: float
      def calibrated(self, judge: str) -> tuple[bool, str]   # (ok, reason)
      def to_dict(self) -> dict[str, Any]
  def calibrate(items, judges: Sequence[JudgeGrader], *, kappa_floor=0.70, min_swap_agreement=0.90,
                hhem: HHEMGrader | None = None) -> CalibrationReport
      # each item becomes Case(name=item.id, goal=item.question or "Summarize the document.",
      #   expect=Expect()) and Trajectory(answer=item.response, steps=(Step("tool","context",{},item.context),))
      # judge label -> "supported"/"unsupported"/"unknown"; HHEM (when given) is a judge named
      #   "hhem@2.1-open" with label supported when unsupported_share == 0.0
  def write_report(report, results_dir: Path) -> Path   # results/calibration/<ts>.json + latest.json
  ```

- [ ] **Step 1: Build script**

`scripts/build_calibration_set.py` (run once; its output is committed):
```python
"""Sample a balanced faithfulness calibration set from RAGTruth's test split.

RAGTruth (https://github.com/ParticleMedia/RAGTruth, MIT) carries human
span annotations on model responses to retrieval prompts. A response with
no annotated span is `supported`; one with at least one span is
`unsupported`. This script draws 30 of each label from the QA task type
and 30 of each from Summary (120 items), seeded, skipping responses whose
`quality` is not "good" (truncated or refusal), and writes
calibration/faithfulness/ragtruth-120.jsonl with full provenance.

Usage: python scripts/build_calibration_set.py --response response.jsonl --source source_info.jsonl
"""

from __future__ import annotations

import argparse
import ast
import json
import random
from pathlib import Path

OUT = Path("calibration/faithfulness/ragtruth-120.jsonl")
SEED = 20260911
PER_CELL = 30


def _context(source: dict) -> tuple[str, str]:
    info = source["source_info"]
    if source["task_type"] == "QA":
        data = ast.literal_eval(info) if isinstance(info, str) else info
        return str(data["passages"]), str(data["question"])
    return str(info), ""


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--response", required=True)
    p.add_argument("--source", required=True)
    a = p.parse_args()
    sources = {s["source_id"]: s for s in map(json.loads, open(a.source, encoding="utf-8"))}
    rows = [json.loads(line) for line in open(a.response, encoding="utf-8")]
    rng = random.Random(SEED)
    out = []
    for task in ("QA", "Summary"):
        for label, want_spans in (("supported", False), ("unsupported", True)):
            pool = [
                r for r in rows
                if r["split"] == "test" and r["quality"] == "good"
                and sources[r["source_id"]]["task_type"] == task and bool(r["labels"]) == want_spans
            ]
            pool.sort(key=lambda r: r["id"])
            for r in rng.sample(pool, PER_CELL):
                s = sources[r["source_id"]]
                context, question = _context(s)
                out.append({
                    "id": f"ragtruth-{r['id']}",
                    "context": context,
                    "question": question,
                    "response": r["response"],
                    "label": label,
                    "provenance": {
                        "dataset": "RAGTruth", "split": "test", "source_id": str(r["source_id"]),
                        "response_id": str(r["id"]), "task_type": task, "model": r["model"],
                        "license": "MIT", "url": "https://github.com/ParticleMedia/RAGTruth",
                    },
                })
    out.sort(key=lambda x: x["id"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        for item in out:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"wrote {len(out)} items to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Download the two files first (about 37 MB, not committed):
```bash
mkdir -p .cache/ragtruth
curl -sL -o .cache/ragtruth/response.jsonl https://raw.githubusercontent.com/ParticleMedia/RAGTruth/main/dataset/response.jsonl
curl -sL -o .cache/ragtruth/source_info.jsonl https://raw.githubusercontent.com/ParticleMedia/RAGTruth/main/dataset/source_info.jsonl
.venv/Scripts/python scripts/build_calibration_set.py --response .cache/ragtruth/response.jsonl --source .cache/ragtruth/source_info.jsonl
```
Copy the RAGTruth LICENSE text verbatim from https://raw.githubusercontent.com/ParticleMedia/RAGTruth/main/LICENSE into `calibration/faithfulness/LICENSE-RAGTruth.txt`. `calibration/README.md` says what the set is, how it was sampled (the command above, the seed), that labels are RAGTruth's human span annotations reduced to a binary per response, that QA contexts are the MS MARCO passages RAGTruth bundles, and that any `*.jsonl` file dropped into `calibration/faithfulness/` is read by `evalplat calibrate` (so hand-labeled items can be added).

- [ ] **Step 2: Write the failing tests**

`tests/test_calibration.py`:
```python
import json
from pathlib import Path

import pytest
from inspect_ai.model import get_model

from eval_platform.calibration import (
    CalibrationItem,
    agreement,
    calibrate,
    cohen_kappa,
    load_items,
    write_report,
)
from eval_platform.graders.judge import RUBRICS, JudgeGrader
from eval_platform.graders.judge_cache import JudgeCache

ROOT = Path(__file__).resolve().parents[1]


def test_kappa_known_values():
    a = ["s", "s", "u", "u", "s", "u", "s", "u"]
    assert cohen_kappa(a, a) == 1.0
    assert cohen_kappa(a, ["u" if x == "s" else "s" for x in a]) == -1.0
    assert cohen_kappa(["s"] * 4, ["s"] * 4) == 0.0  # both constant: undefined, reported as 0.0
    # textbook example: 20 items, observed agreement 0.7, expected 0.5 -> kappa 0.4
    a = ["s"] * 10 + ["u"] * 10
    b = ["s"] * 7 + ["u"] * 3 + ["s"] * 3 + ["u"] * 7
    assert round(cohen_kappa(a, b), 4) == 0.4


def test_agreement_and_length_check():
    assert agreement(["s", "u"], ["s", "s"]) == 0.5
    with pytest.raises(ValueError):
        agreement(["s"], [])


def test_committed_set_shape_and_balance():
    items = load_items(ROOT / "calibration" / "faithfulness")
    assert len(items) >= 50
    labels = [i.label for i in items]
    assert abs(labels.count("supported") - labels.count("unsupported")) <= 2
    assert len({i.id for i in items}) == len(items)
    assert all(i.provenance["license"] == "MIT" for i in items)
    assert all(i.context and i.response for i in items)


def test_load_items_rejects_duplicate_ids(tmp_path: Path):
    row = json.dumps({"id": "x", "context": "c", "question": "", "response": "r",
                      "label": "supported", "provenance": {"dataset": "t", "license": "MIT"}})
    (tmp_path / "a.jsonl").write_text(row + "\n" + row + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_items(tmp_path)


def _items():
    return [
        CalibrationItem(id=f"i{n}", context="Paris is in France.", question="Where is Paris?",
                        response="Paris is in France." if n % 2 == 0 else "Paris is in Spain.",
                        label="supported" if n % 2 == 0 else "unsupported",
                        provenance={"dataset": "t", "license": "MIT"})
        for n in range(8)
    ]


def _judge(tmp_path: Path, name: str, outputs: list[str]) -> JudgeGrader:
    return JudgeGrader(model=f"mockllm/{name}", rubric=RUBRICS["faithfulness"],
                       cache=JudgeCache(tmp_path / name),
                       model_handle=get_model("mockllm/model", custom_outputs=outputs))


def test_calibrate_perfect_and_flipped_judges(tmp_path: Path):
    right = ["VERDICT: SUPPORTED" if n % 2 == 0 else "VERDICT: UNSUPPORTED" for n in range(8)]
    wrong = ["VERDICT: UNSUPPORTED" if n % 2 == 0 else "VERDICT: SUPPORTED" for n in range(8)]
    report = calibrate(_items(), [_judge(tmp_path, "a", right), _judge(tmp_path, "b", wrong)])
    a, b = report.judges
    assert (a.kappa, a.accuracy, a.unknown) == (1.0, 1.0, 0)
    assert b.kappa == -1.0
    assert report.swap_agreement == 0.0
    assert report.calibrated(a.judge) == (False, "swap agreement 0.00 < 0.90")
    assert report.calibrated(b.judge)[0] is False


def test_calibrate_unknowns_are_excluded_from_kappa(tmp_path: Path):
    outs = ["VERDICT: SUPPORTED" if n % 2 == 0 else "VERDICT: UNSUPPORTED" for n in range(8)]
    outs[3] = "no verdict here"
    report = calibrate(_items(), [_judge(tmp_path, "a", outs)])
    (j,) = report.judges
    assert j.unknown == 1 and j.items == 8 and j.kappa == 1.0
    assert report.swap_agreement is None
    assert report.calibrated(j.judge) == (True, "kappa 1.00 >= 0.70; single judge, swap agreement not measured")


def test_write_report_promotes_latest(tmp_path: Path):
    outs = ["VERDICT: SUPPORTED" if n % 2 == 0 else "VERDICT: UNSUPPORTED" for n in range(8)]
    report = calibrate(_items(), [_judge(tmp_path, "a", outs)])
    path = write_report(report, tmp_path / "results")
    latest = json.loads((tmp_path / "results" / "calibration" / "latest.json").read_text())
    assert latest["judges"][0]["kappa"] == 1.0 and path.exists()


def test_cli_calibrate_runs_on_mock(tmp_path: Path, capsys):
    from eval_platform.cli import main
    items_dir = tmp_path / "cal"
    items_dir.mkdir()
    with (items_dir / "t.jsonl").open("w", encoding="utf-8") as f:
        for i in _items():
            f.write(i.model_dump_json() + "\n")
    code = main(["calibrate", "--items", str(items_dir), "--judge", "mockllm/model",
                 "--results", str(tmp_path / "r"), "--cache", str(tmp_path / "c")])
    assert code == 0
    out = capsys.readouterr().out
    assert "kappa" in out and (tmp_path / "r" / "calibration" / "latest.json").exists()
```

The CLI test uses `mockllm/model` with no custom outputs: Inspect's default mock reply is a fixed string, so every verdict parses as UNKNOWN and kappa is 0.0 over zero labeled items; the command must still exit 0 and write the report (an all-unknown judge is a measured result, and the report says so).

- [ ] **Step 3: Implement `eval_platform/calibration.py`**

```python
"""Judge calibration against human labels (design spec 4.5).

A judge may contribute to the gate only after its Cohen's kappa against
the labeled set clears the floor and its verdicts agree with a second
judge model on at least the configured share of items. Everything here
is arithmetic over labels; the judges do the model calls through their
own cache.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from eval_platform.graders.hhem import HHEMGrader
from eval_platform.graders.judge import JudgeGrader
from eval_platform.types import Case, Expect, Step, Trajectory

Label = Literal["supported", "unsupported"]


class CalibrationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    context: str
    question: str = ""
    response: str
    label: Label
    provenance: dict[str, str]


def load_items(directory: Path) -> list[CalibrationItem]:
    """Every `*.jsonl` under `directory`, in sorted file order, one item per
    line. Raises ValueError on a duplicate id or an invalid row (with the
    file and line number), FileNotFoundError when the directory is missing."""
    if not directory.is_dir():
        raise FileNotFoundError(f"calibration directory {directory} does not exist")
    items: list[CalibrationItem] = []
    seen: set[str] = set()
    for path in sorted(directory.glob("*.jsonl")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                item = CalibrationItem.model_validate_json(line)
            except ValueError as e:
                raise ValueError(f"{path.name}:{n}: {e}") from e
            if item.id in seen:
                raise ValueError(f"{path.name}:{n}: duplicate id {item.id!r}")
            seen.add(item.id)
            items.append(item)
    return items


def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float:
    """Cohen's kappa between two label sequences of equal length. Returns
    0.0 when expected agreement is 1.0 (both raters constant), where the
    statistic is undefined. Raises ValueError on a length mismatch or
    empty input."""
    if len(a) != len(b) or not a:
        raise ValueError("kappa needs two equal-length, non-empty label sequences")
    n = len(a)
    observed = sum(1 for x, y in zip(a, b, strict=True) if x == y) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    if expected == 1.0:
        return 0.0
    return (observed - expected) / (1.0 - expected)


def agreement(a: Sequence[str], b: Sequence[str]) -> float:
    """Share of positions where the two sequences carry the same label."""
    if len(a) != len(b) or not a:
        raise ValueError("agreement needs two equal-length, non-empty label sequences")
    return sum(1 for x, y in zip(a, b, strict=True) if x == y) / len(a)


@dataclass(frozen=True)
class JudgeCalibration:
    judge: str
    version: str
    items: int
    unknown: int
    kappa: float
    accuracy: float
    tp: int
    fp: int
    tn: int
    fn: int


@dataclass(frozen=True)
class CalibrationReport:
    started_at: str
    finished_at: str
    items: int
    judges: tuple[JudgeCalibration, ...]
    swap_agreement: float | None
    swap_pair: tuple[str, str] | None
    kappa_floor: float
    min_swap_agreement: float

    def calibrated(self, judge: str) -> tuple[bool, str]:
        """Whether `judge` may block the gate, with the reason either way."""
        match = [j for j in self.judges if j.judge == judge]
        if not match:
            return False, f"judge {judge} not in the calibration report"
        j = match[0]
        if j.kappa < self.kappa_floor:
            return False, f"kappa {j.kappa:.2f} < {self.kappa_floor:.2f}"
        if self.swap_agreement is None:
            return True, (
                f"kappa {j.kappa:.2f} >= {self.kappa_floor:.2f}; "
                "single judge, swap agreement not measured"
            )
        if self.swap_agreement < self.min_swap_agreement:
            return False, f"swap agreement {self.swap_agreement:.2f} < {self.min_swap_agreement:.2f}"
        return True, (
            f"kappa {j.kappa:.2f} >= {self.kappa_floor:.2f}; "
            f"swap agreement {self.swap_agreement:.2f} >= {self.min_swap_agreement:.2f}"
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["calibrated"] = {j.judge: list(self.calibrated(j.judge)) for j in self.judges}
        return d


def _as_case(item: CalibrationItem) -> tuple[Case, Trajectory]:
    case = Case(name=item.id, goal=item.question or "Summarize the document.", expect=Expect())
    traj = Trajectory(
        target="calibration", goal=case.goal, status="completed", answer=item.response,
        steps=(Step("tool", "context", {}, item.context),), side_effects=(),
        cost_usd=0.0, wall_ms=0.0,
    )
    return case, traj


def _labels_for(judge: JudgeGrader | HHEMGrader, items: Sequence[CalibrationItem]) -> list[str]:
    out: list[str] = []
    for item in items:
        case, traj = _as_case(item)
        if isinstance(judge, HHEMGrader):
            g = judge.grade(case, traj)
            out.append("supported" if g.passed else "unsupported")
            continue
        r = judge.judge(case, traj)
        out.append({"pass": "supported", "fail": "unsupported"}.get(r.verdict, "unknown"))
    return out


def _score(judge_id: str, version: str, truth: list[str], got: list[str]) -> JudgeCalibration:
    pairs = [(t, g) for t, g in zip(truth, got, strict=True) if g != "unknown"]
    unknown = len(got) - len(pairs)
    if not pairs:
        return JudgeCalibration(judge_id, version, len(got), unknown, 0.0, 0.0, 0, 0, 0, 0)
    t, g = [p[0] for p in pairs], [p[1] for p in pairs]
    tp = sum(1 for x, y in pairs if x == "unsupported" and y == "unsupported")
    tn = sum(1 for x, y in pairs if x == "supported" and y == "supported")
    fp = sum(1 for x, y in pairs if x == "supported" and y == "unsupported")
    fn = sum(1 for x, y in pairs if x == "unsupported" and y == "supported")
    return JudgeCalibration(judge_id, version, len(got), unknown, cohen_kappa(t, g),
                            agreement(t, g), tp, fp, tn, fn)


def calibrate(
    items: Sequence[CalibrationItem],
    judges: Sequence[JudgeGrader],
    *,
    kappa_floor: float = 0.70,
    min_swap_agreement: float = 0.90,
    hhem: HHEMGrader | None = None,
) -> CalibrationReport:
    """Run every judge (and HHEM when given) over `items`; kappa and
    accuracy are computed over the items the judge labeled (unknowns
    excluded and counted). Swap agreement is between the first two judges
    in `judges`, over items where both gave a label; None with one judge."""
    started = datetime.now(UTC).isoformat(timespec="seconds")
    truth = [i.label for i in items]
    rows: list[JudgeCalibration] = []
    labels: dict[str, list[str]] = {}
    for j in judges:
        labels[j.id] = _labels_for(j, items)
        rows.append(_score(j.id, j.version, truth, labels[j.id]))
    if hhem is not None:
        got = _labels_for(hhem, items)
        rows.append(_score(hhem.id, hhem.version, truth, got))
    swap: float | None = None
    pair: tuple[str, str] | None = None
    if len(judges) >= 2:
        a, b = judges[0].id, judges[1].id
        both = [(x, y) for x, y in zip(labels[a], labels[b], strict=True) if "unknown" not in (x, y)]
        swap = agreement([x for x, _ in both], [y for _, y in both]) if both else 0.0
        pair = (a, b)
    return CalibrationReport(
        started, datetime.now(UTC).isoformat(timespec="seconds"), len(items), tuple(rows),
        swap, pair, kappa_floor, min_swap_agreement,
    )


def write_report(report: CalibrationReport, results_dir: Path) -> Path:
    """Write `results/calibration/<started_at-safe>.json` and copy it to
    `latest.json`. Returns the timestamped path."""
    out = results_dir / "calibration"
    out.mkdir(parents=True, exist_ok=True)
    stem = report.started_at.replace(":", "").replace("+00:00", "Z")
    path = out / f"{stem}.json"
    text = json.dumps(report.to_dict(), indent=2) + "\n"
    path.write_text(text, encoding="utf-8")
    (out / "latest.json").write_text(text, encoding="utf-8")
    return path
```

CLI (`eval_platform/cli.py`), new subcommand:
```
evalplat calibrate --items calibration/faithfulness --judge <model> [--judge <second model>]
                   [--model-args JSON] [--hhem] [--results results] [--cache .cache/judge]
                   [--kappa-floor 0.70] [--min-swap-agreement 0.90] [--limit N]
```
`cmd_calibrate` loads items (`--limit` keeps the first N, for smoke runs), builds one `JudgeGrader` per `--judge` with the faithfulness rubric and `JudgeCache(Path(a.cache))`, `HHEMGrader()` when `--hhem`, calls `calibrate`, writes the report, prints one line per judge (`<judge> kappa=<k> acc=<a> unknown=<u>/<n> calibrated=<yes/no: reason>`) and the swap line; returns 2 on a load error (message on stderr), else 0. Also add `.gitignore` line `!results/calibration/latest.json` (the existing `!results/**/latest.json` already covers it; verify, do not duplicate).

- [ ] **Step 4: Run tests and gates; commit**

```bash
git add scripts/build_calibration_set.py calibration eval_platform/calibration.py eval_platform/cli.py tests/test_calibration.py
git commit -m "Add the RAGTruth calibration set and evalplat calibrate with kappa and swap agreement"
```

---

### Task 4: Judge pass over stored runs, judge metrics, gate rules

**Files:**
- Create: `eval_platform/judge_pass.py`, `tests/test_judge_pass.py`, `tests/test_gate_judges.py`
- Modify: `eval_platform/types.py` (`compute_metrics` judge and semantic metrics), `eval_platform/gate/config.py` (`judges` block), `eval_platform/gate/compare.py` (calibration lookup, `unstable`), `eval_platform/cli.py` (`evalplat judge`; `gate` reads the calibration report), `eval_platform/results.py` (`summary_to_result` inverse of `to_dict`)

**Interfaces:**
- `results.summary_to_result(d: dict) -> SuiteResult` rebuilds the dataclasses from a `latest.json` dict (Steps, Trajectories, Grades, CaseResults); raises ValueError on a malformed dict naming the case.
- `judge_pass.apply(result: SuiteResult, cases_by_name: dict[str, Case], graders: Sequence[Grader], *, sample: int | None) -> SuiteResult`: for every scored case (trajectory present, not skipped), and only the first `sample` of them when given, append one Grade per grader (replacing any earlier grade with the same dimension), recompute `passed` as "every deterministic grade passed and every judge/semantic grade passed or is unknown" (an unknown never fails a case), recompute metrics, set `meta["judge_pass"] = {"graders": [g.id...], "versions": {...}, "at": ..., "sample": sample}`; `started_at`/`finished_at` unchanged. A case missing from `cases_by_name` raises ValueError (the suite files must match the run).
- `compute_metrics` additions: for each dimension starting with `judge:` (per judge id): `judge.<rubric>.<model>.pass_rate` over non-unknown grades, `judge.<rubric>.<model>.unknown_rate` over all; when two judge dimensions share a rubric: `judge.<rubric>.swap_agreement` (share of cases where both gave the same non-unknown verdict, over cases where both are non-unknown; omitted when fewer than one such case); `unsupported_rate` = mean of `(1 - value)` of `unsupported_claims` grades over cases carrying it, omitted when none.
- Gate config:
  ```yaml
  judges: {kappa_floor: 0.70, min_swap_agreement: 0.90, require_swap_agreement: true}
  ```
  `GateConfig.judges: JudgeRules = JudgeRules()` with those three fields and defaults.
- `compare(config, baseline, current, *, calibration: dict | None = None)`: a row whose metric starts with `judge.` is `not_measured` with detail `judge <id> uncalibrated: <reason>` unless `calibration` (the `latest.json` dict of a CalibrationReport) marks that judge id calibrated; with `require_swap_agreement` and a current summary whose metrics carry `judge.<rubric>.swap_agreement` below `min_swap_agreement`, the row is `unstable` with detail `swap agreement <x> < <min>`. The judge id for a metric `judge.<rubric>.<model>.<stat>` is `f"{rubric}@{RUBRICS[rubric].version}:{model}"`.
- CLI:
  ```
  evalplat judge --suite-dir suites/<name> --results results [--judge <model> ...] [--model-args JSON]
                 [--rubric faithfulness|correctness] [--hhem] [--cache .cache/judge] [--sample N]
  ```
  Reads `results/<suite>/latest.json`, loads the suite's cases, builds graders, applies, writes a new per-run file and promotes `latest.json` (via `write_summary`), prints the new metrics. Returns 2 when no `latest.json` exists or no grader was requested. `evalplat gate` gains `--calibration results/calibration/latest.json` (default) and passes its dict when the file exists.

- [ ] **Step 1: Write the failing tests** (`tests/test_judge_pass.py`)

```python
import json
from pathlib import Path

from inspect_ai.model import get_model

from eval_platform.graders.hhem import HHEMGrader
from eval_platform.graders.judge import RUBRICS, JudgeGrader
from eval_platform.graders.judge_cache import JudgeCache
from eval_platform.judge_pass import apply
from eval_platform.results import summary_to_result, write_summary
from eval_platform.suites.runner import run_suite
from eval_platform.budget import Budget
from eval_platform.targets.scripted import ScriptedTarget
from eval_platform.types import Case, Expect, compute_metrics


def _cases():
    return [
        Case(name=f"c{n}", goal="q", target_requirements=["scripted"],
             script=[{"kind": "tool", "name": "search", "input": {}, "output": "Paris is in France."},
                     {"kind": "model", "name": "final", "input": {}, "output": "Paris is in France."}],
             expect=Expect(status="completed"))
        for n in range(3)
    ]


class StubScorer:
    version = "stub"
    def score(self, pairs):
        return [0.9 for _ in pairs]


def _judge(tmp_path, name, outputs):
    return JudgeGrader(model=f"mockllm/{name}", rubric=RUBRICS["faithfulness"], cache=JudgeCache(tmp_path / name),
                       model_handle=get_model("mockllm/model", custom_outputs=outputs))


def test_round_trip_summary(tmp_path: Path):
    result = run_suite("s", _cases(), ScriptedTarget(), budget=Budget(max_usd=1, max_wall_s=60))
    write_summary(result, tmp_path)
    back = summary_to_result(json.loads((tmp_path / "s" / "latest.json").read_text()))
    assert back.to_dict() == result.to_dict()


def test_apply_adds_grades_and_metrics(tmp_path: Path):
    result = run_suite("s", _cases(), ScriptedTarget(), budget=Budget(max_usd=1, max_wall_s=60))
    a = _judge(tmp_path, "a", ["VERDICT: SUPPORTED", "VERDICT: UNSUPPORTED", "nothing"])
    b = _judge(tmp_path, "b", ["VERDICT: SUPPORTED", "VERDICT: SUPPORTED", "VERDICT: SUPPORTED"])
    out = apply(result, {c.name: c for c in _cases()}, [a, b, HHEMGrader(scorer=StubScorer())], sample=None)
    dims = [g.dimension for g in out.cases[0].grades]
    assert dims == ["status", "judge:faithfulness:mockllm/a", "judge:faithfulness:mockllm/b", "unsupported_claims"]
    m = out.metrics
    assert m["judge.faithfulness.mockllm/a.pass_rate"] == 0.5      # 1 pass, 1 fail, 1 unknown
    assert round(m["judge.faithfulness.mockllm/a.unknown_rate"], 4) == round(1 / 3, 4)
    assert m["judge.faithfulness.mockllm/b.pass_rate"] == 1.0
    assert m["judge.faithfulness.swap_agreement"] == 0.5             # over the 2 cases both labeled
    assert m["unsupported_rate"] == 0.0
    assert [c.passed for c in out.cases] == [True, False, True]     # unknown never fails a case
    assert out.meta["judge_pass"]["graders"][0] == "faithfulness@1:mockllm/a"


def test_apply_replaces_same_dimension_and_respects_sample(tmp_path: Path):
    result = run_suite("s", _cases(), ScriptedTarget(), budget=Budget(max_usd=1, max_wall_s=60))
    a = _judge(tmp_path, "a", ["VERDICT: UNSUPPORTED"] * 3 + ["VERDICT: SUPPORTED"] * 3)
    once = apply(result, {c.name: c for c in _cases()}, [a], sample=2)
    assert sum(1 for c in once.cases for g in c.grades if g.dimension.startswith("judge:")) == 2
    twice = apply(once, {c.name: c for c in _cases()}, [a], sample=2)   # cache hits, same grades
    assert [g.dimension for g in twice.cases[0].grades].count("judge:faithfulness:mockllm/a") == 1


def test_apply_unknown_case_raises(tmp_path: Path):
    import pytest
    result = run_suite("s", _cases(), ScriptedTarget(), budget=Budget(max_usd=1, max_wall_s=60))
    with pytest.raises(ValueError, match="c0"):
        apply(result, {}, [_judge(tmp_path, "a", [])], sample=None)


def test_compute_metrics_omits_judge_keys_without_grades():
    m = compute_metrics([])
    assert not any(k.startswith("judge.") for k in m) and "unsupported_rate" not in m


def test_cli_judge_pass(tmp_path: Path, capsys):
    from eval_platform.cli import main
    suite = tmp_path / "suite"
    suite.mkdir()
    for c in _cases():
        (suite / f"{c.name}.yaml").write_text(
            "name: %s\ngoal: q\ntarget_requirements: [scripted]\nscript:\n"
            "  - {kind: tool, name: search, input: {}, output: Paris is in France.}\n"
            "  - {kind: model, name: final, input: {}, output: Paris is in France.}\n"
            "expect: {status: completed}\n" % c.name, encoding="utf-8")
    assert main(["run", "offline", "--suite-dir", str(suite), "--target", "scripted", "--results", str(tmp_path / "r")]) == 0
    code = main(["judge", "--suite-dir", str(suite), "--results", str(tmp_path / "r"),
                 "--judge", "mockllm/model", "--cache", str(tmp_path / "c")])
    assert code == 0
    latest = json.loads((tmp_path / "r" / "suite" / "latest.json").read_text())
    assert "judge.faithfulness.mockllm/model.unknown_rate" in latest["metrics"]
    assert main(["judge", "--suite-dir", str(suite), "--results", str(tmp_path / "none")]) == 2
```

`tests/test_gate_judges.py`:
```python
from eval_platform.gate.compare import compare
from eval_platform.gate.config import GateConfig, JudgeRules, Threshold


def _cfg(**judges):
    return GateConfig(
        suites={"g": Threshold(metric="judge.faithfulness.hf/x.pass_rate", min=0.5),
                "u": Threshold(metric="unsupported_rate", max_rise=0.02)},
        judges=JudgeRules(**judges),
    )


def _cur(pass_rate=0.8, swap=None):
    m = {"judge.faithfulness.hf/x.pass_rate": pass_rate, "unsupported_rate": 0.1}
    if swap is not None:
        m["judge.faithfulness.swap_agreement"] = swap
    return {"g": {"metrics": m, "target": "t"}, "u": {"metrics": m, "target": "t"}}


def _cal(kappa=0.8, swap=0.95):
    return {"judges": [{"judge": "faithfulness@1:hf/x", "kappa": kappa}],
            "swap_agreement": swap, "kappa_floor": 0.70, "min_swap_agreement": 0.90,
            "calibrated": {"faithfulness@1:hf/x": [kappa >= 0.70 and swap >= 0.90, "reason"]}}


def test_judge_row_without_calibration_is_not_measured():
    r = compare(_cfg(), {}, _cur(), calibration=None)
    g = next(v for v in r.verdicts if v.suite == "g")
    assert g.verdict == "not_measured" and "uncalibrated" in g.detail


def test_judge_row_uncalibrated_judge_is_not_measured():
    r = compare(_cfg(), {}, _cur(), calibration=_cal(kappa=0.4))
    g = next(v for v in r.verdicts if v.suite == "g")
    assert g.verdict == "not_measured" and "kappa" in g.detail


def test_judge_row_calibrated_judge_is_judged():
    r = compare(_cfg(), {}, _cur(pass_rate=0.3), calibration=_cal())
    g = next(v for v in r.verdicts if v.suite == "g")
    assert g.verdict == "fail"


def test_swap_disagreement_is_unstable():
    r = compare(_cfg(require_swap_agreement=True), {}, _cur(swap=0.6), calibration=_cal())
    g = next(v for v in r.verdicts if v.suite == "g")
    assert g.verdict == "unstable" and not r.passed


def test_non_judge_rows_ignore_calibration():
    r = compare(_cfg(), {"u": {"metrics": {"unsupported_rate": 0.1}, "target": "t"}}, _cur(), calibration=None)
    u = next(v for v in r.verdicts if v.suite == "u")
    assert u.verdict == "pass"
```

- [ ] **Step 2: Implement** `results.summary_to_result`, `judge_pass.apply`, the metric additions, `JudgeRules`, the `compare` changes, the two CLI changes. Keep `compare`'s docstring in step with the new parameter (what `calibration` is, when `unstable` fires). Keep each function under the linter's branch limit by splitting helpers (`_judge_row_verdict`).

- [ ] **Step 3: Run tests and gates; `evalplat gate` still PASS on main (no rows changed yet); commit**

```bash
git commit -am "Add the judge pass over stored runs, judge metrics, and calibration-gated judge rows"
```

---

### Task 5: EDGAR fixtures, the retriever server, the grounded dimension, and the groundedness suite

**Files:**
- Create: `scripts/build_edgar_fixtures.py`, `eval_platform/retrievers/__init__.py`, `eval_platform/retrievers/edgar_fixture_server.py`, `suites/groundedness/golden.json` (copied from `C:/signalnodus-site/eval/golden.json`, MIT, with a `provenance` block added at the top level), `suites/groundedness/fixtures/*.json`, `suites/groundedness/*.yaml`, `suites/groundedness/README.md`, `tests/test_edgar_fixture_server.py`, `tests/test_graders_grounded.py`, `tests/test_groundedness_suite.py`
- Modify: `eval_platform/types.py` (`Expect.grounded: bool | None`), `eval_platform/graders/deterministic.py` (`quotes_in_source`), `.gitignore` (`.cache/` already ignored; raw filings go there)

**Interfaces:**
- Fixture file `suites/groundedness/fixtures/<accession>-<item>.json`:
  ```json
  {"accession": "0000320193-25-000079", "company": "Apple Inc.", "form": "10-K", "item": "1A",
   "filing_date": "2025-10-31", "document_url": "https://www.sec.gov/...", "golden_id": "aapl-...-1A",
   "window_paragraphs": 40, "paragraphs": [{"id": 0, "text": "..."}, ...],
   "anchors": [{"phrase": "the following summarizes factors", "paragraph_id": 3, "sentence": "The following summarizes ..."}]}
  ```
  Paragraphs are the section's HTML block elements (`p`, `div`, `li`, `tr`) as text, whitespace-normalized, empty ones dropped, and only the window of `window_paragraphs` on each side of every anchor paragraph is kept (windows merged when they overlap), so the fixture holds the part of the section a question is about, not the whole filing. The anchor `sentence` is the sentence containing the phrase, exact casing, split with `split_sentences`.
- Build script `scripts/build_edgar_fixtures.py --golden suites/groundedness/golden.json --out suites/groundedness [--only <golden id>]`: for each golden case with at least one `must_contain` anchor, fetch `documentUrl` (User-Agent `ai-eval-platform hgenix@agentmail.to`, timeout 60 s, 0.5 s between requests, raw HTML cached in `.cache/edgar/<accession>-<document>.htm`), convert to paragraphs, locate the item's section as the slice from the LAST heading matching `Item\s*<item>\.?` (case-insensitive; the earlier ones are the table of contents) to the next heading `Item\s*<next>` where `<next>` is the following item in the form's order (1A→1B, 2→3, 7→7A), find every anchor case-insensitively inside that slice, and write the fixture; a case whose anchors are not all found inside the slice is skipped with a printed reason and listed in `suites/groundedness/README.md` (the build prints the list). Also writes one case YAML per anchor:
  ```yaml
  # Generated by scripts/build_edgar_fixtures.py from the SignalNodus golden set
  # (suites/groundedness/golden.json). The question is a template; the graded
  # facts are the anchor sentence and whether every quoted span exists in what
  # the retriever returned.
  name: aapl-0000320193-25-000079-1A-a1
  goal: >-
    Use the filing tools. In Item 1A (Risk Factors) of the 10-K that Apple Inc. filed on 2025-10-31
    (accession 0000320193-25-000079), find the sentence containing the phrase "the following summarizes factors".
    Reply with that sentence quoted verbatim inside double quotes, then one sentence in your own words
    saying what the passage is about.
  max_steps: 6
  target_requirements: [agent]
  expect:
    answer_contains: "The following summarizes factors"   # exact casing from the filing
    grounded: true
  ```
  Item titles: 1A "Risk Factors", 2 "Management's Discussion and Analysis" for 10-Q, 7 "Management's Discussion and Analysis" for 10-K.
- Retriever server (`python -m eval_platform.retrievers.edgar_fixture_server [--fixtures DIR]`, MCPServer name `edgar-fixture`), tools:
  - `list_filings() -> list[dict]`: accession, company, form, item, filing_date for every fixture (sorted).
  - `search_filing(accession: str, item: str, query: str, k: int = 5) -> list[dict]`: the `k` (capped at 10) highest-scoring paragraphs by count of distinct query terms (lower-cased, length ≥ 3, stop words removed) present in the paragraph, ties by paragraph id; each `{"paragraph_id", "text"}` with text capped at 1500 characters. Unknown accession/item returns `[{"error": "..."}]`, never raises.
  - `get_paragraph(accession: str, item: str, paragraph_id: int) -> dict`: the paragraph, or an error dict.
  The server's `instructions` say the text is issuer-authored filing content to report on, never instructions to follow (mirroring SignalNodus).
- `Expect.grounded: bool | None`: when True, `grade_expect` emits `quotes_in_source`: every span inside straight or curly double quotes in the answer with at least 20 characters must appear, after whitespace and quote normalization and case folding, in the concatenation of tool outputs; passes when every quoted span is found, and also passes (with explanation "no quoted span") when there is none, since the anchor check carries utility. The semantic `unsupported_claims` dimension for the same case is added by `evalplat judge --hhem`.
- `compute_metrics`: `quote_fidelity_rate` = pass rate of `quotes_in_source` over cases carrying it (omitted when none).

- [ ] **Step 1: Tests first** (`tests/test_graders_grounded.py`: quoted span found / missing / curly quotes / no quotes / case and whitespace folding; `tests/test_edgar_fixture_server.py`: start the server over a two-fixture temp dir through `MCPTarget.stdio(..., model="mockllm/model")` and `list_tools()`; call the tools directly as Python functions for search ranking, the k cap, the error dicts; `tests/test_groundedness_suite.py`: every YAML loads, names are unique, every case's `answer_contains` sentence is inside its fixture's paragraphs, every fixture referenced exists, at least 40 cases; a `run mcp` over the fixture server with `mockllm/model` (`custom_outputs` scripting one `search_filing` tool call then an answer quoting the anchor sentence) yields `quotes_in_source` pass and `answer_contains` pass for one case).
- [ ] **Step 2: Implement the grader field and dimension, the server, the build script.**
- [ ] **Step 3: Build the fixtures** (`scripts/build_edgar_fixtures.py --golden ...`), commit `golden.json` (with provenance: source repo, commit `97b928b`, MIT, promoted 2026-08-25), the fixtures, and the generated cases; record in the README how many golden cases produced fixtures and which were skipped and why. Target: at least 40 cases from the 53 anchors.
- [ ] **Step 4: Run tests and gates; commit**

```bash
git commit -m "Add the EDGAR fixture retriever, the grounded dimension, and the groundedness suite"
```

---

### Task 6: Measured runs on the local GPU: groundedness, judge pass, calibration

**Files:**
- Create: `results/groundedness/latest.json` (+ per-run files), `results/calibration/latest.json` (+ per-run), `baselines/groundedness*.json`, `results/ledger.jsonl` lines
- Modify: `gate.yaml` (rows below), `tests/test_gate_rows.py` (row names present), `docs/results.md` (Task 7 writes prose; this task commits data only)

Commands (each recorded in the ledger through the existing `Ledger`; `usd` 0.0 with `note` naming the GPU):

1. Groundedness with the 3B answerer:
```bash
.venv/Scripts/evalplat run mcp --suite-dir suites/groundedness --mcp-command .venv/Scripts/python.exe --mcp-args -m eval_platform.retrievers.edgar_fixture_server --server-name edgar-fixture --model hf/Qwen/Qwen2.5-3B-Instruct --model-args '{"device": "cuda:0", "dtype": "bfloat16", "do_sample": false}' --max-steps 6 --budget-usd 0 --max-wall-s 7200 --results results
```
2. Judge pass with both judges and HHEM (two judges load one after the other; `judge_pass` must release one model before loading the next: build graders lazily and call `torch.cuda.empty_cache()` between judges, both in `judge_pass.apply` when the grader exposes `release()`; add `JudgeGrader.release()` that drops the handle):
```bash
.venv/Scripts/evalplat judge --suite-dir suites/groundedness --results results --judge hf/Qwen/Qwen2.5-3B-Instruct --judge hf/Qwen/Qwen2.5-1.5B-Instruct --model-args '{"device": "cuda:0", "dtype": "bfloat16", "do_sample": false}' --hhem
```
3. Calibration:
```bash
.venv/Scripts/evalplat calibrate --items calibration/faithfulness --judge hf/Qwen/Qwen2.5-3B-Instruct --judge hf/Qwen/Qwen2.5-1.5B-Instruct --model-args '{"device": "cuda:0", "dtype": "bfloat16", "do_sample": false}' --hhem --results results
```
4. `gate.yaml` rows:
```yaml
  # Phase 3. No absolute ceiling on unsupported_rate until the level is
  # measured on more than one model; a rise against the target-tied baseline
  # fails. quote_fidelity_rate is deterministic, so any drop fails.
  groundedness: {metric: unsupported_rate, max_rise: 0.02}
  groundedness_quotes: {metric: quote_fidelity_rate, max_drop: 0.0}
  groundedness_latency: {metric: wall_ms_p95, max_increase_pct: 50}
  # A judge row is not_measured until results/calibration/latest.json marks
  # the judge calibrated (kappa >= judges.kappa_floor and swap agreement >=
  # judges.min_swap_agreement); see ADR-0007.
  groundedness_judge: {metric: judge.faithfulness.hf/Qwen/Qwen2.5-3B-Instruct.pass_rate, max_drop: 0.05}
judges: {kappa_floor: 0.70, min_swap_agreement: 0.90, require_swap_agreement: true}
```
5. `evalplat gate --update-baseline` for the new rows only (do not touch other baselines: run it into a temp dir and copy the three new files), then `evalplat gate` PASS with the judge row `not_measured` (expected) or `pass` (if the 3B judge clears both floors; either is reported as measured).

Expected wall time: groundedness about 40 minutes at 6 s per generate call; the judge pass about 15 minutes; calibration about 20 minutes. GPU memory: one model at a time.

- [ ] Commit data and gate rows: `git commit -m "Publish the first groundedness, judge pass, and calibration runs on the local GPU"`.

---

### Task 7: Docs, report section, CI rung 3, ADRs

**Files:**
- Modify: `docs/results.md` (sections: "Groundedness suite", "Judge calibration", "The gate" additions), `README.md` (Phase 3 status, `evalplat judge` / `calibrate` usage, ladder table rung 3 now "committed judge-graded results and the calibration report"), `.github/workflows/ci.yml` (rung 3: `evalplat calibrate --check results/calibration/latest.json` validates the committed report's schema and prints its verdicts; add `--check` to the command: no model call), `eval_platform/reports/html.py` (a "Judge calibration" table from `results/calibration/latest.json` when present: judge, version, items, unknown, kappa, accuracy, calibrated reason; swap agreement line), `tests/test_report.py`
- Create: `docs/adr/0007-uncalibrated-judges-cannot-block.md`, `docs/adr/0008-groundedness-against-the-golden-set-with-a-fixture-retriever.md`

Content rules: every number in `docs/results.md` is copied from a committed `results/` file with the run timestamp named; the calibration section states the labeled set (120 RAGTruth items, MIT, human span labels), each judge's kappa and accuracy and unknown count, the swap agreement, HHEM's own kappa on the same items, and which judges the gate may listen to; if no judge clears the floor, say so in the first sentence and say what the gate does about it. The groundedness section states the retriever (fixture over EDGAR paragraphs), the answerer, the unsupported-claim rate, quote fidelity, the anchor hit rate (pass rate of `answer_contains`), and the caveat that the fixture holds a window of each section. ADR-0007 records why local 3B judges were used, the calibration rule as implemented, and the hosted-judge path. ADR-0008 records the retriever choice, the paid SignalNodus path as the optional live run, and the anchor-validated extraction.

- [ ] Commit: `git commit -m "Document Phase 3: judge calibration, groundedness results, ADR-0007 and ADR-0008"`.

---

### Task 8 (optional, local GPU): SimpleQA Verified sample with the correctness judge

Only if Tasks 1 to 7 are merged and the GPU is free. `inspect_evals/simpleqa_verified` uses a model-graded scorer; run it with `--model hf/Qwen/Qwen2.5-3B-Instruct --limit 100 --no-cost-cap --max-tokens 256` and the grader model set to the same local model through Inspect's `--model-role grader` equivalent (`model_roles={"grader": ...}` in `run_public`; add a `--grader-model` option that maps to it). Publish under `results/public_simpleqa_verified/` with the caveat that the grader is the uncalibrated correctness rubric on a 3B model, so the number describes the pipeline, not the model. No gate row.

---

## Self-review against the spec

- 4.5 Grader protocol: Task 1 (`base.py`). Judge cache key fields: Task 1 `cache_key` covers all six. Unknown outcome: `parse_verdict` and the 0.5 value; `judge_pass` never fails a case on unknown; metrics report `unknown_rate`. Calibration rule (kappa floor 0.70, agreement 0.90, uncalibrated judges run and report and cannot block): Tasks 3 and 4.
- 4.4 `groundedness` (exact span from pinned EDGAR filings, unsupported-claim rate, span containment plus HHEM): Task 5 (`quotes_in_source`, `unsupported_claims`, `unsupported_rate`). `judge_calibration` (kappa, swap stability): Task 3.
- 4.6 `groundedness` row and `judge_stability`: Tasks 4 and 6; `unstable` verdict: Task 4.
- 4.8 report judge calibration section: Task 7. 4.9 grader-call spans: Task 1 (`eval.grader` with judge id and cache hit).
- 5 rung 3: Task 7 (CI reads committed judge-graded results and checks the calibration report; no model in CI).
- 8 acceptance: judge graders with cache (1), calibration set ≥ 50 (3: 120), calibrate report with kappa per judge (3), swap-stability against a second judge (3, 4), groundedness on the EDGAR golden set with unsupported-claim rate published (5, 6, 7).
- Type consistency: `JudgeGrader.id` format `f"{rubric.id}@{rubric.version}:{model}"` is used by `calibration.calibrated`, by `compare`'s judge-id derivation, and by `judge_pass.meta`; `Grade.dimension` for judges is `judge:<rubric>:<model>` and the metric key is `judge.<rubric>.<model>.<stat>`; `HHEMGrader.id` is `hhem@2.1-open` in both the calibration report and the judge pass.
