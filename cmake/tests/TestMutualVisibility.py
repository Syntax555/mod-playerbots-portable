"""Keep creatures and gameobjects hidden from a player out of that player's sight and theirs.

Era world content and awareness scripts hide later creatures and objects per player.
The production WorldObject::CanSeeOrDetect helpers run against WorldObject, Unit,
Creature, GameObject and Player doubles: a hidden creature is absent for the player
and the player's pets, and it does not perceive them either, so it neither shows nor
engages. Creature aggro and attack targets go through the same check. Mutations drop
the creature's side and the owner of a pet.
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
source = (core / 'src/server/game/Entities/Object/Object.cpp').read_text()
helpers = source[source.index('namespace\n{\n// The player a unit acts for'):source.index('constexpr float VisibilityDistances')]
sight = function(source, 'bool WorldObject::CanSeeOrDetect(WorldObject const* obj, bool ignoreStealth, bool distanceCheck, bool checkAlert) const')
start = sight.index('    // A creature or gameobject hidden from a player')
block = sight[start:sight.index('    // pussywizard: arena spectator', start)]
assert sight.index('if (CanNeverSee(obj))') < start, 'never-seen objects stay unseen first'
assert block.count('HiddenFrom(') == 2

# Native contracts: creatures aggro and pick attack targets only among units they can see,
# owners resolve through the charmer or owner player, and visibility conditions and
# awareness scripts are asked with the player.
notifier = (core / 'src/server/game/Grids/Notifiers/GridNotifiers.cpp').read_text()
assert 'if (c->IsAIEnabled && c->CanSeeOrDetect(u, false, true))\n        {\n            c->AI()->MoveInLineOfSight_Safe(u);' in notifier
unit = (core / 'src/server/game/Entities/Unit/Unit.cpp').read_text()
targets = function(unit, 'bool Unit::_IsValidAttackTarget(Unit const* target, SpellInfo const* bySpell, WorldObject const* obj) const')
assert '!CanSeeOrDetect(target, (bySpell && bySpell->IsAffectingArea())' in targets
assert '[[nodiscard]] Player* GetCharmerOrOwnerPlayerOrPlayerItself() const;' in (
    core / 'src/server/game/Entities/Unit/Unit.h').read_text()
assert 'virtual bool CanBeSeen(Player const* /*seer*/) { return true; }' in (core / 'src/server/game/AI/CreatureAI.h').read_text()
player = (core / 'src/server/game/Entities/Player/Player.cpp').read_text()
assert 'if (IsGameMaster())\n        return true;' in function(
    player, 'bool Player::CanSeeObjectByVisibilityConditions(WorldObject const* object) const')

fixture = r'''
#include <cassert>
#include <iostream>
#include <set>
struct Player;
struct Unit;
struct Creature;
struct GameObject;
struct CreatureAI { bool visible = true; bool CanBeSeen(Player const*) { return visible; } };
struct GameObjectAI { bool visible = true; bool CanBeSeen(Player const*) { return visible; } };
struct WorldObject
{
    virtual ~WorldObject() = default;
    virtual Unit const* ToUnit() const { return nullptr; }
    virtual Creature const* ToCreature() const { return nullptr; }
    virtual GameObject const* ToGameObject() const { return nullptr; }
};
struct Unit : WorldObject
{
    Player* owner = nullptr;
    bool player = false;
    Unit const* ToUnit() const override { return this; }
    Player* GetCharmerOrOwnerPlayerOrPlayerItself() const;
};
struct Player : Unit
{
    std::set<WorldObject const*> hidden;
    bool gameMaster = false;
    Player() { player = true; }
    bool CanSeeObjectByVisibilityConditions(WorldObject const* object) const { return gameMaster || !hidden.count(object); }
};
Player* Unit::GetCharmerOrOwnerPlayerOrPlayerItself() const
{
    return owner ? owner : player ? static_cast<Player*>(const_cast<Unit*>(this)) : nullptr;
}
struct Creature : Unit
{
    bool IsAIEnabled = true;
    CreatureAI ai;
    Creature const* ToCreature() const override { return this; }
    CreatureAI* AI() const { return const_cast<CreatureAI*>(&ai); }
};
struct GameObject : WorldObject
{
    GameObjectAI ai;
    GameObject const* ToGameObject() const override { return this; }
    GameObjectAI* AI() const { return const_cast<GameObjectAI*>(&ai); }
};
@HELPERS@
bool Sees(WorldObject const* self, WorldObject const* obj)
{
@BLOCK@
    return true;
}
int main()
{
    Player early, later;
    Creature raider, wolf, other;
    wolf.owner = &early;
    early.hidden = {&raider};
    // Hidden from the early player: neither sees the other, nor does the player's pet.
    assert(!Sees(&early, &raider) && !Sees(&raider, &early));
    assert(!Sees(&wolf, &raider) && !Sees(&raider, &wolf));
    // A player who earned it, and unrelated creatures, see as before.
    assert(Sees(&later, &raider) && Sees(&raider, &later) && Sees(&raider, &other) && Sees(&other, &raider));
    // An awareness script hides the same way, unless the creature has no AI.
    other.ai.visible = false;
    assert(!Sees(&later, &other) && !Sees(&other, &later));
    other.IsAIEnabled = false;
    assert(Sees(&later, &other) && Sees(&other, &later));
    // A hidden trap neither shows nor springs; a game master sees through conditions.
    GameObject trap;
    early.hidden.insert(&trap);
    assert(!Sees(&early, &trap) && !Sees(&trap, &early) && Sees(&trap, &later));
    early.gameMaster = true;
    assert(Sees(&early, &trap) && Sees(&trap, &early) && Sees(&raider, &wolf));
    std::cout << "Mutual visibility: hidden creatures and objects neither show nor perceive the player or its pets\n";
}
'''.replace('@HELPERS@', helpers).replace('@BLOCK@', block.replace('ActingPlayer(this)', 'ActingPlayer(self)').replace(
    'HiddenFrom(this, viewed)', 'HiddenFrom(self, viewed)'))
assert 'this' not in block.replace('ActingPlayer(this)', '').replace('HiddenFrom(this, viewed)', '')


def build(directory, executable):
    return [cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-g', *SANITIZER_FLAGS,
            str(directory / 'Fixture.cpp'), '-o', str(executable)]


with tempfile.TemporaryDirectory(prefix='mutual-visibility-') as temporary:
    work = Path(temporary)
    (work / 'Fixture.cpp').write_text(fixture)
    subprocess.run(build(work, work / 'fixture'), check=True)
    result = run_fixture([str(work / 'fixture')])
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout, end='')
    reject_mutants(work, (
        ('hidden creature still perceives the player', 'Fixture.cpp',
         'if (Player const* viewed = ActingPlayer(obj); viewed && HiddenFrom(self, viewed))',
         'if (Player const* viewed = nullptr; viewed && HiddenFrom(self, viewed))'),
        ('pets ignore their owner', 'Fixture.cpp',
         'return unit ? unit->GetCharmerOrOwnerPlayerOrPlayerItself() : nullptr;',
         'return unit && unit->player ? static_cast<Player const*>(unit) : nullptr;'),
    ), build, 'Mutual visibility')
