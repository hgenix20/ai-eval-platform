"""Graders that never call a model. Each Expect field that is set yields one
Grade with the field name as its dimension.
"""

from __future__ import annotations

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
    - side_effects: len(t.side_effects) == expect.side_effects
    - history_types: t.meta["history_types"] when present, else each
      step's name (in `t.steps` order), compared for exact equality
      including order
    - max_steps_used: t.meta["steps_used"] (falling back to len(t.steps))
      is at most expect.max_steps_used
    - tools_used: t.tools_used() checked against expect.tools_used's one
      mode ("strict": equal in order, "unordered": equal as sets/multisets
      by sorted order, "subset_of": every used tool is in the allowed list)
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
    return out
