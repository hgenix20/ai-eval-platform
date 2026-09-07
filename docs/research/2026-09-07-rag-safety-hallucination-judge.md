# RAG / hallucination / safety / injection / judge benchmarks, verified inventory, 2026-09-07

Source: research agent, web-verified. UNVERIFIED = not confirmed at a primary source.

## (a) Retrieval / RAG

| Name | Maintainer / URL | Measures | Size | License | Scoring | HF id / runner | Cost |
|---|---|---|---|---|---|---|---|
| BEIR | UKP https://github.com/beir-cellar/beir | zero-shot IR, 18 datasets | 18 datasets | Apache-2.0 code, per-dataset data licenses | nDCG/MAP/Recall | BeIR/*, pip install beir | free CPU, GPU for embedding |
| MTEB v2 / MMTEB | https://github.com/embeddings-benchmark/mteb | 8 embedding task types | MTEB(eng,v2) = 41 datasets; MMTEB 500+ | Apache-2.0 code, mixed data | nDCG@10 | pip install mteb | free to GPU-hours |
| RAGAS metrics | https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/ | faithfulness, context precision/recall, answer relevancy on your data | library | UNVERIFIED (Apache-2.0 reported) | LLM-judge; non-LLM FaithfulnessWithHHEM option | pip install ragas | $ per judge call |
| RAGBench | Galileo https://huggingface.co/datasets/galileo-ai/ragbench arXiv 2407.11005 | TRACe: adherence, relevance, utilization, completeness; 12 subsets | ~100k | CC-BY-4.0 | labels + LLM-judge comparison | galileo-ai/ragbench | free |
| CRAG | Meta https://github.com/facebookresearch/CRAG/ | factual QA w/ hallucination-aware scoring, mock web+KG APIs | 4,409 | CC BY-NC 4.0 | rule + LLM-judge +1/0/-1 | GitHub + AIcrowd mock API | $ judge |
| FRAMES | Google https://huggingface.co/datasets/google/frames-benchmark | multi-hop retrieval + reasoning | 824 | Apache-2.0 | UNVERIFIED | google/frames-benchmark; community Inspect | low |
| HotpotQA | https://hotpotqa.github.io/ | multi-hop QA + supporting facts | ~113k; dev 7,405 | CC BY-SA 4.0 | EM/F1 | hotpotqa/hotpot_qa, BeIR/hotpotqa | free |
| Natural Questions | Google https://github.com/google-research-datasets/natural-questions | long+short answer | 307k/7.8k/7.8k | Apache-2.0 | F1 | google-research-datasets/natural_questions | free |
| BRIGHT | XLang https://github.com/xlang-ai/BRIGHT | reasoning-intensive retrieval, 12 domains | 1,384 queries | CC-BY-4.0 | nDCG@10 | HF; in MTEB | free to GPU |
| RTEB | https://github.com/embedding-benchmark/rteb | production-domain retrieval, open + held-out private tiers | UNVERIFIED | UNVERIFIED (README "to be added") | nDCG@10 | python -m rteb | free to GPU |
| MultiHop-RAG | HKUST https://github.com/yixuantt/MultiHop-RAG/ | multi-hop RAG over news | 609 articles | UNVERIFIED | UNVERIFIED | GitHub | free |
| HELMET / LongBench v2 | Princeton / THUDM | long-context incl RAG-style to 128K | UNVERIFIED | UNVERIFIED | mixed | repo; LongBench v2 in lm-eval | GPU-hours |

Caveats: BEIR/RAGBench licensing is per-subset. CRAG non-commercial. RAGAS results move with the judge model; RAGBench paper found a fine-tuned RoBERTa beating LLM judges. RTEB has no license text. NQ/HotpotQA persist only as subsets. BRIGHT: top MTEB model drops nDCG@10 59.0 -> 18.3.

## (b) Hallucination / factuality

