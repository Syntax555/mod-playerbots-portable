"""Shared helpers for the cmake/tests fixtures."""

from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[2]


def prepared_core(repository=REPOSITORY):
    """The generated core checkout that contains the prepared modules."""
    return repository / '.module-cache/prepared-core'


def function(source, signature):
    """The definition that starts at signature, through its matching closing brace."""
    start = source.index(signature)
    opening = source.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]
