"""Validate Era spell-group SQL with native loading and effect aggregation.

Requires the prepared modules and the pinned English Spell.dbc fetched by client
packaging. The production SpellMgr methods execute against real spell/rank data;
the fixture supplies only the database result and SpellInfo storage interfaces.
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile

from PreparedSources import prepared_core


repo = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--core', type=Path, default=prepared_core(repo))
parser.add_argument('--module', type=Path)
parser.add_argument('--base-dbc', type=Path)
args = parser.parse_args()
module = args.module or args.core / 'modules/mod-era-talents'
lock = json.loads((repo / 'versions.lock.json').read_text())
locale = lock['clientPatch']['localizations']['deDE']
base_dbc = args.base_dbc or repo / '.module-cache/client-locales' / locale['revision'] / 'deDE/Spell.enUS.dbc'
assert hashlib.sha256(base_dbc.read_bytes()).hexdigest() == locale['englishSpellSha256']
sys.path.insert(0, str(module / 'tools'))
spec = importlib.util.spec_from_file_location('era_audit_fixture', module / 'tools/era_audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
spells = audit.G.read_dbc_templates(base_dbc)
sql_directory = module / 'data/sql/world'
update = sql_directory / 'updates/2026_10_09_00_era_spell_group_contracts.sql'
assert update.is_file()


def statements(text):
    # These selected tables contain integer rows and short rule descriptions.
    # Generated spell_dbc text is parsed separately by the module's own parser.
    text = re.sub(r'(?m)^\s*--.*$', '', text)
    return re.findall(r'(?im)^(?:DELETE\s+FROM|INSERT\s+INTO)\s+`'
                      r'(?:spell_group|spell_group_stack_rules|spell_ranks)`[^;]*;', text)


db = sqlite3.connect(':memory:')
db.executescript('''
CREATE TABLE spell_group (id INTEGER, spell_id INTEGER, PRIMARY KEY (id, spell_id));
CREATE TABLE spell_group_stack_rules (group_id INTEGER PRIMARY KEY, stack_rule INTEGER, description TEXT);
CREATE TABLE spell_ranks (first_spell_id INTEGER, spell_id INTEGER PRIMARY KEY, rank INTEGER);
''')
for table in ('spell_group', 'spell_group_stack_rules', 'spell_ranks'):
    for statement in statements((args.core / 'data/sql/base/db_world' / (table + '.sql')).read_text()):
        # MySQL uses backslash-escaped apostrophes in rule descriptions.
        db.executescript(statement.replace("\\'", "''"))
for path in sorted((args.core / 'data/sql/updates/db_world').glob('*.sql')):
    for statement in statements(path.read_text()):
        db.executescript(statement.replace("\\'", "''"))
for path in sorted(sql_directory.rglob('*.sql')):
    if path != update:
        for statement in statements(path.read_text()):
            db.executescript(statement)
    if path.parent.name == 'base':
        spells.update(audit._spell_dbc_rows(path.read_text()))

before = db.execute('SELECT id, spell_id FROM spell_group ORDER BY id, spell_id').fetchall()
rules = db.execute('SELECT group_id, stack_rule FROM spell_group_stack_rules ORDER BY group_id').fetchall()
ranks = db.execute('SELECT first_spell_id, spell_id, rank FROM spell_ranks ORDER BY first_spell_id, rank').fetchall()
deleted = {(1007, s) for s in (932661, 932662, 932664, 946136)}
deleted |= {(1060, s) for s in (932301, 932302, 932303, 932300)}
deleted |= {(1016, 946277), (1037, 932763), (1037, 948860), (1094, 946266), (1122, 920920)}
assert len(deleted) == 13 and deleted <= set(before)
db.executescript(update.read_text())
after = db.execute('SELECT id, spell_id FROM spell_group ORDER BY id, spell_id').fetchall()
assert set(before) - set(after) == deleted and not (set(after) - set(before))
db.executescript(update.read_text())
assert db.execute('SELECT id, spell_id FROM spell_group ORDER BY id, spell_id').fetchall() == after
assert db.execute('SELECT group_id, stack_rule FROM spell_group_stack_rules ORDER BY group_id').fetchall() == rules
assert db.execute('SELECT first_spell_id, spell_id, rank FROM spell_ranks ORDER BY first_spell_id, rank').fetchall() == ranks
# Identical spell ids outside the intended group, and neighboring stock spell ids,
# must survive: the migration is never a DELETE by spell or group alone.
sentinels = [(99999, s) for _, s in deleted] + [(g, 999999) for g, _ in deleted]
db.executemany('INSERT OR IGNORE INTO spell_group VALUES (?, ?)', sentinels)
db.executescript(update.read_text())
assert set(sentinels) <= set(db.execute('SELECT id, spell_id FROM spell_group'))


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


mgr_source = (args.core / 'src/server/game/Spells/SpellMgr.cpp').read_text()
methods = '\n'.join(function(mgr_source, signature) for signature in (
    'SpellSpellGroupMapBounds SpellMgr::GetSpellSpellGroupMapBounds(',
    'bool SpellMgr::IsSpellMemberOfSpellGroup(',
    'SpellGroupSpellMapBounds SpellMgr::GetSpellGroupSpellMapBounds(',
    'void SpellMgr::GetSetOfSpellsInSpellGroup(SpellGroup group_id, std::set<uint32>& foundSpells)',
    'void SpellMgr::GetSetOfSpellsInSpellGroup(SpellGroup group_id, std::set<uint32>& foundSpells,',
    'bool SpellMgr::AddSameEffectStackRuleSpellGroups(',
    'SpellGroupStackRule SpellMgr::CheckSpellGroupStackRules(',
    'void SpellMgr::LoadSpellGroups()', 'void SpellMgr::LoadSpellGroupStackRules()'))
info_source = (args.core / 'src/server/game/Spells/SpellInfo.cpp').read_text()
methods += '\n' + '\n'.join(function(info_source, signature) for signature in (
    'bool SpellEffectInfo::IsAura() const', 'bool SpellEffectInfo::IsAura(AuraType aura) const',
    'bool SpellEffectInfo::IsAreaAuraEffect() const', 'bool SpellEffectInfo::IsUnitOwnedAuraEffect() const',
    'bool SpellInfo::HasAura(AuraType aura) const'))
shared_defines = (args.core / 'src/server/shared/SharedDefines.h').read_text()
aura_effect_names = (
    'SPELL_EFFECT_APPLY_AURA', 'SPELL_EFFECT_PERSISTENT_AREA_AURA', 'SPELL_EFFECT_APPLY_AREA_AURA_PARTY',
    'SPELL_EFFECT_APPLY_AREA_AURA_RAID', 'SPELL_EFFECT_APPLY_AREA_AURA_PET',
    'SPELL_EFFECT_APPLY_AREA_AURA_FRIEND', 'SPELL_EFFECT_APPLY_AREA_AURA_ENEMY', 'SPELL_EFFECT_APPLY_AREA_AURA_OWNER')
aura_effect_constants = '\n'.join(
    f'constexpr uint32 {name} = {re.search(rf"\b{name}\s*=\s*(\d+)", shared_defines).group(1)};'
    for name in aura_effect_names)

stub = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <sstream>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>
using uint8 = std::uint8_t; using uint32 = std::uint32_t; using int32 = std::int32_t;
using int8 = std::int8_t;
using SpellGroup = uint32; using AuraType = uint32;
constexpr uint32 SPELL_GROUP_DB_RANGE_MIN = 1000, SPELL_GROUP_CORE_RANGE_MAX = 3;
constexpr uint32 SPELL_AURA_MOD_MELEE_HASTE = 138, SPELL_AURA_MOD_MELEE_RANGED_HASTE = 192;
constexpr uint32 SPELL_AURA_MOD_RANGED_HASTE = 140;
constexpr uint8 MAX_SPELL_EFFECTS = 3;
AURA_EFFECT_CONSTANTS
enum SpellGroupStackRule { SPELL_GROUP_STACK_RULE_DEFAULT, SPELL_GROUP_STACK_RULE_EXCLUSIVE,
    SPELL_GROUP_STACK_RULE_EXCLUSIVE_FROM_SAME_CASTER, SPELL_GROUP_STACK_RULE_EXCLUSIVE_SAME_EFFECT,
    SPELL_GROUP_STACK_RULE_EXCLUSIVE_HIGHEST, SPELL_GROUP_STACK_RULE_MAX };
using SpellGroupSpellMap = std::unordered_multimap<SpellGroup, int32>;
using SpellGroupSpellMapBounds = std::pair<SpellGroupSpellMap::const_iterator, SpellGroupSpellMap::const_iterator>;
using SpellSpellGroupMap = std::unordered_multimap<uint32, SpellGroup>;
using SpellSpellGroupMapBounds = std::pair<SpellSpellGroupMap::const_iterator, SpellSpellGroupMap::const_iterator>;
using SpellGroupStackMap = std::unordered_map<SpellGroup, SpellGroupStackRule>;
std::vector<std::string> warnings;
template<class... T> void LogError(char const* message, T... values) {
    std::ostringstream out; out << message; ((out << '|' << values), ...); warnings.push_back(out.str());
}
template<class... T> void IgnoreLog(T...) {}
#define LOG_ERROR(category, ...) LogError(__VA_ARGS__)
#define LOG_INFO(category, ...) IgnoreLog(__VA_ARGS__)
#define LOG_WARN(category, ...) IgnoreLog(__VA_ARGS__)
#define ASSERT(condition) assert(condition)
uint32 getMSTime() { return 0; } uint32 GetMSTimeDiffToNow(uint32) { return 0; }
struct SpellEffectInfo {
    uint32 Effect = 0, ApplyAuraName = 0;
    bool IsAura() const; bool IsAura(AuraType) const;
    bool IsAreaAuraEffect() const; bool IsUnitOwnedAuraEffect() const;
};
struct SpellInfo {
    uint32 Id = 0, root = 0, rank = 0, next = 0;
    std::array<SpellEffectInfo, 3> Effects{};
    uint32 GetRank() const { return rank; }
    auto const& GetEffects() const { return Effects; }
    bool HasAura(AuraType) const;
    SpellInfo const* GetFirstRankSpell() const;
    SpellInfo const* GetNextRankSpell() const;
};
std::map<uint32, SpellInfo> store;
SpellInfo const* SpellInfo::GetFirstRankSpell() const { return &store.at(root); }
SpellInfo const* SpellInfo::GetNextRankSpell() const { return next ? &store.at(next) : nullptr; }
struct Field {
    int32 value;
    template<class T> T Get() const { return T(value); }
};
using Rows = std::vector<std::array<Field, 2>>;
struct Result {
    Rows rows; std::size_t cursor = 0;
    Field* Fetch() { return rows.at(cursor).data(); }
    bool NextRow() { return ++cursor < rows.size(); }
};
using QueryResult = std::shared_ptr<Result>;
struct Database {
    Rows groups, rules;
    QueryResult Query(std::string const& query) const {
        auto const& rows = query.find("stack_rules") != std::string::npos ? rules : groups;
        if (rows.empty()) return nullptr;
        return std::make_shared<Result>(Result{rows, 0});
    }
} WorldDatabase;
class SpellMgr {
public:
    SpellGroupSpellMap mSpellGroupSpell;
    SpellSpellGroupMap mSpellSpellGroup;
    SpellGroupStackMap mSpellGroupStack;
    std::unordered_map<SpellGroup, std::unordered_set<uint32>> mSpellSameEffectStack;
    SpellInfo const* GetSpellInfo(uint32 id) const { auto it = store.find(id); return it == store.end() ? nullptr : &it->second; }
    SpellInfo const* AssertSpellInfo(uint32 id) const { auto* info = GetSpellInfo(id); assert(info); return info; }
    uint32 GetFirstSpellInChain(uint32 id) const { return store.at(id).root; }
    SpellSpellGroupMapBounds GetSpellSpellGroupMapBounds(uint32) const;
    bool IsSpellMemberOfSpellGroup(uint32, SpellGroup) const;
    SpellGroupSpellMapBounds GetSpellGroupSpellMapBounds(SpellGroup) const;
    void GetSetOfSpellsInSpellGroup(SpellGroup, std::set<uint32>&) const;
    void GetSetOfSpellsInSpellGroup(SpellGroup, std::set<uint32>&, std::set<SpellGroup>&) const;
    bool AddSameEffectStackRuleSpellGroups(SpellInfo const*, uint32, int32, std::map<SpellGroup, int32>&) const;
    SpellGroupStackRule CheckSpellGroupStackRules(SpellInfo const*, SpellInfo const*) const;
    void LoadSpellGroups(); void LoadSpellGroupStackRules();
};
'''
stub = stub.replace('AURA_EFFECT_CONSTANTS', aura_effect_constants)

ids = {spell for _, spell in before if spell > 0}
roots = {spell: (root, rank) for root, spell, rank in ranks}
for root, spell, rank in ranks:
    if root in ids:
        ids.add(spell)
assert ids <= spells.keys()
idx = audit.IDX
records = []
for spell in sorted(ids):
    row = spells[spell]
    root, rank = roots.get(spell, (spell, 0))
    records.append(f'store[{spell}] = SpellInfo{{{spell}, {root}, {rank}, 0, {{{{'
                   + ', '.join('{' + f'{row[idx[f"Effect_{i}"]]}, {row[idx[f"EffectAura_{i}"]]}' + '}'
                               for i in (1, 2, 3)) + '}}};')
for root, spell, rank in ranks:
    if spell in ids:
        next_spell = next((s for r, s, n in ranks if r == root and n == rank + 1), 0)
        if next_spell:
            assert next_spell in ids
            records.append(f'store.at({spell}).next = {next_spell};')


def cpp_rows(rows):
    return '{' + ','.join('{{' + f'Field{{{a}}},Field{{{b}}}' + '}}' for a, b in rows) + '}'


checks = r'''
SpellGroupStackRule effectiveRule(SpellGroupStackRule rule) {
    // Aura::CanStackWith puts DEFAULT and SAME_EFFECT on the same no-exclusion
    // branch. Rule 3 instead changes only matching effect aggregation, checked below.
    return rule == SPELL_GROUP_STACK_RULE_EXCLUSIVE_SAME_EFFECT ? SPELL_GROUP_STACK_RULE_DEFAULT : rule;
}
int main() {
INIT_RECORDS
    WorldDatabase.rules = RULES;
    WorldDatabase.groups = BEFORE;
    SpellMgr original;
    original.LoadSpellGroups(); original.LoadSpellGroupStackRules();
    auto beforeWarnings = warnings;
    warnings.clear();
    WorldDatabase.groups = AFTER;
    SpellMgr repaired;
    repaired.LoadSpellGroups(); repaired.LoadSpellGroupStackRules();
    std::multiset<std::string> removed(beforeWarnings.begin(), beforeWarnings.end());
    for (auto const& warning : warnings) {
        auto it = removed.find(warning); assert(it != removed.end()); removed.erase(it);
    }
    std::multiset<std::string> expected = {
        "Spell {} listed in `spell_group` is not first rank of spell.|932661",
        "Spell {} listed in `spell_group` is not first rank of spell.|932662",
        "Spell {} listed in `spell_group` is not first rank of spell.|932664",
        "Spell {} listed in `spell_group` is not first rank of spell.|946136",
        "Spell {} listed in `spell_group` is not first rank of spell.|932301",
        "Spell {} listed in `spell_group` is not first rank of spell.|932302",
        "Spell {} listed in `spell_group` is not first rank of spell.|932303",
        "SpellId {} listed in `spell_group` with stack rule 3 does not share aura assigned for group {}|946277|1016",
        "SpellId {} listed in `spell_group` with stack rule 3 does not share aura assigned for group {}|946277|1019",
        "SpellId {} listed in `spell_group` with stack rule 3 does not share aura assigned for group {}|946277|1051",
        "SpellId {} listed in `spell_group` with stack rule 3 does not share aura assigned for group {}|932763|1037",
        "SpellId {} listed in `spell_group` with stack rule 3 does not share aura assigned for group {}|948860|1037",
        "SpellId {} listed in `spell_group` with stack rule 3 does not share aura assigned for group {}|946266|1094",
        "SpellId {} listed in `spell_group` with stack rule 3 does not share aura assigned for group {}|920920|1122"
    };
    // Before the migration, group 1060 ties stat aura 29 with hit aura 54.
    // std::unordered_multiset tie order differs between STL implementations;
    // Linux can choose 29 and disable the actual hit-debuff stacking rule.
    auto const& oldHitAuras = original.mSpellSameEffectStack.at(1060);
    assert(oldHitAuras == std::unordered_set<uint32>{29} || oldHitAuras == std::unordered_set<uint32>{54});
    bool correctedHitRule = oldHitAuras.count(29);
    for (uint32 id : correctedHitRule ? std::vector<uint32>{3043, 5570, 948281} : std::vector<uint32>{932300}) {
        std::ostringstream warning;
        warning << "SpellId {} listed in `spell_group` with stack rule 3 does not share aura assigned for group {}|"
                << id << "|1060";
        expected.insert(warning.str());
    }
    if (removed != expected) {
        for (auto const& warning : removed) std::cerr << "removed: " << warning << '\n';
        for (auto const& warning : warnings) std::cerr << "remaining: " << warning << '\n';
    }
    assert(removed == expected);
    assert(repaired.mSpellGroupStack == original.mSpellGroupStack);
    assert(repaired.mSpellSameEffectStack.at(1060) == std::unordered_set<uint32>{54});
    auto oldSameEffects = original.mSpellSameEffectStack;
    oldSameEffects.at(1060) = {54};
    assert(repaired.mSpellSameEffectStack == oldSameEffects);
    std::size_t effects = 0, pairs = 0;
    std::set<std::pair<uint32, uint32>> restoredInfusionExclusions;
    for (auto const& [id, info] : store) {
        for (auto const& effect : info.GetEffects()) {
            if (!effect.IsAura()) continue;
            for (int32 amount : {-300, -1, 0, 1, 20, 100, 300}) {
                std::map<SpellGroup, int32> oldAmounts, newAmounts;
                // Unit aggregates the aura actually supplied by this spell.
                // Asking an unrelated spell for another spell's aura produces
                // impossible effects for the rows intentionally removed here.
                bool oldGrouped = original.AddSameEffectStackRuleSpellGroups(&info, effect.ApplyAuraName, amount, oldAmounts);
                bool newGrouped = repaired.AddSameEffectStackRuleSpellGroups(&info, effect.ApplyAuraName, amount, newAmounts);
                if (oldGrouped != newGrouped || oldAmounts != newAmounts) {
                    assert(correctedHitRule && original.IsSpellMemberOfSpellGroup(id, 1060));
                    assert(effect.ApplyAuraName == 29 || effect.ApplyAuraName == 54);
                    if (effect.ApplyAuraName == 29) {
                        assert(oldGrouped && oldAmounts.at(1060) == amount && !newAmounts.count(1060));
                    } else {
                        assert(newGrouped && newAmounts.at(1060) == amount && !oldAmounts.count(1060));
                    }
                    oldAmounts.erase(1060); newAmounts.erase(1060);
                    assert(oldAmounts == newAmounts);
                }
                ++effects;
            }
        }
        for (auto const& [otherId, other] : store) {
            auto oldRule = original.CheckSpellGroupStackRules(&info, &other);
            auto newRule = repaired.CheckSpellGroupStackRules(&info, &other);
            if (effectiveRule(oldRule) != effectiveRule(newRule)) {
                // The incorrect earlier group 1122 hid existing rule 1123.
                // Removing it exposes the intended Power Infusion exclusion;
                // no other exclusion may change, including Arcane Power.
                assert(oldRule == SPELL_GROUP_STACK_RULE_EXCLUSIVE_SAME_EFFECT);
                assert(newRule == SPELL_GROUP_STACK_RULE_EXCLUSIVE_HIGHEST);
                assert(repaired.IsSpellMemberOfSpellGroup(id, 1123));
                assert(repaired.IsSpellMemberOfSpellGroup(otherId, 1123));
                restoredInfusionExclusions.emplace(id, otherId);
            }
            ++pairs;
        }
    }
    std::set<std::pair<uint32, uint32>> expectedInfusionExclusions = {
        {10060, 920920}, {920920, 10060}, {920920, 920920}, {920920, 948039}, {948039, 920920}
    };
    assert(restoredInfusionExclusions == expectedInfusionExclusions);
    for (uint32 id : {932617, 932661, 932662, 932664, 946136}) {
        assert(repaired.IsSpellMemberOfSpellGroup(id, 1007));
        assert(repaired.CheckSpellGroupStackRules(&store.at(id), &store.at(20911)) == SPELL_GROUP_STACK_RULE_EXCLUSIVE);
    }
    assert(repaired.IsSpellMemberOfSpellGroup(948281, 1060));
    assert(repaired.IsSpellMemberOfSpellGroup(932764, 1037));
    assert(repaired.IsSpellMemberOfSpellGroup(948960, 1037));
    assert(repaired.IsSpellMemberOfSpellGroup(920920, 1123));
    assert(repaired.IsSpellMemberOfSpellGroup(948039, 1122));
    assert(repaired.CheckSpellGroupStackRules(&store.at(920920), &store.at(932760)) == SPELL_GROUP_STACK_RULE_EXCLUSIVE_HIGHEST);
    for (auto const& [firstAmount, strongestAmount] : std::vector<std::pair<int32, int32>>{
             {-3, -5}, {3, 5}, {0, -5}, {0, 5}, {-3, -3}}) {
        std::map<SpellGroup, int32> hitAmounts;
        assert(repaired.AddSameEffectStackRuleSpellGroups(&store.at(3043), 54, firstAmount, hitAmounts));
        assert(repaired.AddSameEffectStackRuleSpellGroups(&store.at(5570), 54, firstAmount, hitAmounts));
        assert(repaired.AddSameEffectStackRuleSpellGroups(&store.at(948281), 54, strongestAmount, hitAmounts));
        assert(hitAmounts.size() == 1 && hitAmounts.at(1060) == strongestAmount);
        assert(!repaired.AddSameEffectStackRuleSpellGroups(&store.at(932300), 29, -20, hitAmounts));
        assert(hitAmounts.size() == 1 && hitAmounts.at(1060) == strongestAmount);
    }
    std::cout << "Era spell groups: " << expected.size() << " native diagnostics corrected; " << store.size() << " spell/rank records, "
              << pairs - restoredInfusionExclusions.size() << " effective exclusion pairs preserved; "
              << restoredInfusionExclusions.size() << " intended Infusion exclusions restored; "
              << effects << " actual-effect aggregation scenarios checked\n";
}
'''
checks = checks.replace('INIT_RECORDS', '\n'.join(records)).replace('RULES', cpp_rows(rules))
checks = checks.replace('BEFORE', cpp_rows(before)).replace('AFTER', cpp_rows(after))
with tempfile.TemporaryDirectory(prefix='portable-era-spell-groups-') as temporary:
    path = Path(temporary)
    source = path / 'spell-groups.cpp'
    binary = path / 'spell-groups'
    source.write_text(stub + methods + checks)
    subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror', '-fmax-errors=5', '-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer', '-no-pie', str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print('Era spell groups: 13-row migration is targeted and idempotent; spell/rank data and stock rules unchanged')
