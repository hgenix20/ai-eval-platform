# Calibration sets

`evalplat calibrate` reads every `*.jsonl` file under a directory here and
scores each judge against the `label` each item carries. Drop a new
`*.jsonl` file into `calibration/faithfulness/` (hand-labeled items, another
sample, whatever) and it is picked up automatically; item ids must stay
unique across every file in the directory.

## `faithfulness/ragtruth-120.jsonl`

120 items sampled from the test split of
[RAGTruth](https://github.com/ParticleMedia/RAGTruth) (MIT license, copy at
`LICENSE-RAGTruth.txt`), a dataset of human span annotations over model
responses to retrieval prompts. A response with no annotated span becomes
`supported`; a response with at least one annotated span becomes
`unsupported`. That is RAGTruth's own human judgment, reduced from spans to
a single binary label per response.

The set is balanced: 30 `supported` and 30 `unsupported` from the QA task
type, and the same split from Summary, for 120 items and 60 of each label.
QA items carry the MS MARCO passages RAGTruth bundles as `context` and the
question as `question`; Summary items carry the source article as `context`
with an empty `question`.

Rebuild it with:

```bash
mkdir -p .cache/ragtruth
curl -sL -o .cache/ragtruth/response.jsonl https://raw.githubusercontent.com/ParticleMedia/RAGTruth/main/dataset/response.jsonl
curl -sL -o .cache/ragtruth/source_info.jsonl https://raw.githubusercontent.com/ParticleMedia/RAGTruth/main/dataset/source_info.jsonl
.venv/Scripts/python scripts/build_calibration_set.py --response .cache/ragtruth/response.jsonl --source .cache/ragtruth/source_info.jsonl
```

The sample is seeded (`SEED = 20260911` in the script), drawn only from
responses whose `quality` is `"good"` (skipping truncated responses and
refusals), and sorted by response id before sampling, so the same two input
files always produce the same 120 items.
