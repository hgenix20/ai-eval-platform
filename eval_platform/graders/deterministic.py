"""Graders that never call a model. Each Expect field that is set yields one
Grade with the field name as its dimension.
"""

from __future__ import annotations

from eval_platform.graders.trajectory import redundant_calls, step_efficiency
from eval_platform.types import Case, Grade, Trajectory


def _g(dim: str, ok: bool, why: str) -> Grade:
    """Build one Grade: passed mirrors `ok`, value is 1.0/0.0 (Grade requires [0, 1])."""
    return Grade(dimension=dim, value=1.0 if ok else 0.0, passed=ok, explanation=why)


def grade_expect(case: Case, t: Trajectory) -> list[Grade]:
    """Grade one trajectory against a case's Expect fields.

    Contract: emits exactly one Grade per Expect field that is not None,
    in field-declaration order; an all-None Expect yields an empty list.
    Every check is a pure comparison against `t`, so this never raises for
    a well-formed Case/Trajectory pair and never calls a model.

    Dimensions and what they compare:
    - status: t.status == expect.status
    - answer_contains: expect.answer_contains is a substring of t.answer
      (t.answer or "" so a None answer fails instead of raising)
    - side_effects: len(t.side_effects) == expect.side_effects, unless
      `t.meta["side_effects_unavailable"]` is set, in which case the target
      cannot observe side effects and the grade fails rather than passing
      on an empty tuple
    - history_types: t.meta["history_types"] when present, else each
      step's name (in `t.steps` order), compared for exact equality
      including order
    - max_steps_used: t.meta["steps_used"] (falling back to len(t.steps))
      is at most expect.max_steps_used
    - tools_used: t.tools_used() checked against expect.tools_used's one
      mode ("strict": equal in order, "unordered": equal as sets/multisets
      by sorted order, "subset_of": every used tool is in the allowed list)
    - forbidden_tools: fails if any of these tool names appears in
      t.tools_used()
    - max_redundant_calls: redundant_calls(t.steps) is at most this cap
    - step_efficiency: emitted whenever reference_steps is set, value is
      step_efficiency(reference_steps, len(t.tools_used())); passed when
      that value is at least min_step_efficiency (default 0.0, so with no
      floor the dimension records the value but always passes)
    - tool_output_contains: some Step(kind="tool", name=tool_output_contains
      ["tool"]).output contains tool_output_contains["text"] as a substring
    """
    e = case.expect
    out: list[Grade] = []
    if e.status is not None:
        out.append(_g("status", t.status == e.status, f"expected {e.status!r}, got {t.status!r}"))
    if e.answer_contains is not None:
        ok = e.answer_contains in (t.answer or "")
        out.append(
            _g(
                "answer_contains",
                ok,
                f"answer {'contains' if ok else 'lacks'} {e.answer_contains!r}",
            )
        )
    if e.side_effects is not None:
        if t.meta.get("side_effects_unavailable"):
            # A target that cannot see side effects reports an empty tuple
            # for "none happened" and for "none were observed" alike, so
            # `expect: {side_effects: 0}` would pass there without measuring
            # anything. Cases asserting on side effects carry a
            # `side_effects` target requirement and are skipped on such a
            # target; this is the net for one that slips through.
            out.append(_g("side_effects", False, "side effects are not observable on this target"))
        else:
            out.append(
                _g(
                    "side_effects",
                    len(t.side_effects) == e.side_effects,
                    f"expected {e.side_effects}, got {len(t.side_effects)}",
                )
            )
    if e.history_types is not None:
        actual = t.meta["history_types"] if "history_types" in t.meta else [s.name for s in t.steps]
        out.append(
            _g(
                "history_types",
                actual == e.history_types,
                f"expected {e.history_types}, got {actual}",
            )
        )
    if e.max_steps_used is not None:
        used = int(t.meta.get("steps_used", len(t.steps)))
        out.append(
            _g("max_steps_used", used <= e.max_steps_used, f"used {used}, cap {e.max_steps_used}")
        )
    if e.tools_used is not None:
        mode, want = next(iter(e.tools_used.items()))
        got = t.tools_used()
        if mode == "strict":
            ok = got == want
        elif mode == "unordered":
            ok = sorted(got) == sorted(want)
        else:
            ok = set(got) <= set(want)
        out.append(_g("tools_used", ok, f"{mode}: expected {want}, got {got}"))
    out.extend(_trajectory_grades(case, t))
    return out


def _trajectory_grades(case: Case, t: Trajectory) -> list[Grade]:
    """The forbidden_tools, max_redundant_calls, step_efficiency, and
    tool_output_contains dimensions, split out of grade_expect to keep its
    branch count down. Same contract: one Grade per set Expect field."""
    e = case.expect
    out: list[Grade] = []
    if e.forbidden_tools is not None:
        hit = [n for n in t.tools_used() if n in e.forbidden_tools]
        out.append(
            _g(
                "forbidden_tools",
                not hit,
                f"forbidden tools called: {hit}" if hit else "no forbidden tool called",
            )
        )
    if e.max_redundant_calls is not None:
        n = redundant_calls(t.steps)
        out.append(
            _g(
                "max_redundant_calls",
                n <= e.max_redundant_calls,
                f"{n} redundant calls, cap {e.max_redundant_calls}",
            )
        )
    if e.reference_steps is not None:
        eff = step_efficiency(e.reference_steps, len(t.tools_used()))
        floor = e.min_step_efficiency if e.min_step_efficiency is not None else 0.0
        out.append(
            Grade(
                "step_efficiency",
                eff,
                eff >= floor,
                f"efficiency {eff:.2f} (reference {e.reference_steps}, "
                f"used {len(t.tools_used())}, floor {floor})",
            )
        )
    if e.tool_output_contains is not None:
        tool, text = e.tool_output_contains["tool"], e.tool_output_contains["text"]
        outs = [str(s.output) for s in t.steps if s.kind == "tool" and s.name == tool]
        ok = any(text in o for o in outs)
        out.append(
            _g(
                "tool_output_contains",
                ok,
                f"{tool} output {'contains' if ok else 'lacks'} {text!r} ({len(outs)} calls)",
            )
        )
    return out
