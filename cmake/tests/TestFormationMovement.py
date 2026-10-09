"""Exercise formation catch-up velocities with extracted native core methods.

The prepared and original LaunchMovement/DoUpdate paths execute against the
actual MoveSplineInitArgs validator. Fixtures provide positions, straight-line
collision geometry and recording spline launches; no realm is started.
"""

from pathlib import Path
import argparse
import os
import subprocess
import tempfile

from PreparedSources import prepared_core


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    cursor = opening + 1
    while depth:
        depth += (source[cursor] == '{') - (source[cursor] == '}')
        cursor += 1
    return source[start:cursor]


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--core', type=Path, help='prepared core source directory')
parser.add_argument('--baseline', type=Path, help='original pinned core source directory')
args = parser.parse_args()
repository = Path(__file__).resolve().parents[2]
core = args.core or prepared_core(repository)
baseline = args.baseline or repository / 'azerothcore-wotlk'
relative = 'src/server/game/Movement/MovementGenerators/FormationMovementGenerator.cpp'
validator = function((core / 'src/server/game/Movement/Spline/MoveSpline.cpp').read_text(),
                     'bool MoveSplineInitArgs::Validate')

fixture = r'''
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>

using uint32 = std::uint32_t;
constexpr uint32 UNIT_STATE_NOT_MOVE = 1;
constexpr uint32 UNIT_STATE_FOLLOW_MOVE = 2;
constexpr uint32 MOVE_WALK = 0;
constexpr uint32 FORMATION_MOTION_TYPE = 11;
namespace G3D
{
struct Vector3 { float x, y, z; };
}

struct Position
{
    float x = 0.0f, y = 0.0f, z = 0.0f, orientation = 0.0f;
    float GetPositionX() const { return x; }
    float GetPositionY() const { return y; }
    float GetPositionZ() const { return z; }
    void Relocate(Position const& position) { *this = position; }
    static float NormalizeOrientation(float value) { return value; }
    bool operator!=(Position const& other) const
    {
        return x != other.x || y != other.y || z != other.z || orientation != other.orientation;
    }
};

struct Spline
{
    bool finalized = false;
    float velocity = 2.5f;
    uint32 id = 1;
    bool Finalized() const { return finalized; }
    float Velocity() const { return velocity; }
    uint32 GetId() const { return id; }
    G3D::Vector3 CurrentDestination() const { return {100.0f, 0.0f, 0.0f}; }
};

struct Guid { std::string ToString() const { return "formation fixture"; } };
struct Creature;
struct CreatureGroup { Creature* GetLeader() const { return nullptr; } };

struct Unit : Position
{
    Spline spline;
    Spline* movespline = &spline;
    float walkSpeed = 2.5f;
    float GetRelativeAngle(float, float) const { return 0.0f; }
    Position const& GetPosition() const { return *this; }
    float GetOrientation() const { return orientation; }
    float GetSpeed(uint32) const { return walkSpeed; }
    void MovePositionToFirstCollision(Position& destination, float distance, float angle)
    {
        destination.x += distance * std::cos(angle);
        destination.y += distance * std::sin(angle);
    }
    bool IsCreature() const { return false; }
    Creature* ToCreature() { return nullptr; }
    Guid GetGUID() const { return {}; }
};

struct CreatureAI { void MovementInform(uint32, uint32) {} };

struct Creature : Unit
{
    bool blocked = false, casting = false;
    uint32 stops = 0, launches = 0, failures = 0, state = 0;
    float launchedVelocity = 0.0f;
    bool HasUnitState(uint32 flag) const { return flag == UNIT_STATE_NOT_MOVE && blocked; }
    bool IsMovementPreventedByCasting() const { return casting; }
    void StopMoving() { ++stops; spline.finalized = true; }
    void SetHomePosition(Position const&) {}
    void SetFacingTo(float) {}
    void AddUnitState(uint32 flag) { state |= flag; }
    float GetExactDist(Position const& destination) const
    {
        float dx = x - destination.x, dy = y - destination.y, dz = z - destination.z;
        return std::sqrt(dx * dx + dy * dy + dz * dz);
    }
    CreatureGroup* GetFormation() { return nullptr; }
    uint32 GetCurrentWaypointID() const { return 0; }
    CreatureAI* AI() { return nullptr; }
};

struct Timer
{
    uint32 remaining = 0;
    void Reset(uint32 value) { remaining = value; }
    void Update(uint32 value) { remaining = value < remaining ? remaining - value : 0; }
    bool Passed() const { return remaining == 0; }
};

static std::string failedExpression;
#define LOG_ERROR(category, format, expression, ...) failedExpression = expression

namespace Movement
{
struct MoveSplineInitArgs
{
    std::vector<Position> path;
    float velocity = 0.0f, time_perc = 0.0f;
    bool Validate(Unit* unit) const;
};
NATIVE_VALIDATOR

struct MoveSplineInit
{
    Creature* owner;
    MoveSplineInitArgs args;
    explicit MoveSplineInit(Creature* unit) : owner(unit) {}
    void MoveTo(float x, float y, float z)
    {
        args.path = {owner->GetPosition(), Position{x, y, z, 0.0f}};
    }
    void SetVelocity(float value) { args.velocity = value; }
    void Launch()
    {
        owner->launchedVelocity = args.velocity;
        if (!args.Validate(owner))
        {
            ++owner->failures;
            return;
        }
        ++owner->launches;
        owner->spline.finalized = false;
    }
};
}

struct FormationMovementGenerator
{
    Unit* target;
    float _range = 32.0f, _angle = float(M_PI);
    uint32 _point1 = 0, _point2 = 0, _lastLeaderSplineID = 0;
    bool _hasPredictedDestination = false, _isMoving = false;
    Position _lastLeaderPosition;
    Timer _nextMoveTimer;
    static constexpr uint32 FORMATION_MOVEMENT_INTERVAL = 1200;
    explicit FormationMovementGenerator(Unit* leader) : target(leader) {}
    Unit* GetTarget() { return target; }
    void DoInitialize(Creature*);
    bool DoUpdate(Creature*, uint32);
    void LaunchMovement(Creature*, Unit*);
    void MovementInform(Creature*);
};
'''.replace('NATIVE_VALIDATOR', validator)

