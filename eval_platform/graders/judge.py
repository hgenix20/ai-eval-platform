# pyright: reportMissingImports=false
# The `local` extra (torch, transformers, safetensors) is optional and CI
# type-checks without it; the imports below are lazy and resolve only on a
# machine that runs models.
"""Judge graders: a pinned model, a rubric, an explicit unknown outcome,
and a content-addressed cache (design spec 4.5).

A judge never runs inside `run_suite`; it is applied by `evalplat judge`
as a second pass over a stored run, so the answering model and the judge
model are never resident together.
"""

from __future__ import annotations

import asyncio
import re
import sys
from dataclasses import dataclass
from typing import Any, Literal

from inspect_ai.model import ChatMessageSystem, ChatMessageUser, GenerateConfig, Model, get_model

from eval_platform.graders.base import GraderKind
from eval_platform.graders.judge_cache import JudgeCache, cache_key, model_version
from eval_platform.graders.rubrics import RUBRICS, Rubric
from eval_platform.telemetry import set_attributes, span
from eval_platform.types import Case, Grade, Trajectory

Verdict = Literal["pass", "fail", "unknown"]
# Anchored to a whole line, which is the form every rubric asks for. An
# unanchored pattern would read "my verdict: leaning supported" mid-sentence
# as the label and score the reasoning instead of the conclusion. The
# optional `*`/`_` runs and one closing `.`, `!`, or `;` are what small
# judges write around the label in practice: "VERDICT: SUPPORTED." and
# "**VERDICT: UNSUPPORTED**" state a verdict, and reading either as unknown
# would throw away the judgment the model made.
_VERDICT_LINE = re.compile(
    r"^\s*[*_]*verdict\s*:\s*[*_]*([A-Z_]+)[*_]*[.!;]?\s*$", re.IGNORECASE | re.MULTILINE
)


@dataclass(frozen=True)
class JudgeResult:
    verdict: Verdict
    label: str
    raw: str
    cached: bool


def _grade_value(verdict: Verdict) -> float:
    """A verdict as a Grade value: 1.0 for a pass, 0.0 for a fail, and 0.5
    for unknown, which sits between the two because the judge declined to
    label the case rather than finding against it."""
    if verdict == "pass":
        return 1.0
    return 0.0 if verdict == "fail" else 0.5


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

    # Annotated, not inferred: the `Grader` protocol declares `kind` as a
    # GraderKind, and a bare assignment would infer plain `str`, which no
    # `Sequence[Grader]` parameter would accept.
    kind: GraderKind = "judge"

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

    def release(self) -> None:
        """Drop the loaded model handle and free the CUDA cache it held.

        The judge pass grades every case with one judge before it builds the
        next, and calls this in between, so two local judges never occupy GPU
        memory at the same time. A later `judge()` call reloads the handle
        from `model`, which is why this is safe to call at any point. A
        handle the caller injected is dropped here too, so an injected mock
        is released on the same path as a real model.

        The CUDA cache is emptied only when torch is already imported in
        this process. Nothing holds GPU memory otherwise, and a process
        whose judges are all hosted models (or mocks) should not pay a
        torch import to be told so.
        """
        self._handle = None
        if "torch" not in sys.modules:
            return
        import torch  # noqa: PLC0415

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

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
        value = _grade_value(r.verdict)
        return Grade(
            dimension=f"judge:{self.rubric.id}:{self.model}",
            value=value,
            passed=r.verdict == "pass",
            explanation=f"{r.label} ({'cached' if r.cached else 'called'}): {r.raw[:200]}",
        )


__all__ = ["RUBRICS", "JudgeGrader", "JudgeResult", "Verdict", "parse_verdict"]
