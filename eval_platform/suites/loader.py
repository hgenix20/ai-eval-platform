"""Load Case definitions from a directory of YAML files."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from eval_platform.types import Case


class CaseError(Exception):
    """One case file failed to parse or validate.

    The message always starts with the offending file's name, so callers
    (and the CLI) can point the author at the exact file to fix.
    """


def load_cases(directory: Path) -> list[Case]:
    """Parse every `*.yaml` file in `directory` into a Case, sorted by file name.

    Contract: file order is deterministic (sorted glob), so suite output is
    reproducible run to run. Each file is validated independently.

    Raises CaseError naming the file on a YAML parse error or a Case
    validation error (e.g. a missing required field or an unknown key,
    since Case forbids extra fields); the original exception is chained
    via `from e` so the underlying cause is still visible.
    """
    cases: list[Case] = []
    for path in sorted(directory.glob("*.yaml")):
        try:
            cases.append(Case.model_validate(yaml.safe_load(path.read_text(encoding="utf-8"))))
        except (yaml.YAMLError, ValidationError) as e:
            raise CaseError(f"{path.name}: {e}") from e
    return cases
