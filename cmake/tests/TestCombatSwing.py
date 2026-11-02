"""Keep repeated melee swings active and clear rejected attack state.

The native attack-swing handler and Unit::AttackStop run against small packet,
target and player adapters. Mutations drop the repeated-swing guard, the server
stop and the client fallback independently.
"""

import argparse
from pathlib import Path
import subprocess
import tempfile

from FixtureSupport import (
    SANITIZER_FLAGS,
    cxx,
    function,
    prepared_core,
    reject_mutants,
    run_fixture,
    source_argument,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, default=prepared_core(), help='prepared core directory')
core = parser.parse_args().source
handler = function((core / 'src/server/game/Handlers/CombatHandler.cpp').read_text(),
                   'void WorldSession::HandleAttackSwingOpcode(WorldPacket& recvData)')
unit = (core / 'src/server/game/Entities/Unit/Unit.cpp').read_text()
attack = function(unit, 'bool Unit::Attack(Unit* victim, bool meleeAttack)')
stop = function(unit, 'bool Unit::AttackStop()')

# Attack returns false for an existing melee target and for prohibited attacks;
# GetVictim exposes the same pointer that the real AttackStop clears.
same_target = function(attack, 'if (m_attacking == victim)')
assert 'if (!HasUnitState(UNIT_STATE_MELEE_ATTACKING))' in same_target
assert same_target.rstrip().endswith('return false;\n        }')
assert 'if (IsPlayer() && IsMounted())\n        return false;' in attack
header = (core / 'src/server/game/Entities/Unit/Unit.h').read_text()
assert 'Unit* GetVictim() const { return m_attacking; }' in header
assert 'bool Attack(Unit* victim, bool meleeAttack);' in header
assert 'bool AttackStop();' in header

