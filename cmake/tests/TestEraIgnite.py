"""Exercise the era Ignite proc against the native delayed periodic cast.

The production era_ignite proc handler runs against a Unit double with the
native CastDelayedSpellWithPeriodicAmount parameters. Like core Ignite, it must
cast its rolling damage without entering combat. Mutations drop the flag and
revert the recorded fork change.
"""

import argparse
from pathlib import Path
import re
import subprocess
import tempfile

from FixtureSupport import (
    SANITIZER_FLAGS,
    cxx,
    fork_change,
    function,
    git_apply,
    prepared_core,
    reject_mutants,
    run_fixture,
    source_argument,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, default=prepared_core(), help='prepared core directory')
core = parser.parse_args().source
scripts = core / 'modules/mod-era-talents/src/EraTalentProcScripts.cpp'
source = scripts.read_text()
unit_header = (core / 'src/server/game/Entities/Unit/Unit.h').read_text()
unit_source = (core / 'src/server/game/Entities/Unit/Unit.cpp').read_text()
spell = (core / 'src/server/game/Spells/Spell.cpp').read_text()
defines = (core / 'src/server/game/Spells/SpellDefines.h').read_text()
shared = (core / 'src/server/shared/SharedDefines.h').read_text()
utility = (core / 'src/common/Utilities/Util.h').read_text()
mage = (core / 'src/server/scripts/Spells/spell_mage.cpp').read_text()

# The double records what the native function receives; the native function
# adds those flags to both its immediate and its delayed cast.
declaration = re.search(r'void CastDelayedSpellWithPeriodicAmount\([^;]*\);', unit_header)[0]
assert 'TriggerCastFlags extraTriggerFlags = TRIGGERED_NONE' in declaration, declaration
delayed = function(unit_source, 'void Unit::CastDelayedSpellWithPeriodicAmount(')
assert 'TriggerCastFlags((TRIGGERED_FULL_MASK & ~TRIGGERED_NO_PERIODIC_RESET) | extraTriggerFlags)' in delayed
assert delayed.count('triggerFlags') == 3, delayed
# The flag keeps launch and hit from entering combat, and core Ignite passes it.
assert spell.count('HasTriggeredCastFlag(TRIGGERED_DONT_ENTER_COMBAT)') == 3
assert 'SPELL_AURA_PERIODIC_DAMAGE, amount, EFFECT_0, TRIGGERED_DONT_ENTER_COMBAT);' in function(
    mage, 'class spell_mage_ignite')

era = source[source.index('class era_ignite'):]
handler = function(era, 'void HandleProc(AuraEffect const* aurEff, ProcEventInfo& eventInfo)')
spells = function(source, 'enum EraProcSpells') + ';'
fixture = r'''
#include <cassert>
#include <cstdint>
#include <iostream>
using uint8 = std::uint8_t; using uint32 = std::uint32_t; using int32 = std::int32_t;
SPELL_EFFECTS;
TRIGGER_FLAGS;
CALCULATE_PCT
enum AuraType { SPELL_AURA_PERIODIC_DAMAGE = 3 };
ERA_SPELLS
struct SpellInfo { uint32 ticks; uint32 GetMaxTicks() const { return ticks; } };
struct SpellMgr {
    SpellInfo dot{4};
    SpellInfo const* AssertSpellInfo(uint32 id) const { assert(id == SPELL_ERA_IGNITE_DOT); return &dot; }
} spellMgr;
SpellMgr* sSpellMgr = &spellMgr;
struct Unit;
struct Cast { Unit* target = nullptr; Unit* caster = nullptr; uint32 spell = 0; AuraType aura{}; int32 amount = 0;
    uint8 effect = 0; TriggerCastFlags flags = TRIGGERED_NONE; int count = 0; } cast;
struct Unit {
    DECLARATION_BODY
};
struct DamageInfo { uint32 damage; uint32 GetDamage() const { return damage; } };
struct ProcEventInfo {
    Unit* actor; Unit* target; DamageInfo* damage;
    Unit* GetActor() const { return actor; }
    Unit* GetProcTarget() const { return target; }
    DamageInfo* GetDamageInfo() const { return damage; }
};
struct AuraEffect { int32 amount; int32 GetAmount() const { return amount; } };
class era_ignite {
public:
    bool prevented = false;
    void PreventDefaultAction() { prevented = true; }
    HANDLER
};
int main()
{
    Unit mage, target;
    DamageInfo crit{1000};
    ProcEventInfo proc{&mage, &target, &crit};
    AuraEffect rank{40};
    era_ignite script;
    script.HandleProc(&rank, proc);
    assert(script.prevented && cast.count == 1);
    assert(cast.target == &target && cast.caster == &mage && cast.spell == SPELL_ERA_IGNITE_DOT);
    assert(cast.aura == SPELL_AURA_PERIODIC_DAMAGE && cast.amount == 100 && cast.effect == EFFECT_0);
    assert(cast.flags == TRIGGERED_DONT_ENTER_COMBAT);
    std::cout << "Era Ignite fixture passed\n";
}
'''.replace('SPELL_EFFECTS', function(shared, 'enum SpellEffIndex : uint8')) \
   .replace('TRIGGER_FLAGS', function(defines, 'enum TriggerCastFlags')) \
   .replace('CALCULATE_PCT', function(utility, 'template <class T, class U>\ninline T CalculatePct(')) \
   .replace('ERA_SPELLS', spells) \
   .replace('DECLARATION_BODY', declaration[:-1] + '\n    { cast = {this, caster, spellId, auraType, addAmount, effectIndex,'
            ' extraTriggerFlags, cast.count + 1}; }') \
   .replace('HANDLER', handler)


def build(directory, executable):
    return [cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', *SANITIZER_FLAGS,
            str(directory / 'Fixture.cpp'), '-o', str(executable)]


with tempfile.TemporaryDirectory(prefix='era-ignite-') as temporary:
    work = Path(temporary)
    revert = work / 'revert'
    (revert / 'src').mkdir(parents=True)
    (revert / 'src/EraTalentProcScripts.cpp').write_text(source)
    git_apply(revert, fork_change('mod-era-talents', 'mod-era-talents-ignite-combat',
                                  paths=('src/EraTalentProcScripts.cpp',)), '--reverse')
    reverted = (revert / 'src/EraTalentProcScripts.cpp').read_text()
    reverted = function(reverted[reverted.index('class era_ignite'):],
                        'void HandleProc(AuraEffect const* aurEff, ProcEventInfo& eventInfo)')
    assert reverted != handler
    (work / 'Fixture.cpp').write_text(fixture)
    subprocess.run(build(work, work / 'fixture'), check=True)
    result = run_fixture([str(work / 'fixture')])
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout, end='')
    reject_mutants(work, (
        ('recorded fork change reverted', 'Fixture.cpp', handler, reverted),
        ('combat flag dropped', 'Fixture.cpp', 'amount, EFFECT_0,\n            TRIGGERED_DONT_ENTER_COMBAT);',
         'amount, EFFECT_0, TRIGGERED_NONE);'),
    ), build, 'Era Ignite')
