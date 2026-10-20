"""Compile the real raid policy and reject role, learned-spell and subgroup mutations."""
import argparse
import os
from pathlib import Path
import re
import shutil
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


STUBS = r'''
#pragma once
#include <array>
#include <cassert>
#include <cstdint>
#include <map>
#include <memory>
#include <string>
#include <vector>
using uint8=uint8_t;using uint32=uint32_t;
using ObjectGuid=uint32;
constexpr uint8 POWER_MANA=0,POWER_RAGE=1,CLASS_HUNTER=3,CLASS_SHAMAN=7,CLASS_MAGE=8;
constexpr uint32 SPELL_EFFECT_APPLY_AURA=6,SPELL_EFFECT_SUMMON=28,SPELL_EFFECT_APPLY_AREA_AURA_PARTY=35,SPELL_EFFECT_APPLY_AREA_AURA_RAID=65,TARGET_UNIT_CASTER_AREA_PARTY=20;
struct Target {uint32 id=0;uint32 GetTarget()const{return id;}};
struct SpellEffectInfo {uint32 Effect=0;Target TargetA,TargetB;int32_t MiscValue=0;};
struct SpellInfo {std::array<SpellEffectInfo,3> Effects;};
struct SpellMgr {std::map<uint32,SpellInfo> spells;SpellInfo const* GetSpellInfo(uint32 id){auto i=spells.find(id);return i==spells.end()?nullptr:&i->second;}};
SpellMgr spellMgr;SpellMgr* sSpellMgr=&spellMgr;
struct CreatureTemplate {std::array<uint32,8> spells{};};
struct ObjectMgr {std::map<uint32,CreatureTemplate> creatures;CreatureTemplate const* GetCreatureTemplate(uint32 id){auto i=creatures.find(id);return i==creatures.end()?nullptr:&i->second;}};
ObjectMgr objectMgr;ObjectMgr* sObjectMgr=&objectMgr;
struct Player;
struct LearnedSpell {std::string name;bool active=true,removed=false,inSpec=true,passive=false;};
struct Value {uint32 value=0;uint32 Get(){return value;}};
struct Context {Player* player;Value value;template<class T>Value* GetValue(char const*,char const*);};
struct PlayerbotAI {
 Context context;explicit PlayerbotAI(Player* player):context{player,{}}{}
 Context* GetAiObjectContext(){return &context;}
 static bool IsTank(Player*,bool bySpec=false);static bool IsHeal(Player*,bool bySpec=false);static bool IsRanged(Player*,bool bySpec=false);
};
struct Player {
 ObjectGuid guid;uint8 klass=CLASS_MAGE,power=POWER_MANA;
 bool tank=false,heal=false,ranged=false,specTank=false,specHeal=false,specRanged=false;
 std::map<uint32,LearnedSpell> spells;std::map<std::string,uint32> resolvedOverrides;
 std::unique_ptr<PlayerbotAI> ai;
 explicit Player(uint32 id):guid(id),ai(std::make_unique<PlayerbotAI>(this)){}
 uint32 GetGUID()const{return guid;}uint8 getPowerType()const{return power;}uint8 getClass()const{return klass;}
 bool HasActiveSpell(uint32 id)const {auto found=spells.find(id);return found!=spells.end()&&!found->second.removed&&found->second.active&&found->second.inSpec;}
};
#define GET_PLAYERBOT_AI(player) ((player)->ai.get())
bool PlayerbotAI::IsTank(Player* p,bool bySpec){return bySpec?p->specTank:p->tank;}
bool PlayerbotAI::IsHeal(Player* p,bool bySpec){return bySpec?p->specHeal:p->heal;}
bool PlayerbotAI::IsRanged(Player* p,bool bySpec){return bySpec?p->specRanged:p->ranged;}
template<class T>Value* Context::GetValue(char const* type,char const* name){
 assert(std::string(type)=="spell id");value.value=0;
 auto override=player->resolvedOverrides.find(name);
 if(override!=player->resolvedOverrides.end())value.value=override->second;
 else for(auto const& [id,spell]:player->spells)
  if(spell.name==name&&spell.active&&!spell.removed&&spell.inSpec&&!spell.passive)value.value=id;
 return &value;
}
'''


