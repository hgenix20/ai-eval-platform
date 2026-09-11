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
from typing import Any, Protocol, cast

from eval_platform.graders.base import GraderKind
from eval_platform.graders.rubrics.base import context_from
from eval_platform.types import Case, Grade, Trajectory

HHEM_REPO = "vectara/hallucination_evaluation_model"
HHEM_SNAPSHOT = "8e4a2e6e96c708cc76c2344f7e4757df2515292c"
HHEM_FOUNDATION = "google/flan-t5-base"
# The foundation only supplies tokenization and the config shape, not
# weights (those come from HHEM_SNAPSHOT), but it is still pinned: the
# revision already resolved in the local Hugging Face cache, verified
# 2026-09-11.
HHEM_FOUNDATION_SNAPSHOT = "7bcac572ce56db69c1ea7c8af255c5d7c9672fc2"
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
        self._torch: Any = None

    def _loaded(self) -> tuple[Any, Any, Any]:
        """Load the model, tokenizer, and torch module on first use and
        return the three as a plain non-optional tuple, so `score` never
        has to prove the lazy load happened to the type checker."""
        if self._model is not None:
            return self._model, self._tok, self._torch
        # Imports stay local so this module (and eval_platform.graders) is
        # importable without the `local` extra installed; only a grade()
        # call that actually needs the model pays for torch/transformers.
        # The pyright ignores exist because CI type-checks without that
        # extra, so these names resolve only on a machine that runs models.
        import torch  # noqa: PLC0415  # pyright: ignore[reportMissingImports]
        from huggingface_hub import hf_hub_download  # noqa: PLC0415
        from safetensors.torch import (
            load_file,  # pyright: ignore[reportMissingImports]
        )
        from transformers import (  # noqa: PLC0415  # pyright: ignore[reportMissingImports]
            AutoConfig,
            AutoTokenizer,
            T5Config,
            T5ForTokenClassification,
        )

        weights = hf_hub_download(HHEM_REPO, "model.safetensors", revision=HHEM_SNAPSHOT)
        config = cast(
            T5Config,
            AutoConfig.from_pretrained(
                HHEM_FOUNDATION, num_labels=2, revision=HHEM_FOUNDATION_SNAPSHOT
            ),
        )
        model = T5ForTokenClassification(config)
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
        self._tok = AutoTokenizer.from_pretrained(
            HHEM_FOUNDATION, revision=HHEM_FOUNDATION_SNAPSHOT
        )
        self._torch = torch
        return self._model, self._tok, self._torch

    def score(self, pairs: Sequence[tuple[str, str]]) -> list[float]:
        if not pairs:
            return []
        model, tok, tch = self._loaded()
        texts = [HHEM_PROMPT.format(text1=p[:PREMISE_CHARS], text2=h) for p, h in pairs]
        inputs = tok(texts, return_tensors="pt", padding=True, truncation=True, max_length=1024)
        with tch.no_grad():
            logits = model(**inputs).logits[:, 0, :]
        return [float(x) for x in tch.softmax(logits, dim=-1)[:, 1].tolist()]


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
    0.0) with no scorer call; an answer with no sentence yields 0.0.

    The answer is read first, so an empty context with an empty answer is
    0.0, not 1.0: the answer claimed nothing, and nothing claimed cannot be
    unsupported. That case is a run whose target produced no answer, and
    `compute_metrics` counts it through the case's own status instead.
    """
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

    # Annotated for the same reason as JudgeGrader.kind: a bare assignment
    # infers `str`, which the `Grader` protocol's GraderKind does not accept.
    kind: GraderKind = "semantic"
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
        why = f"{len(bad)}/{len(detail)} sentences unsupported" + (
            f": {'; '.join(bad)}" if bad else ""
        )
        return Grade("unsupported_claims", 1.0 - share, share == 0.0, why)