fixture = r'''
#include <cassert>
#include <iostream>
#include <vector>
#define ASSERT(value) assert(value)
#define LOG_DEBUG(...) ((void)0)
enum { UNIT_STATE_MELEE_ATTACKING = 1, CURRENT_MELEE_SPELL = 2, VEHICLE_SEAT_FLAG_CAN_ATTACK = 4 };
struct Unit;
struct ObjectGuid
{
    Unit* target = nullptr;
    static ObjectGuid const Empty;
};
ObjectGuid const ObjectGuid::Empty{};
struct WorldPacket
{
    Unit* target;
    WorldPacket& operator>>(ObjectGuid& guid) { guid.target = target; return *this; }
};
struct Creature
{
    void SetNoCallAssistance(bool) {}
    bool HasSearchedAssistance() const { return false; }
    void SetNoSearchAssistance(bool) {}
};
struct VehicleSeatEntry { int m_flags = VEHICLE_SEAT_FLAG_CAN_ATTACK; };
struct Vehicle
{
    VehicleSeatEntry seat;
    VehicleSeatEntry const* GetSeatForPassenger(Unit*) const { return &seat; }
};
struct Unit
{
    Unit* m_attacking = nullptr;
    bool melee = false, allowed = true, validTarget = true;
    int attempts = 0, removedAttackers = 0, interrupted = 0;
    Vehicle* vehicle = nullptr;
    std::vector<Unit*> stopped;
    Unit* GetVictim() const { return m_attacking; }
    bool HasUnitState(int state) const { assert(state == UNIT_STATE_MELEE_ATTACKING); return melee; }
    bool IsValidAttackTarget(Unit*) const { return validTarget; }
    Vehicle* GetVehicle() const { return vehicle; }
    bool Attack(Unit* victim, bool meleeAttack)
    {
        assert(meleeAttack);
        ++attempts;
        if (!allowed || (m_attacking == victim && melee))
            return false;
        m_attacking = victim;
        melee = true;
        return true;
    }
    bool AttackStop();
    void _removeAttacker(Unit*) { ++removedAttackers; }
    void SetTarget(ObjectGuid guid) { assert(guid.target == nullptr); }
    void ClearUnitState(int state) { assert(state == UNIT_STATE_MELEE_ATTACKING); melee = false; }
    void InterruptSpell(int spell) { assert(spell == CURRENT_MELEE_SPELL); ++interrupted; }
    Creature* ToCreature() const { return nullptr; }
    void SendMeleeAttackStop(Unit* victim) { stopped.push_back(victim); }
};
namespace ObjectAccessor { Unit* GetUnit(Unit&, ObjectGuid guid) { return guid.target; } }
struct WorldSession
{
    Unit* _player;
    void HandleAttackSwingOpcode(WorldPacket& recvData);
};
@STOP@
@HANDLER@
void Swing(Unit& player, Unit* target)
{
    WorldPacket packet{target};
    WorldSession{&player}.HandleAttackSwingOpcode(packet);
}
int main()
{
    Unit target, oldTarget;
    {
        Unit player;
        Swing(player, &target);
        assert(player.GetVictim() == &target && player.melee && player.stopped.empty());
        Swing(player, &target);
        assert(player.attempts == 2 && player.GetVictim() == &target && player.melee);
        assert(player.stopped.empty() && player.interrupted == 0);
    }
    for (bool melee : {false, true})
    {
        Unit player;
        player.m_attacking = &oldTarget;
        player.melee = melee;
        player.allowed = false;
        Swing(player, &target);
        assert(player.GetVictim() == nullptr && !player.melee && player.interrupted == 1);
        assert(player.stopped == std::vector<Unit*>{&oldTarget});
    }
    {
        Unit player;
        player.m_attacking = &target;
        player.allowed = false;
        Swing(player, &target);
        assert(player.GetVictim() == nullptr && !player.melee);
        assert(player.stopped == std::vector<Unit*>{&target});
    }
    {
        Unit player;
        player.allowed = false;
        Swing(player, &target);
        assert(player.attempts == 1 && player.interrupted == 0);
        assert(player.stopped == std::vector<Unit*>{&target});
    }
    for (bool invalid : {false, true})
    {
        Unit player;
        player.validTarget = !invalid;
        Swing(player, invalid ? &target : nullptr);
        assert(player.attempts == 0 && player.stopped == std::vector<Unit*>{invalid ? &target : nullptr});
    }
    {
        Unit player;
        Vehicle vehicle;
        vehicle.seat.m_flags = 0;
        player.vehicle = &vehicle;
        Swing(player, &target);
        assert(player.attempts == 0 && player.stopped == std::vector<Unit*>{&target});
        vehicle.seat.m_flags = VEHICLE_SEAT_FLAG_CAN_ATTACK;
        Swing(player, &target);
        assert(player.attempts == 1 && player.GetVictim() == &target && player.melee);
    }
    std::cout << "combat swing fixture passed\n";
}
'''.replace('@STOP@', stop).replace('@HANDLER@', handler)


def build(directory, executable):
    return [cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', *SANITIZER_FLAGS,
            str(directory / 'fixture.cpp'), '-o', str(executable)]


with tempfile.TemporaryDirectory(prefix='combat-swing-') as temporary:
    work = Path(temporary)
    (work / 'fixture.cpp').write_text(fixture)
    executable = work / 'fixture'
    subprocess.run(build(work, executable), check=True)
    result = run_fixture([str(executable)])
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout, end='')
    reject_mutants(work, (
        ('repeated melee swing stopped', 'fixture.cpp',
         ' && !(_player->GetVictim() == pEnemy && _player->HasUnitState(UNIT_STATE_MELEE_ATTACKING))', ''),
        ('rejected attack retained on server', 'fixture.cpp',
         'if (!_player->AttackStop())', 'if (true)'),
        ('missing client stop without server target', 'fixture.cpp',
         'if (!_player->AttackStop())\n            _player->SendMeleeAttackStop(pEnemy);',
         '_player->AttackStop();'),
    ), build, 'combat swing')