HARNESS = r'''
#include "EarnedRaidComposition.cpp"
using namespace EarnedRaidComposition;
struct Roster {
 std::vector<std::unique_ptr<Player>> owned;std::vector<Player*> players;
 Player* add(Role role){owned.push_back(std::make_unique<Player>(uint32(owned.size()+1)));Player* p=owned.back().get();
  p->tank=role==Tank;p->heal=role==Healer;p->ranged=role==Ranged;p->power=(role==Tank||role==Melee)?POWER_RAGE:POWER_MANA;players.push_back(p);return p;}
 void fill(Requirements q){for(uint8 i=0;i<q.tanks;++i)add(Tank);for(uint8 i=0;i<q.healers;++i)add(Healer);
  for(uint8 i=0;i<q.melee;++i)add(Melee);while(players.size()<q.size)add(Ranged);}
};
void validate(std::vector<Member> const& result,Requirements q){
 assert(result.size()==q.size&&result.front().player->tank);
 std::set<uint32> seen;std::array<uint8,8> counts{},healers{};uint8 tanks=0,heals=0,melee=0;
 for(auto const& member:result){assert(member.player&&member.subgroup<q.size/5);assert(seen.insert(member.player->guid).second);++counts[member.subgroup];
  if(member.player->tank)++tanks;else if(member.player->heal){++heals;++healers[member.subgroup];}else if(!member.player->ranged)++melee;}
 assert(tanks==q.tanks&&heals==q.healers&&melee<=q.melee);
 for(uint8 g=0;g<q.size/5;++g)assert(counts[g]==5&&healers[g]>=1);
 auto range=std::minmax_element(healers.begin(),healers.begin()+q.size/5);assert(*range.second-*range.first<=1);
}
bool same(std::vector<Member> const& a,std::vector<Member> const& b){if(a.size()!=b.size())return false;
 for(size_t i=0;i<a.size();++i)if(a[i].player!=b[i].player||a[i].subgroup!=b[i].subgroup)return false;return true;}
int main(){
 // Test-world party totems use the same summon/template/two-pulse contract as
 // the native producer; installed historical raid-wide totems follow below.
 for(uint32 i=1;i<=9;++i){spellMgr.spells[930000+i].Effects[0]={SPELL_EFFECT_SUMMON,{},{},int32_t(920000+i)};
  objectMgr.creatures[920000+i].spells[0]=930100+i;
  spellMgr.spells[930100+i].Effects[0].Effect=i==9?SPELL_EFFECT_APPLY_AREA_AURA_RAID:SPELL_EFFECT_APPLY_AREA_AURA_PARTY;}
 assert(!SubgroupSpell(0)&&!SubgroupSpell(999999));
 SpellInfo direct;direct.Effects[0].Effect=SPELL_EFFECT_APPLY_AURA;direct.Effects[0].TargetA.id=TARGET_UNIT_CASTER_AREA_PARTY;
 assert(PartyEffect(&direct));direct.Effects[0].TargetA.id=0;direct.Effects[0].TargetB.id=TARGET_UNIT_CASTER_AREA_PARTY;
 assert(PartyEffect(&direct));direct.Effects[0].TargetB.id=0;assert(!PartyEffect(&direct));
 direct.Effects[0].Effect=0;direct.Effects[0].TargetA.id=TARGET_UNIT_CASTER_AREA_PARTY;assert(!PartyEffect(&direct));
 direct.Effects[0].Effect=SPELL_EFFECT_APPLY_AREA_AURA_RAID;assert(!PartyEffect(&direct));
 objectMgr.creatures[920001].spells[0]=0;assert(!SubgroupSpell(930001));
 objectMgr.creatures[920001].spells[1]=930101;assert(SubgroupSpell(930001));objectMgr.creatures[920001].spells[1]=0;
 objectMgr.creatures[920001].spells[0]=930101;
 spellMgr.spells[930010].Effects[0]={SPELL_EFFECT_SUMMON,{},{},999999};assert(!SubgroupSpell(930010));
 spellMgr.spells[930011].Effects[0]={SPELL_EFFECT_SUMMON,{},{},-1};assert(!SubgroupSpell(930011));
 // Each supported map/size/earned-era profile retains the reviewed numeric quota.
 constexpr Profile expectedProfiles[]={
  {309,20,0,3,6,3},{509,20,0,3,5,3},{249,40,0,3,10,4},
  {409,40,0,5,11,8},{469,40,0,5,13,7},{531,40,0,5,12,7},{533,40,0,8,12,6},
  {532,10,1,2,3,2},{568,10,1,2,3,2},{565,25,1,3,7,4},{544,25,1,3,7,5},
  {548,25,1,4,7,4},{550,25,1,3,7,5},{534,25,1,3,7,5},{564,25,1,3,7,4},{580,25,1,3,8,4},
  {249,10,2,2,2,1},{249,25,2,3,5,3},{533,10,2,2,2,2},{533,25,2,3,5,5},
  {615,10,2,2,2,1},{615,25,2,2,5,5},{616,10,2,2,2,2},{616,25,2,2,5,5},
  {624,10,2,2,2,2},{624,25,2,2,5,5},{603,10,2,2,3,1},{603,25,2,3,6,4},
  {649,10,2,2,2,2},{649,25,2,3,6,4},{631,10,2,2,3,1},{631,25,2,2,6,5},
  {724,10,2,2,3,1},{724,25,2,2,6,6}
 };
 static_assert(std::size(expectedProfiles)==34);
 assert(std::size(profiles)==std::size(expectedProfiles));
 for(auto const& expected:expectedProfiles){auto q=Quota(expected.map,expected.size,expected.expansion);assert(q);
  assert(q->size==expected.size&&q->tanks==expected.tanks&&q->healers==expected.healers&&q->melee==expected.melee);
  Roster roster;roster.fill(*q);auto plan=Plan(expected.map,expected.size,expected.expansion,roster.players);validate(plan,*q);
  assert(same(plan,Plan(expected.map,expected.size,expected.expansion,roster.players)));
  Player* tank=roster.players.front();tank->tank=false;tank->ranged=true;assert(Plan(expected.map,expected.size,expected.expansion,roster.players).empty());tank->tank=true;tank->ranged=false;
  Player* healer=roster.players[q->tanks];healer->heal=false;healer->ranged=true;assert(Plan(expected.map,expected.size,expected.expansion,roster.players).empty());healer->heal=true;healer->ranged=false;
  Player* damage=roster.players.back();damage->ranged=false;assert(Plan(expected.map,expected.size,expected.expansion,roster.players).empty());damage->ranged=true;
 }
 assert(!Quota(9999,40,0)&&!Quota(409,10,0)&&!Quota(409,40,2)&&!Quota(249,40,2)&&!Quota(249,10,0));
 assert(!Quota(533,10,0)&&!Quota(533,40,2)&&!Quota(532,10,0)&&!Quota(532,10,2));
 assert(Quota(409,40,0)->tanks==5&&Quota(409,40,0)->healers==11&&Quota(409,40,0)->melee==8);
 assert(Quota(469,40,0)->tanks==5&&Quota(469,40,0)->healers==13);
 assert(Quota(309,20,0)->tanks==3&&Quota(309,20,0)->healers==6);
 assert(Quota(509,20,0)->tanks==3&&Quota(509,20,0)->healers==5);
 assert(Quota(531,40,0)->tanks==5&&Quota(531,40,0)->healers==12);
 assert(Quota(533,40,0)->tanks==8&&Quota(533,40,0)->healers==12&&Quota(533,40,0)->melee==6);
 assert(Quota(533,10,2)->tanks==2&&Quota(533,25,2)->tanks==3);
 assert(Quota(532,10,1)->tanks==2&&Quota(532,10,1)->healers==3);
 Roster roster;auto q=*Quota(532,10,1);roster.fill(q);
 // Actual strategy roles win even when class/spec heuristics disagree.
 for(Player* p:roster.players){p->klass=CLASS_SHAMAN;p->specTank=false;p->specHeal=false;p->specRanged=false;}
 validate(Plan(532,10,1,roster.players),q);
 assert(Plan(9999,10,1,roster.players).empty());assert(Plan(532,10,0,roster.players).empty());
 auto candidates=roster.players;candidates.push_back(candidates.front());assert(Plan(532,10,1,candidates).empty());
 candidates.back()=nullptr;assert(Plan(532,10,1,candidates).empty());
 candidates=roster.players;candidates.pop_back();assert(Plan(532,10,1,candidates).empty());
 // Additional tanks/healers cannot conceal missing damage dealers. Conversely,
 // ranged damage can fill all DPS places without forcing unneeded melee.
 Roster surplus;surplus.fill(q);surplus.players.pop_back();surplus.add(Tank);surplus.add(Healer);
 assert(Plan(532,10,1,surplus.players).empty());
 Roster rangedOnly;for(uint8 i=0;i<q.tanks;++i)rangedOnly.add(Tank);for(uint8 i=0;i<q.healers;++i)rangedOnly.add(Healer);
 while(rangedOnly.players.size()<q.size)rangedOnly.add(Ranged);validate(Plan(532,10,1,rangedOnly.players),q);
 auto saved=std::move(roster.players.back()->ai);assert(Plan(532,10,1,roster.players).empty());roster.players.back()->ai=std::move(saved);
 Player* provider=roster.players[q.tanks];assert(GroupBuffs(provider)==0);
 // Same class, talents and level grant no capability. Only the ordinary
 // learned-spell resolver's active current-spec nonpassive rank is useful.
 provider->spells[8512]={"windfury totem",false};
 provider->spells[930001]={"windfury totem"};assert(GroupBuffs(provider)==Physical);
 provider->spells[930001].active=false;assert(GroupBuffs(provider)==0);provider->spells[930001].active=true;
 provider->spells[930001].removed=true;assert(GroupBuffs(provider)==0);provider->spells[930001].removed=false;
 provider->spells[930001].inSpec=false;assert(GroupBuffs(provider)==0);provider->spells[930001].inSpec=true;
 provider->spells[930001].passive=true;assert(GroupBuffs(provider)==0);provider->spells[930001].passive=false;
 provider->resolvedOverrides["windfury totem"]=999999;assert(GroupBuffs(provider)==0);provider->resolvedOverrides.clear();
 provider->resolvedOverrides["windfury totem"]=8512;assert(GroupBuffs(provider)==0);provider->resolvedOverrides.clear();
 provider->resolvedOverrides["windfury totem"]=930002;assert(GroupBuffs(provider)==0);provider->resolvedOverrides.clear();
 provider->spells[930001].active=false;provider->resolvedOverrides["windfury totem"]=930001;
 assert(GroupBuffs(provider)==0);provider->resolvedOverrides.clear();provider->spells[930001].active=true;
 assert(GroupBuffs(provider)==Physical);
 provider->spells.clear();provider->spells[930002]={"wrath of air totem"};assert(GroupBuffs(provider)==Spell);
 provider->spells.clear();provider->spells[930003]={"mana spring totem"};assert(GroupBuffs(provider)==Mana);
 provider->spells[930004]={"strength of earth totem"};provider->spells[930005]={"totem of wrath"};assert(GroupBuffs(provider)==(Physical|Spell|Mana));
 provider->spells.clear();provider->spells[930006]={"grace of air totem"};assert(GroupBuffs(provider)==Weapon);
 // The shipped historical spells are not assigned subgroup scope from era
 // or class: both TBC Windfury and Vanilla Trueshot are actually raid-wide.
 provider->spells.clear();provider->spells[947330]={"windfury totem"};
 spellMgr.spells[947330].Effects[0]={SPELL_EFFECT_SUMMON,{},{},920560};objectMgr.creatures[920560].spells[0]=947335;
 spellMgr.spells[947335].Effects[0].Effect=SPELL_EFFECT_APPLY_AREA_AURA_RAID;assert(GroupBuffs(provider)==0);
 provider->spells.clear();provider->spells[932963]={"trueshot aura"};
 spellMgr.spells[932963].Effects[0].Effect=SPELL_EFFECT_APPLY_AREA_AURA_RAID;assert(GroupBuffs(provider)==0);
 provider->spells.clear();provider->spells[19506]={"trueshot aura",false};provider->spells[948380]={"trueshot aura"};
 spellMgr.spells[948380].Effects[0].Effect=SPELL_EFFECT_APPLY_AREA_AURA_PARTY;assert(GroupBuffs(provider)==Weapon);
 // Windfury benefits melee; hunters receive the separate learned agility
 // totem and mana regeneration, rather than a nonexistent ranged Windfury.
 Player hunter{99};hunter.klass=CLASS_HUNTER;hunter.ranged=true;
 Candidate hunterCandidate{&hunter,Ranged,0,true,false};
 Candidate buffer{provider,Healer,Physical,false,false};
 std::vector<Candidate> pair{hunterCandidate,buffer};std::vector<uint8> together{0,0};
 assert(GroupScore(pair,together,0)==0);
 pair[1].buffs=Weapon;assert(GroupScore(pair,together,0)==4);
 pair[1].buffs=Mana;assert(GroupScore(pair,together,0)==2);
 pair[1].buffs=Spell;assert(GroupScore(pair,together,0)==3);
 pair[1].role=Ranged;assert(GroupScore(pair,together,0)==0);
 hunter.klass=CLASS_MAGE;pair[0].caster=true;assert(GroupScore(pair,together,0)==3);
 hunter.power=POWER_RAGE;pair[0].mana=false;pair[1].buffs=Mana;assert(GroupScore(pair,together,0)==0);
 // Healer swaps preserve their distribution while bringing two independently
 // learned physical totems to different useful subgroups.
 Roster larger;auto large=*Quota(565,25,1);larger.fill(large);
 auto baseline=Plan(565,25,1,larger.players);validate(baseline,large);
 Player* first=larger.players[large.tanks+3];Player* second=larger.players[large.tanks+4];
 first->spells[930007]={"windfury totem"};second->spells[930008]={"windfury totem"};
 auto buffed=Plan(565,25,1,larger.players);validate(buffed,large);std::set<uint8> buffGroups;
 for(auto const& member:buffed)if(member.player==first||member.player==second)buffGroups.insert(member.subgroup);
 assert(buffGroups.size()==2);uint8 covered=0;
 for(auto const& member:buffed)if(buffGroups.count(member.subgroup)&&(member.player->tank||(!member.player->heal&&!member.player->ranged)))++covered;
 assert(covered>=6&&!same(baseline,buffed));
 // Raid-wide totem data does not cause subgroup shuffling.
 Roster wrath;auto wq=*Quota(533,25,2);wrath.fill(wq);auto without=Plan(533,25,2,wrath.players);
 wrath.players[wq.tanks+4]->spells[930009]={"windfury totem"};assert(same(without,Plan(533,25,2,wrath.players)));
}
'''


