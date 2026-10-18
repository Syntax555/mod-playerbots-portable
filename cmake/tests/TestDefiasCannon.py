"""Compile the complete cannon driver against native-shaped item, loot and movement doubles."""
import argparse
import os
from pathlib import Path
import re
import shutil
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
)


def sql_values(row):
    values, value, quoted, index = [], '', False, 0
    while index < len(row):
        char = row[index]
        if quoted and char == '\\':
            value += row[index + 1]
            index += 1
        elif char == "'":
            quoted = not quoted
        elif char == ',' and not quoted:
            values.append(value)
            value = ''
        else:
            value += char
        index += 1
    return values + [value]


def sql_rows(core, table, entries):
    """Read named fields, so changed upstream table layouts cannot silently change test data."""
    text = (core / f'data/sql/base/db_world/{table}.sql').read_text(encoding='utf-8')
    create = text.split(f'CREATE TABLE `{table}` (')[1].split(') ENGINE')[0]
    columns = [line.split('`')[1] for line in create.splitlines() if line.strip().startswith('`')]
    rows = []
    for line in text.splitlines():
        if line.startswith('(') and int(line.split(',', 1)[0][1:]) in entries:
            rows.append(dict(zip(columns, sql_values(line.rstrip(',;')[1:-1]), strict=True)))
    assert rows, (table, entries)
    return rows


