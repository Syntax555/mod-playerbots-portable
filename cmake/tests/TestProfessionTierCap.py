"""Exercise upstream profession and equipment gates without changing existing characters."""

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
    source_argument,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, 'core', default=prepared_core())
source_argument(parser)
args = parser.parse_args()
module = args.source or args.core / 'modules/mod-individual-progression'
spells = (module / 'src/IndividualProgressionSpells.cpp').read_text()
player = (module / 'src/IndividualProgressionPlayer.cpp').read_text()
progression = (module / 'src/IndividualProgression.cpp').read_text()
header = (module / 'src/IndividualProgression.h').read_text()
assert header.count('bool enabled, questXpFix,') == 1
assert 'CapProfessionSkills' not in player + spells + header
assert 'CapProfessionAchievements' not in player + spells + header
native = (args.core / 'src/server/game/Spells/SpellMgr.h').read_text()
assert re.search(r'uint16 maxvalue;', function(native, 'struct SpellLearnSkillNode'))
assert 'SpellLearnSkillNode const* GetSpellLearnSkill(uint32 spell_id) const;' in native
storage = (args.core / 'src/server/game/Entities/Player/PlayerStorage.cpp').read_text()
assert 'err = CanEquipItem(slot, dest, item, false, false);' in storage
assert 'OnPlayerCanEquipItem(const_cast<Player*>(this), slot, dest, pItem, swap, not_loading)' in storage
skills = re.search(r'static constexpr std::array<uint16, 14> professionSkills =\s*\{.*?\};', spells, re.DOTALL).group(0)
names = re.findall(r'SKILL_[A-Z_]+', skills)
parts = '\n'.join((skills, *(function(spells, signature) for signature in (
    'static SpellLearnSkillNode const* GetProfessionRankNode(',
    'static uint16 GetProfessionRank(',
    'uint16 IndividualProgression::GetProfessionSkillCap(',
    'bool IndividualProgression::IsProfessionRankAboveCap(',
)), function(progression, 'bool IndividualProgression::isLockedExpansionGear(')))
hooks = '\n'.join(function(player, signature).replace(' override', '') for signature in (
    '    void OnPlayerGetTrainerSpellState(', '    bool OnPlayerCanLearnSpell(',
    '    bool OnPlayerCanUseItem(', '    bool OnPlayerCanEquipItem(',
))
prelude = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <map>
using uint8=uint8_t; using uint16=uint16_t; using uint32=uint32_t;
enum { @SKILLS@ };
constexpr int PROGRESSION_PRE_TBC=8, PROGRESSION_TBC_TIER_5=13;
constexpr int SPELL_EFFECT_LEARN_SPELL=36, ITEM_CLASS_WEAPON=2, ITEM_CLASS_ARMOR=4;
constexpr int PLAYER_FIELD_BYTES=0,PLAYER_FIELD_BYTES_OFFSET_LIFETIME_MAX_PVP_RANK=0;
struct ChatHandler {explicit ChatHandler(void*){}void SendSysMessage(char const*){}};
enum InventoryResult { EQUIP_ERR_OK, EQUIP_ERR_CANT_EQUIP_SKILL };
namespace Trainer { enum class SpellState { Available, Unavailable, Known }; }
struct Player {
    int stage=0, level=60; bool world=true, excluded=false, gm=false, bot=false;
    bool IsInWorld() const {return world;}
    uint8 GetLevel() const {return level;}
    void* GetSession() {return nullptr;}
    uint8 GetByteValue(int,int) const {return 0;}
};
struct ItemSpell {int SpellId=0;};
struct ItemTemplate {int Class=ITEM_CLASS_ARMOR; uint32 ItemId=25000, RequiredLevel=57, ItemLevel=90, RequiredHonorRank=0; std::array<ItemSpell,5> Spells{};};
struct Item {ItemTemplate proto;ItemTemplate const* GetTemplate() const {return &proto;}};
struct SpellLearnSkillNode {uint16 skill,step,value,maxvalue;};
struct SpellEffectInfo {int Effect=0;uint32 TriggerSpell=0;};
struct SpellInfo {std::array<SpellEffectInfo,3> Effects{};};
struct SpellManager {
    std::map<uint32,SpellLearnSkillNode> ranks;
    std::map<uint32,SpellInfo> spells;
    SpellLearnSkillNode const* GetSpellLearnSkill(uint32 id) const {auto i=ranks.find(id);return i==ranks.end()?nullptr:&i->second;}
    SpellInfo const* GetSpellInfo(uint32 id) const {auto i=spells.find(id);return i==spells.end()?nullptr:&i->second;}
} manager;
auto* sSpellMgr=&manager;
struct IndividualProgression {
    bool enabled=true, ProfessionTierCap=true, LockLaterExpansionGear=true, strict=true;
    uint8 BotAccountsMaxLevel=80;
    bool IsStrictDefaultProgression() const {return strict;}
    bool isExcludedAccount(Player* p) const {return !strict&&p->excluded;}
    bool isGMAccount(Player* p) const {return p->gm;}
    bool isBotAccount(Player* p) const {return !strict&&p->bot;}
    bool hasPassedProgression(Player* p,int stage) const {return p->stage>=stage;}
    void TrainerRNDbotSpellsUnlock(Player const*,uint32,Trainer::SpellState&) {}
    uint16 GetProfessionSkillCap(Player*);
    bool IsProfessionRankAboveCap(Player*,uint32);
    bool isLockedExpansionGear(Player*,ItemTemplate const*);
} progression;
auto* sIndividualProgression=&progression;
struct Hooks { @HOOKS@ };
@PARTS@
int main() {
    Player p; Hooks hooks; ItemTemplate book;
    manager.ranks[1]={SKILL_COOKING,4,1,300};
    manager.ranks[2]={SKILL_COOKING,5,1,375};
    manager.ranks[3]={SKILL_COOKING,6,1,450};
    manager.ranks[4]={999,6,1,450}; // another skill never becomes a profession
    manager.spells[10].Effects[0]={SPELL_EFFECT_LEARN_SPELL,2};
    manager.spells[11].Effects[2]={SPELL_EFFECT_LEARN_SPELL,3};
    for (int stage : {0,7,8,12,13,18}) {
        p.stage=stage;
        uint16 cap=stage<8?300:stage<13?375:0;
        assert(progression.GetProfessionSkillCap(&p)==cap);
        for(uint32 id : {1,2,3,4,10,11,999}) {
            uint16 rank=id==1?300:id==2||id==10?375:id==3||id==11?450:0;
            bool blocked=cap&&rank>cap;
            assert(progression.IsProfessionRankAboveCap(&p,id)==blocked);
            assert(hooks.OnPlayerCanLearnSpell(&p,id)==!blocked);
            auto state=Trainer::SpellState::Available;
            hooks.OnPlayerGetTrainerSpellState(&p,0,id,state);
            assert((state==Trainer::SpellState::Unavailable)==blocked);
            state=Trainer::SpellState::Known;
            hooks.OnPlayerGetTrainerSpellState(&p,0,id,state);
            assert(state==Trainer::SpellState::Known);
            book.Spells[4].SpellId=id;
            InventoryResult result=EQUIP_ERR_OK;
            assert(hooks.OnPlayerCanUseItem(&p,&book,result)==!blocked);
            assert((result==EQUIP_ERR_CANT_EQUIP_SKILL)==blocked);
        }
    }
    p.stage=0;
    for (int exempt=0;exempt<4;++exempt) {
        progression.enabled=exempt!=0; progression.ProfessionTierCap=exempt!=1;
        p.world=exempt!=2;p.gm=exempt==3;
        assert(!progression.IsProfessionRankAboveCap(&p,3));
    }
    progression.enabled=progression.ProfessionTierCap=p.world=true;p.gm=false;
    p.excluded=p.bot=true;
    assert(progression.IsProfessionRankAboveCap(&p,3)); // strict mode ignores both account labels
    progression.strict=false;
    assert(!progression.IsProfessionRankAboveCap(&p,3)); // explicit non-strict exemption
    p.excluded=false;
    assert(progression.IsProfessionRankAboveCap(&p,3)); // bots still earn profession ranks
    progression.strict=true;p.excluded=p.bot=false;

    Item item;uint16 destination=0;
    assert(hooks.OnPlayerCanEquipItem(&p,0,destination,&item,false,false)); // owned gear stays equipped at login
    assert(!hooks.OnPlayerCanEquipItem(&p,0,destination,&item,false,true)); // new equipping is refused
    ItemTemplate gear;
    for(int level:{60,80}) {p.level=level;assert(progression.isLockedExpansionGear(&p,&gear));}
    gear.ItemId=29594;assert(!progression.isLockedExpansionGear(&p,&gear));
    gear.ItemId=42943;gear.RequiredLevel=0;gear.ItemLevel=1;
    assert(!progression.isLockedExpansionGear(&p,&gear));
    p.stage=8;gear.ItemId=36000;gear.RequiredLevel=67;
    assert(progression.isLockedExpansionGear(&p,&gear));
    gear.ItemId=35733;assert(!progression.isLockedExpansionGear(&p,&gear));
    gear.ItemId=36000;p.stage=13;assert(!progression.isLockedExpansionGear(&p,&gear));
    p.stage=0;progression.LockLaterExpansionGear=false;assert(!progression.isLockedExpansionGear(&p,&gear));
}
'''.replace('@SKILLS@', ','.join(names)).replace('@HOOKS@', hooks)

mutations = (
    ('profession rank gate', 'return cap && rank > cap;', 'return cap && false;'),
    ('trainer refusal before payment', 'state = Trainer::SpellState::Unavailable;', 'state = Trainer::SpellState::Available;'),
    ('profession books', 'result = EQUIP_ERR_CANT_EQUIP_SKILL;\n                return false;', 'result = EQUIP_ERR_OK;\n                return true;'),
    ('owned gear at login', 'not_loading && sIndividualProgression->isLockedExpansionGear', 'sIndividualProgression->isLockedExpansionGear'),
    ('personal gear era at high level', '!IsStrictDefaultProgression() && player->GetLevel() > cap', 'player->GetLevel() > cap'),
)
source = prelude.replace('@PARTS@', parts)
with tempfile.TemporaryDirectory(prefix='portable-profession-gates-') as temporary:
    directory = Path(temporary)
    for label, old, new in (('production', '', ''), *mutations):
        variant = source
        if old:
            assert old in source, label
            variant = source.replace(old, new)
        cpp = directory / 'gates.cpp'
        cpp.write_text(variant)
        executable = directory / 'gates'
        subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                        *SANITIZER_FLAGS, str(cpp), '-o', str(executable)], check=True)
        result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=60, check=False)
        assert (result.returncode == 0) == (label == 'production'), (label, result.stderr)
        print('Profession/equipment gates: ' + label + (' passed' if not old else ' mutation rejected'))
