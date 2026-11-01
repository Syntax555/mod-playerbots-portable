"""Exercise the imported persuasion script with native party-credit eligibility."""
import argparse
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile

from FixtureSupport import (
    SANITIZER_FLAGS,
    TIMEOUT,
    cxx,
    function,
    prepared_core,
    reject_mutants,
    source_argument,
    sql_rows,
)


STUBS = r'''
#include <cassert>
#include <cmath>
#include <cstdint>
#include <vector>
using uint32=uint32_t;using ObjectGuid=uint64_t;
constexpr uint32 REACT_PASSIVE=0,UNIT_STAND_STATE_SIT_MEDIUM_CHAIR=1,CONFIG_GROUP_XP_DISTANCE=1;
struct Map{bool IsDungeon()const{return false;}};
struct WorldObject
{
    virtual ~WorldObject()=default;
    Map* map=nullptr;float x=0;bool world=true;ObjectGuid guid=0;
    virtual bool IsCreature()const{return false;}virtual uint32 GetEntry()const{return 0;}
    ObjectGuid GetGUID()const{return guid;}Map* GetMap()const{return map;}
    bool IsInMap(WorldObject const* other)const{return world&&other->world&&map==other->map;}
    float GetDistance(WorldObject const* other)const{return std::abs(x-other->x);}
};
class Player;
struct Unit:WorldObject
{
    virtual bool IsPlayer()const{return false;}virtual Player* ToPlayer(){return nullptr;}
};
struct Creature:Unit
{
    bool IsCreature()const override{return true;}uint32 GetEntry()const override{return 25478;}
    uint32 GetReactState()const{return REACT_PASSIVE;}void SetReactState(uint32){}
    float GetPositionX()const{return x;}float GetPositionY()const{return 0;}
    float GetOrientation()const{return 0;}void UpdatePosition(float,float,float,float,bool){}
    void SetStandState(uint32){}bool HasAura(uint32)const{return true;}
};
struct GroupReference
{
    Player* player=nullptr;GroupReference* following=nullptr;
    Player* GetSource()const{return player;}GroupReference* next()const{return following;}
};
struct Group
{
    std::vector<GroupReference> members;
    GroupReference* GetFirstMember(){return members.empty()?nullptr:&members[0];}
    void Set(std::vector<Player*> players)
    {
        members.resize(players.size());
        for(uint32 i=0;i<players.size();++i)
            members[i]={players[i],i+1<players.size()?&members[i+1]:nullptr};
    }
};
struct Player:Unit
{
    Group* group=nullptr;WorldObject* corpse=nullptr;bool alive=true,quest=true;uint32 stacks=0,credits=0,calls=0;
    bool IsPlayer()const override{return true;}Player* ToPlayer()override{return this;}
    Group* GetGroup()const{return group;}WorldObject* GetCorpse()const{return corpse;}
    bool IsAlive()const{return alive;}uint32 GetAuraCount(uint32 spell)const{assert(spell==45634);return stacks;}
    bool IsAtGroupRewardDistance(WorldObject const*)const;
    void RewardPlayerAndGroupAtEvent(uint32,WorldObject*);
    void KilledMonsterCredit(uint32 entry,ObjectGuid=0){assert(entry==25478);++calls;if(quest){credits=1;quest=false;}}
};
struct World{float getFloatConfig(uint32 key)const{assert(key==CONFIG_GROUP_XP_DISTANCE);return 100;}}world;
World* sWorld=&world;
namespace ObjectAccessor
{
    Player* caster=nullptr;
    Player* GetPlayer(WorldObject const&,ObjectGuid guid){return caster&&caster->guid==guid?caster:nullptr;}
}
struct SpellInfo{uint32 Id;};
struct CreatureAI
{
    virtual ~CreatureAI()=default;virtual void Reset(){}virtual void UpdateAI(uint32){}
    virtual void JustEngagedWith(Unit*){}virtual void SpellHit(Unit*,SpellInfo const*){}
};
struct ScriptedAI:CreatureAI
{
    Creature* me;uint32 talks=0;explicit ScriptedAI(Creature* creature):me(creature){}
    void UpdateVictim(){}void DoCast(Unit*,uint32){}void DoMeleeAttackIfReady(){}
    void Talk(uint32,Player* =nullptr){++talks;}
};
struct CreatureScript
{
    explicit CreatureScript(char const*){}virtual ~CreatureScript()=default;
    virtual CreatureAI* GetAI(Creature*)const=0;
};
'''