def native_contracts(core, dc):
    playerbots = core / 'modules/mod-playerbots/src/Ai/Base'
    item = sql_rows(core, 'item_template', {5397})[0]
    assert {key: int(item[key]) for key in ('class', 'spellid_1', 'spelltrigger_1', 'spellcharges_1',
                                           'stackable', 'maxcount')} == {
        'class': 13, 'spellid_1': 6250, 'spelltrigger_1': 0, 'spellcharges_1': -1, 'stackable': 1, 'maxcount': 1}
    item_header = (core / 'src/server/game/Entities/Item/ItemTemplate.h').read_text()
    assert re.search(r'ITEM_CLASS_KEY\s*=\s*13\b', item_header)
    objects = {int(row['entry']): row for row in sql_rows(core, 'gameobject_template', {17155, 16398})}
    assert int(objects[17155]['type']) == 3 and int(objects[17155]['Data0']) == 57
    assert int(objects[17155]['Data1']) == 2882 and int(objects[16398]['Data0']) == 83
    loot = sql_rows(core, 'gameobject_loot_template', {2882})
    assert len(loot) == 1 and int(loot[0]['Item']) == 5397
    assert int(loot[0]['QuestRequired']) == 0 and int(loot[0]['Chance']) == 100
    assert int(loot[0]['MinCount']) == int(loot[0]['MaxCount']) == 1
    scripts = sql_rows(core, 'smart_scripts', {16398, 1639800})
    hit = next(row for row in scripts if row['entryorguid'] == '16398' and row['source_type'] == '1')
    assert int(hit['event_type']) == 8 and int(hit['event_param1']) == 6250
    assert int(hit['action_type']) == 80 and int(hit['action_param1']) == 1639800
    opened = next(row for row in scripts if row['entryorguid'] == '1639800' and row['id'] == '1')
    assert int(opened['event_param1']) == int(opened['event_param2']) == 500
    assert int(opened['action_type']) == 118 and int(opened['action_param1']) == 2
    assert int(opened['target_param2']) == 16397

    go_source = (core / 'src/server/game/Entities/GameObject/GameObject.cpp').read_text()
    opening = function(go_source, 'SpellInfo const* GameObject::GetSpellForLock(')
    assert 'GetGOInfo()->GetLockId()' in opening and 'player->GetSpellMap()' in opening
    assert 'SPELL_EFFECT_OPEN_LOCK' in opening and 'effect.CalcValue(player) >= int32(lock->Skill[i])' in opening
    interact = function(go_source, 'bool GameObject::IsWithinDistInMap(Player const* player) const')
    assert 'IsInMap(player) && InSamePhase(player) && IsAtInteractDistance(player)' in interact
    handler = (core / 'src/server/game/Handlers/SpellHandler.cpp').read_text()
    cast = function(handler, 'void WorldSession::HandleCastSpellOpcode(')
    assert 'recvPacket >> castCount >> spellId >> castFlags;' in cast
    assert 'TriggerCastFlags triggerFlag = TRIGGERED_NONE;' in cast and 'spell->prepare(&targets)' in cast
    assert 'go->GetSpellForLock(mover->ToPlayer()) == spellInfo' in cast
    use = function(handler, 'void WorldSession::HandleUseItemOpcode(')
    assert all(contract in use for contract in ('GetUseableItemByPos(bagIndex, slot)',
        'pItem->GetGUID() != itemGUID', 'pUser->CanUseItem(pItem)',
        'pUser->CastItemUseSpell(pItem, targets, castCount, glyphIndex)'))
    player_source = (core / 'src/server/game/Entities/Player/Player.cpp').read_text()
    item_cast = function(player_source, 'void Player::CastItemUseSpell(')
    assert '(count > 0) ? TRIGGERED_FULL_MASK : TRIGGERED_NONE' in item_cast
    assert 'spell->m_CastItem = item;' in item_cast and 'spell->CheckCast(true)' in item_cast
    spell_source = (core / 'src/server/game/Spells/Spell.cpp').read_text()
    lock_cast = function(spell_source, 'SpellCastResult Spell::CanOpenLock(')
    assert 'm_CastItem && m_CastItem->GetEntry() == lockInfo->Index[j]' in lock_cast
    use_action = (playerbots / 'Actions/UseItemAction.cpp').read_text()
    assert 'bool UseItemAction::UseItemOnGameObject(Item* item, ObjectGuid go) { return UseItem(item, go, nullptr); }' in use_action
    use_action = function(use_action, 'bool UseItemAction::UseItem(Item* item, ObjectGuid goGuid, Item* itemTarget, Unit* unitTarget)')
    assert 'botAI->CanCastSpell(spellId, goTarget, false, item)' in use_action
    assert 'bot->GetSession()->HandleUseItemOpcode(packet)' in use_action
    can_move = function((core / 'modules/mod-playerbots/src/Bot/PlayerbotAI.cpp').read_text(), 'bool PlayerbotAI::CanMove()')
    assert all(contract in can_move for contract in ('UNIT_STATE_LOST_CONTROL', 'IsRooted()', 'IsCharmed()',
        'GetMotionSlotType(MOTION_SLOT_CONTROLLED) != NULL_MOTION_TYPE'))
    consume = function(spell_source, 'void Spell::TakeCastItem()')
    assert all(contract in consume for contract in ('proto->Spells[i].SpellCharges < 0',
        '(charges > 0) ? --charges : ++charges', 'if (expendable && withoutCharges)',
        'DestroyItemCount(m_CastItem, count, true)'))

    usage = (playerbots / 'Value/ItemUsageValue.cpp').read_text()
    assert re.search(r'if \(proto->Class == ITEM_CLASS_KEY\)\s+return ITEM_USAGE_USE;', usage)
    strategy = function((playerbots / 'Value/LootStrategyValue.cpp').read_text(), 'class NormalLootStrategy')
    assert 'ItemUsage usage = AI_VALUE2(ItemUsage, "item usage", out.str());' in strategy
    assert 'return usage != ITEM_USAGE_NONE;' in strategy
    store_source = (playerbots / 'Actions/LootAction.cpp').read_text()
    allowed = function(re.sub(r'//[^\n]*', '', store_source), 'bool StoreLootAction::IsLootAllowed(')
    assert 'proto->MaxCount' in allowed and 'HasItemCount(itemid, max, true)' in allowed
    assert 'lootStrategy->CanLoot(proto, context)' in allowed
    store = function(store_source, 'bool StoreLootAction::Execute(')
    assert all(contract in store for contract in ('!IsLootAllowed(itemid, botAI)',
        'lootslot_type != LOOT_SLOT_TYPE_ALLOW_LOOT && lootslot_type != LOOT_SLOT_TYPE_OWNER',
        'AI_VALUE(uint8, "bag space") > 80', 'if (maxStack == 1)',
        'CMSG_AUTOSTORE_LOOT_ITEM', 'CMSG_LOOT_RELEASE'))
    assert store.index('CMSG_AUTOSTORE_LOOT_ITEM') < store.index('CMSG_LOOT_RELEASE')
    native_loot = (core / 'src/server/game/Handlers/LootHandler.cpp').read_text()
    autostore = function(native_loot, 'void WorldSession::HandleAutostoreLootItemOpcode(')
    assert 'go->IsWithinDistInMap(_player)' in autostore and 'player->StoreLootItem(lootSlot, loot, msg)' in autostore
    storage = function(player_source, 'LootItem* Player::StoreLootItem(')
    assert 'CanStoreNewItem' in storage and 'SendEquipError' in storage
    release = function(native_loot, 'void WorldSession::DoLootRelease(')
    assert 'else if (loot->isLooted()' in release and 'go->SetLootState(GO_JUST_DEACTIVATED)' in release

    executor = (dc / 'Ai/Dungeon/DungeonClear/Util/DungeonEventExecutor.cpp').read_text()
    run = function(executor, 'StepResult DungeonEventExecutor::RunStep(')
    dispatch = 'if (DcEarnedEvents::IsDefiasCannonStep(step))\n                return DcDefiasCannon::Run(bot);'
    assert dispatch in run and run.index(dispatch) > run.index('case EventStepKind::UseItemOnGO:')
    events = (dc / 'Ai/Dungeon/DungeonClear/Data/Events/DeadminesEvents.cpp').read_text()
    registration = function(events, 'void RegisterDeadminesEvents(')
    assert all(contract in registration for contract in ('.Persistent()', '.StepsOwnMovement()',
        '.CompleteWhenGOState(DM_GO_IRON_CLAD_DOOR, DM_DOOR_OPEN_STATE, 100.0f)',
        '.UseItemOnGO(DM_ITEM_GUNPOWDER, DM_SPELL_FIRE_CANNON, DM_GO_CANNON',
        'DM_DOOR_OPEN_STATE   = 2'))
    assert 'FireDefiasCannon' not in events and '.Custom(' not in registration
    helper = (dc / 'DcDefiasCannon.cpp').read_text()
    assert all(shortcut not in helper for shortcut in ('AddItem(', 'StoreNewItem(', 'CastSpell(',
        'CastItemUseSpell(', 'SetGoState(', 'SetData(', '->Use(', 'HandleAutostoreLootItemOpcode('))
    print('Native cannon contracts: KEY loot, one negative charge, opening/use opcodes, bag/access checks and delayed door state verified')
    return item


