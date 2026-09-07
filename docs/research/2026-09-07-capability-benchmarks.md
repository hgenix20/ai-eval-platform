# Mainstream Public LLM Benchmarks, verified inventory, 2026-09-07

Source: research agent (web-verified against repos, HF cards, arXiv, leaderboards). UNVERIFIED = not confirmed at a primary source. Dollar costs are scaffold-dependent and UNVERIFIED throughout.

## (a) General capability / reasoning / math

| Benchmark | Maintainer / URL | N | License | Scoring | HF id | Runner | Saturated? |
|---|---|---|---|---|---|---|---|
| MMLU | Hendrycks et al. https://huggingface.co/datasets/cais/mmlu | 14,042 test | MIT | exact-match MC | cais/mmlu | lm-eval mmlu; Inspect mmlu | Yes, ~91-92% ceiling; dropped from most 2026 model cards |
| MMLU-Pro | TIGER-Lab https://github.com/TIGER-AI-Lab/MMLU-Pro | 12,032 (10-option) | MIT | exact-match + CoT | TIGER-Lab/MMLU-Pro | lm-eval mmlu_pro (v3, Jan 2026); Inspect mmlu_pro | Approaching, top ~88% |
| GPQA Diamond | Rein et al. https://github.com/idavidrein/gpqa | 198 (Main 448, Ext 546) | MIT code / CC-BY-4.0 card (conflict, UNVERIFIED) | exact-match MC | idavidrein/gpqa (gated) | lm-eval gpqa_diamond_zeroshot; Inspect gpqa | Near: 91-94% vs 65% PhD baseline; still in every system card |
| HLE | CAIS + Scale AI https://huggingface.co/datasets/cais/hle | 2,500 (2,158 text-only) | MIT | exact-match + LLM-judge short answer | cais/hle, cais/hle-rolling | official repo; Inspect hle | No (37-44%) but ~30% of chem/bio answers disputed (FutureHouse); use hle-rolling |
| ARC-AGI-1 | ARC Prize https://github.com/fchollet/ARC-AGI | 800 | Apache-2.0 | exact grid match | none | ARC Prize / Kaggle | Yes, 87-98% |
| ARC-AGI-2 | ARC Prize https://github.com/arcprize/ARC-AGI-2 | 1,000 train + 120x3 eval | Apache-2.0 | exact grid match + $/task | none | ARC Prize / Kaggle | Not yet, climbing fast |
| ARC-AGI-3 | ARC Prize https://arcprize.org/arc-agi/3 | hundreds of interactive envs, UNVERIFIED | UNVERIFIED | episodic env scoring | none | ARC Prize 2026 | No, best <1% |
| AIME 2024/25/26 | MAA / MathArena https://huggingface.co/datasets/MathArena/aime_2025 | 30/yr | CC-BY-NC-SA-4.0 (MathArena); MIT (Maxwell-Jia/AIME_2024) | exact-match int | MathArena/aime_2026 | Inspect aime2024/2025/2026 | 2024/25 saturated (100% reported); 2026 fresh |
| FrontierMath | Epoch AI https://epoch.ai/frontiermath/tiers-1-4/about | 338, only 12 public | UNVERIFIED | execution / exact | held out | Epoch private infra only | No, SOTA ~40% |
| GSM8K | OpenAI https://huggingface.co/datasets/openai/gsm8k | 1,319 test | MIT | exact-match | openai/gsm8k | lm-eval gsm8k | Fully saturated, deprecated |
| MATH-500 | OpenAI/Hendrycks https://huggingface.co/datasets/HuggingFaceH4/MATH-500 | 500 | UNVERIFIED | exact-match normalized | HuggingFaceH4/MATH-500 | lm-eval minerva_math | Saturated (95-98%) |
| LiveBench | Abacus.AI/NYU https://github.com/livebench/livebench | 18-23 tasks, refreshed monthly | UNVERIFIED | objective ground truth, no LLM judge | livebench/{math,coding,...} | run_livebench.py | No, contamination-resistant |
| SuperGPQA | ByteDance Seed https://huggingface.co/datasets/m-a-p/SuperGPQA | 26,529, 285 disciplines | UNVERIFIED | exact-match MC | m-a-p/SuperGPQA | own repo | No, frontier 60-65% |
| BBEH | Google arXiv:2502.19187 | replaces 23 BBH tasks | UNVERIFIED | exact-match | none | Inspect bbeh | No (BBH itself >90%) |
| SimpleQA / BrowseComp | OpenAI https://github.com/openai/simple-evals | 4,326 / 1,266 | MIT | LLM-judge | in repo (BrowseComp encrypted) | Inspect browse_comp | SimpleQA -> SimpleQA Verified (1,000); BrowseComp o3 89.8% |

