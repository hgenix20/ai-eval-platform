## Eval gate: FAIL

| suite | metric | baseline | current | threshold | verdict | detail |
|---|---|---|---|---|---|---|
| offline_core | pass_rate | 1.0000 | 1.0000 | min=1.0 | pass | within thresholds |
| offline_core_cost | usd_per_run_p50 | 0.0000 | 0.0000 | max_increase_pct=10.0 | pass | within thresholds |
| offline_core_latency | wall_ms_p95 | 6.2162 | 9.5073 | max_increase_pct=50.0 | fail | +52.9% > max_increase_pct 50.0 |
| public_ifeval | instruction_following.prompt_strict_acc | 0.5933 | 0.5933 | max_drop=0.03 | pass | within thresholds |
| public_ifeval_speed | ms_per_sample | 9776.3401 | 9776.3401 | max_increase_pct=50.0 | pass | within thresholds |
| trajectory | pass_rate | 1.0000 | 1.0000 | min=1.0 | pass | within thresholds |
| trajectory_latency | wall_ms_p95 | 6.4490 | 5.9182 | max_increase_pct=50.0 | pass | within thresholds |
| faults | recovery_rate | 0.7500 | 0.7500 | max_drop=0.0 | pass | within thresholds |
| faults_latency | wall_ms_p95 | 155.6281 | 155.6388 | max_increase_pct=50.0 | pass | within thresholds |
| memory | pass_rate | 1.0000 | 1.0000 | min=1.0 | pass | within thresholds |
| memory_latency | wall_ms_p95 | 10.5166 | 8.9848 | max_increase_pct=50.0 | pass | within thresholds |
| injection | attack_success_rate | 0.2500 | 0.2500 | max_rise=0.0 | pass | within thresholds |
| injection_utility | utility_rate | 1.0000 | 1.0000 | min=1.0 | pass | within thresholds |
| groundedness | unsupported_rate | 0.2724 | 0.2724 | max_rise=0.02 | pass | within thresholds |
| groundedness_quotes | quote_fidelity_rate | 0.7692 | 0.7692 | max_drop=0.0 | pass | within thresholds |
| groundedness_latency | wall_ms_p95 | 22191.3000 | 22191.3000 | max_increase_pct=50.0 | pass | within thresholds |
| groundedness_judge | judge.faithfulness.hf/Qwen/Qwen2.5-3B-Instruct.pass_rate | 0.8462 | 0.8462 | max_drop=0.05 | not_measured | judge faithfulness@1:hf/Qwen/Qwen2.5-3B-Instruct uncalibrated: kappa 0.08 < 0.70 (kappa 0.08, floor 0.70) |