STUBS = r'''#pragma once
#include <cassert>
#include <cstdint>
#include <map>
#include <set>
#include <vector>
using uint8=uint8_t;using uint32=uint32_t;using int32=int32_t;
enum TeamId{TEAM_ALLIANCE,TEAM_HORDE,TEAM_NEUTRAL};
enum class DcDifficultyGate:uint8{Any,NormalOnly,HeroicOnly};
struct DcDiffKey{bool IsHeroic()const{return false;}};
enum class StepResult:uint8{Running,Done,Blocked,Failed};
constexpr uint32 GO_STATE_ACTIVE_ALTERNATIVE=2,FORCED_MOVEMENT_NONE=0,CMSG_CAST_SPELL=1;
constexpr uint32 SPELL_CAST_OK=0,SPELL_AURA_MOD_SHAPESHIFT=1;
class Player;class GameObject;
struct SpellInfo{uint32 Id=3365;uint32 CheckShapeshift(uint32 form)const{return form?1:SPELL_CAST_OK;}};
struct Item{uint32 entry=5397,itemClass=NATIVE_KEY_CLASS;int charges=NATIVE_CHARGES;};
struct PlayerbotAI{Player* bot;bool movable=true;bool CanMove()const{return movable;}};
struct GameObject
{
    uint32 entry,guid,state=1;bool spawned=true,within=true,los=true,canOpen=true,knownOpening=entry==17155;
    float distance=2,x=0,y=0,z=0;SpellInfo opening;
    bool isSpawned()const{return spawned;}uint32 GetGoState()const{return state;}
    uint32 GetEntry()const{return entry;}uint32 GetGUID()const{return guid;}
    bool IsWithinDistInMap(Player*)const{return within;}
    float GetPositionX()const{return x;}float GetPositionY()const{return y;}float GetPositionZ()const{return z;}
    SpellInfo const* GetSpellForLock(Player*)const{return knownOpening?&opening:nullptr;}
};
struct WorldPacket
{
    uint32 opcode;std::vector<uint32> fields;GameObject* target=nullptr;
    explicit WorldPacket(uint32 op):opcode(op){};
    template<class T>WorldPacket& operator<<(T value){fields.push_back(uint32(value));return *this;}
};
struct SpellCastTargets{GameObject* target=nullptr;void SetGOTarget(GameObject* go){target=go;}void Write(WorldPacket& p){p.target=target;}};
struct MotionMaster
{
    Player* bot;uint32 calls=0;bool generated=false;
    void MovePoint(uint32,float,float,float,uint32,float,float,bool generate,bool);
};
struct WorldSession
{
    Player* bot;uint32 casts=0,lootAttempts=0,lootReleased=0,itemUses=0,acceptedUses=0;
    bool openingAllowed=true,itemAllowed=true,bagSpace=true,lootEligible=true,lookOnly=false,chestEmpty=false;
    void HandleCastSpellOpcode(WorldPacket& packet);
    void StoreNormalLoot();
    bool UseOwnedItem(Item* item,uint32 guid);
};
class Player
{
public:
    uint32 mapId=36,loot=0,form=0,stops=0,removedForms=0;bool ai=true,alive=true,combat=false,flight=false,casting=false,moving=false,reachable=true;
    Player* m_mover=this;PlayerbotAI botAI{this};WorldSession session{this};MotionMaster motion{this};
    GameObject chest{17155,101},cannon{16398,102},door{16397,103};Item item;bool ownsPowder=false;
    std::map<uint32,GameObject*> objects{{17155,&chest},{16398,&cannon},{16397,&door}};
    uint32 GetMapId()const{return mapId;}bool IsAlive()const{return alive;}bool IsInCombat()const{return combat;}
    bool IsInFlight()const{return flight;}bool IsNonMeleeSpellCast(bool)const{return casting;}uint32 GetLootGUID()const{return loot;}
    GameObject* FindNearestGameObject(uint32 entry,float radius){auto found=objects.find(entry);return found==objects.end()||found->second->distance>radius?nullptr:found->second;}
    Item* GetItemByEntry(uint32 entry){return ownsPowder&&entry==item.entry?&item:nullptr;}
    float GetExactDist(GameObject* go)const{return go->distance;}bool isMoving()const{return moving;}
    void StopMoving(){++stops;moving=false;}MotionMaster* GetMotionMaster(){return &motion;}WorldSession* GetSession(){return &session;}
    uint32 GetShapeshiftForm()const{return form;}void RemoveAurasByType(uint32 aura){assert(aura==SPELL_AURA_MOD_SHAPESHIFT);form=0;++removedForms;}
};
void MotionMaster::MovePoint(uint32,float,float,float,uint32,float,float,bool generate,bool)
{assert(bot->reachable);++calls;generated=generate;bot->moving=true;}
void WorldSession::HandleCastSpellOpcode(WorldPacket& packet)
{
    ++casts;assert(packet.opcode==CMSG_CAST_SPELL&&packet.fields==std::vector<uint32>({1,3365,0}));
    assert(packet.target==&bot->chest&&packet.target->knownOpening);assert(!bot->ownsPowder);
    if(openingAllowed&&bot->form==0&&!chestEmpty&&packet.target->spawned&&packet.target->within&&packet.target->canOpen)
        bot->loot=packet.target->guid;
}
void WorldSession::StoreNormalLoot()
{
    assert(bot->loot==bot->chest.guid);++lootAttempts;
    // Normal loot strategy sees the native KEY class as ITEM_USAGE_USE. It
    // respects slot eligibility, native CanStoreNewItem and the unique count.
    if(bot->item.itemClass==13&&bagSpace&&lootEligible&&!lookOnly&&!chestEmpty&&!bot->ownsPowder)
    {bot->ownsPowder=true;chestEmpty=true;bot->item.charges=NATIVE_CHARGES;}
    ++lootReleased;bot->loot=0;
    if(chestEmpty)bot->chest.spawned=false;
}
bool WorldSession::UseOwnedItem(Item* item,uint32 guid)
{
    ++itemUses;assert(bot->ownsPowder&&item==&bot->item&&guid==bot->cannon.guid);
    if(!itemAllowed||bot->form||!bot->cannon.spawned||!bot->cannon.within||!bot->cannon.canOpen)return false;
    ++acceptedUses;
    // TakeCastItem: the native -1 charge advances to zero and destroys one item.
    if(item->charges<0&&++item->charges==0)bot->ownsPowder=false;
    return true; // SmartAI opens the door 500 ms later, independently of this return.
}
#define GET_PLAYERBOT_AI(bot) ((bot)->ai?&(bot)->botAI:nullptr)
struct Config{std::set<uint32> DisallowedGameObjects;} sPlayerbotAIConfig;
namespace DcEarnedEvents{inline bool CanOpen(Player* bot,GameObject* go){return go->canOpen&&(go->entry!=16398||bot->ownsPowder);}}
namespace DcEarnedPlay{inline bool ReachableLeg(Player* bot,float,float,float){return bot->reachable;}}
struct DungeonEventExecutor{static bool HasGameObjectLos(Player*,GameObject* go){return go->los;}};
namespace DcFormGate{inline bool DropBlockingForm(Player* bot,Item*){if(!bot->form)return false;bot->RemoveAurasByType(SPELL_AURA_MOD_SHAPESHIFT);return true;}}
struct UseItemAction{PlayerbotAI* ai;explicit UseItemAction(PlayerbotAI* value):ai(value){}bool UseItemOnGameObject(Item* item,uint32 guid){return ai->bot->session.UseOwnedItem(item,guid);}};
'''


