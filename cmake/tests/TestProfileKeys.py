"""Check that every shipped configuration key is read by the prepared sources.

The launcher's profiles and realm-phase overrides only take effect while the
pinned servers read the same key names. A renamed upstream key would otherwise
be ignored silently, and the upstream default would apply instead. Each key
must appear as a string literal in the prepared core or module sources; keys
that a module builds from a prefix must be composed of literals from those
sources. Mutation checks rename read keys and confirm that they are rejected.
"""

import argparse
from pathlib import Path
import re

from PreparedSources import prepared_core


# Families whose full key names are assembled at runtime from source literals.
PREFIX_BUILT = {
    'DungeonClear.': 'DcSettings prepends the prefix to the suffixes in its settings registry',
    'WorldBuffBots.': 'each world-buff event appends its key and option name to the prefix',
    'Logger.': 'the log system reads every Logger.* key and names each logger in a log call',
}
# Profile keys that no prepared source reads, each with the reason it is shipped.
UNREAD = {
    'EraTalents.AdvanceGossip': 'compatibility key; the earned-progression patch removes the force-advance '
                                'gossip that read it, and 0 keeps an unpatched module closed',
}
TOKENS = re.compile(r'"((?:\\.|[^"\\\n])*)"|\'(?:\\.|[^\'\\\n])*\'|//[^\n]*|/\*.*?\*/', re.DOTALL)
ASSIGNMENT = re.compile(r'^\s*([A-Za-z][A-Za-z0-9_.]*)\s*=', re.MULTILINE)


def source_literals(roots):
    literals = set()
    for root in roots:
        for path in root.rglob('*'):
            if path.suffix in ('.cpp', '.h', '.hpp', '.cc') and path.is_file():
                text = path.read_text(encoding='utf-8', errors='replace')
                literals.update(match.group(1) for match in TOKENS.finditer(text) if match.group(1))
    return literals


def shipped_keys(repository):
    keys = {}
    for path in sorted((repository / 'cmd/startup/profiles').glob('*.conf')):
        for key in ASSIGNMENT.findall(path.read_text(encoding='utf-8')):
            keys.setdefault(key, path.name)
    # The launcher also writes realm-phase values into these profiles.
    launcher = (repository / 'cmd/startup/expansion.go').read_text(encoding='utf-8')
    phase = re.search(r'func \(phase realmPhase\) profile\(.*?\n}\n', launcher, re.DOTALL).group(0)
    for key in re.findall(r'(?:"|\\n)([A-Za-z][A-Za-z0-9_.]*) = ', phase):
        keys.setdefault(key, 'expansion.go')
    for key in re.findall(r'\{"[^"]+\.conf", "([^"]+)"\}', launcher):
        keys.setdefault(key, 'expansion.go')
    return keys


def composed(text, literals):
    # Whether text is a concatenation of one or more source literals.
    reachable = [True] + [False] * len(text)
    for start in range(len(text)):
        if reachable[start]:
            for end in range(start + 1, len(text) + 1):
                if not reachable[end] and text[start:end] in literals:
                    reachable[end] = True
    return reachable[-1]


def is_read(key, literals):
    if key in literals:
        return True
    return any(key.startswith(prefix) and prefix in literals and composed(key[len(prefix):], literals)
               for prefix in PREFIX_BUILT)


def problems(keys, literals):
    errors = [f'{key} in {origin} is not read by the prepared sources'
              for key, origin in sorted(keys.items()) if key not in UNREAD and not is_read(key, literals)]
    for key in UNREAD:
        if key not in keys:
            errors.append(f'{key} is listed as unread but no longer shipped; remove it from UNREAD')
        elif is_read(key, literals):
            errors.append(f'{key} is listed as unread but the prepared sources read it; remove it from UNREAD')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, help='prepared core checkout with its modules')
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[2]
    core = args.source or prepared_core(repository)
    if not (core / 'modules/mod-playerbots/src').is_dir():
        raise SystemExit('PrepareModules.cmake must prepare the core and modules first')
    keys = shipped_keys(repository)
    literals = source_literals([core / 'src', core / 'modules'])
    errors = problems(keys, literals)
    if errors:
        raise SystemExit('\n'.join(errors))

    # An upstream rename such as AiPlayerbot.* to Playerbots.* must fail.
    renamed = {value.replace('AiPlayerbot.', 'Playerbots.') for value in literals}
    failures = problems(keys, renamed)
    expected = {key for key in keys if key.startswith('AiPlayerbot.')}
    if not expected or not all(any(error.startswith(key + ' ') for error in failures) for key in expected):
        raise SystemExit('Renamed Playerbots keys were not rejected')
    for key in ('AiPlayerbot.NaturalProgression', 'IndividualProgression.ProgressionLimit', 'MaxPlayerLevel'):
        if key not in keys or not problems(keys, literals - {key}):
            raise SystemExit(f'A renamed {key} was not rejected')
    if not problems(keys, literals - {'StrandedRecovery'}):
        raise SystemExit('A renamed Dungeon Clear setting was not rejected')
    print(f'Profile keys: {len(keys)} shipped keys are read by the prepared sources; '
          f'renamed keys and prefix-built settings are rejected')


if __name__ == '__main__':
    main()
