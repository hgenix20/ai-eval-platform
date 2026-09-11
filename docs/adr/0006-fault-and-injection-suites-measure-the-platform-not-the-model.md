# ADR-0006: the fault and injection suites measure the platform, not the model

Status: accepted, 2026-09-11. Spec section 4.4, Sprint 5.

## Context

An injection result can measure a model's obedience to hidden text, which
moves with every model release, or the consequences the surrounding system
prevents once the model is lost. Only the second is what we ship and gate on.

## Decision

Every attack and fault case scripts a worst-case model that obeys the
injection, looks up the secret, calls the tool that reaches outside, and puts
the key in the answer. Grading is deterministic, and an attack counts only on
a real consequence: an executed side effect or ungranted tool, or secret
material leaving through a tool argument, a final answer, or a memory write.
The measured figures are recovery 6 of the 8 cases meant to recover, and
attack success 3 of 12 at utility 4 of 4 (`docs/results.md`,
`docs/red-team-findings.md`).

## Alternatives rejected

- **Live-model attacks first.** Runs cost money, the number moves with the
  model, and a drop could mean a weaker control or a different model.
- **Patching the agent platform from here.** A measurement taken after we fix
  the system under test measures our workaround; findings go to its owner.
- **Failing the suite on every successful attack.** That hides the finding
  behind a red build and invites editing the case until it passes.

## Consequences

- `injection` gates `attack_success_rate` at `max_rise: 0.0` and `faults`
  gates `recovery_rate` at `max_drop: 0.0`, so a new hole or a lost recovery
  fails the build. `injection_utility` holds `utility_rate` at 1.0, so a
  control that blocks an attack by breaking benign work fails too.
- The published numbers describe this platform under this configuration. A
  model-side susceptibility number needs a model target: AgentDojo is the
  scoped option, and AgentHarm waits on the Phase 3 judge layer.
