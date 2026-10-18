"""Exercise native point movement without natural-mode position corrections.

The complete DoMovePoint production function runs against recording Unit and
MotionMaster doubles with native method declarations. Every combination of
natural mode, water-walking flag/aura, direction and path generation is checked;
the mutation restores the water-height shortcut for natural bots.
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
source_argument(parser, 'core', help='prepared core source directory')
args = parser.parse_args()
core = args.core or prepared_core(Path(__file__).resolve().parents[2])
module = args.source or core / 'modules/mod-playerbots/src'
production = function((module / 'Ai/Base/Actions/MovementActions.cpp').read_text(),
                      'void MovementAction::DoMovePoint(')
motion = (core / 'src/server/game/Movement/MotionMaster.h').read_text()
unit = (core / 'src/server/game/Entities/Unit/Unit.h').read_text()
enums = '\n'.join(function(motion, name) + ';' for name in
                  ('enum MovementSlot', 'enum ForcedMovement', 'enum class AnimTier'))
declarations = '\n'.join(re.search(re.escape(signature) + r'[^;]+;', motion).group(0)
                         for signature in ('void MovePoint(uint32 id, float x,',
                                           'void MovePointBackwards(uint32 id, float x,'))
update = re.search(r'virtual bool UpdatePosition\(float x, float y, float z, float ang,[^;]+;', unit).group(0)

source = r'''
#include <cassert>
#include <cstdint>
#include <initializer_list>
#include <iostream>
#include <optional>
using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
@ENUMS@
constexpr uint32 MOVEMENTFLAG_WATERWALKING = 0x10000000;
struct Config { bool naturalProgression = true; } sPlayerbotAIConfig;

struct MotionMaster
{
    int clears = 0, forwards = 0, backwards = 0;
    bool generated = false;
    void Clear(bool reset = true) { assert(reset); ++clears; }
    @DECLARATIONS@
    void Record(uint32 id, float x, float y, float z, bool generatePath,
                bool forceDestination, MovementSlot slot, float orientation)
    {
        assert(clears == 1 && forwards + backwards == 1);
        assert(id == 0 && x == 50.0f && y == 60.0f && z == 70.0f);
        assert(!forceDestination && slot == MOTION_SLOT_ACTIVE && orientation == 0.0f);
        generated = generatePath;
    }
};
void MotionMaster::MovePoint(uint32 id, float x, float y, float z, ForcedMovement forcedMovement,
                             float speed, float orientation, bool generatePath, bool forceDestination,
                             MovementSlot slot, std::optional<AnimTier> animTier)
{
    ++forwards;
    assert(forcedMovement == FORCED_MOVEMENT_NONE && speed == 0.0f && !animTier);
    Record(id, x, y, z, generatePath, forceDestination, slot, orientation);
}
void MotionMaster::MovePointBackwards(uint32 id, float x, float y, float z, bool generatePath,
                                      bool forceDestination, MovementSlot slot, float orientation)
{
    ++backwards;
    Record(id, x, y, z, generatePath, forceDestination, slot, orientation);
}

struct Unit
{
    MotionMaster motion;
    bool hasMotion = true, waterFlag = false, waterAura = false;
    float x = 10.0f, y = 20.0f, z = 30.0f, orientation = 1.25f;
    int heightQueries = 0, updates = 0;
    MotionMaster* GetMotionMaster() { return hasMotion ? &motion : nullptr; }
    bool HasUnitMovementFlag(uint32 flag) const
    { assert(flag == MOVEMENTFLAG_WATERWALKING); return waterFlag; }
    bool HasWaterWalkAura() const { return waterAura; }
    float GetPositionX() const { return x; }
    float GetPositionY() const { return y; }
    float GetPositionZ() const { return z; }
    float GetMapWaterOrGroundLevel(float requestedX, float requestedY, float requestedZ,
                                  float* ground = nullptr)
    {
        assert(requestedX == x && requestedY == y && requestedZ == z && !ground);
        ++heightQueries;
        return 40.0f;
    }
    @UPDATE@
};
bool Unit::UpdatePosition(float newX, float newY, float newZ, float ang, bool teleport)
{
    assert(heightQueries == 1 && motion.clears == 0 && !teleport);
    ++updates;
    x = newX; y = newY; z = newZ; orientation = ang;
    return true;
}
struct MovementAction
{
    void DoMovePoint(Unit*, float, float, float, bool, bool);
};
@PRODUCTION@

int main()
{
    MovementAction action;
    for (bool natural : {false, true})
    for (bool flag : {false, true})
    for (bool aura : {false, true})
    for (bool backwards : {false, true})
    for (bool generatePath : {false, true})
    {
        sPlayerbotAIConfig.naturalProgression = natural;
        Unit unit;
        unit.waterFlag = flag;
        unit.waterAura = aura;
        action.DoMovePoint(&unit, 50.0f, 60.0f, 70.0f, generatePath, backwards);
        bool const corrected = !natural && flag && aura;
        assert(unit.heightQueries == int(corrected) && unit.updates == int(corrected));
        assert(unit.x == 10.0f && unit.y == 20.0f && unit.z == (corrected ? 40.0f : 30.0f));
        // The native fourth UpdatePosition argument is orientation, not its teleport argument.
        assert(unit.orientation == (corrected ? 0.0f : 1.25f));
        assert(unit.motion.clears == 1 && unit.motion.generated == generatePath);
        assert(unit.motion.backwards == int(backwards) && unit.motion.forwards == int(!backwards));

        unit = Unit{};
        unit.hasMotion = false;
        unit.waterFlag = flag;
        unit.waterAura = aura;
        action.DoMovePoint(&unit, 50.0f, 60.0f, 70.0f, generatePath, backwards);
        assert(unit.heightQueries == 0 && unit.updates == 0);
        assert(unit.z == 30.0f && unit.orientation == 1.25f);
        assert(unit.motion.clears == 0 && unit.motion.forwards == 0 && unit.motion.backwards == 0);
        action.DoMovePoint(nullptr, 50.0f, 60.0f, 70.0f, generatePath, backwards);
    }
    std::cout << "Natural movement: water-height shortcuts refused; native point movement preserved\n";
}
'''.replace('@ENUMS@', enums).replace('@DECLARATIONS@', declarations).replace('@UPDATE@', update)
source = source.replace('@PRODUCTION@', production)

guard = '!sPlayerbotAIConfig.naturalProgression &&\n        '
assert production.count(guard) == 1, 'Natural mode must exclude water-height position correction'
with tempfile.TemporaryDirectory(prefix='portable-natural-movement-') as temporary:
    target = Path(temporary) / 'movement.cpp'
    executable = Path(temporary) / 'movement'
    for label, body in (('production', source), ('water-height shortcut', source.replace(guard, '', 1))):
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
            print(f'Natural movement rejects the {label} mutation')
