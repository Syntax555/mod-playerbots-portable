"""Exercise hunter Arcane Shot eligibility against native combat-rating fields."""

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


root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, help='Playerbots src directory')
args = parser.parse_args()
core = prepared_core(root)
module = args.source or core / 'modules/mod-playerbots/src'
hunter = module / 'Ai/Class/Hunter'
actions = (hunter / 'HunterActions.cpp').read_text()
context = (hunter / 'HunterAiObjectContext.cpp').read_text()
ai = (module / 'Bot/PlayerbotAI.cpp').read_text()
known_spell = function(ai, 'bool PlayerbotAI::HasSpell(')
assert 'return spellId && bot->HasSpell(spellId);' in known_spell
assert 'creators["arcane shot"] = &HunterAiObjectContextInternal::arcane_shot;' in context
assert 'return new CastArcaneShotAction(botAI);' in context
for name in ('BeastMastery', 'Marksmanship', 'Survival'):
    strategy = (hunter / f'Strategy/{name}HunterStrategy.cpp').read_text()
    assert 'NextAction("arcane shot",' in strategy

# The native producer writes raw rating points at the base plus the rating id;
# GetRatingBonusValue instead returns a level-dependent percentage.
updates = (core / 'src/server/game/Entities/Player/PlayerUpdates.cpp').read_text()
update = function(updates, 'void Player::UpdateRating(')
assert 'SetUInt32Value(static_cast<uint16>(PLAYER_FIELD_COMBAT_RATING_1) + static_cast<uint16>(cr), uint32(amount));' in update
objects = (core / 'src/server/game/Entities/Object/Object.cpp').read_text()
assert 'return m_uint32Values[index];' in function(objects, 'uint32 Object::GetUInt32Value(')
unit_header = (core / 'src/server/game/Entities/Unit/Unit.h').read_text()
parts = {
    'rating': function(unit_header, 'enum CombatRating : uint8') + ';',
    'useful': function(actions, 'bool CastArcaneShotAction::isUseful()'),
}
fixture = r'''
#include <array>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <string_view>
#include "UpdateFields.h"
using uint8 = std::uint8_t;
using uint16 = std::uint16_t;
using uint32 = std::uint32_t;
using int32 = std::int32_t;
// RATING
struct Unit {};
struct Player {
    std::array<uint32, PLAYER_END> values{};
    uint32 GetUInt32Value(uint16 index) const { return values.at(index); }
};
struct PlayerbotAI {
    bool explosiveShot = false;
    bool HasSpell(std::string_view spell) const {
        assert(spell == "explosive shot");
        return explosiveShot;
    }
};
struct CastArcaneShotAction {
    Player* bot;
    PlayerbotAI* botAI;
    Unit* target;
    Unit* GetTarget() const { return target; }
    bool isUseful();
};
// USEFUL
int main() {
    Player player; PlayerbotAI ai; Unit target;
    CastArcaneShotAction action{&player, &ai, &target};
    assert(action.isUseful()); // BM/MM and earlier-era hunters have no Explosive Shot.
    action.target = nullptr; assert(!action.isUseful()); action.target = &target;
    ai.explosiveShot = true; assert(!action.isUseful()); ai.explosiveShot = false;
    player.values[PLAYER_FIELD_COMBAT_RATING_1] = 1000;
    player.values[CR_ARMOR_PENETRATION] = 1000;
    assert(action.isUseful()); // Other update fields cannot suppress Arcane Shot.
    player.values[PLAYER_FIELD_COMBAT_RATING_1] = 0;
    player.values[CR_ARMOR_PENETRATION] = 0;
    player.values[static_cast<uint16>(PLAYER_FIELD_COMBAT_RATING_1) + static_cast<uint16>(CR_ARMOR_PENETRATION)] = 435;
    assert(action.isUseful());
    player.values[static_cast<uint16>(PLAYER_FIELD_COMBAT_RATING_1) + static_cast<uint16>(CR_ARMOR_PENETRATION)] = 436;
    assert(!action.isUseful());
    player.values[static_cast<uint16>(PLAYER_FIELD_COMBAT_RATING_1) + static_cast<uint16>(CR_ARMOR_PENETRATION)] = UINT32_MAX;
    assert(!action.isUseful());
    std::cout << "Hunter Arcane Shot: targets, replacement spell and native raw rating passed\n";
}
'''


def build(work, name):
    source = fixture.replace('// RATING', work['rating']).replace('// USEFUL', work['useful'])
    path = directory / (name + '.cpp')
    path.write_text(source)
    executable = directory / name
    subprocess.run([cxx(), '-std=c++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror', *SANITIZER_FLAGS,
                    '-I' + str(core / 'src/server/game/Entities/Object/Updates'),
                    str(path), '-o', str(executable)], check=True)
    return run_fixture([str(executable)], name)


with tempfile.TemporaryDirectory(prefix='hunter-combat-') as temporary:
    directory = Path(temporary)
    result = build(parts, 'production')
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout, end='')
    mutations = (
        ('missing-target', 'useful', '!target || ', '(target == nullptr && false) || '),
        ('inverted-replacement-gate', 'useful', '|| botAI->HasSpell("explosive shot")',
         '|| !botAI->HasSpell("explosive shot")'),
        ('missing-replacement-gate', 'useful', ' || botAI->HasSpell("explosive shot")', ''),
        ('incorrect-rating-fields', 'useful',
         ('bot->GetUInt32Value(static_cast<uint16>(PLAYER_FIELD_COMBAT_RATING_1) +\n'
          '                                                      static_cast<uint16>(CR_ARMOR_PENETRATION))'),
         'bot->GetUInt32Value(PLAYER_FIELD_COMBAT_RATING_1) + bot->GetUInt32Value(CR_ARMOR_PENETRATION)'),
        ('missing-rating-cap', 'useful', 'armorPenRating > 435', 'armorPenRating > 1000'),
        ('rating-boundary', 'useful', 'armorPenRating > 435', 'armorPenRating >= 435'),
    )
    reject_part_mutants(parts, mutations, build, 'Hunter combat')
