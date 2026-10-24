"""Exercise native TBC recovery actions without permitting natural-mode teleports."""

import argparse
from pathlib import Path
import re
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
source_argument(parser, help='prepared Playerbots src directory')
args = parser.parse_args()
module = args.source or prepared_core() / 'modules/mod-playerbots/src'
bt = (module / 'Ai/Raid/BT/BTActions.cpp').read_text()
kara = (module / 'Ai/Raid/Kara/KaraActions.cpp').read_text()
names = ('IllidariCouncilMainTankPositionGathiosAction',
         'IllidariCouncilFirstAssistTankFocusMalandeAction',
         'IllidariCouncilSecondAssistTankPositionDarkshadowAction',
         'NightbaneTeleportBackToTerraceAction')
actions = [function(bt if index < 3 else kara, f'bool {name}::Execute(Event /*event*/)')
           for index, name in enumerate(names)]
helpers = (module / 'Ai/Raid/BT/BTHelpers.h').read_text()
threshold = re.search(r'constexpr float COUNCIL_FLOOR_Z_THRESHOLD = [^;]+;', helpers).group(0)
terrace = re.search(r'inline Position const NIGHTBANE_TELEPORT_POSITION = [^;]+;',
                    (module / 'Ai/Raid/Kara/KaraHelpers.h').read_text()).group(0)