tests = r'''
Position PredictedDestination(Unit& target, FormationMovementGenerator const& generator)
{
    Position destination = target.GetPosition();
    target.MovePositionToFirstCollision(destination, target.spline.velocity * 1.65f, 0.0f);
    target.MovePositionToFirstCollision(destination, generator._range, generator._angle);
    return destination;
}

int main()
{
    // Actual float positions cover both sides of the native validator threshold.
    // Valid slow, walking and running leader splines retain their normal speed cap.
    for (float leaderVelocity : {0.0101f, 2.5f, 8.0f})
    {
        for (float gap : {0.0f, 0.001f, 0.005f, 0.015f, 0.0164f, 0.0166f, 0.017f, 1.0f, 20.0f})
        {
            Unit target;
            target.spline.velocity = leaderVelocity;
            Creature owner;
            FormationMovementGenerator generator(&target);
            Position destination = PredictedDestination(target, generator);
            owner.x = destination.x + gap;
            owner.y = destination.y;
            assert(generator.DoUpdate(&owner, 50));
            float actualGap = owner.GetExactDist(destination);
            float calculatedVelocity = leaderVelocity * std::min(actualGap / (leaderVelocity * 1.65f), 1.5f);
#ifdef ORIGINAL_CORE
            bool rejected = actualGap > 0.0f && calculatedVelocity <= 0.01f;
            assert(owner.failures == unsigned(rejected));
            assert(owner.launches == unsigned(!rejected));
            if (rejected)
                assert(failedExpression == "velocity > 0.01f");
#else
            assert(owner.failures == 0 && owner.launches == 1);
            if (calculatedVelocity <= 0.01f)
                assert(owner.launchedVelocity == target.walkSpeed);
#endif
            if (actualGap > 0.0f && calculatedVelocity > 0.01f)
                assert(std::fabs(owner.launchedVelocity - calculatedVelocity) < 1e-5f);
            assert(generator._hasPredictedDestination && generator._isMoving);
            assert(owner.state & UNIT_STATE_FOLLOW_MOVE);
            assert(!(generator._lastLeaderPosition != target.GetPosition()));
            assert(generator._lastLeaderSplineID == target.spline.id);
        }
    }

    // Existing immobilization/casting paths must stop rather than launch a fallback.
    for (bool casting : {false, true})
    {
        Unit target;
        Creature owner;
        owner.blocked = !casting;
        owner.casting = casting;
        FormationMovementGenerator generator(&target);
        generator.DoInitialize(&owner);
        assert(owner.stops == 1 && owner.launches == 0);
        generator._isMoving = true;
        generator._hasPredictedDestination = true;
        assert(generator.DoUpdate(&owner, 50));
        assert(owner.stops == 2 && owner.launches == 0 && owner.failures == 0);
        assert(!generator._isMoving && !generator._hasPredictedDestination);
    }

    // The predicted movement must end when the leader's same spline finishes.
    {
        Unit target;
        target.spline.finalized = true;
        Creature owner;
        FormationMovementGenerator generator(&target);
        generator._lastLeaderSplineID = target.spline.id;
        generator._hasPredictedDestination = true;
        generator._isMoving = true;
        assert(generator.DoUpdate(&owner, 50));
        assert(owner.stops == 1 && owner.launches == 0 && owner.failures == 0);
        assert(!generator._isMoving && !generator._hasPredictedDestination);
    }

    // Finalized leaders still use the pre-existing walk-speed positioning path.
    {
        Unit target;
        target.spline.finalized = true;
        Creature owner;
        FormationMovementGenerator generator(&target);
        generator.LaunchMovement(&owner, &target);
        assert(owner.launches == 1 && owner.failures == 0);
        assert(owner.launchedVelocity == target.walkSpeed);
        assert(!generator._hasPredictedDestination);
    }

    // An invalid custom/effect-derived walk speed is not replaced by invented speed.
    for (float walkSpeed : {0.0f, 0.005f, 0.01f})
    {
        Unit target;
        target.walkSpeed = walkSpeed;
        Creature owner;
        FormationMovementGenerator generator(&target);
        Position destination = PredictedDestination(target, generator);
        owner.x = destination.x;
        owner.y = destination.y;
        generator.LaunchMovement(&owner, &target);
        assert(owner.failures == 1 && owner.launches == 0);
        assert(owner.launchedVelocity == walkSpeed);
        assert(failedExpression == "velocity > 0.01f");
#ifndef ORIGINAL_CORE
        owner.x += 0.005f;
        generator.LaunchMovement(&owner, &target);
        assert(owner.failures == 2 && owner.launches == 0);
        assert(owner.launchedVelocity == walkSpeed);
#endif
    }
    std::cout << "Formation native catch-up, speed caps, immobilization and spline lifecycle passed\n";
}
'''

with tempfile.TemporaryDirectory(prefix='portable-formation-') as temporary:
    temporary = Path(temporary)
    for name, source_root in [('original', baseline), ('prepared', core)]:
        source = (source_root / relative).read_text()
        production = '\n'.join(function(source, signature) for signature in [
            'void FormationMovementGenerator::DoInitialize',
            'bool FormationMovementGenerator::DoUpdate',
            'void FormationMovementGenerator::LaunchMovement',
            'void FormationMovementGenerator::MovementInform',
        ])
        cpp = temporary / (name + '.cpp')
        cpp.write_text(fixture + production + tests)
        executable = temporary / name
        command = ['c++', '-std=c++20', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-g', '-O1',
                   '-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        if name == 'original':
            command.append('-DORIGINAL_CORE')
        command += [str(cpp), '-o', str(executable)]
        subprocess.run(command, check=True)
        print(name + ':', flush=True)
        subprocess.run([str(executable)], check=True, timeout=30,
                       env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=1:abort_on_error=1',
                            'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1'})