| Name | Maintainer / URL | Measures | Size | License | Scoring | HF id / runner |
|---|---|---|---|---|---|---|
| TruthfulQA | https://github.com/sylinrl/TruthfulQA | imitative falsehoods, 38 categories | 817 | Apache-2.0 | MC1/MC2 | truthfulqa/truthful_qa; lm-eval, Inspect truthfulqa |
| HaluEval | RUCAIBox https://github.com/RUCAIBox/HaluEval | binary hallucination recognition, 4 task types | 35,000 | MIT | binary accuracy | flowaicom/HaluEval |
| HaluEval 2.0 | UNVERIFIED | broader taxonomy, 5 domains | 8,770 (secondary) | UNVERIFIED | trained auto-evaluator | UNVERIFIED, no official repo found |
| FActScore | UW/Meta https://github.com/shmsw25/FActScore | long-form factual precision via atomic facts vs Wikipedia | 183 labeled + 500 unlabeled | MIT | retrieval + ChatGPT | pip install factscore; ~$1/100 sentences |
| SimpleQA | OpenAI https://github.com/openai/simple-evals | short-form closed-book factuality | 4,326 | MIT | LLM-judge correct/incorrect/not-attempted | Inspect simpleqa; repo unmaintained since Jul 2025 |
| SimpleQA Verified | DeepMind https://huggingface.co/datasets/google/simpleqa-verified arXiv 2509.07968 | de-duplicated successor | 1,000 | UNVERIFIED | LLM-judge F1-style | google/simpleqa-verified; Kaggle LB; Inspect |
| FACTS Grounding | DeepMind https://www.kaggle.com/benchmarks/google/facts-grounding | grounded long-document faithfulness | 860 public + held-out | CC-BY-4.0 | ensemble frontier judges | google/FACTS-grounding-public |
| HHEM-2.1-Open / Vectara LB | https://github.com/vectara/hallucination-leaderboard | summarization faithfulness (NLI-style) | LB corpus 7,700+ private | Apache-2.0 | trained classifier (FLAN-T5-Base), deterministic | vectara/hallucination_evaluation_model, <600MB, CPU-runnable; public LB runs closed HHEM-2.3 |
| BrowseComp | OpenAI arXiv 2504.12516 | agentic live-web factfinding | 1,266 | MIT | short-answer match | in simple-evals |
| LongFact / SAFE | DeepMind https://github.com/google-deepmind/long-form-factuality | long-form open-domain factuality | 2,280 prompts | Apache-2.0 / CC-BY-4.0 | SAFE via live Google Search | repo; needs Search API quota |
| HalluLens | Meta FAIR https://github.com/facebookresearch/HalluLens | extrinsic vs intrinsic | dynamically generated per run | CC-BY-NC mostly | LLM-judge | repo |
| RAGTruth | https://github.com/ParticleMedia/RAGTruth | span-level RAG hallucination | ~17,790 responses / 14,289 spans | MIT | human span annotation | repo |
| FaithBench | Vectara https://github.com/vectara/FaithBench | detector-disagreement summarization cases | UNVERIFIED | UNVERIFIED | human 4-way span labels | repo + FaithJudge |

Caveats: TruthfulQA aging (Jan 2025 update deleted a category); prefer SimpleQA Verified; FACTS public 860 is a dev set; Vectara LB corpus not released; SAFE costs Search quota; HaluEval's 2023 hallucinations easy for 2026 models.

## (c) Safety / jailbreak

| Name | Maintainer | Size | License | Scoring | Access | Inspect |
|---|---|---|---|---|---|---|
| HarmBench https://github.com/centerforaisafety/HarmBench | CAIS | 510 behaviors (400 text + 110 MM) | MIT code | classifier cais/HarmBench-Llama-2-13b-cls | open | harmbench |
| JailbreakBench https://github.com/JailbreakBench/jailbreakbench | JBB | 200 (100 harmful/100 benign) | MIT | Llama3-70B judge + 8B refusal judge | JailbreakBench/JBB-Behaviors | absent |
| StrongREJECT https://github.com/dsbowen/strong_reject | Souly/Bowen | 313 (60 subset) | MIT | rubric judge refusal x convincingness x specificity | pip | present |
| XSTest https://github.com/paul-rottger/xstest | Rottger | 450 (250 safe / 200 unsafe) | CC-BY-4.0 | compliance/refusal | Paul/XSTest | xstest |
| AILuminate https://mlcommons.org/ailuminate/ | MLCommons | demo 1,200 / practice 12,000 gated / test 12,000 held out | CC-BY-4.0 (demo/practice) | tuned ensemble via ModelBench | partly gated | absent |
| SORRY-Bench https://github.com/sorry-bench/sorry-bench | Xie, Qi | 440 x 44 categories, 20 mutations | MIT | fine-tuned Mistral-7B classifier | sorry-bench/sorry-bench-202503 | absent |
| AgentHarm https://huggingface.co/datasets/ai-safety-institute/AgentHarm | UK AISI + Gray Swan | 110/440 | MIT + safety-research clause | deterministic graders + refusal judge | open | agentharm |
| OR-Bench https://huggingface.co/datasets/bench-llm/or-bench | Cui, ICML'25 | 80,400 / Hard-1K 1,320 / Toxic 655 | CC-BY-4.0 | over-refusal via GPT-4-class judge | open | Hard-1K present |
| WildGuardMix / WildJailbreak | AI2 | 86,759+1,725 / 262K | ODC-BY | allenai/wildguard 7B Apache-2.0 | GATED | absent |
| SafetyBench https://github.com/thu-coai/SafetyBench | Tsinghua | 11,435 MCQ | MIT | MCQ | open | absent |

Also in inspect_evals: Do-Not-Answer, FORTRESS, SALAD-Bench, SOS-Bench, AIR-Bench. Caveats: SafetyBench released test answers Jul 2025; OR-Bench is the scaled successor to XSTest; AgentHarm without augmentation near-saturated (ASR 1.5-1.9%); HarmBench/SORRY-Bench/WildGuard need a 7B-13B classifier GPU.

## (d) Prompt injection / agent security

