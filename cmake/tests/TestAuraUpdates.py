"""Exercise native owned-aura iteration and update cadence with production Unit methods.

Unit::ModifyAuraState and Unit::_UpdateSpells run against Unit, Aura and session
doubles whose aura map moves its storage like the native flat map. Effects that
add or remove auras while an aura state changes must not invalidate the walk.
Players without an open connection apply the accumulated time every 100 ms with
unchanged totals, while connected players and creatures update every tick.
Mutations revert both recorded fork changes and drop the accumulated time.
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
relative = 'src/server/game/Entities/Unit/Unit.cpp'
unit_source = (core / relative).read_text()
unit_header = (core / 'src/server/game/Entities/Unit/Unit.h').read_text()
STATE = 'void Unit::ModifyAuraState(AuraStateType flag, bool apply)'
UPDATE = 'void Unit::_UpdateSpells(uint32 time)'
modify_state, update_spells = function(unit_source, STATE), function(unit_source, UPDATE)

# Native contracts: the owned-aura map is contiguous, removed auras stay allocated
# until _DeleteRemovedAuras, aura time is applied as a diff (periodic effects catch
# up on every elapsed tick), and Playerbots sessions have no socket.
assert 'typedef boost::container::flat_multimap<uint32,  Aura*> AuraMap;' in unit_header
assert 'm_removedAuras.push_back(aura);' in function(unit_source, 'void Unit::RemoveOwnedAura(AuraMap::iterator& i')
assert 'delete m_removedAuras.front();' in function(unit_source, 'void Unit::_DeleteRemovedAuras()')
auras = (core / 'src/server/game/Spells/Auras/SpellAuras.cpp').read_text()
assert 'Update(diff, caster);' in function(auras, 'void Aura::UpdateOwner(uint32 diff, WorldObject* owner)')
assert 'm_duration -= diff;' in function(auras, 'void Aura::Update(uint32 diff, Unit* caster)')
effect = function((core / 'src/server/game/Spells/Auras/SpellAuraEffects.cpp').read_text(),
                  'void AuraEffect::Update(uint32 diff, Unit* caster)')
assert 'm_periodicTimer -= int32(diff);\n        while (m_periodicTimer <= 0)' in effect
assert 'return !m_Socket || !m_Socket->IsOpen();' in function(
    (core / 'src/server/game/Server/WorldSession.cpp').read_text(), 'bool WorldSession::IsSocketClosed() const')
for path in ('src/Bot/PlayerbotMgr.cpp', 'src/Bot/Factory/RandomPlayerbotFactory.cpp'):
    assert re.search(r'new WorldSession\(accountId, "", 0x0, nullptr,',
                     (core / 'modules/mod-playerbots' / path).read_text()), path
shared = (core / 'src/server/shared/SharedDefines.h').read_text()
aura_states = function(shared, 'enum AuraStateType') + ';'
current_spells = function(unit_header, 'enum CurrentSpellTypes') + ';'
assert '#define CURRENT_MAX_SPELL             4' in unit_header

fixture = r'''
#include <cassert>
#include <cstdint>
#include <functional>
#include <iostream>
#include <list>
#include <map>
#include <utility>
#include <vector>
using uint8 = std::uint8_t; using uint32 = std::uint32_t; using uint64 = std::uint64_t;
@AURA_STATES@
@CURRENT_SPELLS@
constexpr uint32 CURRENT_MAX_SPELL = 4;
enum { SPELL_STATE_FINISHED = 3, UNIT_FIELD_AURASTATE = 1, AURA_EFFECT_HANDLE_REAL = 1 };
enum AuraRemoveMode { AURA_REMOVE_BY_EXPIRE = 1, AURA_REMOVE_BY_CANCEL = 2 };
struct ObjectGuid
{
    uint64 value = 0;
    static ObjectGuid const Empty;
    bool operator!=(ObjectGuid const& other) const { return value != other.value; }
};
ObjectGuid const ObjectGuid::Empty{};
struct Unit;
struct SpellInfo
{
    AuraStateType CasterAuraState = AURA_STATE_NONE;
    bool channeled = false;
    bool IsChanneled() const { return channeled; }
};
struct AuraApplication
{
    bool needsUpdate = false;
    int clientUpdates = 0;
    bool IsNeedClientUpdate() const { return needsUpdate; }
    void ClientUpdate() { ++clientUpdates; needsUpdate = false; }
};
struct Aura
{
    SpellInfo info;
    bool removed = false, expired = false;
    AuraApplication application;
    std::vector<std::pair<bool, int>> handled; // apply flag and count
    std::vector<uint32> updates;
    std::function<void()> onHandle;
    bool IsRemoved() const { return removed; }
    bool IsExpired() const { return expired; }
    SpellInfo const* GetSpellInfo() const { return &info; }
    ObjectGuid GetCasterGUID() const { return {1}; }
    AuraApplication* GetApplicationOfTarget(ObjectGuid) { return &application; }
    void HandleAllEffects(AuraApplication*, int, bool apply)
    {
        handled.push_back({apply, 1});
        if (onHandle)
            onHandle();
    }
    void UpdateOwner(uint32 time, Unit*) { updates.push_back(time); }
};
struct Spell
{
    int state = 0;
    int getState() const { return state; }
    void SetReferencedFromCurrent(bool) {}
};
struct GameObject
{
    bool isSpawned() const { return true; }
    void SetOwnerGUID(ObjectGuid) {}
    void SetRespawnTime(int) {}
    void Delete() {}
};
struct WorldSession
{
    bool closed = false;
    bool IsSocketClosed() const { return closed; }
};
struct Player;
struct Unit
{
    // A vector stands in for the native flat map: inserting and erasing move its storage.
    using AuraMap = std::vector<std::pair<uint32, Aura*>>;
    using VisibleAuraMap = std::map<uint8, AuraApplication*>;
    using GameObjectList = std::list<ObjectGuid>;
    AuraMap m_ownedAuras;
    VisibleAuraMap m_visibleAuras;
    std::list<Aura*> m_removedAuras;
    std::vector<Aura*> m_auraUpdateSnapshot;
    uint32 m_pendingAuraUpdateTime = 0;
    GameObjectList m_gameObj;
    Spell* m_currentSpells[CURRENT_MAX_SPELL] = {};
    uint32 auraStateFlags = 0;
    bool player = false;
    int deletions = 0;
    virtual ~Unit() = default;
    bool IsPlayer() const { return player; }
    Player* ToPlayer();
    ObjectGuid GetGUID() const { return {7}; }
    AuraMap& GetOwnedAuras() { return m_ownedAuras; }
    bool HasFlag(int, uint32 flag) const { return (auraStateFlags & flag) != 0; }
    void SetFlag(int, uint32 flag) { auraStateFlags |= flag; }
    void RemoveFlag(int, uint32 flag) { auraStateFlags &= ~flag; }
    void _UpdateAutoRepeatSpell() {}
    void RemoveOwnedAura(AuraMap::iterator& i, AuraRemoveMode)
    {
        i->second->removed = true;
        m_removedAuras.push_back(i->second);
        i = m_ownedAuras.erase(i);
    }
    void _DeleteRemovedAuras() { deletions += int(m_removedAuras.size()); m_removedAuras.clear(); }
    Aura* Add(SpellInfo info)
    {
        Aura* aura = new Aura;
        aura->info = info;
        m_ownedAuras.push_back({uint32(m_ownedAuras.size()), aura});
        return aura;
    }
    void ModifyAuraState(AuraStateType flag, bool apply);
    void _UpdateSpells(uint32 time);
};
struct Player : Unit
{
    WorldSession session;
    Player() { player = true; }
    WorldSession* GetSession() { return &session; }
};
Player* Unit::ToPlayer() { return player ? static_cast<Player*>(this) : nullptr; }
namespace ObjectAccessor
{
Unit* GetWorldObject(Unit& unit, ObjectGuid) { return &unit; }
GameObject* GetGameObject(Unit&, ObjectGuid) { return nullptr; }
}
@PRODUCTION@
int Handled(Aura const* aura, bool apply)
{
    int count = 0;
    for (auto [applied, n] : aura->handled)
        count += applied == apply ? n : 0;
    return count;
}
void AuraStateCases()
{
    for (bool apply : {true, false})
    {
        Unit unit;
        unit.auraStateFlags = apply ? 0 : 1u << (AURA_STATE_FROZEN - 1);
        unit.m_ownedAuras.reserve(3);
        Aura* growing = unit.Add({AURA_STATE_FROZEN});
        Aura* removedLater = unit.Add({AURA_STATE_FROZEN});
        Aura* other = unit.Add({AURA_STATE_HEALTHLESS_20_PERCENT});
        std::vector<Aura*> added;
        // The first handler applies new auras and removes a later one, as triggered effects can.
        growing->onHandle = [&]
        {
            for (int i = 0; i < 16; ++i)
                added.push_back(unit.Add({AURA_STATE_FROZEN}));
            for (auto i = unit.m_ownedAuras.begin(); i != unit.m_ownedAuras.end(); ++i)
                if (i->second == removedLater)
                {
                    unit.RemoveOwnedAura(i, AURA_REMOVE_BY_CANCEL);
                    break;
                }
        };
        unit.ModifyAuraState(AURA_STATE_FROZEN, apply);
        assert(unit.HasFlag(UNIT_FIELD_AURASTATE, 1u << (AURA_STATE_FROZEN - 1)) == apply);
        assert(Handled(growing, apply) == 1 && Handled(removedLater, apply) == 0 && other->handled.empty());
        for (Aura* aura : added)
            assert(aura->handled.empty());
        // A repeated transition with the state unchanged handles nothing.
        unit.ModifyAuraState(AURA_STATE_FROZEN, apply);
        assert(Handled(growing, apply) == 1);
        unit._DeleteRemovedAuras();
        delete removedLater;
        for (auto& [id, aura] : unit.m_ownedAuras)
            delete aura;
    }
    Unit enraged;
    enraged.auraStateFlags = 1u << (AURA_STATE_ENRAGE - 1);
    Aura* aura = enraged.Add({AURA_STATE_ENRAGE});
    enraged.ModifyAuraState(AURA_STATE_ENRAGE, false);
    assert(aura->handled.empty() && !enraged.auraStateFlags); // enrage auras continue
    delete aura;
}
uint32 Total(Aura const* aura)
{
    uint32 total = 0;
    for (uint32 time : aura->updates)
        total += time;
    return total;
}
void CadenceCases()
{
    Player connected, bot;
    bot.session.closed = true;
    Unit creature;
    Aura* playerAura = connected.Add({});
    Aura* botAura = bot.Add({});
    Aura* creatureAura = creature.Add({});
    for (int tick = 0; tick < 10; ++tick)
        for (Unit* unit : {static_cast<Unit*>(&connected), static_cast<Unit*>(&bot), &creature})
            unit->_UpdateSpells(20);
    assert(playerAura->updates.size() == 10 && creatureAura->updates.size() == 10);
    assert((botAura->updates == std::vector<uint32>{100, 100}) && Total(botAura) == Total(playerAura));
    bot._UpdateSpells(150);
    assert(botAura->updates.back() == 150);

    // Removal, expiry and client updates wait for the next sweep but still happen.
    Aura* expiring = bot.Add({});
    expiring->expired = true;
    botAura->application.needsUpdate = true;
    bot.m_visibleAuras[1] = &botAura->application;
    bot._UpdateSpells(40);
    assert(!expiring->removed && botAura->application.clientUpdates == 0);
    bot._UpdateSpells(60);
    assert(expiring->removed && bot.deletions == 1 && botAura->application.clientUpdates == 1);

    // A reconnected player first applies the time gathered while disconnected.
    bot._UpdateSpells(30);
    bot.session.closed = false;
    bot._UpdateSpells(20);
    assert(botAura->updates.back() == 50);
    delete expiring;
    for (Aura* aura : {playerAura, botAura, creatureAura})
        delete aura;
}
int main()
{
    AuraStateCases();
    CadenceCases();
    std::cout << "Owned auras: aura-state snapshot, 100 ms sweeps without a connection and unchanged totals passed\n";
}
'''.replace('@AURA_STATES@', aura_states).replace('@CURRENT_SPELLS@', current_spells)


def build(directory, executable):
    return [cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-g', *SANITIZER_FLAGS,
            str(directory / 'Fixture.cpp'), '-o', str(executable)]


def reverted(change, signature):
    with tempfile.TemporaryDirectory(prefix='aura-revert-') as directory:
        revert = Path(directory)
        (revert / Path(relative).parent).mkdir(parents=True)
        (revert / relative).write_text(unit_source)
        git_apply(revert, fork_change('azerothcore-wotlk', change, paths=(relative,)), '--reverse')
        original = function((revert / relative).read_text(), signature)
    assert original != function(unit_source, signature)
    return original


with tempfile.TemporaryDirectory(prefix='aura-updates-') as temporary:
    work = Path(temporary)
    (work / 'Fixture.cpp').write_text(fixture.replace('@PRODUCTION@', modify_state + '\n' + update_spells))
    subprocess.run(build(work, work / 'fixture'), check=True)
    result = run_fixture([str(work / 'fixture')])
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout, end='')
    reject_mutants(work, (
        ('aura-state fork change reverted', 'Fixture.cpp', modify_state,
         reverted('azerothcore-aura-state-snapshot', STATE)),
        ('aura cadence fork change reverted', 'Fixture.cpp', update_spells,
         reverted('azerothcore-unconnected-aura-updates', UPDATE)),
        ('accumulated time dropped', 'Fixture.cpp', 'uint32 const auraTime = m_pendingAuraUpdateTime;',
         'uint32 const auraTime = time;'),
    ), build, 'Owned auras')
