"""Resolve the generated core checkout that contains the prepared modules."""

from pathlib import Path


def prepared_core(repository: Path) -> Path:
    return repository / '.module-cache/prepared-core'
