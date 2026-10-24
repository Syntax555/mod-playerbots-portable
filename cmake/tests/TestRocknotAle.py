"""Exercise Rocknot's production turn-in without granting unpaid quest progress."""
import argparse
import os
from pathlib import Path
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
#include <cstdint>
#include <string>
using uint32=std::uint32_t;
constexpr uint32 TYPE_BAR=0,STATE_DONE=3,STATE_SPECIAL=4;
constexpr uint32 QUEST_ALE=4295,ITEM_DARK_IRON_ALE_MUG=11325,ALE_MUGS_PER_TURN_IN=2;
constexpr uint32 NPC_ROCKNOT=9503,BRD_ALE_TURN_IN_FLOOR_MS=1500;
constexpr float BRD_BAR_SCAN=80.0f,BRD_BAR_NPC_REACH=4.0f;
constexpr uint32 QUEST_STATUS_NONE=0,QUEST_STATUS_INCOMPLETE=1,QUEST_STATUS_COMPLETE=2;
#define LOG_ERROR(...) do {} while (false)
#define LOG_INFO(...) do {} while (false)
#define LOG_WARN(...) do {} while (false)
enum class ObjectiveArriveResult{Running,Done,Blocked};
struct AiObjectContext{bool throttled=false;};
struct DungeonBossInfo{};
struct Quest{};Quest aleQuest;
struct Player;
struct InstanceScript{uint32 state=0,turnIns=0;uint32 GetData(uint32)const{return state;}} instance;
struct RocknotAI{
 int calls=0;
 void sQuestReward(Player*,Quest const*,uint32){++calls;if(++instance.turnIns==3)instance.state=STATE_SPECIAL;}
};
struct Creature{
 RocknotAI ai;
 RocknotAI* AI(){return &ai;}
 float GetPositionX()const{return 1;}float GetPositionY()const{return 2;}float GetPositionZ()const{return 3;}
} rocknot;
bool natural=true,hasInstance=true,hasNpc=true,hasQuest=true,scriptHandles=false;
namespace DcEarnedPlay{bool Active(){return natural;}}
namespace DcTargeting{InstanceScript* GetInstanceScript(Player*){return hasInstance?&instance:nullptr;}}
namespace DcThrottle{constexpr int BrdAleTurnIn=0;}
namespace DcRun{
 struct Run{AiObjectContext* context;bool Throttled(int,uint32){return context->throttled;}};
 Run Of(AiObjectContext* context){return {context};}
}
struct ObjectMgr{Quest const* GetQuestTemplate(uint32){return hasQuest?&aleQuest:nullptr;}} objectMgr;
ObjectMgr* sObjectMgr=&objectMgr;
struct ScriptMgr{
 int calls=0;
 bool OnQuestReward(Player*,Creature*,Quest const*,uint32){++calls;if(scriptHandles&&++instance.turnIns==3)instance.state=STATE_SPECIAL;return scriptHandles;}
} scriptMgr;
ScriptMgr* sScriptMgr=&scriptMgr;
struct Player{
 uint32 mugs=6,status=QUEST_STATUS_NONE;
 bool inReach=true,canTake=true,canAdd=true,canReward=true;
 int rewards=0,removed=0,moves=0,accepts=0;
 Creature* FindNearestCreature(uint32,float,bool){return hasNpc?&rocknot:nullptr;}
 std::string GetName()const{return "Bot";}
 bool IsWithinDistInMap(Creature*,float)const{return inReach;}
 void StopMoving(){}void SetFacingToObject(Creature*){}
 uint32 GetItemCount(uint32)const{return mugs;}
 uint32 GetQuestStatus(uint32)const{return status;}
 bool CanTakeQuest(Quest const*,bool)const{return canTake;}
 bool CanAddQuest(Quest const*,bool)const{return canAdd;}
 void AddQuestAndCheckCompletion(Quest const*,Creature*){++accepts;status=QUEST_STATUS_COMPLETE;}
 bool CanRewardQuest(Quest const*,int,bool)const{return canReward&&status==QUEST_STATUS_COMPLETE;}
 void RewardQuest(Quest const*,int,Creature*){assert(mugs>=2);mugs-=2;status=QUEST_STATUS_NONE;++rewards;}
 void RemoveActiveQuest(uint32){++removed;status=QUEST_STATUS_NONE;}
};
void HopToward(Player* bot,float,float,float){++bot->moves;}
'''

HARNESS = r'''
void reset(){instance={};rocknot={};scriptMgr={};natural=true;hasInstance=hasNpc=hasQuest=true;scriptHandles=false;}
int main(){
 AiObjectContext context;
 // Three paid native rewards, each consuming its own two mugs, start the escort.
 reset();Player bot;
 for(int i=0;i<3;++i)assert(StartRocknotAleRun(&bot,&context,{})==(i==2?ObjectiveArriveResult::Done:ObjectiveArriveResult::Running));
 assert(bot.mugs==0&&bot.rewards==3&&bot.accepts==3&&rocknot.ai.calls==3&&scriptMgr.calls==3);
 assert(StartRocknotAleRun(&bot,&context,{})==ObjectiveArriveResult::Done&&bot.rewards==3);
 // Native script interception must not invoke the creature hook twice.
 reset();bot={};scriptHandles=true;
 for(int i=0;i<3;++i)StartRocknotAleRun(&bot,&context,{});
 assert(bot.rewards==3&&rocknot.ai.calls==0&&scriptMgr.calls==3&&instance.state==STATE_SPECIAL);
 // Missing payment, unavailable/full quest log and failed reward never count a drink.
 for(int failure=0;failure<5;++failure){
  reset();bot={};
  if(failure==0)bot.mugs=0;
  if(failure==1)bot.canTake=false;
  if(failure==2)bot.canAdd=false;
  if(failure==3)bot.canReward=false;
  if(failure==4){bot.mugs=1;bot.status=QUEST_STATUS_INCOMPLETE;}
  assert(StartRocknotAleRun(&bot,&context,{})==ObjectiveArriveResult::Blocked);
  assert(bot.rewards==0&&bot.removed==0&&rocknot.ai.calls==0&&scriptMgr.calls==0&&instance.turnIns==0);
 }
 // Existing non-natural fallback remains explicitly available outside earned play.
 reset();bot={};bot.mugs=0;natural=false;
 assert(StartRocknotAleRun(&bot,&context,{})==ObjectiveArriveResult::Running&&rocknot.ai.calls==1);
 reset();bot={};bot.inReach=false;
 assert(StartRocknotAleRun(&bot,&context,{})==ObjectiveArriveResult::Running&&bot.moves==1&&bot.rewards==0);
 reset();bot={};context.throttled=true;
 assert(StartRocknotAleRun(&bot,&context,{})==ObjectiveArriveResult::Running&&bot.rewards==0);
 context.throttled=false;hasQuest=false;
 assert(StartRocknotAleRun(&bot,&context,{})==ObjectiveArriveResult::Blocked);
}
'''


def main():
    parser = argparse.ArgumentParser()
    source_argument(parser)
    args = parser.parse_args()
    core = prepared_core()
    source = args.source or core/'modules/mod-dungeon-clear/src'
    events = (source/'Ai/Dungeon/DungeonClear/Data/Events/BlackrockDepthsEvents.cpp').read_text()
    turn_in = function(events, 'ObjectiveArriveResult StartRocknotAleRun(')
    # Native opcode dispatches the creature reward hook only after a paid reward.
    handler = function((core/'src/server/game/Handlers/QuestHandler.cpp').read_text(),
                       'void WorldSession::HandleQuestgiverChooseRewardOpcode(')
    assert handler.index('_player->CanRewardQuest(') < handler.index('_player->RewardQuest(') < handler.index('OnQuestReward(')
    assert 'questgiver->AI()->sQuestReward(' in handler
    # The double consumes two mugs and returns NONE after each repeatable reward.
    quest = sql_rows(core, 'quest_template', {4295})[0]
    addon = sql_rows(core, 'quest_template_addon', {4295})[0]
    assert (quest['RequiredItemId1'], quest['RequiredItemCount1'], addon['SpecialFlags']) == ('11325', '2', '1')
    assert sql_rows(core, 'item_template', {11325})
    definition = (core/'src/server/game/Quests/QuestDef.h').read_text()
    assert 'QUEST_SPECIAL_FLAGS_REPEATABLE              = 0x0001' in definition
    assert 'return SpecialFlags & QUEST_SPECIAL_FLAGS_REPEATABLE;' in function(definition, 'bool   IsRepeatable() const')
    player_quests = (core/'src/server/game/Entities/Player/PlayerQuest.cpp').read_text()
    reward = function(player_quests, 'void Player::RewardQuest(')
    assert 'DestroyItemCount(quest->RequiredItemId[i], quest->RequiredItemCount[i], true);' in reward
    assert reward.index('RemoveActiveQuest(quest_id, false);') < reward.index('SetRewardedQuest(quest_id);')
    assert 'm_QuestStatus.erase(itr);' in function(player_quests, 'void Player::RemoveActiveQuest(')
    status = function(player_quests, 'QuestStatus Player::GetQuestStatus(')
    assert 'if (!qInfo->IsRepeatable() && IsQuestRewarded(quest_id))' in status
    assert status.rstrip().endswith('return QUEST_STATUS_NONE;\n}')
    tables = (source/'Ai/Dungeon/DungeonClear/Data/Events/DungeonEventTables.h').read_text()
    for setting in ('QUEST_ALE = 4295', 'ITEM_DARK_IRON_ALE_MUG = 11325', 'ALE_MUGS_PER_TURN_IN = 2'):
        assert setting in tables
    compiler = cxx()
    with tempfile.TemporaryDirectory(prefix='rocknot-ale-') as temporary:
        work = Path(temporary)
        (work/'fixture.cpp').write_text(STUBS + turn_in + HARNESS)
        flags = ['-std=c++20', '-O1', '-Wall', '-Wextra', '-Wno-unused-parameter']
        if os.name != 'nt':
            flags += [*SANITIZER_FLAGS, '-no-pie']
        def build(directory, executable):
            return [compiler, *flags, str(directory/'fixture.cpp'), '-o', str(executable)]
        executable = work/('fixture.exe' if os.name == 'nt' else 'fixture')
        subprocess.run(build(work, executable), check=True)
        subprocess.run([str(executable)], check=True, timeout=TIMEOUT)
        reject_mutants(work, [
            ('unpaid reward fallback', 'fixture.cpp', 'if (DcEarnedPlay::Active())', 'if (false)'),
            ('native reward eligibility skipped', 'fixture.cpp', 'if (bot->CanRewardQuest(ale, 0, false))', 'if (true)'),
            ('mug payment skipped', 'fixture.cpp', 'bot->RewardQuest(ale, 0, rocknot);', ''),
        ], build, 'Rocknot ale')


if __name__ == '__main__':
    main()