HARNESS = r'''
#include "DcDefiasCannon.cpp"
#include "AuthoredCannon.cpp"
#include <iostream>
using DcDefiasCannon::Run;
void running(Player& bot){assert(Run(&bot)==StepResult::Running);}
void quiet(Player& bot){running(bot);assert(bot.session.casts==0&&bot.session.itemUses==0&&bot.motion.calls==0);}
void BusyTests()
{
    for(bool powder:{false,true})
    {
        for(uint32 which=0;which<6;++which)
        {
            Player bot;bot.ownsPowder=powder;
            switch(which){case 0:bot.alive=false;break;case 1:bot.combat=true;break;case 2:bot.flight=true;break;
                case 3:bot.m_mover=nullptr;break;case 4:bot.casting=true;break;case 5:bot.loot=999;break;}
            quiet(bot);
        }
    }
}
void AccessTests()
{
    for(bool powder:{false,true})
    {
        for(uint32 which=0;which<8;++which)
        {
            Player bot;bot.ownsPowder=powder;GameObject* target=powder?&bot.cannon:&bot.chest;
            switch(which){case 0:bot.objects.erase(target->entry);break;case 1:target->spawned=false;break;
                case 2:target->distance=101;break;case 3:target->canOpen=false;break;
                case 4:sPlayerbotAIConfig.DisallowedGameObjects.insert(target->entry);break;
                case 5:target->distance=20;bot.reachable=false;break;
                case 6:bot.objects.erase(target->entry);bot.objects.erase(powder?17155:16398);break;
                case 7:target->distance=20;bot.botAI.movable=false;break;}
            assert(Run(&bot)==((which==3||which==4)?StepResult::Blocked:StepResult::Running));
            assert(bot.session.casts==0&&bot.session.itemUses==0&&bot.motion.calls==0);
            sPlayerbotAIConfig.DisallowedGameObjects.clear();
        }
        for(uint32 which=0;which<3;++which)
        {
            Player bot;bot.ownsPowder=powder;GameObject& target=powder?bot.cannon:bot.chest;
            if(which==0)target.distance=3.01f;
            if(which==1)target.within=false; // Wrong phase/map or outside native interaction bounds.
            if(which==2)target.los=false;
            running(bot);assert(bot.motion.calls==1&&bot.motion.generated&&bot.moving);
            assert(bot.session.casts==0&&bot.session.itemUses==0);
            running(bot);assert(bot.motion.calls==1); // Do not restart a mesh walk each tick.
        }
        Player bot;bot.ownsPowder=powder;bot.moving=true;
        running(bot);assert(bot.stops==1&&bot.session.casts==0&&bot.session.itemUses==0);
        running(bot);assert(powder?bot.session.itemUses==1:bot.session.casts==1);
    }
}
void ProgressionTests()
{
    Player bot;bot.chest.distance=3.0f;
    running(bot);assert(bot.loot==bot.chest.guid&&!bot.ownsPowder&&bot.session.itemUses==0);
    // Opening never creates inventory. The unchanged normal loot handler owns
    // selection, full-bag failure, retry, release and the chest's native event.
    running(bot);assert(bot.session.casts==1);
    bot.session.bagSpace=false;bot.session.StoreNormalLoot();
    assert(!bot.ownsPowder&&!bot.loot&&bot.chest.spawned);
    running(bot);assert(bot.session.casts==2&&bot.loot==bot.chest.guid);
    bot.session.bagSpace=true;bot.session.lookOnly=true;bot.session.StoreNormalLoot();
    assert(!bot.ownsPowder);running(bot);bot.session.lookOnly=false;bot.session.lootEligible=false;
    bot.session.StoreNormalLoot();assert(!bot.ownsPowder);running(bot);bot.session.lootEligible=true;
    bot.session.StoreNormalLoot();assert(bot.ownsPowder&&bot.item.itemClass==13&&bot.item.charges==-1);
    assert(!bot.chest.spawned&&bot.session.lootReleased==4&&bot.session.itemUses==0);
    bot.session.itemAllowed=false;running(bot);
    assert(bot.ownsPowder&&bot.session.itemUses==1&&bot.session.acceptedUses==0);
    bot.session.itemAllowed=true;running(bot);
    assert(!bot.ownsPowder&&bot.session.acceptedUses==1&&bot.item.charges==0&&bot.door.state==1);
    // Consumption and success of an interaction do not complete the objective.
    for(uint32 tick=0;tick<4;++tick)running(bot);
    assert(bot.session.itemUses==2&&bot.session.acceptedUses==1);
    bot.door.state=0;running(bot); // GO_STATE_ACTIVE is not the cannon's broken-door state.
    bot.door.state=2;assert(Run(&bot)==StepResult::Done);
    bot.combat=true;bot.ownsPowder=true;assert(Run(&bot)==StepResult::Done);
    assert(bot.session.itemUses==2); // Re-entry with extra powder still cannot refire.
}
void OpeningTests()
{
    Player bot;bot.chest.knownOpening=false;assert(Run(&bot)==StepResult::Blocked);assert(!bot.session.casts);
    bot.chest.knownOpening=true;bot.session.openingAllowed=false;running(bot);
    assert(bot.session.casts==1&&!bot.loot&&!bot.ownsPowder);
    bot.session.openingAllowed=true;running(bot);assert(bot.session.casts==2&&bot.loot==bot.chest.guid);
    for(bool powder:{false,true})
    {
        Player shifted;shifted.ownsPowder=powder;shifted.form=1;running(shifted);
        assert(shifted.form==0&&shifted.removedForms==1);
        assert(powder?shifted.session.acceptedUses==1:shifted.loot==shifted.chest.guid);
    }
}
void AuthoredEventTests()
{
    std::vector<DungeonEvent> events;RegisterDeadminesEvents(events);assert(events.size()==1);
    auto const& event=events.front();assert(event.mapId==36&&event.id==1&&event.required);
    assert(event.persistent&&event.stepsOwnMovement&&event.activation==EventActivation::Anchored);
    assert(event.completeGoEntry==16397&&event.completeGoState==2&&event.completeGoRadius==100);
    assert(event.steps.size()==3&&event.steps[0].kind==EventStepKind::MoveTo);
    auto const& step=event.steps[1];assert(DcEarnedEvents::IsDefiasCannonStep(step)&&step.timeoutMs==120000);
    assert(event.steps[2].kind==EventStepKind::WaitForGameObjectState&&event.steps[2].goEntry==16397&&event.steps[2].wantState==2);
    Player bot;assert(RunAuthoredStep(&bot,step)==StepResult::Running&&bot.loot==bot.chest.guid);
    for(uint32 which=0;which<5;++which)
    {
        EventStep refused=step;
        switch(which){case 0:refused.kind=EventStepKind::Custom;break;case 1:++refused.goEntry;break;
            case 2:++refused.itemId;break;case 3:++refused.spellId;break;case 4:++refused.hookId;break;}
        assert(!DcEarnedEvents::IsDefiasCannonStep(refused));
        assert(RunAuthoredStep(&bot,refused)==StepResult::Failed);
    }
}
int main()
{
    assert(Run(nullptr)==StepResult::Failed);
    Player invalid;invalid.mapId=1;assert(Run(&invalid)==StepResult::Failed);
    invalid.mapId=36;invalid.ai=false;assert(Run(&invalid)==StepResult::Failed);
    Player stale;stale.door.state=2;stale.door.spawned=false;running(stale);
    stale.door.spawned=true;stale.objects.erase(16397);running(stale);
    BusyTests();AccessTests();ProgressionTests();OpeningTests();AuthoredEventTests();
    std::cout<<"Defias cannon: owned native KEY loot, full-bag retry, native item consumption, real mesh/range/access gates and delayed door completion verified\n";
}
'''