| Name | Maintainer / URL | Measures | Size | License | Scoring | Runner |
|---|---|---|---|---|---|---|
| AgentDojo https://github.com/ethz-spylab/agentdojo | ETH Zurich | utility and attack success jointly, 4 suites | 97 tasks, 629 security cases | MIT | deterministic per-task checkers | pip install agentdojo; Inspect agentdojo |
| InjecAgent https://github.com/uiuc-kang-lab/InjecAgent | UIUC | indirect injection to tool misuse | 1,054 cases | MIT | rule-based ASR | own scripts |
| BIPIA https://github.com/microsoft/BIPIA | Microsoft | indirect injection, 5 task types | UNVERIFIED | MIT | LLM-judge | own scripts |
| Gandalf https://huggingface.co/collections/Lakera/gandalf-65a034d1074bfce80224f6dc | Lakera | hosted game; derived corpora only | 1,000 / 279k | MIT | none | classifier training only |
| OWASP LLM Top 10 / Agentic Top 10 (2026) https://genai.owasp.org/initiatives/top-10-for-llm-and-genai/ | OWASP | taxonomy only, no dataset | N/A | CC | N/A | N/A |
| CyberSecEval 4 https://github.com/meta-llama/PurpleLlama/blob/main/CybersecurityBenchmarks/README.md | Meta | 9 sub-benchmarks; prompt injection is one | MITRE ~100/category; AutoPatchBench 142/120/20 | UNVERIFIED | mixed | CybersecurityBenchmarks.benchmark.run; Inspect cyberseceval_2/3/4 |
| ASB https://github.com/agiresearch/ASB | Rutgers | attacks+defenses across prompt/tool/memory/plan | 10 scenarios, 400+ tools, ~9e4 cases | MIT | ASR + rejection | own on AIOS |
| WASP https://github.com/facebookresearch/wasp | Meta FAIR | web-agent injection | UNVERIFIED | CC-BY-NC 4.0 | LLM-judge | own; possibly archived 2026-07-01 UNVERIFIED |
| MCPSecBench arXiv 2508.13220 | academic | MCP tool poisoning | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| Gray Swan ART | Gray Swan | user-side + indirect injection | not released | proprietary | | |

Cost: hundreds to tens of thousands of agentic calls per model, $10s-$100s. CyberSecEval 1 superseded; Gandalf public levels saturated.

## (e) LLM-as-judge quality

| Name | Maintainer / URL | Evaluates | Size | License | Scoring | Runner / cost |
|---|---|---|---|---|---|---|
| MT-Bench https://github.com/lm-sys/FastChat | LMSYS | models via GPT-4 judge | 80 | Apache-2.0 | LLM-judge | fastchat/llm_judge ~$10 |
| Arena-Hard-Auto v2.0 https://github.com/lmarena/arena-hard-auto | LMArena | models via judge | 500 hard + 250 creative | Apache-2.0 | Gemini-2.5 primary, GPT-4.1 alt | v0.1 cost $25 |
| AlpacaEval 2.0 LC https://github.com/tatsu-lab/alpaca_eval | Stanford | length-controlled win rate | 805 | Apache-2.0 | GPT-4-Turbo judge | <$10, <3 min |
| JudgeBench https://github.com/ScalerLab/JudgeBench | ScalerLab ICLR'25 | the judge, on objective hard pairs | 620 pairs | UNVERIFIED | accuracy | run_judge.py; HF LB |
| RewardBench 2 https://github.com/allenai/reward-bench | Ai2 ICLR'26 | reward models, best-of-4 | 1,865 | Apache-2.0 code, ODC-BY data | GPU forward pass or generative judge | pip install rewardbench; allenai/reward-bench-2 |
| PPE https://github.com/lmarena/PPE | LMArena | reward models vs human preference | 16K pairs + correctness sets | UNVERIFIED | accuracy | repo |
| RM-Bench | academic | style vs content bias | UNVERIFIED | UNVERIFIED | accuracy | UNVERIFIED |

Saturation: MT-Bench agreement with Chatbot Arena 26.1%, separability 22.6% (Arena-Hard 89.1/87.4) https://lmsys.org/blog/2024-04-19-arena-hard/ . AlpacaEval last release Mar 2024. RewardBench v1 saturated; v2 r=0.87 with best-of-N (arXiv 2506.01937). Judge failure modes: position bias, verbosity bias, self-preference.

## Gaps with no good public benchmark

1. Agent trajectory quality (path efficiency/sensibility independent of outcome).
2. Tool-use error recovery (retry behavior after failed/malformed calls; fault injection).
3. Cost and latency regression as a failing result (only BFCL reports cost/latency alongside accuracy).
4. Multi-turn memory (LongMemEval closest, GPT-4o judged; writes/conflict/forgetting uncovered).
5. Deterministic grading of open-ended output (pin judge versions or history is meaningless).
6. Cross-benchmark contamination tracking (held-out splits mean headline numbers are not locally reproducible; run open subset, cite leaderboard for the rest).

inspect_evals confirmed: truthfulqa, simpleqa, harmbench, xstest, strongreject, or-bench, agentharm, agentdojo, cyberseceval_2/3/4, do_not_answer. Absent: JailbreakBench, SORRY-Bench, AILuminate, WildGuard, SafetyBench, InjecAgent, BIPIA, WASP, ASB.