source = r'''
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <initializer_list>
#include <iostream>
#include <map>
#include <string>
using uint8 = std::uint8_t;
using ObjectGuid = unsigned;
struct Config { bool naturalProgression = true; } sPlayerbotAIConfig;
struct Event {};
struct Position
{
    float x, y, z;
    float GetPositionX() const { return x; }
    float GetPositionY() const { return y; }
    float GetPositionZ() const { return z; }
};
@THRESHOLD@
@TERRACE@
constexpr unsigned BLACK_TEMPLE_MAP_ID = 564;
Position const GATHIOS_TANK_POSITIONS[] = {{100, 100, 150}, {105, 100, 150}, {105, 105, 150}, {100, 105, 150}};
std::map<ObjectGuid, uint8> gathiosTankStep;
enum class MovementPriority { MOVEMENT_COMBAT };
struct Unit : Position
{
    Unit* victim = nullptr;
    Unit* GetVictim() const { return victim; }
};
struct Player : Unit
{
    int teleports = 0, attacks = 0, moves = 0;
    float orientation = 1.25f;
    float GetOrientation() const { return orientation; }
    ObjectGuid GetGUID() const { return 1; }
    bool IsWithinMeleeRange(Unit*) const { return true; }
    float GetExactDist2d(float targetX, float targetY) const { return std::hypot(x - targetX, y - targetY); }
    float GetExactDist2d(Position const& p) const { return GetExactDist2d(p.x, p.y); }
    float GetExactDist2d(Position const* p) const { return GetExactDist2d(*p); }
    void NearTeleportTo(float targetX, float targetY, float targetZ, float targetOrientation)
    { ++teleports; x = targetX; y = targetY; z = targetZ; orientation = targetOrientation; }
};
struct PlayerbotAI {};
Unit* target = nullptr;
Unit* currentTarget = nullptr;
Player* mainTank = nullptr;
bool markResult = false;
#define AI_VALUE2(type, name, qualifier) target
#define AI_VALUE(type, name) currentTarget
bool MarkTargetWithSquare(Player*, Unit*) { return markResult; }
bool MarkTargetWithStar(Player*, Unit*) { return markResult; }
bool MarkTargetWithCircle(Player*, Unit*) { return markResult; }
void SetRtiTarget(PlayerbotAI*, char const*) {}
bool HasDangerousCouncilAura(Player*) { return false; }
Player* GetGroupMainTank(Player*) { return mainTank; }
struct Action
{
    Player* bot;
    PlayerbotAI* botAI = nullptr;
    bool Attack(Unit* victim) { assert(victim == target); ++bot->attacks; return true; }
    bool MoveTo(unsigned map, float, float, float z, bool a, bool b, bool c, bool d,
                MovementPriority priority, bool e, bool)
    {
        assert(map == BLACK_TEMPLE_MAP_ID && z == bot->GetPositionZ());
        assert(!a && !b && !c && !d && e && priority == MovementPriority::MOVEMENT_COMBAT);
        ++bot->moves;
        return true;
    }
};
@DECLARATIONS@
@PRODUCTION@

template <class Recovery>
void CheckCouncil()
{
    for (bool natural : {false, true})
        for (bool belowFloor : {false, true})
        {
            sPlayerbotAIConfig.naturalProgression = natural;
            Player bot;
            bot.x = 10; bot.y = 20;
            bot.z = COUNCIL_FLOOR_Z_THRESHOLD + (belowFloor ? -10.0f : 10.0f);
            Unit boss;
            boss.x = 30; boss.y = 40; boss.z = COUNCIL_FLOOR_Z_THRESHOLD + 20;
            target = &boss;
            currentTarget = nullptr;
            markResult = false;
            Recovery action{{&bot}};
            assert(action.Execute({}));
            assert(bot.teleports == (!natural && belowFloor ? 1 : 0));
            assert(bot.attacks == 1); // normal target acquisition remains available
            if (natural || !belowFloor)
                assert(bot.x == 10 && bot.y == 20);

            // Missing encounter targets never trigger recovery.
            target = nullptr;
            assert(!action.Execute({}));
        }
}

int main()
{
    CheckCouncil<IllidariCouncilMainTankPositionGathiosAction>();
    CheckCouncil<IllidariCouncilFirstAssistTankFocusMalandeAction>();
    CheckCouncil<IllidariCouncilSecondAssistTankPositionDarkshadowAction>();
    for (bool natural : {false, true})
    {
        sPlayerbotAIConfig.naturalProgression = natural;
        Player bot;
        bot.x = 10; bot.y = 20; bot.z = 30;
        NightbaneTeleportBackToTerraceAction action{{&bot}};
        assert(action.Execute({}) == !natural);
        assert(bot.teleports == (natural ? 0 : 1));
        if (natural)
            assert(bot.x == 10 && bot.y == 20 && bot.z == 30);
        else
            assert(bot.x == NIGHTBANE_TELEPORT_POSITION.x && bot.y == NIGHTBANE_TELEPORT_POSITION.y &&
                   bot.z == NIGHTBANE_TELEPORT_POSITION.z);
    }
    std::cout << "TBC raid recovery: natural mode refuses Council and Nightbane teleports; native attacks remain available\n";
}
'''.replace('@THRESHOLD@', threshold).replace('@TERRACE@', terrace)
source = source.replace('@DECLARATIONS@', '\n'.join(f'struct {name} : Action {{ bool Execute(Event); }};'
                                                   for name in names))
source = source.replace('@PRODUCTION@', '\n'.join(actions))
mutations = []
for index, action in enumerate(actions):
    guard = ('!sPlayerbotAIConfig.naturalProgression && ' if index < 3 else
             '    if (sPlayerbotAIConfig.naturalProgression)\n        return false;\n\n')
    assert action.count(guard) == 1, names[index]
    mutations.append((names[index], source.replace(action, action.replace(guard, '', 1))))

with tempfile.TemporaryDirectory(prefix='portable-raid-recovery-') as temporary:
    target_file = Path(temporary) / 'recovery.cpp'
    executable = Path(temporary) / 'recovery'
    for label, body in [('production', source), *mutations]:
        target_file.write_text(body)
        subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-g',
                        *SANITIZER_FLAGS, str(target_file), '-o', str(executable)], check=True)
        result = subprocess.run([str(executable)], capture_output=True, text=True,
                                check=False, timeout=TIMEOUT)
        if label == 'production':
            assert result.returncode == 0, result.stderr
            print(result.stdout, end='')
        else:
            assert result.returncode != 0 and 'Assertion' in result.stderr, result.stderr
            print(f'TBC raid recovery mutation rejected: {label}')
