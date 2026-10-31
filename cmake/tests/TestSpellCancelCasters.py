"""Cancel spells from game object, world-trigger and unit casters with native Spell::cancel.

Game objects cast through WorldObject::CastSpell, so their spells have no unit
caster. The production cancel path runs against WorldObject, Unit and Spell
doubles; it must skip the missing unit while still removing the dynamic objects
of a world trigger's original caster. Mutations revert the recorded fork change
and drop the owner selection.
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
relative = 'src/server/game/Spells/Spell.cpp'
spell = (core / relative).read_text()
cancel = function(spell, 'void Spell::cancel(bool bySelf)')

# Native contracts the doubles rely on: game objects reach Spell as WorldObject
# casters, ToUnit returns null for them and world triggers have a fixed entry.
object_header = (core / 'src/server/game/Entities/Object/Object.h').read_text()
assert ('Unit* ToUnit() { if (IsCreature() || IsPlayer()) return reinterpret_cast<Unit*>(this); '
        'else return nullptr; }') in object_header
cast = function((core / 'src/server/game/Entities/Object/Object.cpp').read_text(),
                'SpellCastResult WorldObject::CastSpell(CastSpellTargetArg const& targets, SpellInfo const* info,')
assert 'new Spell(this, info, args.TriggerFlags, originalCaster);' in cast
assert 'Spell::Spell(WorldObject* caster, SpellInfo const* info' in spell
spell_header = (core / 'src/server/game/Spells/Spell.h').read_text()
assert 'WorldObject* const m_caster;' in spell_header and re.search(r'\bUnit\* m_originalCaster;', spell_header)
trigger = re.search(r'#define WORLD_TRIGGER\s+(\d+)', (core / 'src/server/game/Entities/Unit/Unit.h').read_text())[1]
# Cancelling calls finish, which the double records instead of running.
assert cancel.rstrip().endswith('finish(false);\n}')

fixture = r'''
#include <cassert>
#include <cstdint>
#include <iostream>
#include <list>
#include <set>
#include <vector>
using uint32 = std::uint32_t;
constexpr uint32 WORLD_TRIGGER = @TRIGGER@;
enum SpellState { SPELL_STATE_NULL, SPELL_STATE_PREPARING, SPELL_STATE_CASTING, SPELL_STATE_FINISHED, SPELL_STATE_IDLE,
                  SPELL_STATE_DELAYED };
enum { SPELL_FAILED_INTERRUPTED = 1, SPELL_MISS_NONE = 0, AURA_REMOVE_BY_CANCEL = 1, SPELL_EFFECT_ADD_FARSIGHT = 72,
       GAMEOBJECT_TYPE_SUMMONING_RITUAL = 18 };
using ObjectGuid = uint32;
struct Map {};
struct Player;
struct Spell;
struct GameObject { uint32 type = 0; uint32 GetGoType() const { return type; } };
struct WorldObject
{
    ObjectGuid guid = 0;
    bool unit = false;
    virtual ~WorldObject() = default;
    struct Unit* ToUnit();
    ObjectGuid GetGUID() const { return guid; }
    Player* GetSpellModOwner() const { return nullptr; }
    Map* FindMap() const { return nullptr; }
};
struct Unit : WorldObject
{
    uint32 entry = 0;
    std::vector<uint32> removedDynamicObjects;
    Unit() { unit = true; }
    uint32 GetEntry() const { return entry; }
    bool IsPlayer() const { return false; }
    Player* ToPlayer() const { return nullptr; }
    void RemoveDynObject(uint32 spellId) { removedDynamicObjects.push_back(spellId); }
    GameObject* GetGameObject(uint32) const { return nullptr; }
    void RemoveGameObject(GameObject*, bool) {}
    void RemoveOwnedAura(uint32, ObjectGuid, uint32, int) {}
};
Unit* WorldObject::ToUnit() { return unit ? static_cast<Unit*>(this) : nullptr; }
struct Player : Unit
{
    bool NeedSendSpectatorData() const { return false; }
    void RemoveSpellCooldown(uint32, bool) {}
    void RemoveSpellMods(Spell*) {}
};
namespace ArenaSpectator { inline void SendCommand_Spell(Map*, ObjectGuid, char const*, uint32, int) {} }
namespace ObjectAccessor { inline Unit* GetUnit(WorldObject const&, ObjectGuid) { return nullptr; } }
struct SpellInfo
{
    uint32 Id = 0;
    bool channeled = false;
    bool HasEffect(int) const { return false; }
    bool IsChanneled() const { return channeled; }
    bool IsCooldownStartedOnEvent() const { return false; }
};
struct TargetInfo { ObjectGuid targetGUID = 0; int missCondition = SPELL_MISS_NONE; };
struct ScriptMgr { int cancels = 0; void OnSpellCastCancel(Spell*, Unit*, SpellInfo const*, bool) { ++cancels; } };
ScriptMgr scriptMgr;
ScriptMgr* sScriptMgr = &scriptMgr;
struct Spell
{
    WorldObject* const m_caster;
    Unit* m_originalCaster;
    SpellInfo const* m_spellInfo;
    uint32 m_spellState = SPELL_STATE_CASTING;
    bool m_autoRepeat = true;
    std::list<TargetInfo> m_UniqueTargetInfo;
    ObjectGuid m_originalCasterGUID = 0;
    std::set<int> m_appliedMods;
    Spell** m_selfContainer = nullptr;
    int finished = 0;
    Spell(WorldObject* caster, Unit* originalCaster, SpellInfo const* info)
        : m_caster(caster), m_originalCaster(originalCaster), m_spellInfo(info) {}
    void CancelGlobalCooldown() {}
    void SendCastResult(int) {}
    void SendInterrupted(int) {}
    void SendChannelUpdate(uint32) {}
    void SetReferencedFromCurrent(bool) {}
    void finish(bool ok) { assert(!ok); ++finished; }
    void cancel(bool bySelf = false);
};
@CANCEL@
int main()
{
    SpellInfo channel{20000, true};
    for (uint32 state : {uint32(SPELL_STATE_PREPARING), uint32(SPELL_STATE_CASTING)})
    {
        // A game object's spell has no unit caster to resolve.
        WorldObject chest;
        Spell spell(&chest, nullptr, &channel);
        spell.m_spellState = state;
        spell.cancel();
        assert(spell.finished == 1 && spell.m_spellState == state && !spell.m_autoRepeat);

        // A world trigger's dynamic objects belong to its original caster.
        Unit triggerCaster, owner;
        triggerCaster.entry = WORLD_TRIGGER;
        Spell triggered(&triggerCaster, &owner, &channel);
        triggered.m_spellState = state;
        triggered.cancel();
        assert(owner.removedDynamicObjects == std::vector<uint32>{channel.Id});
        assert(triggerCaster.removedDynamicObjects == std::vector<uint32>{channel.Id});

        // Other units remove their own dynamic objects.
        Unit caster, original;
        Spell own(&caster, &original, &channel);
        own.m_spellState = state;
        own.cancel();
        assert(original.removedDynamicObjects.empty());
        assert(caster.removedDynamicObjects == (std::vector<uint32>{channel.Id, channel.Id}));
    }
    assert(scriptMgr.cancels == 6);
    std::cout << "Spell cancel fixture passed for game object, world-trigger and unit casters\n";
}
'''.replace('@TRIGGER@', trigger).replace('@CANCEL@', cancel)


def build(directory, executable):
    return [cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-g', *SANITIZER_FLAGS,
            str(directory / 'Fixture.cpp'), '-o', str(executable)]


with tempfile.TemporaryDirectory(prefix='spell-cancel-') as temporary:
    work = Path(temporary)
    revert = work / 'revert'
    (revert / Path(relative).parent).mkdir(parents=True)
    (revert / relative).write_text(spell)
    git_apply(revert, fork_change('azerothcore-wotlk', 'azerothcore-spell-cancel-without-unit-caster',
                                  paths=(relative,)), '--reverse')
    reverted = function((revert / relative).read_text(), 'void Spell::cancel(bool bySelf)')
    assert reverted != cancel
    (work / 'Fixture.cpp').write_text(fixture)
    subprocess.run(build(work, work / 'fixture'), check=True)
    result = run_fixture([str(work / 'fixture')])
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout, end='')
    reject_mutants(work, (
        ('recorded fork change reverted', 'Fixture.cpp', cancel, reverted),
        ('world-trigger owner ignored', 'Fixture.cpp', '? m_originalCaster : unitCaster', '? unitCaster : unitCaster'),
    ), build, 'Spell cancel')
