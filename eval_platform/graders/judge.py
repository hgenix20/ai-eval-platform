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
    that hits the cache for every case never loads the judge weights.

    `judge()` calls `asyncio.run` internally and is meant to be called from
    synchronous code (the `evalplat judge` command). Calling it from inside
    an already-running event loop raises `RuntimeError`; that is acceptable
    here because the judge pass is always a top-level command, never a
    solver step inside Inspect's own event loop.
    """

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
            self.cache.put(
                key, {"label": label, "raw": raw, "judge": self.id, "version": self.version}
            )
            set_attributes(s, **{"eval.cache_hit": False, "eval.label": label})
            return JudgeResult(self._verdict(label), label, raw, False)

    def grade(self, case: Case, trajectory: Trajectory) -> Grade:
        r = self.judge(case, trajectory)
        # "pass" here is a Verdict literal, not a credential; bandit's B105
        # heuristic matches the dict key string regardless.
        value = {"pass": 1.0, "fail": 0.0, "unknown": 0.5}[r.verdict]  # nosec B105
        return Grade(
            dimension=f"judge:{self.rubric.id}:{self.model}",
            value=value,
            passed=r.verdict == "pass",
            explanation=f"{r.label} ({'cached' if r.cached else 'called'}): {r.raw[:200]}",
        )


__all__ = ["RUBRICS", "JudgeGrader", "JudgeResult", "Verdict", "parse_verdict"]