def main():
    parser = argparse.ArgumentParser()
    source_argument(parser)
    args = parser.parse_args()
    core = prepared_core()
    source = args.source or core / 'modules/mod-dungeon-clear/src'
    if not (source / 'DcDefiasCannon.cpp').exists():
        raise SystemExit('PrepareModules.cmake must prepare the Defias Cannon driver first')
    item = native_contracts(core, source)
    compiler = cxx()
    with tempfile.TemporaryDirectory(prefix='defias-cannon-') as temp:
        work = Path(temp)
        stubs = STUBS.replace('NATIVE_KEY_CLASS', item['class']).replace('NATIVE_CHARGES', item['spellcharges_1'])
        (work / 'NativeStubs.h').write_text(stubs)
        for name in ('Define.h', 'DcEarnedEvents.h', 'DcEarnedPlay.h', 'GameObject.h', 'MotionMaster.h',
                     'Player.h', 'Playerbots.h', 'Spell.h', 'UseItemAction.h', 'WorldPacket.h', 'WorldSession.h',
                     'Common.h', 'SharedDefines.h', 'Ai/Dungeon/DungeonClear/Data/DcDifficultyGate.h',
                     'Ai/Dungeon/DungeonClear/Util/DcFormGate.h',
                     'Ai/Dungeon/DungeonClear/Util/DungeonEventExecutor.h'):
            path = work / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('#include "NativeStubs.h"\n')
        for name in ('DcDefiasCannon.cpp', 'DcDefiasCannon.h'):
            shutil.copyfile(source / name, work / name)
        registry = source / 'Ai/Dungeon/DungeonClear/Data/DungeonEventRegistry.h'
        shutil.copyfile(registry, work / 'DungeonEventRegistry.h')
        builder = registry.with_suffix('.cpp').read_text()
        authored = ['#include "DungeonEventRegistry.h"', '#include <utility>']
        for signature in ('EventBuilder::EventBuilder(', 'EventStep& EventBuilder::Add(',
                          'EventBuilder& EventBuilder::Anchored(', 'EventBuilder& EventBuilder::Persistent(',
                          'EventBuilder& EventBuilder::StepsOwnMovement(', 'EventBuilder& EventBuilder::CompleteWhenGOState(',
                          'EventBuilder& EventBuilder::MoveTo(', 'EventBuilder& EventBuilder::UseItemOnGO(',
                          'EventBuilder& EventBuilder::Timeout(', 'EventBuilder& EventBuilder::WaitForGOState('):
            authored.append(function(builder, signature))
        events = source / 'Ai/Dungeon/DungeonClear/Data/Events/DeadminesEvents.cpp'
        authored.append(function(events.read_text(), 'void RegisterDeadminesEvents('))
        earned = function((source / 'DcEarnedEvents.cpp').read_text(), 'bool IsDefiasCannonStep(')
        authored.append('namespace DcEarnedEvents {\n' + earned + '\n}')
        executor = (source / 'Ai/Dungeon/DungeonClear/Util/DungeonEventExecutor.cpp').read_text()
        dispatcher = executor.split('case EventStepKind::UseItemOnGO:', 1)[1]
        dispatcher = dispatcher[dispatcher.index('if (DcEarnedEvents::IsDefiasCannonStep(step))'):]
        dispatcher = dispatcher[:dispatcher.index('return DcDefiasCannon::Run(bot);') + len('return DcDefiasCannon::Run(bot);')]
        authored.append('StepResult RunAuthoredStep(Player* bot,EventStep const& step) {\n' + dispatcher +
                        '\nreturn StepResult::Failed;\n}')
        (work / 'AuthoredCannon.cpp').write_text('\n'.join(authored))
        (work / 'fixture.cpp').write_text(HARNESS)
        exe = work / ('fixture.exe' if os.name == 'nt' else 'fixture')
        flags = ['-std=c++20', '-O1', '-Wall', '-Wextra', '-Wno-missing-field-initializers', '-I', str(work)]
        if os.name != 'nt':
            flags += [*SANITIZER_FLAGS, '-no-pie']
        subprocess.run([compiler, *flags, str(work / 'fixture.cpp'), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=TIMEOUT)
        mutations = [
            ('wrong map accepted', 'bot->GetMapId() != 36', 'false'),
            ('missing bot AI accepted', '!GET_PLAYERBOT_AI(bot)', 'false'),
            ('dead bot interacts', '!bot->IsAlive()', 'false'),
            ('combat interaction', 'bot->IsInCombat()', 'false'),
            ('flight interaction', 'bot->IsInFlight()', 'false'),
            ('remote mover interaction', 'bot->m_mover != bot', 'false'),
            ('casting interrupted by item use', 'bot->IsNonMeleeSpellCast(false)', 'false'),
            ('open loot interrupted', 'bot->GetLootGUID()', 'false'),
            ('unspawned target accepted', '!target->isSpawned()', 'false'),
            ('server disallow ignored', 'sPlayerbotAIConfig.DisallowedGameObjects.contains(target->GetEntry())', 'false'),
            ('native access ignored', '!DcEarnedEvents::CanOpen(bot, target)', 'false'),
            ('three yard range removed', 'bot->GetExactDist(target) > 3.0f', 'false'),
            ('native interaction bounds removed', '!target->IsWithinDistInMap(bot)', 'false'),
            ('line of sight removed', '!DungeonEventExecutor::HasGameObjectLos(bot, target)', 'false'),
            ('crowd controlled bot moves', 'GET_PLAYERBOT_AI(bot)->CanMove()', 'true'),
            ('mesh proof removed', 'DcEarnedPlay::ReachableLeg(bot, target->GetPositionX(), target->GetPositionY(), target->GetPositionZ())', 'true'),
            ('path generation removed', '/*generatePath*/ true, false', '/*generatePath*/ false, false'),
            ('moving interaction', 'if (bot->isMoving())', 'if (false)'),
            ('item form gate removed', 'DcFormGate::DropBlockingForm(bot, powder);', ''),
            ('opening form gate removed', 'bot->RemoveAurasByType(SPELL_AURA_MOD_SHAPESHIFT);', '(void)0;'),
            ('native item use skipped', 'UseItemAction(GET_PLAYERBOT_AI(bot)).UseItemOnGameObject(powder, target->GetGUID());', '(void)powder;'),
            ('item use attempted without owned powder', 'if (powder)', 'if (true)'),
            ('ordinary opening opcode skipped', 'bot->GetSession()->HandleCastSpellOpcode(packet);', '(void)packet;'),
            ('item use completes before native door', 'return StepResult::Running;\n    }', 'return StepResult::Done;\n    }'),
            ('wrong door state completes', 'door->GetGoState() == GO_STATE_ACTIVE_ALTERNATIVE', 'door->GetGoState() != GO_STATE_ACTIVE_ALTERNATIVE'),
            ('unspawned door completes', 'door->isSpawned() && ', ''),
            ('open door refired', 'door && door->isSpawned() && door->GetGoState() == GO_STATE_ACTIVE_ALTERNATIVE', 'false'),
            ('owned powder ignored', 'bot->GetItemByEntry(5397)', 'nullptr'),
        ]
        authored_mutations = [
            ('event loses movement ownership', '.StepsOwnMovement()', ''),
            ('event loses persistence', '.Persistent()', ''),
            ('event loses native completion gate', '.CompleteWhenGOState(DM_GO_IRON_CLAD_DOOR, DM_DOOR_OPEN_STATE, 100.0f)', ''),
            ('acquisition timeout falls back to short default', '.Timeout(120000)', ''),
            ('dispatcher skips the earned cannon', 'return DcDefiasCannon::Run(bot);', 'return StepResult::Done;'),
            ('wrong event kind dispatched', 'step.kind == EventStepKind::UseItemOnGO &&', ''),
            ('unrelated item interaction dispatched', 'step.goEntry == 16398 &&', ''),
            ('wrong powder dispatched', 'step.itemId == 5397 &&', ''),
            ('wrong spell dispatched', 'step.spellId == 6250 &&', ''),
            ('scripted hook dispatched', 'step.hookId == 0', 'true'),
        ]
        reject_mutants(work, [(label, 'DcDefiasCannon.cpp', old, new) for label, old, new in mutations] +
                       [(label, 'AuthoredCannon.cpp', old, new) for label, old, new in authored_mutations],
                       lambda directory, executable: [compiler, '-std=c++20', '-O1', '-I', str(directory),
                                                      str(directory / 'fixture.cpp'), '-o', str(executable)],
                       'Defias cannon')


if __name__ == '__main__':
    main()
