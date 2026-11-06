"""Keep historical paladin blessings in the Playerbots blessing planner.

EraTalents gives a historical paladin its talent blessings as clones with their own
spell ids and the stock names. The production blessing registry and cast-strength
helper run against SpellMgr, Player and EraTalents resolver doubles: a clone counts
as the stock blessing's highest known rank and as that blessing's aura, while other
spells stay unrecognised. Mutations remove the clone rank, name and family checks
and the historical Improved Blessing of Might strength.
"""

import argparse
from pathlib import Path
import re
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
source_argument(parser, 'core', default=prepared_core())
source_argument(parser, 'module')
args = parser.parse_args()
module = args.module or args.core / 'modules/mod-playerbots'
paladin = module / 'src/Ai/Class/Paladin'


def without_includes(text):
    return re.sub(r'^#include [^\n]*\n', '', text, flags=re.MULTILINE)


types = without_includes((paladin / 'PaladinBlessingTypes.h').read_text())
registry = without_includes((paladin / 'PaladinBlessingRegistry.h').read_text())
helper = (paladin / 'PaladinBlessingHelper.h').read_text()
strength = function(helper, '    inline int32 GetBlessingCastStrength(')
bridge = without_includes((module / 'src/Bot/EraTalentBridge.h').read_text())
planner = (paladin / 'Actions/PaladinBlessingAction.cpp').read_text()
assert 'flags.hasSanctuary   = EraKnown(member, SPELL_BLESSING_OF_SANCTUARY) != 0;' in planner
assert 'ai::blessing::scanBlessingAuras(unit, _humanCaster)' in planner
assert 'BaseBlessingCategory cat = CategoryOfSpell(aura->GetId());' in function(
    helper, '    inline std::vector<MemberBlessing> scanBlessingAuras(')

# Native contracts: the resolver returns a known stock id first, then a known era clone of the
# same name; the Vanilla Sanctuary clone copies stock 20911, whose spell family is the paladin's.
core = args.core
era = core / 'modules/mod-era-talents'
resolver = function((era / 'src/EraTalentBots.cpp').read_text(),
                    'uint32 EraTalentBots_ResolveSpellId(Player* bot, uint32 stockSpellId)')
assert 'if (bot->HasSpell(stockSpellId))\n        return stockSpellId;' in resolver
assert 'spellId < EraTalents::ERA_CUSTOM_BAND_LOW || spellId >= EraTalents::ERA_CUSTOM_BAND_HIGH' in resolver
assert '- id: 932617\n  name: Blessing of Sanctuary\n  template: 20911\n' in (
    era / 'era-data/vanilla/paladin.yaml').read_text()
spell_info = (core / 'src/server/game/Spells/SpellInfo.h').read_text()
assert 'std::array<char const*, 16> SpellName;' in spell_info and 'uint32 SpellFamilyName;' in spell_info
assert 'SpellInfo const* GetNextRankSpell() const;' in spell_info
assert re.search(r'SPELLFAMILY_PALADIN\s*= 10,', (core / 'src/server/shared/SharedDefines.h').read_text())

