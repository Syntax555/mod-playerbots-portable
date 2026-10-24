"""Replay world SQL in the native updater order for fresh and existing realms."""

import argparse
from collections import Counter
import re

from FixtureSupport import (
    pinned_source,
    prepared_core,
    source_argument,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, 'core', default=prepared_core())
args = parser.parse_args()
core = args.core
modules = core / 'modules'
ip = modules / 'mod-individual-progression'
world = core / 'data/sql/base/db_world'
updates = core / 'data/sql/updates/db_world'

# Core and module updates form one set ordered by file name. An existing realm
# applies new core updates after module files it applied earlier, reapplies a
# changed file and keeps the applied state of a renamed, unchanged file.
fetcher = (core / 'src/server/database/Updater/UpdateFetcher.cpp').read_text()
assert 'left.first.filename().string() < right.first.filename().string()' in fetcher
assert 'if (dirName.find(_dbModuleName) == std::string::npos)' in fetcher
assert 'RenameEntry(hashIter->second, filePath.filename().string());' in fetcher
assert 'if (iter->second.hash != hash)' in fetcher
module_files = sorted((path for path in modules.glob('*/data/sql/*/**/*.sql')
                       if 'world' in path.relative_to(modules).parts[3]), key=lambda path: path.name)
# The updater stops the server when two update files share a name.
assert 'Duplicate filename' in fetcher
included = re.findall(r"\('\$/(data/sql/[\w/]+)','\w+'\)", (world / 'updates_include.sql').read_text())
assert 'data/sql/updates/db_world' in included, included
names = Counter(path.name for path in module_files)
names.update(path.name for directory in included for path in (core / directory).rglob('*.sql'))
duplicates = [name for name, count in names.items() if count > 1]
assert not duplicates, duplicates

# A fresh world database still has creature.id1 until the core renames it.
assert '`id1` int unsigned' in (world / 'creature.sql').read_text()
renames = [path.name for path in sorted(updates.glob('*.sql'))
           if 'ALTER TABLE `creature` CHANGE COLUMN `id1` `id`' in path.read_text()]
assert len(renames) == 1, renames
rename = renames[0]
recorded = set(re.findall(r"\('([^']+[.]sql)','[0-9A-F]{40}'", (world / 'updates.sql').read_text()))
assert rename not in recorded, 'the base dump already contains the creature.id rename'
CREATURE_ID = re.compile(r'(?is)\b(?:DELETE\s+FROM|UPDATE|(?:INSERT|REPLACE)(?:\s+IGNORE)?\s+INTO)\s+'
                         r'`creature`[\s(][^;]*?`id`')


def early_creature_ids(names):
    """Module files that would reach a fresh database before the creature.id rename."""
    return [name for name, path in names if name < rename and CREATURE_ID.search(path.read_text())]


cleanup = ip / 'data/sql/world/base/2026_06_16_00_ip_cleanup.sql'
upstream_cleanup = 'data/sql/world/base/00_cleanup.sql'
assert not (ip / upstream_cleanup).exists()
# Unchanged contents let an existing realm record the rename without reapplying it.
assert cleanup.read_text() == pinned_source('mod-individual-progression', upstream_cleanup)
assert CREATURE_ID.search(cleanup.read_text()), 'the cleanup no longer needs creature.id'
ip_files = [path.name for path in module_files if path.is_relative_to(ip)]
assert all(cleanup.name <= name for name in ip_files), 'the cleanup must still precede the module data'
named = [(path.name, path) for path in module_files]
assert not early_creature_ids(named), early_creature_ids(named)
upstream_order = [('00_cleanup.sql' if path == cleanup else name, path) for name, path in named]
assert early_creature_ids(upstream_order) == ['00_cleanup.sql']
print('Update order mutation rejected: cleanup before the creature.id rename')
print(f'Fresh world update order: module creature statements follow {rename}; renamed cleanup unchanged')