def native_contracts(core):
    playerbots = core / 'modules/mod-playerbots/src'
    ai = (playerbots / 'Bot/PlayerbotAI.cpp').read_text()
    header = (playerbots / 'Bot/PlayerbotAI.h').read_text()
    for method, strategy in (('IsTank', 'TANK'), ('IsHeal', 'HEAL'), ('IsRanged', 'RANGED')):
        body = function(ai, f'bool PlayerbotAI::{method}(Player* player, bool bySpec)')
        assert f'bool {method}(Player* player, bool bySpec = false)' in header
        assert (f'if (!bySpec && botAi)\n        return botAi->ContainsStrategy(STRATEGY_TYPE_{strategy});') in body
    resolver = function((playerbots / 'Ai/Base/Value/SpellIdValue.cpp').read_text(), 'uint32 SpellIdValue::Calculate()')
    for guard in ('bot->GetSpellMap()', 'PLAYERSPELL_REMOVED || !itr->second->Active',
                  '!itr->second->IsInSpec(bot->GetActiveSpec())', '!spellInfo || spellInfo->IsPassive()',
                  'LocaleConstant loc = LOCALE_enUS;', 'spellInfo->SpellName[loc]', 'spellIds.insert(spellId);'):
        assert guard in resolver, f'Native learned-spell resolver contract changed: {guard}'
    player = (core / 'src/server/game/Entities/Player/Player.cpp').read_text()
    active = function(player, 'bool Player::HasActiveSpell(uint32 spell) const')
    assert 'PLAYERSPELL_REMOVED' in active and 'Active' in active and 'IsInSpec(m_activeSpec)' in active
    # Direct party effects and both totem pulse slots are the real native
    # producers used by the scope adapter, not inferred historical mechanics.
    definitions = (core / 'src/server/shared/SharedDefines.h').read_text()
    for symbol, value in (('SPELL_EFFECT_SUMMON', 28), ('SPELL_EFFECT_APPLY_AREA_AURA_PARTY', 35),
                          ('SPELL_EFFECT_APPLY_AREA_AURA_RAID', 65), ('TARGET_UNIT_CASTER_AREA_PARTY', 20)):
        assert re.search(r'\b' + symbol + r'\s*=\s*' + str(value) + r'\b', definitions)
    totem = (core / 'src/server/game/Entities/Totem/Totem.cpp').read_text()
    summon = function(totem, 'void Totem::InitSummon()')
    assert 'CastSpell(this, GetSpell(), true);' in summon and 'CastSpell(this, GetSpell(1), true);' in summon
    assert 'uint32 GetSpell(uint8 slot = 0) const { return m_spells[slot]; }' in (
        core / 'src/server/game/Entities/Totem/Totem.h').read_text()
    creature = (core / 'src/server/game/Entities/Creature/Creature.cpp').read_text()
    assert 'm_spells[i] = GetCreatureTemplate()->spells[i];' in creature
    auras = (core / 'src/server/game/Spells/Auras/SpellAuras.cpp').read_text()
    assert 'GetSpellInfo()->Effects[effIndex].Effect == SPELL_EFFECT_APPLY_AREA_AURA_RAID)' in auras
    # These are actual shipped historical rows. Their scopes intentionally
    # differ from the era's original textbook mechanics.
    data = core / 'modules/mod-era-talents/era-data'
    def helpers(era, klass):
        return {row['id']: row for row in yaml.safe_load((data / era / f'{klass}.yaml').read_text())['helpers']}
    vanilla_hunter = helpers('vanilla', 'hunter')
    tbc_hunter = helpers('tbc', 'hunter')
    tbc_shaman = helpers('tbc', 'shaman')
    assert vanilla_hunter[932963]['effects'][0]['effect'] == 65
    assert tbc_hunter[948380]['effects'][0]['effect'] == 35
    assert tbc_shaman[947330]['effects'][0]['effect'] == 28
    assert tbc_shaman[947330]['effects'][0]['misc'] == 920560
    assert tbc_shaman[947335]['effects'][0]['effect'] == 65


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source_argument(parser)
    args = parser.parse_args()
    core = prepared_core()
    source = args.source or core / 'modules/mod-dungeon-clear/src'
    native_contracts(core)
    with tempfile.TemporaryDirectory(prefix='earned-raid-composition-') as temporary:
        work = Path(temporary)
        (work / 'NativeStubs.h').write_text(STUBS)
        for name in ('Define.h', 'AiObjectContext.h', 'CreatureData.h', 'ObjectMgr.h', 'Player.h', 'PlayerbotAI.h', 'Playerbots.h', 'SpellMgr.h'):
            (work / name).write_text('#include "NativeStubs.h"\n')
        for name in ('EarnedRaidComposition.h', 'EarnedRaidComposition.cpp'):
            shutil.copyfile(source / name, work / name)
        (work / 'fixture.cpp').write_text(HARNESS)
        flags = ['-std=c++20', '-O1', '-Wall', '-Wextra', '-Werror', '-Wno-misleading-indentation', '-I', str(work)]
        if os.name != 'nt':
            flags += [*SANITIZER_FLAGS, '-no-pie']
        executable = work / 'fixture'
        subprocess.run([cxx(), *flags, str(work / 'fixture.cpp'), '-o', str(executable)], check=True)
        result = run_fixture([str(executable)])
        if result.returncode:
            raise SystemExit(result.stdout + result.stderr)
        mutations = (
            ('tank shortfall accepted', 'EarnedRaidComposition.cpp',
             'roles[Tank].size() < quota->tanks || ', ''),
            ('healer shortfall accepted', 'EarnedRaidComposition.cpp',
             'roles[Healer].size() < quota->healers', 'false'),
            ('tank inferred from spec', 'EarnedRaidComposition.cpp',
             'PlayerbotAI::IsTank(player)', 'PlayerbotAI::IsTank(player, true)'),
            ('healer inferred from spec', 'EarnedRaidComposition.cpp',
             'PlayerbotAI::IsHeal(player)', 'PlayerbotAI::IsHeal(player, true)'),
            ('ranged inferred from spec', 'EarnedRaidComposition.cpp',
             'PlayerbotAI::IsRanged(player)', 'PlayerbotAI::IsRanged(player, true)'),
            ('duplicate character admitted', 'EarnedRaidComposition.cpp',
             '!seen.insert(player->GetGUID()).second', 'false'),
            ('wrong raid era admitted', 'EarnedRaidComposition.cpp',
             ' && profile.expansion == expansion', ' && expansion <= 2'),
            ('Naxx40 tank quota reduced', 'EarnedRaidComposition.cpp',
             '{533,40,0,8,12,6}', '{533,40,0,7,12,6}'),
            ('melee ceiling ignored', 'EarnedRaidComposition.cpp',
             'std::min<size_t>(quota->melee, roles[Melee].size())', 'roles[Melee].size()'),
            ('caster buff applied to hunters', 'EarnedRaidComposition.cpp',
             '(candidate.caster || candidate.role == Healer)', '(candidate.role == Ranged || candidate.role == Healer)'),
            ('mana buff applied without mana', 'EarnedRaidComposition.cpp', '&& candidate.mana)', ')'),
            ('healers concentrated', 'EarnedRaidComposition.cpp', '++healers[group];', '(void)healers;'),
            ('six members per subgroup', 'EarnedRaidComposition.cpp', 'occupancy[group] == 5', 'occupancy[group] == 6'),
            ('unlearned or stale spell accepted', 'EarnedRaidComposition.cpp',
             'return spell && player->HasActiveSpell(spell) && SubgroupSpell(spell);', 'return spell && SubgroupSpell(spell);'),
            ('class assumed to provide totems', 'EarnedRaidComposition.cpp',
             'return spell && player->HasActiveSpell(spell) && SubgroupSpell(spell);', 'return spell || player->getClass() == CLASS_SHAMAN;'),
            ('physical subgroup buff ignored', 'EarnedRaidComposition.cpp', 'buffs |= Physical;', 'buffs |= 0;'),
            ('hunter agility buff ignored', 'EarnedRaidComposition.cpp', 'buffs |= Weapon;', 'buffs |= 0;'),
            ('hunter receives melee Windfury', 'EarnedRaidComposition.cpp',
             '(candidate.role == Tank || candidate.role == Melee))',
             '(candidate.role == Tank || candidate.role == Melee || candidate.player->getClass() == CLASS_HUNTER))'),
            ('caster subgroup buff ignored', 'EarnedRaidComposition.cpp', 'buffs |= Spell;', 'buffs |= 0;'),
            ('mana subgroup buff ignored', 'EarnedRaidComposition.cpp', 'buffs |= Mana;', 'buffs |= 0;'),
            ('raid-wide spell treated as subgroup buff', 'EarnedRaidComposition.cpp',
             'if (effect.Effect == SPELL_EFFECT_APPLY_AREA_AURA_RAID)', 'if (false)'),
            ('actual spell scope ignored', 'EarnedRaidComposition.cpp', '&& SubgroupSpell(spell)', ''),
            ('totem primary pulse ignored', 'EarnedRaidComposition.cpp', 'uint8 slot = 0; slot < 2', 'uint8 slot = 1; slot < 2'),
            ('totem secondary pulse ignored', 'EarnedRaidComposition.cpp', 'slot < 2;', 'slot < 1;'),
            ('party target A ignored', 'EarnedRaidComposition.cpp',
             'effect.TargetA.GetTarget() == TARGET_UNIT_CASTER_AREA_PARTY ||', ''),
            ('party target B ignored', 'EarnedRaidComposition.cpp',
             'effect.TargetB.GetTarget() == TARGET_UNIT_CASTER_AREA_PARTY', 'false'),
            ('empty effect counted as party scope', 'EarnedRaidComposition.cpp', 'effect.Effect && (', '('),
            ('learned buffs do not improve groups', 'EarnedRaidComposition.cpp',
             'if (GroupScore(picked, groups, a) + GroupScore(picked, groups, b) > before)',
             'if (GroupScore(picked, groups, a) + GroupScore(picked, groups, b) > before + 1000)'),
        )
        reject_mutants(work, mutations,
                       lambda directory, binary: [cxx(), '-std=c++20', '-O1', '-I', str(directory),
                                                   str(directory / 'fixture.cpp'), '-o', str(binary)],
                       'Earned raid composition')
    print('Earned raid profiles, actual roles, learned historical buffs and five-member subgroups verified')


if __name__ == '__main__':
    main()
