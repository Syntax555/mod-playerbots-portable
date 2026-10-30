"""Exercise the native item scorer's slot-aware caps, set tiers, hand pairs and era talents.

StatsWeightCalculator's weights, caps, set tiers, weapon handling and talent spell
hit are extracted unchanged and compiled with doubles for the stats collector,
player, aura effects and DBC stores. The real AuraEffect, SpellInfo and Unit aura
totals decide which talent modifiers apply. Spell-hit talent masks come from the
pinned EraTalents Vanilla/TBC data; the native Wrath talents and the spec spells'
family flags are the values of the pinned client Spell.dbc.
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
import yaml


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, help='prepared Playerbots src directory')
source_argument(parser, 'core', help='prepared core source directory')
args = parser.parse_args()
core = args.core or prepared_core()
module = args.source or core / 'modules/mod-playerbots/src'
era_data = core / 'modules/mod-era-talents/era-data'

scorer = (module / 'Mgr/Item/StatsWeightCalculator.cpp').read_text()
scorer_header = (module / 'Mgr/Item/StatsWeightCalculator.h').read_text()
collector_header = (module / 'Mgr/Item/StatsCollector.h').read_text()
ai_header = (module / 'Bot/PlayerbotAI.h').read_text()
game = core / 'src/server/game'
shared = (core / 'src/server/shared/SharedDefines.h').read_text()
unit = (game / 'Entities/Unit/Unit.cpp').read_text()
unit_header = (game / 'Entities/Unit/Unit.h').read_text()
aura_types = (game / 'Spells/Auras/SpellAuraDefines.h').read_text()
aura_effects = (game / 'Spells/Auras/SpellAuraEffects.cpp').read_text()
spell_defines = (game / 'Spells/SpellDefines.h').read_text()
spell_info = (game / 'Spells/SpellInfo.cpp').read_text()
item_header = (game / 'Entities/Item/Item.h').read_text()
item_template = (game / 'Entities/Item/ItemTemplate.h').read_text()
player_header = (game / 'Entities/Player/Player.h').read_text()

# Spell hit talents are flat SPELLMOD_RESIST_MISS_CHANCE modifiers built from the aura's
# misc value and amount, and the core applies them to the hit chance of the cast spell.
calculate_mod = function(aura_effects, 'void AuraEffect::CalculateSpellMod()')
assert 'm_spellmod->op = SpellModOp(GetMiscValue());' in calculate_mod
assert 'm_spellmod->value = GetAmount();' in calculate_mod
assert 'modOwner->ApplySpellMod(spellId, SPELLMOD_RESIST_MISS_CHANCE, hitChance);' in unit
assert 'typedef std::vector<AuraEffect*> AuraEffectList;' in unit_header
# The item instance stores gems and enchantments by slot; random properties use later slots.
assert 'MAX_INSPECTED_ENCHANTMENT_SLOT  = 7,' in item_header and 'PROP_ENCHANTMENT_SLOT_0         = 7,' in item_header
assert 'typedef std::unordered_map<uint32, ItemTemplate> ItemTemplateContainer;' in item_template


def enum(source, name):
    return function(source, 'enum ' + name) + ';'


def resist_miss_talents(cls):
    """Era spell-hit talents with their own masks: (era, talent, tab, mask, best rank)."""
    found = []

    def walk(node, era, talent=None):
        if isinstance(node, dict):
            if {'tab', 'name', 'maxRank'} <= node.keys():
                talent = node
            if node.get('op') == 'resistMiss' and node.get('affectsMask') and node.get('kind') == 'flat':
                mask = node['affectsMask']
                found.append((era, talent['name'], talent['tab'] - 1,
                              (mask.get('a', 0), mask.get('b', 0), mask.get('c', 0)), max(node['vals'])))
            for value in node.values():
                walk(value, era, talent)
        elif isinstance(node, list):
            for value in node:
                walk(value, era, talent)

    for era in ('vanilla', 'tbc'):
        walk(yaml.safe_load((era_data / era / f'{cls}.yaml').read_text())['tabs'], era)
    return found


FAMILY = {'priest': 6, 'mage': 3, 'warlock': 5}
CLASS = {'priest': 'CLASS_PRIEST', 'mage': 'CLASS_MAGE', 'warlock': 'CLASS_WARLOCK'}
talents = {cls: resist_miss_talents(cls) for cls in FAMILY}
names = {(cls, name) for cls, found in talents.items() for _, name, *_ in found}
assert {('priest', 'Shadow Focus'), ('mage', 'Arcane Focus'), ('mage', 'Elemental Precision'),
        ('warlock', 'Suppression')} <= names, names
# Native Wrath ranks from the pinned client Spell.dbc: Shadow Focus 15328 and Arcane Focus 12840.
talent_cases = [('CLASS_PRIEST', 'PRIEST_TAB_SHADOW', 6, (0x68ba104, 0x3c044a, 0x2148), 3),
                ('CLASS_MAGE', 'MAGE_TAB_ARCANE', 3, (0xa1205000, 0x8010, 0), 3)]
talent_cases += [(CLASS[cls], str(tab), FAMILY[cls], mask, best)
                 for cls, found in talents.items() for _, _, tab, mask, best in found]
talent_calls = '\n'.join(f'    TalentHit({cls}, {tab}, {family}, {{{mask[0]}u, {mask[1]}u, {mask[2]}u}}, {best});'
                         for cls, tab, family, mask, best in talent_cases)

enums = '\n'.join([
    enum(shared, 'Classes'), enum(unit_header, 'CombatRating : uint8'), enum(aura_types, 'AuraType'),
    enum(spell_defines, 'SpellModOp'), enum(item_header, 'EnchantmentSlot : uint8'),
    enum(item_template, 'InventoryType'), enum(item_template, 'ItemClass'),
    enum(item_template, 'ItemSubclassWeapon'), enum(player_header, 'EquipmentSlots'),
    *(enum(ai_header, name) for name in ('HUNTER_TABS', 'ROGUE_TABS', 'PRIEST_TABS', 'DEATH_KNIGHT_TABS',
                                          'DRUID_TABS', 'MAGE_TABS', 'SHAMAN_TABS', 'PALADIN_TABS',
                                          'WARLOCK_TABS', 'WARRIOR_TABS')),
    enum(collector_header, 'StatsType : uint8'), enum(collector_header, 'CollectorType : uint8'),
    enum(scorer_header, 'StatsOverflowThreshold'),
])
single_hand = scorer_header[scorer_header.index('#define ITEM_SUBCLASS_MASK_SINGLE_HAND'):
                            scorer_header.index('enum StatsOverflowThreshold')]
ranged = item_template[item_template.index('#define ITEM_SUBCLASS_MASK_WEAPON_RANGED'):
                       item_template.index('#define MAX_ITEM_SUBCLASS_WEAPON')]
declaration = function(scorer_header, 'class StatsWeightCalculator') + ';'
native = '\n\n'.join([
    function(spell_info, 'bool SpellInfo::IsAffected(uint32 familyName, flag96 const& familyFlags) const'),
    function(aura_effects, 'bool AuraEffect::IsAffectedOnSpell(SpellInfo const* spell) const'),
    function(unit, 'int32 Unit::GetTotalAuraModifier(AuraType auraType, std::function<bool(AuraEffect const*)> const& predicate) const')
    .replace('int32 Unit::', 'int32 Player::'),
])
production = '\n\n'.join([
    function(scorer, 'namespace\n{'),
    function(scorer, 'template <size_t Size>'),
    *(function(scorer, signature) for signature in (
        'StatsWeightCalculator::StatsWeightCalculator(Player* player)',
        'void StatsWeightCalculator::Reset()',
        'float StatsWeightCalculator::CalculateItem(',
        'void StatsWeightCalculator::CollectReplacedStats(',
        'void StatsWeightCalculator::GenerateWeights(',
        'void StatsWeightCalculator::GenerateBasicWeights(',
        'void StatsWeightCalculator::GenerateAdditionalWeights(',
        'void StatsWeightCalculator::CollectItemSetBonus(',
        'void StatsWeightCalculator::CalculateItemSetMod(',
        'void StatsWeightCalculator::CalculateSocketBonus(',
        'void StatsWeightCalculator::CalculateItemTypePenalty(',
        'void StatsWeightCalculator::ApplyOverflowPenalty(',
        'float StatsWeightCalculator::TalentSpellHit(',
        'void StatsWeightCalculator::ApplyWeightFinetune(',
        'float StatsWeightCalculator::ApplyPreferredSpecWeapons(',
    )),
])

FIXTURE = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <functional>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <unordered_map>
#include <vector>
using uint8 = std::uint8_t; using int8 = std::int8_t; using uint32 = std::uint32_t; using int32 = std::int32_t;
using Milliseconds = std::chrono::milliseconds;
using namespace std::chrono_literals;
NATIVE_ENUMS
SINGLE_HAND_MASK
RANGED_MASK
constexpr uint8 INVENTORY_SLOT_BAG_0 = 255;
constexpr uint32 MAX_ITEM_SET_SPELLS = 8, MAX_GEM_SOCKETS = 3, PLAYER_EXPERTISE = 1;
enum SpellGroup : uint32 {};

struct flag96
{
    uint32 part[3]{};
    flag96 operator&(flag96 const& other) const
    {
        return {{part[0] & other.part[0], part[1] & other.part[1], part[2] & other.part[2]}};
    }
    explicit operator bool() const { return part[0] || part[1] || part[2]; }
};
struct SpellEffectInfo { flag96 SpellClassMask; };
struct SpellInfo
{
    uint32 Id = 0;
    uint32 SpellFamilyName = 0;
    flag96 SpellFamilyFlags;
    SpellEffectInfo Effects[3];
    bool IsAffected(uint32 familyName, flag96 const& familyFlags) const;
};
struct AuraEffect
{
    SpellInfo const* m_spellInfo;
    uint8 m_effIndex;
    int32 misc, amount;
    SpellInfo const* GetSpellInfo() const { return m_spellInfo; }
    int32 GetMiscValue() const { return misc; }
    int32 GetAmount() const { return amount; }
    bool IsAffectedOnSpell(SpellInfo const* spell) const;
};
typedef std::vector<AuraEffect*> AuraEffectList;
struct SpellMgr
{
    std::map<uint32, SpellInfo> spells;
    SpellInfo const* GetSpellInfo(uint32 id) const { auto found = spells.find(id); return found == spells.end() ? nullptr : &found->second; }
    // Talent auras carry no same-effect stack rule group.
    bool AddSameEffectStackRuleSpellGroups(SpellInfo const*, uint32, int32, std::map<SpellGroup, int32>&) const { return false; }
} spellMgr;
SpellMgr* sSpellMgr = &spellMgr;

struct ItemTemplate
{
    uint32 ItemId = 0, Class = ITEM_CLASS_ARMOR, SubClass = 0, InventoryType = INVTYPE_HEAD, ItemSet = 0, Delay = 0;
    struct { uint32 Color = 0; } Socket[3];
    std::map<uint32, float> stats;
};
std::unordered_map<uint32, ItemTemplate> templates;
struct ObjectMgr { std::unordered_map<uint32, ItemTemplate> const* GetItemTemplateStore() const { return &templates; } } objectMgr;
ObjectMgr* sObjectMgr = &objectMgr;
struct SpellItemEnchantmentEntry { std::map<uint32, float> stats; };
struct ItemSetEntry { uint32 spells[MAX_ITEM_SET_SPELLS]{}; uint32 items_to_triggerspell[MAX_ITEM_SET_SPELLS]{}; };
template <class Entry> struct Store
{
    std::map<uint32, Entry> entries;
    Entry const* LookupEntry(uint32 id) const { auto found = entries.find(id); return found == entries.end() ? nullptr : &found->second; }
};
Store<SpellItemEnchantmentEntry> sSpellItemEnchantmentStore;
Store<ItemSetEntry> sItemSetStore;
std::map<uint32, std::map<uint32, float>> spellStats;

struct StatsCollector
{
    float stats[STATS_TYPE_MAX]{};
    StatsCollector(CollectorType, int32 = -1, int32 = -1) {}
    void Reset() { std::fill(std::begin(stats), std::end(stats), 0.0f); }
    void CollectItemStats(ItemTemplate const* proto) { for (auto [stat, value] : proto->stats) stats[stat] += value; }
    void CollectSpellStats(uint32 id, float multiplier = 1.0f, Milliseconds = -1ms)
    {
        for (auto [stat, value] : spellStats.at(id)) stats[stat] += value * multiplier;
    }
    void CollectEnchantStats(SpellItemEnchantmentEntry const* enchant, uint32 = 0, uint32 = 0, bool = false)
    {
        for (auto [stat, value] : enchant->stats) stats[stat] += value;
    }
};
struct ItemSetEffect { uint32 setid; uint32 item_count; };
struct Item
{
    uint32 entry = 0;
    std::map<uint32, uint32> enchantments;
    ItemTemplate const* GetTemplate() const { return &templates.at(entry); }
    uint32 GetEntry() const { return entry; }
    int32 GetItemRandomPropertyId() const { return 0; }
    uint32 GetEnchantmentId(EnchantmentSlot slot) const { auto found = enchantments.find(slot); return found == enchantments.end() ? 0 : found->second; }
};
struct Player
{
    uint8 cls = CLASS_WARRIOR, level = 80;
    int tab = WARRIOR_TAB_FURY;
    bool tank = false, heal = false, caster = false, dual = false, titan = false;
    float multiplier = 0.5f;
    std::map<uint32, float> ratings;
    std::map<uint32, Item> equipped;
    std::vector<ItemSetEffect*> ItemSetEff;
    std::set<uint32> auras;
    AuraEffectList flatModifiers;
    uint8 getClass() const { return cls; }
    uint8 GetLevel() const { return level; }
    bool HasAura(uint32 id) const { return id && auras.contains(id); }
    bool HasSpell(uint32) const { return false; }
    bool CanDualWield() const { return dual; }
    bool CanTitanGrip() const { return titan; }
    float GetRatingBonusValue(CombatRating rating) const { auto found = ratings.find(rating); return found == ratings.end() ? 0.0f : found->second * multiplier; }
    float GetRatingMultiplier(CombatRating) const { return multiplier; }
    uint32 GetUInt32Value(uint32 field) const { assert(field == PLAYER_EXPERTISE); return 0; }
    int32 GetTotalAuraModifier(AuraType) const { return 0; }
    int32 GetTotalAuraModifier(AuraType auraType, std::function<bool(AuraEffect const*)> const& predicate) const;
    AuraEffectList const& GetAuraEffectsByType(AuraType type) const { assert(type == SPELL_AURA_ADD_FLAT_MODIFIER); return flatModifiers; }
    Item* GetItemByPos(uint8 bag, uint8 slot)
    {
        assert(bag == INVENTORY_SLOT_BAG_0);
        auto found = equipped.find(slot);
        return found == equipped.end() ? nullptr : &found->second;
    }
};
struct PlayerbotAI
{
    static bool IsHeal(Player* player) { return player->heal; }
    static bool IsCaster(Player* player) { return player->caster; }
    static bool IsTank(Player* player) { return player->tank; }
    static bool IsMelee(Player* player) { return !player->caster && !player->heal && player->cls != CLASS_HUNTER; }
};
struct AiFactory { static int GetPlayerSpecTab(Player* player) { return player->tab; } };
std::map<uint32, uint32> eraSpells;
uint32 EraKnown(Player*, uint32 spellId) { auto found = eraSpells.find(spellId); return found == eraSpells.end() ? spellId : found->second; }
struct { bool PreferredSpecWeapons = false; } sPlayerbotAIConfig;

DECLARATION

NATIVE

void StatsWeightCalculator::CalculateRandomProperty(int32, uint32) { assert(false && "fixture items carry no random property"); }

PRODUCTION

void AddItem(uint32 id, std::map<uint32, float> stats, uint32 type = INVTYPE_HEAD, uint32 itemClass = ITEM_CLASS_ARMOR,
             uint32 subclass = 0)
{
    templates[id] = {};
    auto& proto = templates[id];
    proto.ItemId = id; proto.InventoryType = type; proto.Class = itemClass; proto.SubClass = subclass;
    proto.stats = std::move(stats);
}
float Score(Player& player, uint32 id, int32 slot, bool pairs = false)
{
    StatsWeightCalculator calculator(&player);
    calculator.SetWeaponPairs(pairs);
    return calculator.CalculateItem(id, 0, slot);
}
bool Same(float left, float right) { return std::fabs(left - right) < 0.001f; }

void TalentHit(uint8 cls, int tab, uint32 family, std::array<uint32, 3> mask, int32 amount)
{
    // A candidate's spell hit is useful only up to the cap the talent leaves.
    Player player; player.cls = cls; player.tab = tab; player.caster = true;
    SpellInfo talent{900000, family, {}, {{{{mask[0], mask[1], mask[2]}}}, {}, {}}};
    AuraEffect effect{&talent, 0, SPELLMOD_RESIST_MISS_CHANCE, amount};
    // A modifier for another operation or another family's spells leaves the cap alone.
    SpellInfo other{900001, family == 6 ? 3u : 6u, {}, {{{{mask[0], mask[1], mask[2]}}}, {}, {}}};
    AuraEffect cost{&talent, 0, SPELLMOD_COST, 50}, foreign{&other, 0, SPELLMOD_RESIST_MISS_CHANCE, 50};
    player.flatModifiers = {&effect, &cost, &foreign};
    float headroom = (SPELL_HIT_OVERFLOW - amount) / player.multiplier;
    AddItem(800, {{STATS_TYPE_HIT, 200}}); AddItem(801, {{STATS_TYPE_HIT, headroom}});
    AddItem(802, {{STATS_TYPE_HIT, float(SPELL_HIT_OVERFLOW) / player.multiplier}});
    assert(Score(player, 801, EQUIPMENT_SLOT_HEAD) > 0);
    assert(Same(Score(player, 800, EQUIPMENT_SLOT_HEAD), Score(player, 801, EQUIPMENT_SLOT_HEAD)));
    player.flatModifiers.clear();
    assert(Same(Score(player, 800, EQUIPMENT_SLOT_HEAD), Score(player, 802, EQUIPMENT_SLOT_HEAD)));
}

int main()
{
    // Pinned client Spell.dbc family flags of each spec's nuke.
    spellMgr.spells = {{8092, {8092, 6, {{0x2000, 0, 0}}, {}}}, {7268, {7268, 3, {{0x200000, 0, 0}}, {}}},
                       {133, {133, 3, {{0x1, 0, 0x8}}, {}}}, {116, {116, 3, {{0x20, 0, 0}}, {}}},
                       {172, {172, 5, {{0x2, 0, 0}}, {}}}, {686, {686, 5, {{0x1, 0, 0}}, {}}}};
    {
        // At the hit cap, the worn head's own hit and gem keep their value in its slot.
        Player player; player.ratings[CR_HIT_MELEE] = float(MELEE_HIT_OVERFLOW) / player.multiplier;
        AddItem(1, {{STATS_TYPE_HIT, 6}, {STATS_TYPE_STRENGTH, 10}}); AddItem(2, {{STATS_TYPE_STRENGTH, 14}});
        AddItem(3, {{STATS_TYPE_HIT, 10}}); AddItem(4, {{STATS_TYPE_HIT, 8}}); AddItem(5, {{STATS_TYPE_HIT, 6}});
        sSpellItemEnchantmentStore.entries[77] = {{{STATS_TYPE_HIT, 2}}};
        player.equipped[EQUIPMENT_SLOT_HEAD] = {1, {{SOCK_ENCHANTMENT_SLOT, 77}}};
        assert(Score(player, 1, EQUIPMENT_SLOT_HEAD) > Score(player, 2, EQUIPMENT_SLOT_HEAD));
        assert(Score(player, 1, -1) < Score(player, 2, -1));
        // A candidate's hit counts up to the headroom the replaced head and gem free.
        assert(Same(Score(player, 3, EQUIPMENT_SLOT_HEAD), Score(player, 4, EQUIPMENT_SLOT_HEAD)));
        assert(Score(player, 4, EQUIPMENT_SLOT_HEAD) > Score(player, 5, EQUIPMENT_SLOT_HEAD) && Score(player, 3, -1) == 0);
    }
    {
        // A worn set piece keeps the tier it completes; a slotless score cannot know it.
        Player player; ItemSetEffect set{500, 2}; player.ItemSetEff = {&set};
        sItemSetStore.entries[500].spells[0] = 9000; sItemSetStore.entries[500].items_to_triggerspell[0] = 2;
        spellStats[9000] = {{STATS_TYPE_STRENGTH, 20}};
        AddItem(10, {{STATS_TYPE_STRENGTH, 10}}); templates[10].ItemSet = 500;
        AddItem(11, {{STATS_TYPE_STRENGTH, 16}});
        player.equipped[EQUIPMENT_SLOT_HEAD] = {10, {}};
        assert(Score(player, 10, EQUIPMENT_SLOT_HEAD) > Score(player, 11, EQUIPMENT_SLOT_HEAD));
        assert(Score(player, 10, -1) < Score(player, 11, -1));
    }
    {
        // Hand pairs count a two-hander whole and a caster's one-hander unscaled.
        Player arms; arms.tab = WARRIOR_TAB_ARMS;
        AddItem(20, {{STATS_TYPE_STRENGTH, 40}}, INVTYPE_2HWEAPON, ITEM_CLASS_WEAPON, ITEM_SUBCLASS_WEAPON_AXE2);
        assert(Same(Score(arms, 20, EQUIPMENT_SLOT_MAINHAND, true), 2 * Score(arms, 20, EQUIPMENT_SLOT_MAINHAND)));
        Player mage; mage.cls = CLASS_MAGE; mage.tab = MAGE_TAB_FROST; mage.caster = true;
        AddItem(21, {{STATS_TYPE_SPELL_POWER, 50}}, INVTYPE_WEAPON, ITEM_CLASS_WEAPON, ITEM_SUBCLASS_WEAPON_DAGGER);
        assert(Same(Score(mage, 21, EQUIPMENT_SLOT_MAINHAND), 0.65f * Score(mage, 21, EQUIPMENT_SLOT_MAINHAND, true)));
        Player holy; holy.cls = CLASS_PALADIN; holy.tab = PALADIN_TAB_HOLY; holy.heal = true;
        AddItem(22, {{STATS_TYPE_HEAL_POWER, 50}}, INVTYPE_WEAPON, ITEM_CLASS_WEAPON, ITEM_SUBCLASS_WEAPON_MACE);
        assert(Same(Score(holy, 22, EQUIPMENT_SLOT_MAINHAND), 0.8f * Score(holy, 22, EQUIPMENT_SLOT_MAINHAND, true)));
    }
    {
        // An era-managed hunter's Careful Aim is its historical talent spell.
        Player hunter; hunter.cls = CLASS_HUNTER; hunter.tab = HUNTER_TAB_BEAST_MASTERY;
        AddItem(30, {{STATS_TYPE_INTELLECT, 10}});
        assert(Score(hunter, 30, EQUIPMENT_SLOT_HEAD) == 0);
        eraSpells[34484] = 924484; hunter.auras.insert(924484);
        assert(Score(hunter, 30, EQUIPMENT_SLOT_HEAD) > 0);
    }
TALENT_CALLS
    std::cout << "Equipment scoring: slot cap headroom, set tiers, hand pairs, era Careful Aim and "
              << TALENT_COUNT << " Vanilla, TBC and Wrath spell-hit talents passed\n";
}
'''

source = (FIXTURE.replace('NATIVE_ENUMS', enums).replace('SINGLE_HAND_MASK', single_hand)
          .replace('RANGED_MASK', ranged).replace('DECLARATION', declaration).replace('NATIVE', native)
          .replace('PRODUCTION', production).replace('TALENT_CALLS', talent_calls)
          .replace('TALENT_COUNT', str(len(talent_cases))))

mutations = (
    ('set bonuses off by default', 'enable_item_set_bonus_ = true;', 'enable_item_set_bonus_ = false;'),
    ('caps off by default', 'enable_overflow_penalty_ = true;', 'enable_overflow_penalty_ = false;'),
    ('replaced item kept in cap', 'CollectReplacedStats(slot);', ''),
    ('replaced gem kept in cap', 'collector_->CollectEnchantStats(enchant);\n    }\n\n    std::copy',
     'enchant = nullptr;\n    }\n\n    std::copy'),
    ('replaced headroom ignored', '+ replaced_[stat];', ';'),
    ('worn set piece counted twice', '                --worn;', '                {}'),
    ('two-hander per hand in pairs', 'if (!weapon_pairs_)\n                weight_ *= 0.5;', 'weight_ *= 0.5;'),
    ('caster one-hander scaled in pairs', 'if (!weapon_pairs_ && (cls == CLASS_MAGE', 'if ((cls == CLASS_MAGE'),
    ('holy one-hander scaled in pairs', '!weapon_pairs_ && cls == CLASS_PALADIN', 'cls == CLASS_PALADIN'),
    ('stock Careful Aim only', 'HasAura(EraKnown(player, SPELL_CAREFUL_AIM))', 'HasAura(SPELL_CAREFUL_AIM)'),
    ('talent spell hit ignored', 'hit_current += TalentSpellHit(player);', ''),
    ('every spell modifier counted', 'effect->GetMiscValue() == SPELLMOD_RESIST_MISS_CHANCE && ', ''),
    ('unaffected spells counted', ' && effect->IsAffectedOnSpell(spellInfo)', ''),
    ('arcane nuke outside the talent', 'tab == MAGE_TAB_ARCANE ? SPELL_ARCANE_MISSILE', 'tab == MAGE_TAB_ARCANE ? SPELL_FROSTBOLT'),
    ('affliction nuke outside the talent', 'tab == WARLOCK_TAB_AFFLICTION ? SPELL_CORRUPTION',
     'tab == WARLOCK_TAB_AFFLICTION ? SPELL_SHADOW_BOLT'),
)


def build(directory, executable):
    return [cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', *SANITIZER_FLAGS, '-no-pie',
            str(Path(directory) / 'fixture.cpp'), '-o', str(executable)]


with tempfile.TemporaryDirectory(prefix='equipment-scoring-') as temporary:
    work = Path(temporary)
    (work / 'fixture.cpp').write_text(source)
    subprocess.run(build(work, work / 'fixture'), check=True)
    result = run_fixture([str(work / 'fixture')], 'equipment scoring')
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout.strip())
    reject_mutants(work, [(label, 'fixture.cpp', old, new) for label, old, new in mutations], build,
                   'Equipment scoring')
