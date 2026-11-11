"""Run Playerbots' Ahn'kahet Shadow Crash action when the caster's target is missing.

A Forgotten One's target field is empty while it focuses itself and can name a
unit that has left the map before the cast ends. The production action and unit
lookup run against engine doubles under AddressSanitizer: a missing target must
fall through to the ordinary ranged spread, and a present one is still avoided.
Mutation checks restore the unchecked target and remove the avoidance.
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
    reject_part_mutants,
    run_fixture,
    source_argument,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, help='prepared Playerbots src directory')
args = parser.parse_args()
core = prepared_core()
module = args.source or core / 'modules/mod-playerbots/src'
actions = (module / 'Ai/Dungeon/AK/AKActions.cpp').read_text()
ai = (module / 'Bot/PlayerbotAI.cpp').read_text()
macros = (module / 'Script/Playerbots.h').read_text()
assert '#define AI_VALUE(type, name) context->GetValue<type>(name)->Get()' in macros
assert '#define AI_VALUE2(type, name, param) context->GetValue<type>(name, param)->Get()' in macros

# Native casts clear the caster's target field for a self focus and never keep the target alive.
creature = (core / 'src/server/game/Entities/Creature/Creature.cpp').read_text()
focus = function(creature, 'void Creature::FocusTarget(')
assert 'SetGuidValue(UNIT_FIELD_TARGET, this == target ? ObjectGuid::Empty : target->GetGUID());' in focus
unit_header = (core / 'src/server/game/Entities/Unit/Unit.h').read_text()
assert 'ObjectGuid GetTarget() const { return GetGuidValue(UNIT_FIELD_TARGET); }' in unit_header
accessor = (core / 'src/server/game/Globals/ObjectAccessor.cpp').read_text()
assert 'return GetCreature(u, guid);' in function(accessor, 'Unit* ObjectAccessor::GetUnit(')
assert 'return u.GetMap()->GetCreature(guid);' in function(accessor, 'Creature* ObjectAccessor::GetCreature(')
position = (core / 'src/server/game/Entities/Object/Position.h').read_text()
assert 'float GetExactDist2d(Position const& pos) const' in position

parts = {
    'lookup': function(ai, 'Unit* PlayerbotAI::GetUnit(ObjectGuid guid)'),
    'action': function(actions, 'bool AvoidShadowCrashAction::Execute(Event /*event*/)'),
}

harness = r'''
#include <cassert>
#include <cmath>
#include <cstdint>
#include <map>
#include <string>
#include <vector>
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;
enum UnitState : uint32 { UNIT_STATE_CASTING = 0x00008000 };
class ObjectGuid
{
public:
    ObjectGuid() = default;
    explicit ObjectGuid(uint64 raw) : raw(raw) { }
    explicit operator bool() const { return raw != 0; }
    bool operator==(ObjectGuid const& other) const { return raw == other.raw; }
    bool operator<(ObjectGuid const& other) const { return raw < other.raw; }
private:
    uint64 raw = 0;
};
using GuidVector = std::vector<ObjectGuid>;
struct Position
{
    float x = 0.0f, y = 0.0f;
    Position const& GetPosition() const { return *this; }
    float GetExactDist2d(Position const& other) const { return std::hypot(x - other.x, y - other.y); }
    template <class Object> float GetExactDist2d(Object const* other) const { return GetExactDist2d(other->GetPosition()); }
};
struct Unit : Position
{
    ObjectGuid guid, target;
    uint32 state = 0;
    bool melee = false;
    ObjectGuid GetGUID() const { return guid; }
    ObjectGuid GetTarget() const { return target; }
    bool HasUnitState(uint32 flag) const { return (state & flag) != 0; }
};
using Player = Unit;
std::map<ObjectGuid, Unit*> world;
namespace ObjectAccessor
{
    // Native lookups return null for a unit that is not on the searcher's map.
    Unit* GetUnit(Unit const&, ObjectGuid guid)
    {
        auto const found = world.find(guid);
        return found == world.end() ? nullptr : found->second;
    }
}
struct PlayerbotAI
{
    Player* bot;
    Unit* GetUnit(ObjectGuid guid);
    static bool IsMelee(Player* player) { return player->melee; }
};
@LOOKUP@
struct Event { };
struct Context
{
    Unit* forgottenOne = nullptr;
    GuidVector members;
    template <class T> struct Value { T value; T Get() { return value; } };
    template <class T> Value<T>* GetValue(std::string const& name, std::string const& qualifier)
    {
        assert(name == "find target" && qualifier == "forgotten one");
        static Value<T> result;
        result.value = forgottenOne;
        return &result;
    }
    template <class T> Value<T>* GetValue(std::string const& name)
    {
        assert(name == "group members");
        static Value<T> result;
        result.value = members;
        return &result;
    }
};
#define AI_VALUE(type, name) context->GetValue<type>(name)->Get()
#define AI_VALUE2(type, name, param) context->GetValue<type>(name, param)->Get()
struct AvoidShadowCrashAction
{
    Player* bot;
    PlayerbotAI* botAI;
    Context* context;
    Unit* avoided = nullptr;
    float avoidedBy = 0.0f;
    bool MoveAway(Unit* target, float distance) { avoided = target; avoidedBy = distance; return true; }
    bool Execute(Event event);
};
@ACTION@

int main()
{
    Unit bot, caster, ally, victim;
    bot.guid = ObjectGuid(1);
    caster.guid = ObjectGuid(2);
    ally.guid = ObjectGuid(3);
    victim.guid = ObjectGuid(4);
    ally.x = 6.0f;
    world = { { bot.guid, &bot }, { caster.guid, &caster }, { ally.guid, &ally } };
    PlayerbotAI ai{ &bot };
    Context context;
    context.members = { bot.guid, ally.guid };
    auto run = [&]
    {
        AvoidShadowCrashAction action{ &bot, &ai, &context };
        bool const moved = action.Execute(Event());
        assert(moved == (action.avoided != nullptr));
        return action;
    };

    assert(!run().avoided);                 // no Forgotten One is fighting the group
    context.forgottenOne = &caster;
    assert(run().avoided == &ally);         // idle caster: ranged members only spread

    // A cast without a target, or at a unit that has left the map, keeps the ordinary spread.
    caster.state = UNIT_STATE_CASTING;
    for (ObjectGuid missing : { ObjectGuid(), victim.guid })
    {
        caster.target = missing;
        auto const action = run();
        assert(action.avoided == &ally && action.avoidedBy == 6.0f);
        bot.melee = true;
        assert(!run().avoided);
        bot.melee = false;
    }

    // A Shadow Crash aimed at a unit within ten yards is still avoided first, by melee too.
    world[victim.guid] = &victim;
    victim.x = -4.0f;
    for (bool melee : { false, true })
    {
        bot.melee = melee;
        auto const action = run();
        assert(action.avoided == &victim && action.avoidedBy == 8.0f);
    }
    victim.x = -40.0f;
    assert(!run().avoided);
    bot.melee = false;
    assert(run().avoided == &ally);
}
'''

measured = '            float distance = bot->GetExactDist2d(victim->GetPosition());\n'
mutations = (
    ('missing cast target dereferenced', 'action',
     '        if (victim)\n        {\n' + measured + '            if (distance < radius)',
     measured + '        {\n            if (victim && distance < radius)'),
    ('aimed Shadow Crash ignored', 'action', 'if (distance < radius)', 'if (false)'),
)

with tempfile.TemporaryDirectory(prefix='portable-shadow-crash-') as temporary:
    directory = Path(temporary)

    def build(variant, tag):
        source = directory / f'{tag}.cpp'
        source.write_text(harness.replace('@LOOKUP@', variant['lookup']).replace('@ACTION@', variant['action']))
        executable = directory / tag
        subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                        *SANITIZER_FLAGS, str(source), '-o', str(executable)], check=True)
        return run_fixture([str(executable)], f'Ahn\'kahet Shadow Crash {tag}')

    result = build(parts, 'production')
    assert result.returncode == 0, result.stderr
    print('Ahn\'kahet Shadow Crash passed')
    reject_part_mutants(parts, mutations, build, 'Ahn\'kahet Shadow Crash')
