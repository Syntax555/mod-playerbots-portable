"""Check that SSC ground recovery never teleports a natural-progression bot.

The complete production recovery action runs against recording position,
terrain-height and motion doubles. The feature-off path still recovers to the
reported ground height; a mutation check removes the natural-mode refusal.
"""

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
module = args.source or prepared_core(Path(__file__).resolve().parents[2]) / 'modules/mod-playerbots/src'
ssc = module / 'Ai/Raid/SSC'
production = function((ssc / 'SSCActions.cpp').read_text(),
                      'bool LadyVashjReturnToTheGroundAction::Execute(Event /*event*/)')
position = re.search(r'inline Position const VASHJ_PLATFORM_CENTER_POSITION = [^;]+;',
                     (ssc / 'Util/SSCHelpers.h').read_text()).group(0)

source = r'''
#include <cassert>
#include <initializer_list>
#include <iostream>

struct Config { bool naturalProgression = true; } sPlayerbotAIConfig;
struct Event {};
struct Position
{
    float x, y, z;
    float GetPositionZ() const { return z; }
};
@POSITION@
constexpr float INVALID_HEIGHT = -100000.0f;

struct MotionMaster
{
    int clears = 0;
    void Clear() { ++clears; }
};
struct Player
{
    float x = 10.0f, y = 20.0f, z = 90.0f, orientation = 1.25f;
    float floorZ = 40.0f;
    int heightQueries = 0, attackStops = 0, castStops = 0, moveStops = 0, teleports = 0;
    MotionMaster motion;
    float GetPositionX() const { return x; }
    float GetPositionY() const { return y; }
    float GetOrientation() const { return orientation; }
    float GetMapHeight(float requestedX, float requestedY, float referenceZ)
    {
        assert(requestedX == x && requestedY == y);
        assert(referenceZ == VASHJ_PLATFORM_CENTER_POSITION.GetPositionZ());
        ++heightQueries;
        return floorZ;
    }
    void AttackStop() { ++attackStops; }
    void CastStop() { ++castStops; }
    void StopMoving() { ++moveStops; }
    MotionMaster* GetMotionMaster() { return &motion; }
    void NearTeleportTo(float newX, float newY, float newZ, float newOrientation)
    {
        ++teleports;
        x = newX; y = newY; z = newZ; orientation = newOrientation;
    }
};
struct LadyVashjReturnToTheGroundAction
{
    Player* bot;
    bool Execute(Event);
};
@PRODUCTION@

void Unchanged(Player const& bot)
{
    assert(bot.x == 10.0f && bot.y == 20.0f && bot.z == 90.0f && bot.orientation == 1.25f);
    assert(bot.attackStops == 0 && bot.castStops == 0 && bot.moveStops == 0);
    assert(bot.motion.clears == 0 && bot.teleports == 0);
}

int main()
{
    for (float height : {INVALID_HEIGHT, INVALID_HEIGHT - 1.0f, 40.0f})
    {
        Player bot;
        bot.floorZ = height;
        LadyVashjReturnToTheGroundAction action{&bot};
        assert(!action.Execute({}));
        Unchanged(bot);
    }

    sPlayerbotAIConfig.naturalProgression = false;
    for (float height : {INVALID_HEIGHT, INVALID_HEIGHT - 1.0f})
    {
        Player bot;
        bot.floorZ = height;
        LadyVashjReturnToTheGroundAction action{&bot};
        assert(!action.Execute({}));
        assert(bot.heightQueries == 1);
        Unchanged(bot);
    }

    Player bot;
    LadyVashjReturnToTheGroundAction action{&bot};
    assert(action.Execute({}));
    assert(bot.heightQueries == 1 && bot.attackStops == 1 && bot.castStops == 1);
    assert(bot.moveStops == 1 && bot.motion.clears == 1 && bot.teleports == 1);
    assert(bot.x == 10.0f && bot.y == 20.0f && bot.z == bot.floorZ && bot.orientation == 1.25f);
    std::cout << "SSC earned play: natural mode refuses ground teleport; feature-off recovery remains available\n";
}
'''.replace('@POSITION@', position).replace('@PRODUCTION@', production)

guard = '    if (sPlayerbotAIConfig.naturalProgression)\n        return false;\n'
assert production.count(guard) == 1, 'SSC ground recovery must refuse natural progression'
with tempfile.TemporaryDirectory(prefix='portable-ssc-earned-') as temporary:
    target = Path(temporary) / 'ssc.cpp'
    executable = Path(temporary) / 'ssc'
    for label, body in (('production', source), ('ground teleport refusal', source.replace(guard, '', 1))):
        target.write_text(body)
        subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-g',
                        *SANITIZER_FLAGS, str(target), '-o', str(executable)], check=True)
        result = subprocess.run([str(executable)], capture_output=True, text=True,
                                check=False, timeout=TIMEOUT)
        if label == 'production':
            assert result.returncode == 0, result.stderr
            print(result.stdout, end='')
        else:
            assert result.returncode != 0 and 'Assertion' in result.stderr, result.stderr
            print(f'SSC earned play rejects the {label} mutation')
