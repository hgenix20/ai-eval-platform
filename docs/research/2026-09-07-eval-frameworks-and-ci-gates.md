# Eval frameworks, CI quality gates, and job-posting eval expectations, 2026-09-07

Source: research agent, web-verified. UNVERIFIED = not confirmed at a primary source.

## Tier 1: benchmark runners

| Framework | URL | License | Version / cadence | Stars | Status |
|---|---|---|---|---|---|
| Inspect AI | https://github.com/UKGovernmentBEIS/inspect_ai https://inspect.aisi.org.uk | MIT | 0.3.263 (2026-09-04), near-daily | ~2.7k | ACTIVE |
| inspect_evals | https://github.com/UKGovernmentBEIS/inspect_evals | MIT | commits 2026-09-01 | ~659 | ACTIVE |
| lm-evaluation-harness | https://github.com/EleutherAI/lm-evaluation-harness | MIT | 0.4.13 (2026-08-31) | ~13.9k | ACTIVE |
| OpenAI Evals | https://github.com/openai/evals | MIT | last real commit 2026-04 | ~19.4k | STALE; hosted product deprecated 2026-06-03, read-only 2026-10-31, shutdown 2026-11-30; OpenAI recommends promptfoo https://developers.openai.com/api/docs/deprecations |
| HELM | https://github.com/stanford-crfm/helm | Apache-2.0 | 0.5.16 (2026-04-30) | ~2.9k | maintenance mode since 2026-06-01 (UNVERIFIED) |
| lighteval | https://github.com/huggingface/lighteval | MIT | 0.13.0 (2025-11-24) | ~2.5k | ACTIVE; names inspect-ai as preferred backend |
| BigCode harness | https://github.com/bigcode-project/bigcode-evaluation-harness | Apache-2.0 | 2 commits in 14 months | ~1.1k | STALE |
| SWE-bench | https://github.com/SWE-bench/SWE-bench | MIT | 5.0.2 (2026-08-18) | ~5.8k | ACTIVE; x86_64, 120GB disk, 16GB RAM |

Inspect AI: ~100+ evals via inspect_evals. Graders: match/includes/pattern/exact/f1/choice/math, model_graded_qa/model_graded_fact, custom scorers. Agents: ReAct loop, multi-agent, native tools (bash, python, editor, web, computer-use), MCP. Sandboxes: Docker, Kubernetes, Modal, Proxmox, Vagrant + extension API. CI: no --fail-on, no official Action; eval_set() returns (bool, list[EvalLog]) with resumable log dirs and retries. Storage: .eval logs, Inspect View, VS Code ext, dataframe export. Six entry-point-discovered extension types (model APIs, tasks/solvers/scorers/tools, sandboxes, approvers, hooks, filesystems).
lm-eval-harness: 60+ benchmarks; filter-pipeline grading; code execution unsandboxed (--confirm_run_unsafe_code); no agent loop; YAML tasks; no CI story.

## Tier 2: application eval frameworks

| Framework | URL | License | Version | Stars | CI gate |
|---|---|---|---|---|---|
| promptfoo | https://github.com/promptfoo/promptfoo | MIT | 0.122.2 (2026-08-28) | ~24.9k | promptfoo-action@v1, exit 100 on failure, PROMPTFOO_PASS_RATE_THRESHOLD, JUnit XML, PR comment, caching; ~35 assertion types incl trajectory:*; custom assertions unsandboxed |
| DeepEval | https://github.com/confident-ai/deepeval | Apache-2.0 | 4.2.0 (2026-08-24) | ~18.1k | pytest-native; ~50 metrics, 6 agentic, mostly LLM-judge; Tool Correctness single-turn only |
| RAGAS | https://github.com/explodinggradients/ragas | Apache-2.0 | 0.4.3 (2026-01-13) | ~15.6k | none; ~29 metrics, 4 agent/tool |
| Braintrust autoevals | https://github.com/braintrustdata/autoevals | MIT (platform closed) | | ~1.0k | eval-action@v2 PR comments; bt eval --first N |
| openevals / agentevals | https://github.com/langchain-ai/openevals https://github.com/langchain-ai/agentevals | MIT (LangSmith closed) | | ~1.2k / 717 | @pytest.mark.langsmith; agentevals: strict/unordered/subset/superset trajectory match + LangGraph graph-trajectory judges |
| Arize Phoenix | https://github.com/Arize-ai/phoenix | Elastic License 2.0 | | ~11.3k | none |
| MLflow GenAI eval | https://github.com/mlflow/mlflow | Apache-2.0 | | ~27.8k | none; 21 named judges |
| W&B Weave | https://github.com/wandb/weave | Apache-2.0 SDK, hosted backend | | ~1.1k | UNVERIFIED |
| Langfuse | https://github.com/langfuse/langfuse | MIT except ee/ | | ~34.3k | "block deploys on regressions" named, mechanics UNVERIFIED |
| Opik | https://github.com/comet-ml/opik | Apache-2.0 | | ~21.8k | UNVERIFIED |

Self-hostable observability: Opik, Langfuse. Braintrust/LangSmith/Weave/Phoenix keep tracking proprietary or non-OSI.

## Tier 3: security / red-team

