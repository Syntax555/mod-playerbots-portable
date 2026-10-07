"""Resolve the locked generated core without mixing patched and original modules."""

import json
from pathlib import Path


def prepared_core(repository: Path) -> Path:
    lock = json.loads((repository / 'versions.lock.json').read_text())
    if lock['core'].get('patches'):
        return repository / '.module-cache/prepared-core'
    return repository / lock['core']['source']