fixture = r'''
#include <array>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <unordered_map>
#include <vector>
using uint8 = std::uint8_t; using uint32 = std::uint32_t; using int32 = std::int32_t;
class Group;
enum LocaleConstant { LOCALE_enUS = 0 };
enum SpellFamilyNames { SPELLFAMILY_GENERIC = 0, SPELLFAMILY_PALADIN = 10 };
enum AuraType { SPELL_AURA_NONE = 0, SPELL_AURA_MOD_ATTACK_POWER = 99, SPELL_AURA_MOD_POWER_REGEN = 85 };
constexpr uint8 MAX_SPELL_EFFECTS = 3;
struct SpellEffectInfo { uint32 ApplyAuraName = 0; int32 BasePoints = 0; };
struct SpellInfo
{
    uint32 Id = 0, SpellFamilyName = SPELLFAMILY_PALADIN, Next = 0;
    std::array<char const*, 16> SpellName{};
    std::array<SpellEffectInfo, MAX_SPELL_EFFECTS> Effects{};
    SpellInfo const* GetNextRankSpell() const;
};
struct SpellMgr
{
    std::map<uint32, SpellInfo> spells;
    SpellInfo const* GetSpellInfo(uint32 id) const
    { auto found = spells.find(id); return found == spells.end() ? nullptr : &found->second; }
} spellMgr;
SpellMgr* sSpellMgr = &spellMgr;
SpellInfo const* SpellInfo::GetNextRankSpell() const { return Next ? sSpellMgr->GetSpellInfo(Next) : nullptr; }
class Player
{
public:
    std::set<uint32> spells, auras;
    bool HasSpell(uint32 id) const { return spells.contains(id); }
    bool HasAura(uint32 id) const { return id && auras.contains(id); }
};
// The EraTalents resolver: a known stock id, else the highest known band clone of its name.
uint32 EraTalentBots_ResolveSpellId(Player* bot, uint32 stock)
{
    if (bot->HasSpell(stock))
        return stock;
    std::string const name = sSpellMgr->GetSpellInfo(stock)->SpellName[LOCALE_enUS];
    uint32 best = 0;
    for (uint32 id : bot->spells)
    {
        std::string candidate = sSpellMgr->GetSpellInfo(id)->SpellName[LOCALE_enUS];
        if (std::size_t const rank = candidate.rfind(" (Rank "); rank != std::string::npos)
            candidate.resize(rank);
        if (id >= 900000 && id < 1000000 && candidate == name)
            best = id;
    }
    return best;
}
bool EraTalentBots_SpecTabs(Player*, uint32*) { return false; }
bool EraTalentBots_FactoryReconcile(Player*, int) { return false; }
int EraTalentBots_FeralSpec(Player*) { return 0; }
@BRIDGE@
@TYPES@
@REGISTRY@
namespace ai::blessing
{
@STRENGTH@
}
using namespace ai::blessing;
void Spell(uint32 id, char const* name, uint32 next = 0, uint32 family = SPELLFAMILY_PALADIN)
{
    SpellInfo& info = spellMgr.spells[id];
    info.Id = id; info.Next = next; info.SpellFamilyName = family; info.SpellName[LOCALE_enUS] = name;
}
int main()
{
    Spell(SPELL_BLESSING_OF_MIGHT, "Blessing of Might", 19834);
    Spell(19834, "Blessing of Might");
    spellMgr.spells[19834].Effects[0] = {SPELL_AURA_MOD_ATTACK_POWER, 39};
    Spell(SPELL_GREATER_BLESSING_OF_MIGHT, "Greater Blessing of Might");
    Spell(SPELL_BLESSING_OF_WISDOM, "Blessing of Wisdom");
    Spell(SPELL_GREATER_BLESSING_OF_WISDOM, "Greater Blessing of Wisdom");
    Spell(SPELL_BLESSING_OF_KINGS, "Blessing of Kings");
    Spell(SPELL_GREATER_BLESSING_OF_KINGS, "Greater Blessing of Kings");
    Spell(SPELL_BLESSING_OF_SANCTUARY, "Blessing of Sanctuary");
    Spell(SPELL_GREATER_BLESSING_OF_SANCTUARY, "Greater Blessing of Sanctuary");
    Spell(SPELL_IMPROVED_MIGHT_R1, "Improved Blessing of Might");
    Spell(SPELL_IMPROVED_MIGHT_R2, "Improved Blessing of Might");
    Spell(932617, "Blessing of Sanctuary");  // Vanilla clones, ranks 1 and 2
    Spell(932661, "Blessing of Sanctuary");
    Spell(932611, "Improved Blessing of Might (Rank 5)");
    Spell(465, "Devotion Aura");
    Spell(700000, "Blessing of Sanctuary", 0, SPELLFAMILY_GENERIC);

    Player stock;
    stock.spells = {SPELL_BLESSING_OF_SANCTUARY, SPELL_BLESSING_OF_MIGHT, 19834};
    assert(HighestKnownBlessingRank(&stock, BASE_SANCTUARY, false) == SPELL_BLESSING_OF_SANCTUARY);
    assert(HighestKnownBlessingRank(&stock, BASE_MIGHT, false) == 19834u);
    assert(!HighestKnownBlessingRank(&stock, BASE_SANCTUARY, true));

    Player historical;
    historical.spells = {932617};
    assert(HighestKnownBlessingRank(&historical, BASE_SANCTUARY, false) == 932617u);
    historical.spells.insert(932661);
    assert(HighestKnownBlessingRank(&historical, BASE_SANCTUARY, false) == 932661u);
    assert(!HighestKnownBlessingRank(&historical, BASE_SANCTUARY, true));
    assert(!HighestKnownBlessingRank(&historical, BASE_KINGS, false));
    assert(EraKnown(&historical, SPELL_BLESSING_OF_SANCTUARY) == 932661u);

    // The planner's aura scan counts a clone as Sanctuary; other spells stay unrecognised.
    assert(CategoryOfSpell(SPELL_BLESSING_OF_SANCTUARY) == BASE_SANCTUARY);
    assert(CategoryOfSpell(932617) == BASE_SANCTUARY && !IsGreaterBlessingSpell(932617));
    assert(CategoryOfSpell(SPELL_GREATER_BLESSING_OF_SANCTUARY) == BASE_SANCTUARY
        && IsGreaterBlessingSpell(SPELL_GREATER_BLESSING_OF_SANCTUARY));
    assert(CategoryOfSpell(465) == BASE_NONE && CategoryOfSpell(700000) == BASE_NONE && CategoryOfSpell(1) == BASE_NONE);

    // A historical Improved Blessing of Might gives the full talent bonus.
    Player talented;
    talented.spells = {SPELL_BLESSING_OF_MIGHT, 932611};
    talented.auras = {932611};
    assert(GetBlessingCastStrength(&talented, BLESSING_MIGHT_SINGLE, 19834) == 40 * 125 / 100);
    assert(GetBlessingCastStrength(&stock, BLESSING_MIGHT_SINGLE, 19834) == 40);
    std::cout << "Paladin era blessings: historical ranks, aura identity and talent strength passed\n";
}
'''
fixture = fixture.replace('@BRIDGE@', bridge).replace('@TYPES@', types).replace(
    '@REGISTRY@', registry).replace('@STRENGTH@', strength)


def build(directory, executable):
    return [cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-g', *SANITIZER_FLAGS,
            str(directory / 'Fixture.cpp'), '-o', str(executable)]


with tempfile.TemporaryDirectory(prefix='paladin-era-blessings-') as temporary:
    work = Path(temporary)
    (work / 'Fixture.cpp').write_text(fixture)
    subprocess.run(build(work, work / 'fixture'), check=True)
    result = run_fixture([str(work / 'fixture')])
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout, end='')
    reject_mutants(work, (
        ('historical rank ignored', 'Fixture.cpp', '                best = era;', '                (void)era;'),
        ('clone aura unrecognised', 'Fixture.cpp',
         'auto it = registry.byName.find(info->SpellName[LOCALE_enUS]);', 'auto it = registry.byName.end();'),
        ('another family counted', 'Fixture.cpp', 'info->SpellFamilyName != SPELLFAMILY_PALADIN || ', ''),
        ('historical Improved Might ignored', 'Fixture.cpp',
         ' || caster->HasAura(EraKnown(caster, SPELL_IMPROVED_MIGHT_R2))', ''),
    ), build, 'Paladin era blessings')