MAIN = r'''
int main()
{
    Map northrend,elsewhere;Creature prisoner;prisoner.map=&northrend;prisoner.guid=108032;
    Player caster,nearby,distant,otherMap,ghost,unreleased,noQuest;
    for(Player* player:{&caster,&nearby,&distant,&otherMap,&ghost,&unreleased,&noQuest})player->map=&northrend;
    caster.guid=1;nearby.x=20;distant.x=101;otherMap.map=&elsewhere;noQuest.quest=false;
    WorldObject corpse;corpse.map=&northrend;corpse.x=20;ghost.alive=false;ghost.corpse=&corpse;
    unreleased.alive=false;
    Group group;group.Set({&caster,&nearby,nullptr,&distant,&otherMap,&ghost,&unreleased,&noQuest});
    for(auto const& member:group.members)if(member.player)member.player->group=&group;
    ObjectAccessor::caster=&caster;
    npc_imprisoned_beryl_sorcerer_ipp script;
    auto* ai=static_cast<npc_imprisoned_beryl_sorcerer_ipp::npc_imprisoned_beryl_sorcerer_ippAI*>(script.GetAI(&prisoner));
    SpellInfo needle{45634},wrong{1};
    for(caster.stacks=0;caster.stacks<4;++caster.stacks)ai->SpellHit(&caster,&needle);
    assert(!caster.calls&&!nearby.calls);
    ai->SpellHit(&caster,&wrong);ai->SpellHit(&prisoner,&needle);ai->GotStinged(999);
    assert(!caster.calls&&!nearby.calls);
    ai->SpellHit(&caster,&needle);
    assert(caster.credits==1&&caster.calls==1&&nearby.credits==1&&nearby.calls==1);
    assert(!distant.calls&&!otherMap.calls&&!ghost.calls&&!noQuest.credits);
    assert(unreleased.credits==1);
    for(caster.stacks=5;caster.stacks<7;++caster.stacks)ai->SpellHit(&caster,&needle);
    assert(caster.calls==1&&nearby.calls==1);
    delete ai;

    Player solo;solo.map=&northrend;solo.guid=2;solo.stacks=4;ObjectAccessor::caster=&solo;
    ai=static_cast<npc_imprisoned_beryl_sorcerer_ipp::npc_imprisoned_beryl_sorcerer_ippAI*>(script.GetAI(&prisoner));
    ai->SpellHit(&solo,&needle);assert(solo.credits==1&&solo.calls==1);
    solo.RewardPlayerAndGroupAtEvent(25478,nullptr);assert(solo.calls==1);
    delete ai;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source_argument(parser)
    args = parser.parse_args()
    core = prepared_core()
    module = args.source or core / 'modules/mod-individual-progression'
    source = (module / 'src/wotlkScripts/zone_borean_tundra.cpp').read_text()
    loader = (module / 'src/IndividualProgression_loader.cpp').read_text()
    assert loader.count('void AddSC_ipp_zone_borean_tundra();') == 1
    assert loader.count('    AddSC_ipp_zone_borean_tundra();') == 1

    spawn = sql_rows(core, 'creature', {108032})[0]
    assert spawn['id1'] == '25478' and spawn['map'] == '571'
    binding = (module / 'data/sql/world/base/zone_borean_tundra.sql').read_text()
    with sqlite3.connect(':memory:') as db:
        db.execute('CREATE TABLE creature (guid INTEGER, id INTEGER, ScriptName TEXT)')
        db.executemany('INSERT INTO creature VALUES (?, ?, ?)', [(108032, 25478, ''), (2, 25478, 'custom'), (3, 1, '')])
        db.executescript(binding)
        db.executescript(binding)
        assert db.execute('SELECT * FROM creature ORDER BY guid').fetchall() == [
            (2, 25478, 'custom'), (3, 1, ''), (108032, 25478, 'npc_imprisoned_beryl_sorcerer_ipp')]

    player = (core / 'src/server/game/Entities/Player/Player.cpp').read_text()
    native = function(player, 'void Player::RewardPlayerAndGroupAtEvent(') + '\n'
    native += function(player, 'bool Player::IsAtGroupRewardDistance(') + '\n'
    aura_count = function((core / 'src/server/game/Entities/Unit/Unit.cpp').read_text(), 'uint32 Unit::GetAuraCount(')
    assert 'm_appliedAuras.equal_range(spellId)' in aura_count
    assert 'count += (uint32)itr->second->GetBase()->GetStackAmount();' in aura_count
    objects = (core / 'src/server/game/Entities/Object/Object.cpp').read_text()
    assert 'IsInWorld() && obj->IsInWorld() && (FindMap() == obj->FindMap())' in function(objects, 'bool WorldObject::IsInMap(')
    quests = function((core / 'src/server/game/Entities/Player/PlayerQuest.cpp').read_text(), 'void Player::KilledMonsterCredit(')
    assert 'q_status.Status == QUEST_STATUS_INCOMPLETE' in quests
    assert 'if (reqkill == real_entry)' in quests and 'if (curkillcount < reqkillcount)' in quests
    assert 'if (CanCompleteQuest(questid))' in quests and 'CompleteQuest(questid)' in quests

    with tempfile.TemporaryDirectory(prefix='borean-persuasion-') as temporary:
        work = Path(temporary)
        (work / 'fixture.cpp').write_text(STUBS + native + '\n' + re.sub(r'^#include[^\n]*', '', source, flags=re.MULTILINE) + MAIN)

        def build(directory, executable):
            return [cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', *SANITIZER_FLAGS,
                    str(directory / 'fixture.cpp'), '-o', str(executable)]

        executable = work / 'fixture'
        subprocess.run(build(work, executable), check=True)
        subprocess.run([str(executable)], check=True, timeout=TIMEOUT)
        mutations = [
            ('caster-only credit', 'fixture.cpp',
             'caster->RewardPlayerAndGroupAtEvent(NPC_IMPRISONED_BERYL_SORCERER, me);',
             'caster->KilledMonsterCredit(NPC_IMPRISONED_BERYL_SORCERER);'),
            ('remote party credit', 'fixture.cpp',
             'if (!player->IsAtGroupRewardDistance(pRewardSource))', 'if (false)'),
            ('released ghost credit', 'fixture.cpp',
             'if (player->IsAlive() || !player->GetCorpse())', 'if (true)'),
            ('late quest credit', 'fixture.cpp', 'case 5:', 'case 8:'),
        ]
        reject_mutants(work, mutations, build, 'Borean persuasion')
    print('Borean persuasion: fifth needle, native nearby party credit, solo credit and spawn binding verified')


if __name__ == '__main__':
    main()
