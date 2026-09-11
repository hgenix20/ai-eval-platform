# ADR-0007: an uncalibrated judge cannot block a build

Status: accepted, 2026-09-11. Spec section 4.5, Phase 3.

## Context

A judge grader is one model scoring another model's answer. Its verdict reads
like a measurement whether or not it agrees with a person, and a gate row wired
to it will fail builds on that basis. Phase 3 needed judges in the platform. It
needed just as much a rule that keeps a judge's opinion out of the gate until
someone has checked the judge against human labels.

No hosted credits existed on the account when Phase 3 ran. The 2026-09-10
IFEval attempt had already stopped on a 402 from Hugging Face Inference
Providers with monthly credits exhausted. What the machine does have is an
RTX 4080 Laptop GPU with 12 GB, which holds a 3B instruct model in bfloat16
with room for the retrieval context.

## Decision

Judges run locally through Inspect's `hf/` provider. Two were measured:
Qwen2.5-3B-Instruct, licensed qwen-research, and Qwen2.5-1.5B-Instruct,
Apache-2.0, each per its own model card
(<https://huggingface.co/Qwen/Qwen2.5-3B-Instruct>,
<https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct>).

`evalplat calibrate` scores every judge against 120 items taken from RAGTruth,
which publishes human span annotations under MIT
(<https://github.com/ParticleMedia/RAGTruth>). Each item's spans are reduced to
one binary label, supported or unsupported, and the set is balanced 60 and 60.

A judge may contribute to the gate only once its Cohen's kappa against those
labels reaches 0.70 and its verdicts agree with a second judge model on at
least 0.90 of the items. Both floors sit in `gate.yaml`'s `judges:` block, and
a test pins their values. Until a judge clears them, its gate row reports
not_measured and carries the kappa and the floor in the row's detail, so the
number stays on the page and decides nothing.

Here is what the 2026-09-11 calibration run measured
(`results/calibration/latest.json`):

| grader | kappa | accuracy | unknown |
| --- | --- | --- | --- |
| `faithfulness@1:hf/Qwen/Qwen2.5-3B-Instruct` | 0.0763 | 0.5339 | 2 of 120 |
| `faithfulness@1:hf/Qwen/Qwen2.5-1.5B-Instruct` | 0.0167 | 0.5083 | 0 of 120 |
| `hhem@2.1-open` | 0.5167 | 0.7583 | 0 of 120 |

Swap agreement between the two judges was 0.7458. No grader clears 0.70, so
`groundedness_judge` reports not_measured, and the floors were left where they
were. Lowering a floor to admit the judge you happen to have is the failure
this rule exists to prevent.

HHEM-2.1-Open sits outside the judge rule on purpose. It is a fixed
classifier over a pinned snapshot, licensed Apache-2.0 on a FLAN-T5-base
foundation (<https://huggingface.co/vectara/hallucination_evaluation_model>),
and `unsupported_rate` keeps a relative gate row for the reason under
Consequences. Its kappa of 0.52 is published next to the judges so a reader can
weigh the row for themselves.

## Alternatives rejected

- **Gate on the judges anyway and watch the trend.** Both local judges sit near
  chance on the labeled set, and the 1.5B judge calls 57 of 60 unsupported
  items supported. A row wired to either one would move with judge noise and be
  read as a change in answer quality.
- **Lower the kappa floor to 0.50 so HHEM qualifies.** The floor was set before
  anything was measured, which is the only time a floor can be set honestly. A
  measurement is not a reason to move it.
- **Wait for hosted credits before shipping any judge layer.** The cache, the
  rubric, the swap check, and the calibration arithmetic are all testable
  without a good judge, and shipping them now means a hosted judge costs a
  calibration run and two lines of config instead of a project.
- **Treat a judge's own confidence as the calibration signal.** A small model's
  stated confidence is a token distribution over words like "supported". It
  carries no information about agreement with a person, which is the thing the
  floor is about.

## Consequences

- `evalplat judge` and `evalplat calibrate` both work today and cost $0.00.
  Moving to a hosted judge takes four things: the `--judge` value and its key,
  a calibration run for that judge against the same 120 items, the metric name
  on the `groundedness_judge` row in `gate.yaml` (the row names the model it
  measures, so a new judge is a new metric), and a baseline for that row under
  the new metric. Nothing else in the pipeline changes: the cache, the rubric,
  the swap check, the calibration arithmetic, and the gate's own rule all take
  the new judge as they stand.
- `.cache/judge/` is gitignored and keyed by a SHA-256 over the case id, the
  prompt text, the judge model id and version (the Hugging Face snapshot hash
  for an `hf/` judge), the rubric id and version, and the sampling parameters.
  Re-grading the same run with the same judge is free, and a judge upgrade
  misses every entry, which is the behavior you want from a version-keyed
  cache.
- `unsupported_rate` from HHEM keeps its gate row at `max_rise: 0.02`. The
  classifier is fixed and its snapshot is pinned, so the same cases scored
  again give the same numbers, and a rise means the answers changed. That is a
  relative claim about one model's answers over time and it holds at kappa
  0.52. An absolute ceiling on the metric waits until the level has been
  measured on a second model, since 0.2724 on a 3B answerer says nothing yet
  about where the ceiling belongs.
- HHEM is loaded by this repository's own code, not by the checkpoint's
  `trust_remote_code` class, which raises `AttributeError:
  all_tied_weights_keys` under transformers 5. The replacement reads the
  checkpoint's safetensors, strips the wrapper's `t5.` prefix from every key,
  and loads a plain `T5ForTokenClassification`. It reproduces the model card's
  seven published example scores to four decimals, and `tests/test_hhem.py`
  asserts that (marked gpu and network, so it stays out of CI).
- CI reads the committed calibration report instead of calling a judge.
  `evalplat calibrate --check results/calibration/latest.json` validates the
  report's shape, prints each grader's verdict, and exits 2 when the file is
  missing or malformed. That is rung 3 on a runner with no GPU.