| Tool | URL | License | Version | Stars | Notes |
|---|---|---|---|---|---|
| garak | https://github.com/NVIDIA/garak | Apache-2.0 | 0.16.0 (2026-08-04) | ~9.1k | ~21 probe modules; GOAT multi-turn + agent-breaker; JSONL + HTML; custom probes/detectors |
| PyRIT | https://github.com/microsoft/PyRIT (Azure/PyRIT archived) | MIT | 1.1.0 (2026-09-04) | ~4.4k | |
| Giskard | https://github.com/Giskard-AI/giskard | Apache-2.0 | 3.0.0 (2026-08-26) | ~5.8k | OWASP LLM Top-10 scanning |
| PurpleLlama / CyberSecEval | https://github.com/meta-llama/PurpleLlama | MIT | UNVERIFIED | ~4.4k | |

Anthropic: no maintained eval framework. Petri donated to Meridian Labs https://github.com/meridianlabs-ai/inspect_petri (MIT, built on Inspect). Cookbook: claude-cookbooks misc/building_evals.ipynb.

## Substrate recommendation (research agent)
Inspect AI core (plugin extension model, inspect_evals catalog, real sandboxing, agent/trajectory model, eval_set completion bool, institutional durability). Pair with promptfoo or a thin own layer for the gate (Inspect has no --fail-on/JUnit/Action). Skip Braintrust/LangSmith/Weave as substrate.

## CI quality gate patterns (primary sources)
- Anthropic, "Demystifying evals for AI agents", 2026-01-09 https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- Airbnb, "Eval-driven development", 2026-07-28 https://medium.com/airbnb-engineering/eval-driven-development-lessons-from-evaluating-genai-at-scale-e817e5ae5788 ; "From weeks to a day", 2026-07-14 https://medium.com/airbnb-engineering/from-weeks-to-a-day-how-we-made-llm-evaluation-fast-enough-to-iterate-on
- Vercel, "AI agent evaluation frameworks for production" https://vercel.com/i/ai-agent-evaluation-frameworks-production
- promptfoo GitHub Action https://www.promptfoo.dev/docs/integrations/github-action/
- DoorDash flywheel (blocked, UNVERIFIED); Cursor via Arize writeup (secondary, UNVERIFIED)

Eight recurring elements:
1. Cost-ordered ladder, cheapest first (regex/parse/import checks at zero token cost -> LLM judge -> human).
2. Small golden set in the repo (Anthropic: 20-50 tasks from real failures; Airbnb: 50-100 rows incl. bad examples, scale to ~5,000 later).
3. Judges calibrated against humans before gating (high-80s to 90s agreement, Cohen's kappa / Krippendorff's alpha; one judge per rubric dimension; "Unknown" escape hatch; 3-5 calibrated judges beat 20-30 noisy).
4. Non-determinism removed, not averaged: per-sample cache keyed on (sample, output, judge config, metric); ~3/4 of LLM references differ across runs, judge drifts ~1% vs 1-3% real signal; majority voting converges to judge tendency not accuracy; a difference that flips under judge swap isn't shippable.
5. Regression against a moving baseline, reported inside the PR (PR comment with before/after; exit code blocks merge).
6. Every production failure becomes a test case.
7. Trajectory grading, not just final answers (reconstruct trace tree; assert which subagents/tools ran; pass@k vs pass^k).
8. Cost control by sampling and caching (--first N smoke on PR, full suite at merge; 5% daily prod sample online).

## Job postings (retrieved 2026-09-07)
1. Airbnb, Senior Staff MLE, Data & Eval https://careers.airbnb.com/positions/6757302?gh_jid=6757302 : "Build and scale evaluation frameworks (golden sets, synthetic data, automated regressions, rubric-based grading, LLM-as-judge where appropriate) with strong controls for bias, drift, and reliability."
2. Databricks, Senior Staff Applied AI, Context Retrieval https://databricks.com/company/careers/open-positions/job?gh_jid=8540267002 : "Stand up offline evals (nDCG, MRR, Recall@K, Precision@K), LLM-as-judge harnesses, human-in-the-loop labeling, and online experimentation."
3. Coinbase, Staff MLE Platform https://www.coinbase.com/careers/positions/7891045?gh_jid=7891045 : "building the in-house evaluation layer that catches regressions before they reach users."
4. Cursor, SWE Agent Evaluation and Quality https://jobs.ashbyhq.com/cursor/2bbe9f02-83a5-4173-98be-9085d1cb5693 : "curated datasets, offline replay, scorers / judges, regression alerts, and dashboards."
5. Cursor, EM Evals https://jobs.ashbyhq.com/cursor/74a6ac48-d85f-45a0-9775-3cdb8b713e1a : "online evaluation systems that track agent quality in production, and the close integration between online and offline evaluations."
6. Harvey, Staff SWE AI Platform https://jobs.ashbyhq.com/harvey/01da8934-d3e3-4ebb-beb9-681b3c24fb9c : "shared eval tooling and frameworks that let every team ... measure and improve AI quality systematically."
7. Anthropic, RE Model Evaluations https://job-boards.greenhouse.io/anthropic/jobs/5198255008 : "distributed eval execution platform so hundreds of evals run reliably against checkpoints."
8. OpenAI, RE Frontier Evals https://jobs.ashbyhq.com/openai/bba18df5-f30f-4d2c-909c-30e651f95579 : GDPval, SWE-bench Verified, MLE-bench, PaperBench, SWE-Lancer.
9. Scale AI, RS Frontier Risk Evals https://job-boards.greenhouse.io/scaleai/jobs/4677657005 : "evaluation measures, harnesses and datasets for measuring the risks."
Themes: own eval infra as a platform (6/9); offline+online paired (4); regression catching (3); calibrated LLM-judge (3); golden datasets + HITL (3); agent/trajectory quality (3). No posting names a framework.