Also verified: MMLU-Redux-2.0 (5,700, CC-BY-4.0), IFEval (541, Apache-2.0, deterministic checkers, still live), MuSR, HMMT. DROP is retired (no 2026 model card cites it).

## (b) Coding

| Benchmark | Maintainer / URL | N | License | Scoring | HF id | Runner | Saturated? |
|---|---|---|---|---|---|---|---|
| SWE-bench Verified | https://www.swebench.com/ | 500 | MIT | execution, Docker | SWE-bench/SWE-bench_Verified | swebench pip v5; Inspect swe_bench | Yes. Open leaderboard plateau 79.2% (Dec 2025); labs self-report to 95%. OpenAI: "Why SWE-bench Verified no longer measures frontier coding capabilities" |
| SWE-bench full/Lite/MM/Multilingual | same | 2,294 / 300 / 480 / 300 | MIT | execution | SWE-bench/* | same | 52.6 / 60.3 / 36.0 / 72.7% |
| SWE-bench Pro | Scale AI https://huggingface.co/datasets/ScaleAI/SWE-bench_Pro | 731 public / 858 held-out / 276 commercial | UNVERIFIED (GPL sources) | execution, Docker | ScaleAI/SWE-bench_Pro | own harness | No, top 61.5% |
| SWE-bench Live | Microsoft https://github.com/microsoft/SWE-bench-Live | 1,888 growing ~50/mo | MIT | execution | yes | own harness | No, contamination-resistant |
| SWE-rebench | Nebius https://swe-rebench.com | rolling ~111 window of 6,542 | CC-BY-4.0 | execution | nebius/SWE-rebench | own harness | No, 62-65% |
| Multi-SWE-bench | ByteDance https://github.com/multi-swe-bench/multi-swe-bench | 1,632, 7 langs | Apache-2.0 (data CC0) | execution, Docker | ByteDance-Seed/Multi-SWE-bench | own | UNVERIFIED |
| Terminal-Bench | Stanford/Harbor/Laude https://www.tbench.ai/ | v4.0 = 66 tasks; v2.1 = 89 | Apache-2.0 | execution in container, Docker required | harborframework/terminal-bench-2.0 | tb CLI (pip install terminal-bench) | No, 4.0 SOTA ~58%; maintainers drop saturated tasks |
| LiveCodeBench | https://github.com/LiveCodeBench/LiveCodeBench | v6 = 1,055 rolling | MIT | execution pass@1 | livecodebench/code_generation_lite | lcb_runner, no Docker | Approaching, 90-92% |
| LiveCodeBench Pro | https://livecodebenchpro.com | 584 Olympiad/ICPC | UNVERIFIED | execution via judge server | QAQAQAQAQ/LiveCodeBench-Pro | own, Docker | No, 53% medium, 0% hard |
| Aider Polyglot | https://aider.chat/docs/leaderboards/ | 225 Exercism, 6 langs | per-track UNVERIFIED | execution | unofficial mirror | in aider repo | No, top 88%. Publishes cost: $29.08 / 5.3M tokens per full run |
| SWE-Lancer | OpenAI arXiv:2502.12115 | 1,488; Diamond 502 | CC-BY-4.0 | execution + manager grading | none | Inspect swe_lancer | Repo archived; UNVERIFIED |
| BigCodeBench | https://github.com/bigcode-project/bigcodebench | 1,140 (Hard 148) | Apache-2.0 | execution pass@k | bigcode/bigcodebench | bigcodebench pip; Inspect | UNVERIFIED |
| SciCode | https://github.com/scicode-bench/SciCode | 80 main / 338 sub | Apache-2.0 | execution | SciCode1/SciCode | ships an Inspect harness | No, ~10.8% main |
| HumanEval / MBPP (+EvalPlus) | OpenAI / Google / EvalPlus | 164 / 974 (MBPP+ 378) | MIT / CC-BY-4.0 / Apache-2.0 | execution | openai/openai_humaneval, evalplus/* | lm-eval, evalplus pip | Saturated, deprecated (95-97%) |

CRUXEval archived read-only 2025-09-18. APPS and CodeContests superseded by LiveCodeBench. Also verified: SWE-PolyBench (Amazon, 2,110, MIT), SWE-smith (52k, MIT), Commit0, RepoBench (exact-match), KernelBench (270, real GPU), CodeElo (408, Codeforces judge).

## (c) Tool calling / function calling

| Benchmark | Maintainer / URL | N | License | Scoring | Runner | Saturated? |
|---|---|---|---|---|---|---|
| BFCL V4 | UC Berkeley Gorilla https://gorilla.cs.berkeley.edu/leaderboard.html | V1 ~1,660 + V2-Live ~2,251 + V3 multi-turn 1,000 + V4 web-search 100 | Apache-2.0 | AST match (V1/V2), state comparison (V3), task-specific (V4) | pip install bfcl-eval; Inspect bfcl (5,092 samples) | V1/V2 saturated; V4 agentic not (memory-management ~12%) |
| tau-bench | Sierra https://github.com/sierra-research/tau-bench | 165 (115 retail + 50 airline) | MIT | DB state comparison, pass^k | own harness | Not saturated; needs user-simulator LLM |
| tau2-bench / tau3-bench | Sierra https://github.com/sierra-research/tau2-bench | per-domain UNVERIFIED | MIT | state/action comparison | tau2 CLI --user-llm; Inspect tau2_airline | Repo ships tau3-bench v1.0.1 (telecom + banking_knowledge + full-duplex voice) |
| ACEBench | USTC + Huawei https://github.com/chenchen0103/ACEBench | 2,000, 4,538 APIs | MIT | LLM-free: AST + binary + process | generate.py/eval_main.py | No |
| ComplexFuncBench | Zhipu https://github.com/zai-org/ComplexFuncBench | 1,000, 128K ctx | UNVERIFIED | ComplexEval | own, vLLM 131k | No |
| MCP-Universe | arXiv:2508.14704 | 11 MCP servers / 6 domains | UNVERIFIED | format + static + dynamic evaluators | own | No, GPT-5 43.7% |
| MCPMark | https://mcpmark.ai | 127 tasks, 5 servers | UNVERIFIED | programmatic, pass@1 / pass^4 | own | No, best 52.6% pass@1 |
| MCP-Bench | Accenture https://github.com/Accenture/mcp-bench | 28 MCP servers | Apache-2.0 | rule + LLM-judge (o4-mini) | own | GPT-5 0.749 |

ToolBench/ToolLLM, API-Bank, ToolTalk, Nexus are 2023-era legacy. "MCP-Bench" names two distinct projects; key registry on URL.

## (d) Agents / multi-step / computer use

| Benchmark | Maintainer / URL | N | License | Scoring | Infra | Inspect task | Saturated? |
|---|---|---|---|---|---|---|---|
| GAIA | Meta FAIR + HF https://huggingface.co/datasets/gaia-benchmark/GAIA | 466 (test private) | UNVERIFIED | quasi-exact-match | tools only | gaia, gaia_level1/2/3 | UNVERIFIED; no GAIA-2 exists |
| GDPval | OpenAI https://huggingface.co/datasets/openai/gdpval | 1,320 full / 220 public gold, 44 occupations | CC-BY-4.0 | human-expert rubric | none | gdpval | No |
| OSWorld / Verified / 2.0 | XLang https://github.com/xlang-ai/OSWorld | 369 | Apache-2.0 | execution, 134 eval fns | full desktop VM | osworld, osworld_small | Use Verified; OSWorld 2.0 shipped 2026-06-26 |
| TheAgentCompany | CMU/OpenHands https://github.com/TheAgentCompany/TheAgentCompany | 175 | MIT | result + subcheckpoint partial credit | Docker Compose 30+GB | theagentcompany | UNVERIFIED |
| Mind2Web 2 | OSU + Amazon arXiv:2506.21506 | 130 | MIT | Agent-as-a-Judge rubric | live web | none | 50-70% of human |
| BrowseComp / -ZH | OpenAI / Zhou | 1,266 / 289 | MIT / UNVERIFIED | LLM-judge / short-answer | live web | browse_comp (EN) | o3 89.8% EN; ZH 42.9% |
| WebArena | https://github.com/web-arena-x/webarena | 812 | Apache-2.0 | env-state | Docker/AMI | none | Superseded in practice; last update Dec 2024 |
| VisualWebArena | web-arena-x | 910 | MIT | execution | Docker/AMI | none | last activity Aug 2024 |
| AndroidWorld | Google https://github.com/google-research/android_world | 116 tasks, 20 apps | Apache-2.0 | env-state | Android emulator | none | UNVERIFIED |
| WorkArena / ++ | ServiceNow https://github.com/ServiceNow/WorkArena | 19,912 L1; 682 L2/L3 | Apache-2.0 | programmatic | live ServiceNow + Playwright | none | UNVERIFIED |
| CRMArena / Pro | Salesforce Salesforce/CRMArena | UNVERIFIED | CC BY-NC 4.0 (non-commercial) | UNVERIFIED | UNVERIFIED | none | Pro accepted TMLR |
| AgentHarm | UK AISI + Gray Swan https://huggingface.co/datasets/ai-safety-institute/AgentHarm | 110 / 440 | MIT + safety-use restriction | dual LLM-judge | none | agentharm | N/A |
| HAL | Princeton https://hal.cs.princeton.edu/ | meta-leaderboard over 9 benchmarks | UNVERIFIED | reuses each + $/run | varies | n/a | Cost-accuracy Pareto; princeton-pli/hal-harness is a reference architecture |
| METR time-horizon / RE-Bench | METR https://github.com/METR/ai-rd-tasks | RE-Bench 8 families; HCAST 189 tasks | MIT | logistic fit to human task duration | heavy | none | Non-saturating by construction |
| AgentBench | THUDM https://github.com/THUDM/AgentBench | 8 envs | Apache-2.0 | per-env state | Docker | agent_bench_os (OS subset, 151) | Maintained but legacy |
| AgentRewardBench | Mila/McGill arXiv:2504.08942 | 1,302 trajectories | UNVERIFIED | human expert ratings | offline | none | Finding: rule-based scoring under-reports agent success vs human judgment |

WebVoyager frozen; WindowsAgentArena inactive since Nov 2024; webgames.ai is a parked domain (real: webgames.convergence.ai).

## (e) Long-context

| Benchmark | Maintainer / URL | N | License | Scoring | HF id | Token cost | Saturated? |
|---|---|---|---|---|---|---|---|
| RULER | NVIDIA https://github.com/NVIDIA/RULER | 13 tasks x 500/tier; 4K-128K | Apache-2.0 | exact/recall | synthetic generator | ~1.68B input tokens full pass | NIAH saturated; VT/aggregation discriminate |
| LongBench v2 | THUDM https://github.com/THUDM/LongBench | 503 MC | MIT | exact MC | THUDM/LongBench-v2 | 8K-2M words/item | Human 53.7%, best model 50.1% |
| HELMET | Princeton https://github.com/princeton-nlp/HELMET | 7 categories | MIT | EM/F1/ROUGE + GPT-4o judge | princeton-nlp/HELMET (~34GB) | high | Adopted by Phi-4, Jamba 1.6 |
| MRCR (OpenAI) | https://huggingface.co/datasets/openai/mrcr | 2,400 rows, to 1M tokens | MIT | difflib ratio + anti-cheat hash | openai/mrcr | 1M bin ~100M+ tokens | No, the 1M discriminator |
| MRCR v2 | DeepMind https://github.com/google-deepmind/eval_hub | UNVERIFIED | UNVERIFIED | exact reproduction | none | scales to 8M | No |
| InfiniteBench | OpenBMB https://github.com/OpenBMB/InfiniteBench | 3,932 | Apache-2.0 | accuracy + ROUGE | xinrongzhang2022/InfiniteBench | hundreds of millions | UNVERIFIED |
| NoLiMa | Adobe https://github.com/adobe-research/NoLiMa | UNVERIFIED | Adobe Research License, non-commercial | accuracy | amodaresi/NoLiMa | moderate | No: GPT-4o 99.3% -> 69.7% without literal match |
| BABILong | https://github.com/booydar/babilong | 25,000, tiers to 1M | Apache-2.0 code | UNVERIFIED | RMT-team/babilong | ~2B tokens for 1M tier | No |
| LOFT | DeepMind https://github.com/google-deepmind/loft | 35 datasets to 1M | Apache-2.0 / CC-BY-4.0 | recall@1, exec_acc, EM | direct | very high | UNVERIFIED |
| NIAH | Kamradt https://github.com/gkamradt/LLMTest_NeedleInAHaystack | generator | MIT | exact | none | small | Trivially solved |
| LV-Eval | https://github.com/infinigence/LVEval | ~1,500 to 256K | CC-BY-SA-4.0 + MIT | keyword recall then F1 | Infinigence/LVEval | <=384M | UNVERIFIED |
| LongProc | Princeton https://github.com/princeton-pli/LongProc | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | output-dominated | No |

Also: LongCodeBench (1,043, Apache-2.0), LongICLBench (MIT), OOLONG (Nov 2025, MIT, aggregation; scripts "coming soon"), LoCoBench, BEAM (10M). ZeroSCROLLS legacy. Fiction.LiveBench not peer-reviewed, no license.

## What changed in 2025-2026

1. Saturation hit the 2021-2024 canon: GSM8K, MATH-500, MMLU, BBH, HumanEval, MBPP, ARC-AGI-1, AIME 2024/25 retired for frontier comparison. Artificial Analysis Intelligence Index v4.2 contains none of MMLU, GPQA, HumanEval, SWE-bench, AIME; its ten components: AA-Briefcase, GDPval-AA v2, tau3-Banking, Terminal-Bench v2.1, SciCode, AA-Omniscience, GDP.pdf, AA-LCR, HLE, CritPt.
2. SWE-bench Verified plateaued at 79.2% open; replacements SWE-bench Pro, Terminal-Bench 4.0, SWE-bench Live, SWE-rebench, Multi-SWE-bench. SWE-MERA: 32.67% of successful patches involved solution leakage, 31.08% passed only due to inadequate tests.
3. Contamination resistance is a design requirement: rolling refresh, private held-out splits, encryption + canaries, gated downloads.
4. Benchmarks moved from questions to work: GDPval, TheAgentCompany, WorkArena, CRMArena, METR time-horizon (cannot saturate).
5. Tool calling split into three tiers: syntactic AST (solved), state-comparison multi-turn (discriminates), agentic MCP (29-75%).
6. Long-context abandoned the needle: RULER, HELMET, NoLiMa, MRCR, LongBench v2, OOLONG.
7. Reported vs reproducible scores diverged (scaffold). HAL's cost-vs-accuracy framing and AgentRewardBench's finding (rule-based under-reports vs human) are methodology to build in.

## Runner coverage

Inspect AI inspect_evals tasks verified: swe_bench, swe_lancer, gaia(+levels), osworld, browse_comp, bfcl, tau2_airline, theagentcompany, gdpval, mind2web, agent_bench_os, agentharm, mmlu, mmlu_pro, gpqa, hle, aime2024/2025/2026, gsm8k, math, humaneval, mbpp, bigcodebench, livecodebench_pro, scicode, apps, kernelbench, niah, bbh, bbeh, ifeval, drop.
Absent (custom harness needed): WebArena, VisualWebArena, WebVoyager, WebGames, WindowsAgentArena, AndroidWorld, Mind2Web 2, BrowseComp-ZH, DeepResearch Bench, Terminal-Bench, CRMArena, WorkArena, RULER, LongBench, ARC-AGI, METR/RE-Bench, full AgentBench.
lm-eval-harness: mmlu, mmlu_pro v3, gpqa, gsm8k, bbh, ifeval, drop, humaneval, mbpp, longbench, arc, agieval, leaderboard group; no HLE, RULER, BFCL, BigCodeBench, LiveCodeBench.
Legal flags: CRMArena CC BY-NC 4.0; NoLiMa non-commercial; GPQA license ambiguous.
