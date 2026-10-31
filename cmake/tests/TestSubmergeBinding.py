"""Replay delivered spell bindings and exercise both native submerge auras."""

import argparse
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile

from FixtureSupport import (
    SANITIZER_FLAGS,
    TIMEOUT,
    cxx,
    function,
    prepared_core,
    source_argument,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, 'core', default=prepared_core())
source_argument(parser, 'module', help='Individual Progression source directory')
args = parser.parse_args()
module = args.module or args.core / 'modules/mod-individual-progression'
core_source = (args.core / 'src/server/scripts/Spells/spell_generic.cpp').read_text()
module_source = (module / 'src/naxx40Scripts/custom_spells_40.cpp').read_text()
generic = function(core_source, 'class spell_gen_submerge_visual :') + ';'
custom = function(module_source, 'class spell_submerge_visual_aura :') + ';'
assert 'RegisterSpellScript(spell_gen_submerge_visual);' in core_source
assert 'RegisterSpellScript(spell_submerge_visual_aura);' in module_source
for source, handlers in ((generic, ('HandleEffectApply', 'HandleEffectRemove')),
                         (custom, ('OnApply', 'OnRemove'))):
    for handler in handlers:
        assert re.search(r'::' + handler + r', EFFECT_0, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL\)', source)


def statements(path):
    text = re.sub(r'(?m)^\s*--.*$', '', path.read_text())
    return re.findall(r'(?im)^(?:DELETE\s+FROM|INSERT(?:\s+IGNORE)?\s+INTO)\s+'
                      r'`spell_script_names`[^;]*;', text)


paths = [args.core / 'data/sql/base/db_world/spell_script_names.sql']
paths += sorted((args.core / 'data/sql/updates/db_world').glob('*.sql'))
module_paths = [path for path in (args.core / 'modules').glob('*/data/sql/world/**/*.sql')
                if 'mod-individual-progression' not in path.parts]
module_paths += list((module / 'data/sql/world').rglob('*.sql'))
# The native updater runs core updates first, then modules ordered by filename.
paths += sorted(module_paths, key=lambda path: path.name)
spells = module / 'data/sql/world/base/naxx40_spells.sql'
assert spells in paths


def bindings(replace=None):
    """Spell bindings 26234 and 28819 after replaying the delivered SQL, optionally with one base text replaced."""
    db = sqlite3.connect(':memory:')
    db.execute('CREATE TABLE spell_script_names (spell_id INTEGER, ScriptName TEXT, PRIMARY KEY(spell_id, ScriptName))')
    replaced = 0
    for path in paths:
        for statement in statements(path):
            if replace and path == spells and replace[0] in statement:
                statement = statement.replace(*replace)
                replaced += 1
            db.executescript(statement.replace('INSERT IGNORE', 'INSERT OR IGNORE'))
    assert replaced == bool(replace)
    return db.execute('SELECT spell_id, ScriptName FROM spell_script_names '
                      'WHERE spell_id IN (26234, 28819) ORDER BY spell_id, ScriptName').fetchall()


# Established realms reapply the changed base file, so it alone must bind the native script.
expected = [(26234, 'spell_submerge_visual_aura'), (28819, 'spell_gen_submerge_visual')]
assert bindings() == expected, bindings()
native = "(28819, 'spell_gen_submerge_visual')"
assert native in spells.read_text()
assert bindings((native, "(28819, 'spell_submerge_visual_aura')")) != expected, \
    'reverting the base binding did not reproduce the missing native script'

fixture = r'''
#include <cassert>
#include <functional>
#include <vector>
enum { UNIT_STAND_STATE_STAND, UNIT_STAND_STATE_SUBMERGED };
using AuraEffectHandleModes = int;
struct AuraEffect {};
struct Unit
{
    bool creature = true;
    int stand = UNIT_STAND_STATE_STAND;
    bool IsCreature() const { return creature; }
    void SetStandState(int state) { stand = state; }
};
struct Hook
{
    std::vector<std::function<void(AuraEffect const*, AuraEffectHandleModes)>> callbacks;
    void operator+=(std::function<void(AuraEffect const*, AuraEffectHandleModes)> callback) { callbacks.push_back(callback); }
    void Run() { for (auto& callback : callbacks) callback(nullptr, 0); }
};
struct AuraScript
{
    Unit unit;
    Hook OnEffectApply, OnEffectRemove, AfterEffectRemove;
    virtual bool Load() { return true; }
    virtual void Register() {}
    Unit* GetUnitOwner() { return &unit; }
    Unit* GetTarget() { return &unit; }
};
#define PrepareAuraScript(name) public:
#define AuraEffectApplyFn(handler, effect, aura, mode) [this](AuraEffect const* e, AuraEffectHandleModes m) { (this->* &handler)(e, m); }
#define AuraEffectRemoveFn AuraEffectApplyFn
GENERIC
CUSTOM
int main()
{
    spell_gen_submerge_visual generic;
    generic.Register();
    assert(generic.Load());
    assert(generic.OnEffectApply.callbacks.size() == 1);
    assert(generic.OnEffectRemove.callbacks.empty());
    assert(generic.AfterEffectRemove.callbacks.size() == 1);
    generic.OnEffectApply.Run();
    assert(generic.unit.stand == UNIT_STAND_STATE_SUBMERGED);
    generic.AfterEffectRemove.Run();
    assert(generic.unit.stand == UNIT_STAND_STATE_STAND);
    generic.unit.creature = false;
    assert(!generic.Load());
    spell_submerge_visual_aura custom;
    custom.Register();
    assert(custom.OnEffectApply.callbacks.size() == 1);
    assert(custom.OnEffectRemove.callbacks.size() == 1);
    custom.OnEffectApply.Run();
    assert(custom.unit.stand == UNIT_STAND_STATE_SUBMERGED);
    custom.OnEffectRemove.Run();
    assert(custom.unit.stand == UNIT_STAND_STATE_STAND);
}
'''.replace('GENERIC', generic).replace('CUSTOM', custom)
with tempfile.TemporaryDirectory(prefix='submerge-binding-') as directory:
    source, executable = Path(directory) / 'fixture.cpp', Path(directory) / 'fixture'
    source.write_text(fixture)
    subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', *SANITIZER_FLAGS,
                    '-fno-pie', '-no-pie', str(source), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True, timeout=TIMEOUT)
print('Native submerge binding from the module base, reverted-binding mutation and both aura transitions: passed')
