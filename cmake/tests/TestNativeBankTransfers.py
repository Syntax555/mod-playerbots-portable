"""Exercise native bank handlers, quest accounting and the Bridge packet path.

The production quest checks and StoreItem destination loop run unchanged. Small
inventory producers preserve native stack merging and deletion of the source;
bank access and packet readers use the production session functions.
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
    in_parallel,
    prepared_core,
    run_fixture,
)


root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--core', type=Path, default=prepared_core(root))
parser.add_argument('--bridge', type=Path, help='MultiBot Bridge src directory')
args = parser.parse_args()
core = args.core
bridge_dir = args.bridge or core / 'modules/mod-multibot-bridge/src'
bank = (core / 'src/server/game/Handlers/BankHandler.cpp').read_text()
packets = (core / 'src/server/game/Server/Packets/BankPackets.cpp').read_text()
packet_header = (core / 'src/server/game/Server/Packets/BankPackets.h').read_text()
storage = (core / 'src/server/game/Entities/Player/PlayerStorage.cpp').read_text()
quests = (core / 'src/server/game/Entities/Player/PlayerQuest.cpp').read_text()
quest_header = (core / 'src/server/game/Quests/QuestDef.h').read_text()
player_header = (core / 'src/server/game/Entities/Player/Player.h').read_text()
item_header = (core / 'src/server/game/Entities/Item/Item.h').read_text()
bridge = (bridge_dir / 'MultiBotBridge.cpp').read_text()

# The storage double follows the real producer: split destinations can clone,
# merging returns a different stack and may delete the original source item.
store_native = function(storage, 'Item* Player::_StoreItem(')
assert 'pItem = pItem->CloneItem(count, this);' in store_native
assert 'pItem2->SetCount(pItem2->GetCount() + count);' in store_native
assert 'pItem->SetState(ITEM_REMOVED, this);' in store_native
item_source = (core / 'src/server/game/Entities/Item/Item.cpp').read_text()
assert 'delete this;' in function(item_source, 'void Item::SetState(')
assert 'return pItem2;' in store_native
native_count = function(storage, 'uint32 Player::GetItemCount(uint32 item, bool inBankAlso, Item* skipItem) const')
assert 'if (inBankAlso)' in native_count and 'BANK_SLOT_ITEM_START' in native_count
assert '#define INVENTORY_SLOT_BAG_0    255' in player_header
assert '#define MAX_QUEST_LOG_SIZE 25' in quest_header
assert 'return StoreItem(dest, pItem, update);' in function(player_header, 'Item* BankItem(')
can_bank = function(storage, 'InventoryResult Player::CanBankItem(')
specific_slot = function(can_bank, 'if (bag != NULL_BAG && slot != NULL_SLOT)')
assert can_bank.count('CanUseItem(') == specific_slot.count('CanUseItem(') == 1
assert 'sScriptMgr' not in can_bank
store_overload = function(player_header, 'InventoryResult CanStoreItem(uint8 bag, uint8 slot, ItemPosCountVec& dest, Item* pItem,')
assert 'return CanStoreItem(bag, slot, dest, pItem->GetEntry(), count, pItem, swap, nullptr);' in store_overload
assert 'sScriptMgr' not in function(storage, 'InventoryResult Player::CanStoreItem(uint8 bag, uint8 slot, ItemPosCountVec& dest, uint32 entry,')

parts = {
    'enums': '\n'.join(function(text, signature) + ';' for text, signature in (
        (quest_header, 'enum QuestStatus : uint8'), (quest_header, 'enum QuestSpecialFlags'),
        (quest_header, 'struct QuestStatusData'), (item_header, 'enum InventorySlot'),
        (player_header, 'enum InventorySlots'), (player_header, 'enum InventoryPackSlots'),
        (player_header, 'enum BankItemSlots'), (player_header, 'enum BankBagSlots'),
        (player_header, 'enum KeyRingSlots'), (player_header, 'enum CurrencyTokenSlots'),
        (player_header, 'struct ItemPosCount'))),
    'packet_classes': '\n'.join(function(packet_header, 'class ' + name) + ';' for name in (
        'AutoBankItem final', 'AutoStoreBankItem final', 'ShowBank final')),
    'packet_read': '\n'.join(function(packets, 'void WorldPackets::Bank::' + name + '::Read()') for name in (
        'AutoBankItem', 'AutoStoreBankItem')),
    'packet_write': function(packets, 'WorldPacket const* WorldPackets::Bank::ShowBank::Write()'),
    'access': '\n'.join(function(bank, signature) for signature in (
        'bool WorldSession::CanUseBank(', 'void WorldSession::HandleBankerActivateOpcode(',
        'void WorldSession::SendShowBank(')),
    'deposit': function(bank, 'void WorldSession::HandleAutoBankItemOpcode('),
    'transfer': function(bank, 'void WorldSession::HandleAutoStoreBankItemOpcode('),
    'position': '\n'.join(function(storage, signature) for signature in (
        'bool Player::IsInventoryPos(uint8', 'bool Player::IsBankPos(uint8')),
    'store': function(storage, 'Item* Player::StoreItem('),
    'quest': '\n'.join(function(quests, signature) for signature in (
        'void Player::ItemAddedQuestCheck(', 'void Player::ItemRemovedQuestCheck(')),
    'bridge': function(bridge, 'uint32 MoveNaturalBankItem('),
}
constants = '\n'.join(re.findall(r'^#define (?:QUEST_ITEM_OBJECTIVES_COUNT|QUEST_OBJECTIVES_COUNT) \d+',
                                quest_header, re.MULTILINE))
assert len(constants.splitlines()) == 2
opcodes = (core / 'src/server/game/Server/Protocol/Opcodes.h').read_text()
constants += '\n' + '\n'.join('constexpr uint32 ' + name + '=' + re.search(
    r'\b' + name + r'\s*=\s*(0x[0-9a-fA-F]+)', opcodes).group(1) + ';' for name in (
        'CMSG_BANKER_ACTIVATE', 'CMSG_AUTOSTORE_BANK_ITEM', 'CMSG_AUTOBANK_ITEM', 'SMSG_SHOW_BANK'))
unit_defines = (core / 'src/server/game/Entities/Unit/UnitDefines.h').read_text()
constants += '\nconstexpr uint32 UNIT_NPC_FLAG_BANKER=' + re.search(
    r'UNIT_NPC_FLAG_BANKER\s*=\s*(0x[0-9a-fA-F]+)', unit_defines).group(1) + ';'

fixture = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <functional>
#include <iostream>
#include <map>
#include <memory>
#include <string>
#include <utility>
#include <vector>
using uint8=std::uint8_t; using uint16=std::uint16_t; using uint32=std::uint32_t; using uint64=std::uint64_t;
#define LOG_DEBUG(...) do {} while(false)
@@CONSTANTS@@
constexpr uint8 INVENTORY_SLOT_BAG_0=255;
constexpr uint32 MAX_QUEST_LOG_SIZE=25;
constexpr uint32 UNIT_STATE_DIED=1, SPELL_AURA_FEIGN_DEATH=1;
constexpr uint32 ADDITIONAL_SAVING_INVENTORY_AND_GOLD=1, ADDITIONAL_SAVING_QUEST_STATUS=2;
@@ENUMS@@
using ItemPosCountVec=std::vector<ItemPosCount>;
enum InventoryResult { EQUIP_ERR_OK, EQUIP_ERR_NONE, EQUIP_ERR_BANK_FULL, EQUIP_ERR_INVENTORY_FULL, EQUIP_ERR_BAG_FULL, EQUIP_ERR_INVALID };
struct ObjectGuid {
    uint64 value=0;
    explicit operator bool() const { return value!=0; }
    bool operator==(ObjectGuid const&) const=default;
};
struct WorldPacket {
    uint32 opcode; std::vector<uint64> values; std::size_t at=0;
    WorldPacket(uint32 code, uint32):opcode(code) {}
    WorldPacket& operator<<(uint8 value) { values.push_back(value); return *this; }
    WorldPacket& operator<<(ObjectGuid value) { values.push_back(value.value); return *this; }
    WorldPacket& operator>>(uint8& value) { value=values.at(at++); return *this; }
    WorldPacket& operator>>(ObjectGuid& value) { value.value=values.at(at++); return *this; }
};
struct ClientPacket {
    WorldPacket _worldPacket;
    ClientPacket(uint32 code,WorldPacket&& packet):_worldPacket(std::move(packet)) { assert(code==_worldPacket.opcode); }
    virtual ~ClientPacket()=default; virtual void Read()=0;
};
struct ServerPacket {
    WorldPacket _worldPacket;
    ServerPacket(uint32 code,uint32 size):_worldPacket(code,size) {}
    virtual ~ServerPacket()=default; virtual WorldPacket const* Write()=0;
};
namespace WorldPackets::Bank { @@PACKET_CLASSES@@ }
@@PACKET_READ@@
@@PACKET_WRITE@@
struct Creature { ObjectGuid guid{9}; ObjectGuid GetGUID() const { return guid; } };
struct Item {
    ObjectGuid guid; uint32 entry=100,count=1; uint8 bag=INVENTORY_SLOT_BAG_0,slot=INVENTORY_SLOT_ITEM_START;
    ObjectGuid GetGUID() const { return guid; }
    uint32 GetEntry() const { return entry; }
    uint32 GetCount() const { return count; }
    uint8 GetBagSlot() const { return bag; }
    uint8 GetSlot() const { return slot; }
    uint16 GetPos() const { return (uint16(bag)<<8)|slot; }
};
struct Quest {
    uint32 RequiredItemId[QUEST_ITEM_OBJECTIVES_COUNT]{100};
    uint32 RequiredItemCount[QUEST_ITEM_OBJECTIVES_COUNT]{10};
    bool deliver=true;
    bool HasSpecialFlag(QuestSpecialFlags flag) const { assert(flag==QUEST_SPECIAL_FLAGS_DELIVER); return deliver; }
};
struct ObjectMgr {
    Quest quest;
    Quest const* GetQuestTemplate(uint32 id) const { return id==1?&quest:nullptr; }
} objectMgr;
auto* sObjectMgr=&objectMgr;
class WorldSession;
struct Player {
    ObjectGuid guid{1}; Creature banker; bool reachable=true,dead=false,failStore=false;
    WorldSession* session=nullptr;
    uint64 nextGuid=20;
    std::map<uint64,std::unique_ptr<Item>> owned;
    std::map<uint16,Item*> slots;
    std::map<uint32,QuestStatusData> m_QuestStatus;
    std::map<uint32,bool> m_QuestStatusSave;
    ItemPosCountVec destinations;
    InventoryResult eligibility=EQUIP_ERR_OK;
    uint32 checks=0,denyCheck=0,removed=0,errors=0,titanUpdates=0,questUpdates=0;
    uint32 GetQuestSlotQuestId(uint8 slot) const { return slot==0?1:0; }
    uint32 GetItemCount(uint32 entry,bool bank) const {
        uint32 count=0; for(auto const& [pos,item]:slots)
            if(item->entry==entry && (bank || !IsBankPos(pos>>8,pos&255))) count+=item->count;
        return count;
    }
    bool CanCompleteQuest(uint32) const { return m_QuestStatus.at(1).ItemCount[0]>=objectMgr.quest.RequiredItemCount[0]; }
    void CompleteQuest(uint32 id) { m_QuestStatus[id].Status=QUEST_STATUS_COMPLETE; }
    void IncompleteQuest(uint32 id) { m_QuestStatus[id].Status=QUEST_STATUS_INCOMPLETE; }
    void AdditionalSavingAddMask(uint32) {}
    void UpdateForQuestWorldObjects() { ++questUpdates; }
    void ItemAddedQuestCheck(uint32,uint32);
    void ItemRemovedQuestCheck(uint32,uint32);
    static bool IsInventoryPos(uint8,uint8);
    static bool IsBankPos(uint8,uint8);
    ObjectGuid GetGUID() const { return guid; }
    WorldSession* GetSession() const { return session; }
    Creature* GetNPCIfCanInteractWith(ObjectGuid id,uint32 flag) {
        assert(flag==UNIT_NPC_FLAG_BANKER); return reachable && id==banker.guid ? &banker:nullptr;
    }
    bool HasUnitState(uint32 state) const { assert(state==UNIT_STATE_DIED); return dead; }
    void RemoveAurasByType(uint32 type) { assert(type==SPELL_AURA_FEIGN_DEATH); dead=false; }
    Item* GetItemByPos(uint8 bag,uint8 slot) const { auto it=slots.find((uint16(bag)<<8)|slot); return it==slots.end()?nullptr:it->second; }
    Item* Add(uint32 count,uint8 slot,uint32 entry=100,uint8 bag=INVENTORY_SLOT_BAG_0) {
        auto item=std::make_unique<Item>(); item->guid={nextGuid++}; item->count=count; item->entry=entry; item->slot=slot; item->bag=bag;
        auto* ptr=item.get(); owned[ptr->guid.value]=std::move(item); slots[ptr->GetPos()]=ptr; return ptr;
    }
    InventoryResult CanBankItem(uint8 bag,uint8 slot,ItemPosCountVec& dest,Item*,bool swap) {
        assert(bag==NULL_BAG && slot==NULL_SLOT && !swap); dest=destinations; return Check();
    }
    InventoryResult CanStoreItem(uint8 bag,uint8 slot,ItemPosCountVec& dest,Item*,bool swap) {
        assert(bag==NULL_BAG && slot==NULL_SLOT && !swap); dest=destinations; return Check();
    }
    InventoryResult Check() { ++checks; return denyCheck==checks?EQUIP_ERR_INVALID:eligibility; }
    void SendEquipError(InventoryResult,Item*,Item*) { ++errors; }
    void RemoveItem(uint8 bag,uint8 slot,bool update) { assert(update); slots.erase((uint16(bag)<<8)|slot); ++removed; }
    Item* StoreItem(ItemPosCountVec const&,Item*,bool);
    Item* BankItem(ItemPosCountVec const& dest,Item* item,bool update) { return StoreItem(dest,item,update); }
    Item* _StoreItem(uint16 pos,Item* item,uint32 count,bool clone,bool update) {
        assert(update); if(failStore) return nullptr;
        auto found=slots.find(pos);
        if(found!=slots.end()) {
            auto* merged=found->second; assert(merged!=item && merged->entry==item->entry);
            merged->count+=count; if(!clone) owned.erase(item->guid.value); return merged;
        }
        if(clone) return Add(count,pos&255,item->entry,pos>>8);
        item->bag=pos>>8; item->slot=pos&255; item->count=count; slots[pos]=item; return item;
    }
    void UpdateTitansGrip() { ++titanUpdates; }
};
class WorldSession {
public:
    Player* _player; ObjectGuid m_currentBankerGUID{9}; std::function<void()> activation;
    explicit WorldSession(Player& player):_player(&player) { player.session=this; }
    Player* GetPlayer() const { return _player; }
    bool CanUseBank(ObjectGuid bankerGUID={}) const;
    void HandleBankerActivateOpcode(WorldPacket&);
    void HandleAutoBankItemOpcode(WorldPackets::Bank::AutoBankItem&);
    void HandleAutoStoreBankItemOpcode(WorldPackets::Bank::AutoStoreBankItem&);
    void SendShowBank(ObjectGuid);
    void SendPacket(WorldPacket const*) { if(activation) activation(); }
};
@@POSITION@@
@@STORE@@
@@QUEST@@
@@ACCESS@@
@@DEPOSIT@@
@@TRANSFER@@
@@BRIDGE@@
struct Scenario {
    Player player; WorldSession session{player};
    Scenario() { objectMgr.quest=Quest{}; player.m_QuestStatus[1].Status=QUEST_STATUS_INCOMPLETE; }
    uint16 Count() const { return player.m_QuestStatus.at(1).ItemCount[0]; }
    void QuestCount(uint16 count,bool complete=false) { player.m_QuestStatus[1].ItemCount[0]=count; player.m_QuestStatus[1].Status=complete?QUEST_STATUS_COMPLETE:QUEST_STATUS_INCOMPLETE; }
    void Plan(uint8 slot,uint32 count) { player.destinations={{uint16((uint16(INVENTORY_SLOT_BAG_0)<<8)|slot),count}}; }
    void Call(Item* item,bool autoBank=false) {
        WorldPacket packet(autoBank?CMSG_AUTOBANK_ITEM:CMSG_AUTOSTORE_BANK_ITEM,2); packet<<item->bag<<item->slot;
        if(autoBank) { WorldPackets::Bank::AutoBankItem request(std::move(packet)); request.Read(); session.HandleAutoBankItemOpcode(request); }
        else { WorldPackets::Bank::AutoStoreBankItem request(std::move(packet)); request.Read(); session.HandleAutoStoreBankItemOpcode(request); }
    }
    uint32 Bridge(Item* item,bool deposit,std::string& reason) { return MoveNaturalBankItem(&player,&player.banker,item,deposit,reason); }
};
void NativeTransfers() {
    for(bool autoBank:{false,true}) for(uint32 total:{8u,10u,14u}) {
        Scenario s; auto* source=s.player.Add(4,INVENTORY_SLOT_ITEM_START);
        s.player.Add(total-4,INVENTORY_SLOT_ITEM_START+1); s.QuestCount(std::min(total,10u),total>=10);
        s.Plan(BANK_SLOT_ITEM_START,4); s.Call(source,autoBank);
        assert(s.player.GetItemCount(100,false)==total-4 && s.player.GetItemCount(100,true)==total);
        assert(s.Count()==std::min(total-4,10u) && s.player.titanUpdates==1);
        assert(s.player.m_QuestStatus[1].Status==(total-4>=10?QUEST_STATUS_COMPLETE:QUEST_STATUS_INCOMPLETE));
    }
    for(bool split:{false,true}) for(uint32 required:{10u,20u}) {
        Scenario s; objectMgr.quest.RequiredItemCount[0]=required;
        s.player.Add(3,INVENTORY_SLOT_ITEM_START); s.QuestCount(3);
        auto* source=s.player.Add(6,BANK_SLOT_ITEM_START);
        auto first=uint16((uint16(INVENTORY_SLOT_BAG_0)<<8)|INVENTORY_SLOT_ITEM_START);
        s.player.destinations=split?ItemPosCountVec{{uint16(first+1),2},{first,4}}:ItemPosCountVec{{first,6}};
        s.Call(source); assert(s.player.GetItemCount(100,false)==9 && s.player.GetItemCount(100,true)==9);
        assert(s.Count()==9 && s.player.m_QuestStatus[1].Status==QUEST_STATUS_INCOMPLETE);
        assert(s.player.owned.size()==(split?2u:1u));
    }
    {
        Scenario s; s.player.Add(4,INVENTORY_SLOT_ITEM_START); s.QuestCount(4);
        auto* source=s.player.Add(6,BANK_SLOT_ITEM_START); s.Plan(INVENTORY_SLOT_ITEM_START,6); s.Call(source);
        assert(s.Count()==10 && s.player.m_QuestStatus[1].Status==QUEST_STATUS_COMPLETE);
    }
    for(bool autoBank:{false,true}) for(int refusal=0;refusal<3;++refusal) {
        Scenario s; auto* source=s.player.Add(4,INVENTORY_SLOT_ITEM_START); s.QuestCount(4);
        s.Plan(BANK_SLOT_ITEM_START,4);
        if(refusal==0) s.player.reachable=false;
        if(refusal==1) s.player.eligibility=EQUIP_ERR_BANK_FULL;
        if(refusal==2) s.player.slots.clear();
        s.Call(source,autoBank); assert(s.Count()==4 && !s.player.removed && !s.player.titanUpdates);
    }
    {
        Scenario s; auto* source=s.player.Add(4,BANK_SLOT_ITEM_START); s.Plan(BANK_SLOT_ITEM_START,4);
        s.QuestCount(4); s.Call(source,true); assert(s.Count()==4 && !s.player.removed && s.player.errors==1);
    }
    {
        Scenario s; auto* source=s.player.Add(4,BANK_SLOT_ITEM_START); s.Plan(INVENTORY_SLOT_ITEM_START,4);
        s.player.failStore=true; s.Call(source); assert(s.Count()==0 && !s.player.questUpdates);
    }
}
void BridgeTransfers() {
    for(bool deposit:{false,true}) {
        Scenario s; auto* source=s.player.Add(4,deposit?uint8(INVENTORY_SLOT_ITEM_START):uint8(BANK_SLOT_ITEM_START));
        s.QuestCount(deposit?4:0); s.Plan(deposit?uint8(BANK_SLOT_ITEM_START):uint8(INVENTORY_SLOT_ITEM_START),4);
        std::string reason; assert(s.Bridge(source,deposit,reason)==4 && reason.empty());
        assert(s.Count()==(deposit?0:4) && s.player.checks==2);
    }
    for(int refusal=0;refusal<8;++refusal) {
        Scenario s; auto* source=s.player.Add(4,INVENTORY_SLOT_ITEM_START); s.QuestCount(4);
        s.Plan(BANK_SLOT_ITEM_START,4); auto guid=source->guid;
        if(refusal==0) s.player.reachable=false;
        if(refusal==1) s.session.activation=[&]{s.player.reachable=false;s.session.m_currentBankerGUID=s.player.guid;};
        if(refusal==2) s.player.eligibility=EQUIP_ERR_BANK_FULL;
        if(refusal==3) s.player.denyCheck=2;
        if(refusal==4) s.session.activation=[&]{source->guid.value++;};
        if(refusal==5) s.session.activation=[&]{source->count++;};
        if(refusal==6) { source->bag=INVENTORY_SLOT_BAG_0; source->slot=BANK_SLOT_ITEM_START; s.player.slots.clear(); s.player.slots[source->GetPos()]=source; }
        if(refusal==7) s.player.destinations={{source->GetPos(),4}};
        std::string reason; assert(s.Bridge(source,true,reason)==0 && !reason.empty());
        assert(!s.player.removed && s.Count()==4);
        if(refusal==6) assert(reason=="BAD_POSITION" && !s.player.checks);
        if(refusal!=4) assert(source->guid==guid);
    }
    {
        Scenario s; Player other; WorldSession otherSession(other); otherSession.m_currentBankerGUID={9};
        auto* source=s.player.Add(4,INVENTORY_SLOT_ITEM_START); s.QuestCount(4); s.Plan(BANK_SLOT_ITEM_START,4);
        other.Add(4,INVENTORY_SLOT_ITEM_START); other.destinations=s.player.destinations;
        s.session._player=&other;
        std::string reason; assert(s.Bridge(source,true,reason)==0 && !s.player.removed && !other.removed);
    }
    {
        Scenario s; auto* source=s.player.Add(4,BANK_SLOT_ITEM_START); s.Plan(INVENTORY_SLOT_ITEM_START,4);
        s.player.eligibility=EQUIP_ERR_INVENTORY_FULL;
        std::string reason; assert(!s.Bridge(source,false,reason) && reason=="BAGS_FULL" && !s.player.removed);
    }
    std::string reason;
    assert(!MoveNaturalBankItem(nullptr,nullptr,nullptr,true,reason));
}
int main() { NativeTransfers(); BridgeTransfers(); std::cout<<"Native bank transfers: quest counts, completed objectives, stack merging, packet routing and access guards passed\n"; }
'''

mutations = (
    ('auto-bank removal order', 'deposit',
     '_player->ItemRemovedQuestCheck(item->GetEntry(), item->GetCount());\n    _player->RemoveItem(packet.Bag, packet.Slot, true);',
     '_player->RemoveItem(packet.Bag, packet.Slot, true);\n    _player->ItemRemovedQuestCheck(item->GetEntry(), item->GetCount());'),
    ('auto-store removal order', 'transfer',
     '_player->ItemRemovedQuestCheck(item->GetEntry(), item->GetCount());\n        _player->RemoveItem(packet.Bag, packet.Slot, true);',
     '_player->RemoveItem(packet.Bag, packet.Slot, true);\n        _player->ItemRemovedQuestCheck(item->GetEntry(), item->GetCount());'),
    ('merged stack credited', 'transfer', 'storedItem->GetEntry(), count',
     'storedItem->GetEntry(), count + storedItem->GetCount() - count'),
    ('native bank access', 'transfer', 'if (!CanUseBank())', 'if (false)'),
    ('failed store credited', 'transfer',
     'if (Item const* storedItem = _player->StoreItem(dest, item, true))',
     'if (Item const* storedItem = _player->StoreItem(dest, item, true); true)'),
    ('bridge physical banker', 'bridge',
     'bot->GetNPCIfCanInteractWith(banker->GetGUID(), UNIT_NPC_FLAG_BANKER) != banker', 'false'),
    ('bridge session owner', 'bridge', 'bot->GetSession()->GetPlayer() != bot', 'false'),
    ('bridge stale source', 'bridge', 'item->GetGUID() != itemGuid', '(item->GetGUID() != itemGuid && false)'),
    ('bridge source position', 'bridge',
     'deposit ? !bot->IsInventoryPos(bag, slot) : !bot->IsBankPos(bag, slot)', 'false'),
)


def build(work, values, name):
    text = fixture.replace('@@CONSTANTS@@', constants)
    for key, value in values.items():
        text = text.replace('@@' + key.upper() + '@@', value)
    assert '@@' not in text
    source = work / (name + '.cpp')
    source.write_text(text)
    executable = work / name
    subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-g', '-O1',
                    *SANITIZER_FLAGS, '-no-pie', str(source), '-o', str(executable)], check=True)
    return run_fixture([str(executable)], name)


with tempfile.TemporaryDirectory(prefix='native-bank-transfers-') as temporary:
    work = Path(temporary)
    baseline = build(work, parts, 'bank')
    assert baseline.returncode == 0, baseline.stdout + baseline.stderr
    print(baseline.stdout, end='', flush=True)

    def rejected(numbered):
        index, (label, key, old, new) = numbered
        assert old in parts[key], label
        result = build(work, {**parts, key: parts[key].replace(old, new)}, 'mutant-' + str(index))
        assert result.returncode != 0, 'Bank mutation survived: ' + label
        return label

    for label in in_parallel(rejected, enumerate(mutations)):
        print('Bank mutation rejected:', label)
