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
    rng = random.Random(SEED)  # noqa: S311 -- deterministic sampling, not cryptographic
    out = []
    for task in ("QA", "Summary"):
        for label, want_spans in (("supported", False), ("unsupported", True)):
            pool = [
                r
                for r in rows
                if r["split"] == "test"
                and r["quality"] == "good"
                and sources[r["source_id"]]["task_type"] == task
                and bool(r["labels"]) == want_spans
            ]
            pool.sort(key=lambda r: r["id"])
            for r in rng.sample(pool, PER_CELL):
                s = sources[r["source_id"]]
                context, question = _context(s)
                out.append(
                    {
                        "id": f"ragtruth-{r['id']}",
                        "context": context,
                        "question": question,
                        "response": r["response"],
                        "label": label,
                        "provenance": {
                            "dataset": "RAGTruth",
                            "split": "test",
                            "source_id": str(r["source_id"]),
                            "response_id": str(r["id"]),
                            "task_type": task,
                            "model": r["model"],
                            "license": "MIT",
                            "url": "https://github.com/ParticleMedia/RAGTruth",
                        },
                    }
                )
    out.sort(key=lambda x: x["id"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        for item in out:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"wrote {len(out)} items to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
