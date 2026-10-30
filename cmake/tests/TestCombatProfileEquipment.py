"""Exercise owned-inventory profile equipment through the real equip actions.

The production equipment classifier, selection, per-item equip code and both
action entry points run with native-shaped item instances and session packets.
Only owned bag instances can be equipped; no inventory item is granted, bought
or selected from a bank.
"""

import argparse
from pathlib import Path
import subprocess
import tempfile

from FixtureSupport import SANITIZER_FLAGS, cxx, function, prepared_core, run_fixture


ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, default=prepared_core(ROOT) / 'modules/mod-playerbots/src')
args = parser.parse_args()
source = (args.source / 'Ai/Base/Actions/EquipAction.cpp').read_text()
header = (args.source / 'Ai/Base/Actions/EquipAction.h').read_text()
core = prepared_core(ROOT)
item_header = (core / 'src/server/game/Entities/Item/ItemTemplate.h').read_text()
item_instance = (core / 'src/server/game/Entities/Item/Item.h').read_text()
player_header = (core / 'src/server/game/Entities/Player/Player.h').read_text()
shared = (core / 'src/server/shared/SharedDefines.h').read_text()

# The doubles below follow the producers these actions call: fresh upgrade
# evaluation, bag-only item instances and a session equip packet identifying GUID.
value = (args.source / 'Bot/Engine/Value/Value.h').read_text()
usage = (args.source / 'Ai/Base/Value/ItemUsageValue.cpp').read_text()
visitor = (args.source / 'Mgr/Item/ItemVisitors.h').read_text()
handler = (core / 'src/server/game/Handlers/ItemHandler.cpp').read_text()
storage = (core / 'src/server/game/Entities/Player/PlayerStorage.cpp').read_text()
native_handler = function(handler, 'void WorldSession::HandleAutoEquipItemSlotOpcode(')
assert 'if (checkInterval < 2)' in value and 'value = Calculate();' in value
assert 'QueryItemUsageForEquip(proto, randomPropertyId)' in function(usage, 'ItemUsage ItemUpgradeValue::Calculate()')
# The native core keeps the off hand empty beside a two-hander unless Titan's Grip holds an
# axe, mace or sword; the doubles' CanEquipItem and session handler follow that rule.
can_equip = function(storage, 'InventoryResult Player::CanEquipItem(uint8 slot, uint16& dest, Item* pItem, bool swap, bool not_loading) const')
assert 'if (IsTwoHandUsed())\n                    return EQUIP_ERR_CANT_EQUIP_WITH_TWOHANDED;' in can_equip
assert 'mhWeaponProto->SubClass == ITEM_SUBCLASS_WEAPON_STAFF' in can_equip
ai_source = (args.source / 'Bot/PlayerbotAI.cpp').read_text()
inventory_items = function(ai_source, 'std::vector<Item*> PlayerbotAI::GetInventoryItems()')
assert 'pBag->GetItemByPos(j)' in inventory_items and 'i < INVENTORY_SLOT_ITEM_END' in inventory_items
assert 'GetInt32Value(ITEM_FIELD_RANDOM_PROPERTIES_ID)' in function(usage, 'ItemUsage ItemUsageValue::QueryItemUsageForEquip(')
assert 'std::vector<Item*> items;' in function(visitor, 'class CollectItemsVisitor')
assert '_player->GetItemByGuid(packet.ItemGuid)' in native_handler
assert '_player->SwapItem(item->GetPos(), dstpos);' in native_handler
assert 'return GetInt32Value(ITEM_FIELD_RANDOM_PROPERTIES_ID);' in function(item_instance, 'int32 GetItemRandomPropertyId()')
current_item = function(usage, 'Item* ItemUsageValue::CurrentItem(')
assert 'item->GetUInt32Value(ITEM_FIELD_DURABILITY) < bestItem->GetUInt32Value(ITEM_FIELD_DURABILITY)' in current_item
assert 'void EquipItem(Item* item, uint8 forcedSlot = NULL_SLOT);' in header
assert 'static uint8 GetSmallestBagSlot(Player* bot);' in header
assert 'return item->ToBag();' in function(storage, 'Bag* Player::GetBagByPos(uint8 bag) const')
bag_source = (core / 'src/server/game/Entities/Item/Container/Bag.cpp').read_text()
bag_header = (core / 'src/server/game/Entities/Item/Container/Bag.h').read_text()
assert 'SetUInt32Value(CONTAINER_FIELD_NUM_SLOTS, itemProto->ContainerSlots);' in function(bag_source, 'bool Bag::Create(')
assert 'return GetUInt32Value(CONTAINER_FIELD_NUM_SLOTS);' in function(bag_header, 'uint32 GetBagSize() const')
item_source = (core / 'src/server/game/Entities/Item/Item.cpp').read_text()
assert 'uint8(INVENTORY_SLOT_BAG_0)' in function(item_source, 'uint8 Item::GetBagSlot() const')
native_swap = function(storage, 'void Player::SwapItem(uint16 src, uint16 dst)')
assert 'if (IsBagPos(dst) && srcbag == dstslot)' in native_swap
assert 'CanUnequipItem(dst,' in native_swap and 'CanEquipItem(dstslot,' in native_swap
inventory = (args.source / 'Ai/Base/Actions/InventoryAction.cpp').read_text()
assert 'for (uint32 i = INVENTORY_SLOT_ITEM_START;' in function(inventory, 'void InventoryAction::IterateItemsInBags(')

enums = '\n'.join(function(text, 'enum ' + name) + ';' for text, name in (
    (item_header, 'InventoryType'), (item_header, 'ItemClass'), (item_header, 'ItemSubclassWeapon'),
    (item_header, 'ItemFlags : uint32'), (item_header, 'ItemSubclassContainer'), (item_header, 'ItemSubclassQuiver'),
    (player_header, 'EquipmentSlots'), (player_header, 'InventorySlots'),
    (player_header, 'InventoryPackSlots'), (shared, 'Classes')))
production = '\n\n'.join(function(source, signature) for signature in (
    'uint8 EquipAction::GetSmallestBagSlot(Player* bot)',
    'bool EquipAction::FillsBothHands(Player* bot, ItemTemplate const* proto)',
    'float EquipAction::BestOffhandScore(PlayerbotAI* botAI, StatsWeightCalculator& calculator, uint32 candidateId)',
    'void EquipAction::EquipItem(Item* item, uint8 forcedSlot)',
    'bool EquipAction::EquipUpgrades()',
    'bool EquipUpgradesPacketAction::Execute(Event event)',
    'bool EquipUpgradeAction::Execute(Event'))
production = function(usage, 'ItemUsage ItemUsageValue::QueryItemUsageForEquip(') + '\n\n' + production

FIXTURE = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <list>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <utility>
#include <vector>
using uint8=std::uint8_t; using uint16=std::uint16_t; using uint32=std::uint32_t;
using uint64=std::uint64_t; using int32=std::int32_t;
// ENUMS
constexpr uint8 INVENTORY_SLOT_BAG_0=255, NULL_SLOT=255;
constexpr uint32 CMSG_AUTOEQUIP_ITEM_SLOT=1, TRADE_STATUS_TRADE_ACCEPT=1;
constexpr uint32 ITEM_FIELD_RANDOM_PROPERTIES_ID=0;
constexpr uint32 ITEM_FIELD_DURABILITY=1, ITEM_FIELD_MAXDURABILITY=2;
constexpr uint32 ITERATE_ITEMS_IN_BAGS=1;
enum InventoryResult { EQUIP_ERR_OK, EQUIP_ERR_CANT_CARRY_MORE_OF_THIS, EQUIP_ERR_INVALID };
enum ItemUsage { ITEM_USAGE_NONE, ITEM_USAGE_EQUIP, ITEM_USAGE_REPLACE, ITEM_USAGE_BAD_EQUIP, ITEM_USAGE_BROKEN_EQUIP };
struct ObjectGuid { uint64 value=0; uint32 GetCounter() const { return value; } };
struct ItemTemplate {
    uint32 ItemId=0, InventoryType=INVTYPE_HEAD, Class=ITEM_CLASS_ARMOR, SubClass=0;
    uint32 allowedClass=0, level=1;
    std::map<int32,float> tank, dps;
    // Scores in the item's own slot, where a set tier or freed cap headroom changes it.
    std::map<int32,float> slotScores{};
    bool proper=true;
    uint32 ContainerSlots=0;
    bool HasFlag(ItemFlags) const { return false; }
};
std::map<uint32,ItemTemplate> templates;
struct Player;
struct Item {
    uint64 guid=0; uint32 entry=0; int32 property=0; uint8 bag=INVENTORY_SLOT_BAG_0,slot=0; bool broken=false;
    ItemTemplate const* GetTemplate() const { return &templates.at(entry); }
    uint32 GetEntry() const { return entry; }
    int32 GetItemRandomPropertyId() const { return property; }
    int32 GetInt32Value(uint32 field) const { assert(field==ITEM_FIELD_RANDOM_PROPERTIES_ID); return property; }
    uint32 GetUInt32Value(uint32 field) const { return field==ITEM_FIELD_MAXDURABILITY?100:(broken?0:100); }
    static Item* CreateItem(uint32 entry,uint32 count,Player*) {
        assert(count==1); auto* item=new Item; item->entry=entry; return item;
    }
    void RemoveFromUpdateQueueOf(Player*) {}
    ObjectGuid GetGUID() const { return {guid}; }
    uint8 GetBagSlot() const { return bag; }
    uint8 GetSlot() const { return slot; }
    bool IsEquipped() const { return bag==INVENTORY_SLOT_BAG_0 && slot<EQUIPMENT_SLOT_END; }
    bool IsBroken() const { return broken; }
};
struct Bag : Item { uint32 GetBagSize() const { return GetTemplate()->ContainerSlots; } };
struct WorldPacket {
    std::vector<uint64> values; std::size_t index=0;
    WorldPacket()=default;
    WorldPacket(uint32 opcode,uint32) { assert(opcode==CMSG_AUTOEQUIP_ITEM_SLOT); }
    void rpos(uint32 n) { index=n; }
    WorldPacket& operator<<(ObjectGuid guid) { values.push_back(guid.value); return *this; }
    WorldPacket& operator<<(uint8 value) { values.push_back(value); return *this; }
    WorldPacket& operator>>(ObjectGuid& guid) { guid.value=values.at(index++); return *this; }
    template<class T> WorldPacket& operator>>(T& value) { value=values.at(index++); return *this; }
};
namespace WorldPackets::Item {
struct AutoEquipItemSlot {
    WorldPacket packet; explicit AutoEquipItemSlot(WorldPacket&& p):packet(std::move(p)) {}
    void Read() { assert(packet.values.size()==2); }
};
}
struct Player;
struct Session {
    Player* owner=nullptr;
    void HandleAutoEquipItemSlotOpcode(WorldPackets::Item::AutoEquipItemSlot& packet);
};
struct Player {
    uint8 cls=CLASS_WARRIOR,level=60;
    bool tank=false,combat=false,dual=true,titan=false,random=false;
    std::list<Bag> owned;
    std::map<uint8,Item*> equipped;
    std::vector<uint64> equips;
    uint32 bagScans=0,swapCalls=0;
    bool rejectSwap=false;
    Session session{this};
    uint8 getClass() const { return cls; }
    uint8 GetLevel() const { return level; }
    bool IsInCombat() const { return combat; }
    bool CanDualWield() const { return dual; }
    bool CanTitanGrip() const { return titan; }
    ObjectGuid GetGUID() const { return {1}; }
    Session* GetSession() { return &session; }
    Item* GetItemByPos(uint8 bag,uint8 slot) {
        if (bag==INVENTORY_SLOT_BAG_0) {
            auto found=equipped.find(slot); if(found!=equipped.end()) return found->second;
        }
        for(auto& item:owned) if(item.bag==bag && item.slot==slot) return &item;
        return nullptr;
    }
    Item* GetItemByPos(uint16 pos) { return GetItemByPos(pos>>8,pos&255); }
    Bag* GetBagByPos(uint8 slot) {
        auto* item=GetItemByPos(INVENTORY_SLOT_BAG_0,slot);
        return item?static_cast<Bag*>(item):nullptr;
    }
    bool HasItemOrGemWithIdEquipped(uint32 id,uint32 count) const {
        assert(count==1);
        return std::any_of(equipped.begin(),equipped.end(),[&](auto const& pair){return pair.second->entry==id;});
    }
    InventoryResult CanUseItem(ItemTemplate const* p) const {
        return (p->allowedClass && p->allowedClass!=cls) || p->level>level ? EQUIP_ERR_INVALID:EQUIP_ERR_OK;
    }
    void SetAmmo(uint32) { assert(false && "ammo is not armor"); }
    void SwapItem(uint16 src,uint16 dst) {
        ++swapCalls;
        auto* item=GetItemByPos(src);
        assert(item && "bag changes must identify an owned item instance");
        uint8 dstBag=dst>>8,dstSlot=dst&255;
        assert(dstBag==INVENTORY_SLOT_BAG_0 && dstSlot>=INVENTORY_SLOT_BAG_START && dstSlot<INVENTORY_SLOT_BAG_END);
        if(rejectSwap || combat || CanUseItem(item->GetTemplate())!=EQUIP_ERR_OK || item->bag==dstSlot) return;
        auto bag=item->bag,slot=item->slot;
        if(auto* old=GetItemByPos(dst)) { old->bag=bag; old->slot=slot; }
        item->bag=dstBag; item->slot=dstSlot; equipped[dstSlot]=item; equips.push_back(item->guid);
    }
    Item* Add(uint32 entry,int32 property=0,bool equip=false,uint8 equipSlot=EQUIPMENT_SLOT_HEAD) {
        owned.push_back({{owned.size()+1,entry,property,INVENTORY_SLOT_BAG_0,
            uint8(owned.size()+INVENTORY_SLOT_ITEM_START),false}});
        auto* item=&owned.back();
        if(equip) { item->bag=INVENTORY_SLOT_BAG_0; item->slot=equipSlot; equipped[equipSlot]=item; }
        return item;
    }
};
struct StatsWeightCalculator {
    Player* player; bool pairs=false; explicit StatsWeightCalculator(Player* p):player(p) {}
    void SetPvpSpec(bool) {} void SetWeaponPairs(bool apply) { pairs=apply; }
    float CalculateItem(uint32 id,int32 property=0,int32 slot=-1) {
        auto const& proto=templates.at(id);
        auto const& weights=player->tank?proto.tank:proto.dps;
        auto it=weights.find(property); float score=it==weights.end()?weights.at(0):it->second;
        if(auto found=proto.slotScores.find(slot); found!=proto.slotScores.end()) score=found->second;
        // Production normalizes a two-hander to one hand unless both hands are compared.
        return proto.InventoryType==INVTYPE_2HWEAPON && !pairs ? score/2 : score;
    }
};
struct PlayerbotAI {
    Player* bot; static bool IsTank(Player* p) { return p->tank; }
    Player* GetBot() { return bot; }
    std::vector<Item*> GetInventoryItems() {
        std::vector<Item*> items;
        for(auto& item:bot->owned) if(!item.IsEquipped() && !(item.bag==INVENTORY_SLOT_BAG_0 && item.slot<INVENTORY_SLOT_BAG_END)) items.push_back(&item);
        return items;
    }
    uint8 FindEquipSlot(ItemTemplate const* p,uint8,bool) {
        switch(p->InventoryType) {
            case INVTYPE_WEAPON: case INVTYPE_WEAPONMAINHAND: case INVTYPE_2HWEAPON:return EQUIPMENT_SLOT_MAINHAND;
            case INVTYPE_SHIELD: case INVTYPE_WEAPONOFFHAND: case INVTYPE_HOLDABLE:return EQUIPMENT_SLOT_OFFHAND;
            case INVTYPE_FINGER:return EQUIPMENT_SLOT_FINGER1;
            case INVTYPE_BAG:case INVTYPE_QUIVER:return INVENTORY_SLOT_BAG_START;
            default:return EQUIPMENT_SLOT_HEAD;
        }
    }
    InventoryResult CanEquipItem(uint8 slot,uint16& dest,Item* item,bool swap,bool notLoading) {
        assert(swap && notLoading);
        auto* p=item->GetTemplate();
        if(bot->combat || bot->CanUseItem(p)!=EQUIP_ERR_OK) return EQUIP_ERR_INVALID;
        if(slot==NULL_SLOT) slot=FindEquipSlot(p,NULL_SLOT,true);
        dest=(uint16(INVENTORY_SLOT_BAG_0)<<8)|slot;
        auto* main=bot->GetItemByPos(INVENTORY_SLOT_BAG_0,EQUIPMENT_SLOT_MAINHAND);
        if(slot==EQUIPMENT_SLOT_OFFHAND && main && main->GetTemplate()->InventoryType==INVTYPE_2HWEAPON && !bot->titan)
            return EQUIP_ERR_INVALID;
        return EQUIP_ERR_OK;
    }
    void TellMaster(std::ostringstream const&) {}
    ItemUsage Upgrade(std::string const& qualifier);
};
void Session::HandleAutoEquipItemSlotOpcode(WorldPackets::Item::AutoEquipItemSlot& packet) {
    auto guid=packet.packet.values.at(0); uint8 slot=packet.packet.values.at(1);
    assert(slot<EQUIPMENT_SLOT_END);
    auto found=std::find_if(owner->owned.begin(),owner->owned.end(),[&](auto const& item){return item.guid==guid;});
    assert(found!=owner->owned.end() && "equip must identify an owned item instance");
    auto* item=&*found;
    PlayerbotAI ai{owner}; uint16 dest=0;
    if(ai.CanEquipItem(slot,dest,item,true,true)!=EQUIP_ERR_OK) return;
    auto bag=item->bag,bagSlot=item->slot;
    if(item->IsEquipped()) owner->equipped.erase(item->slot);
    if(auto* old=owner->GetItemByPos(INVENTORY_SLOT_BAG_0,slot)) { old->bag=bag; old->slot=bagSlot; }
    item->bag=INVENTORY_SLOT_BAG_0; item->slot=slot; owner->equipped[slot]=item; owner->equips.push_back(guid);
    if(slot==EQUIPMENT_SLOT_MAINHAND && item->GetTemplate()->InventoryType==INVTYPE_2HWEAPON && !owner->titan)
        if(auto* off=owner->GetItemByPos(INVENTORY_SLOT_BAG_0,EQUIPMENT_SLOT_OFFHAND)) {
            off->bag=INVENTORY_SLOT_BAG_0; off->slot=INVENTORY_SLOT_ITEM_END-1; owner->equipped.erase(EQUIPMENT_SLOT_OFFHAND);
        }
}
struct CollectItemsVisitor { std::vector<Item*> items; };
struct Chat { std::string FormatItem(ItemTemplate const* p) { return std::to_string(p->ItemId); } };
struct Config { bool AutoEquipUpgradeLoot=false; float EquipUpgradeThreshold=1.01f; } sPlayerbotAIConfig;
struct RandomMgr { bool IsRandomBot(Player* p) { return p->random; } bool IsSpecPvp(uint32,uint8) { return false; } } sRandomPlayerbotMgr;
struct RandomItemMgr {
    bool CanEquipWeapon(ItemTemplate const* p,uint8) { return p->proper; }
    bool CanEquipArmor(ItemTemplate const* p,uint8,uint8) { return p->proper; }
} sRandomItemMgr;
struct ObjectMgr { ItemTemplate const* GetItemTemplate(uint32 id) { return &templates.at(id); } } manager;
auto* sObjectMgr=&manager;
struct Event {
    std::string source; WorldPacket packet;
    std::string GetSource() const { return source; } WorldPacket getPacket() const { return packet; }
};
class EquipAction {
public:
    Player* bot; PlayerbotAI* botAI; Chat* chat;
    EquipAction(Player* p,PlayerbotAI* a,Chat* c):bot(p),botAI(a),chat(c) {}
    void EquipItem(Item*,uint8 forcedSlot=NULL_SLOT);
    bool EquipUpgrades();
    static uint8 GetSmallestBagSlot(Player* bot);
    static bool FillsBothHands(Player* bot,ItemTemplate const* proto);
    static float BestOffhandScore(PlayerbotAI* botAI,StatsWeightCalculator& calculator,uint32 candidateId);
    void IterateItems(CollectItemsVisitor* visitor,uint32 mask) {
        assert(mask==ITERATE_ITEMS_IN_BAGS); ++bot->bagScans;
        for(auto& item:bot->owned)
            if(!item.IsEquipped() && !(item.bag==INVENTORY_SLOT_BAG_0 && item.slot<INVENTORY_SLOT_BAG_END))
                visitor->items.push_back(&item);
    }
};
struct EquipUpgradesPacketAction:EquipAction { using EquipAction::EquipAction; bool Execute(Event event); };
struct EquipUpgradeAction:EquipAction { using EquipAction::EquipAction; bool Execute(Event event); };
#define AI_VALUE2(type,name,qualifier) botAI->Upgrade(qualifier)
struct ItemUsageValue {
    Player* bot; PlayerbotAI* botAI;
    ItemUsage QueryItemUsageForEquip(ItemTemplate const*,int32);
    Item* CurrentItem(ItemTemplate const* proto) const {
        for(auto& item:bot->owned) if(item.entry==proto->ItemId && !item.broken) return &item;
        return nullptr;
    }
};
ItemUsage PlayerbotAI::Upgrade(std::string const& qualifier) {
    auto comma=qualifier.find(',');
    auto id=std::stoul(qualifier.substr(0,comma));
    auto property=comma==std::string::npos?0:std::stoi(qualifier.substr(comma+1));
    return ItemUsageValue{bot,this}.QueryItemUsageForEquip(&templates.at(id),property);
}
// PRODUCTION
void AddTemplate(uint32 id,uint32 type,float tank,float dps,uint32 cls=0,uint32 level=1) {
    uint32 itemClass=(type==INVTYPE_WEAPON || type==INVTYPE_WEAPONMAINHAND || type==INVTYPE_2HWEAPON)?ITEM_CLASS_WEAPON:ITEM_CLASS_ARMOR;
    uint32 subclass=type==INVTYPE_2HWEAPON?ITEM_SUBCLASS_WEAPON_SWORD2:ITEM_SUBCLASS_WEAPON_SWORD;
    templates[id]={id,type,itemClass,subclass,cls,level,{{0,tank}},{{0,dps}}};
}
void ScoringTests(Chat& chat) {
    AddTemplate(40,INVTYPE_HEAD,40,40); templates[40].slotScores[EQUIPMENT_SLOT_HEAD]=70;
    AddTemplate(41,INVTYPE_HEAD,80,80); templates[41].slotScores[EQUIPMENT_SLOT_HEAD]=65;
    {
        // The equipped piece keeps its set tier and freed cap headroom in its own slot.
        Player p; PlayerbotAI ai{&p}; EquipUpgradeAction equip(&p,&ai,&chat);
        auto* worn=p.Add(40,0,true); p.Add(41);
        assert(ai.Upgrade("41")==ITEM_USAGE_NONE && equip.Execute({}));
        assert(p.equipped.at(EQUIPMENT_SLOT_HEAD)==worn && p.equips.empty());
    }
    AddTemplate(42,INVTYPE_HEAD,-5,-5); AddTemplate(43,INVTYPE_HEAD,0,0);
    {
        // An item scoring nothing or worse than nothing never fills an empty slot.
        Player p; PlayerbotAI ai{&p}; EquipUpgradeAction equip(&p,&ai,&chat);
        p.Add(42); p.Add(43);
        assert(ai.Upgrade("42")==ITEM_USAGE_NONE && ai.Upgrade("43")==ITEM_USAGE_NONE);
        assert(equip.Execute({}) && p.equips.empty() && !p.equipped.contains(EQUIPMENT_SLOT_HEAD));
    }
    AddTemplate(44,INVTYPE_HEAD,100,100); templates[44].proper=false;
    AddTemplate(45,INVTYPE_HEAD,100.5f,100.5f); templates[45].proper=false;
    {
        // An unsuitable item may fill an empty slot but replaces another only past the threshold.
        Player p; PlayerbotAI ai{&p}; EquipUpgradeAction equip(&p,&ai,&chat);
        assert(ai.Upgrade("45")==ITEM_USAGE_BAD_EQUIP);
        auto* worn=p.Add(44,0,true); p.Add(45);
        assert(ai.Upgrade("45")==ITEM_USAGE_NONE && equip.Execute({}) && p.equipped.at(EQUIPMENT_SLOT_HEAD)==worn);
    }
    AddTemplate(46,INVTYPE_HEAD,30,30); AddTemplate(47,INVTYPE_HEAD,-5,-5);
    {
        // A broken item is replaced only by one that is worth wearing.
        Player p; PlayerbotAI ai{&p}; EquipUpgradeAction equip(&p,&ai,&chat);
        auto* worn=p.Add(46,0,true); worn->broken=true; p.Add(47);
        assert(ai.Upgrade("47")==ITEM_USAGE_NONE && equip.Execute({}) && p.equipped.at(EQUIPMENT_SLOT_HEAD)==worn);
    }
    AddTemplate(50,INVTYPE_WEAPON,100,100); AddTemplate(51,INVTYPE_SHIELD,60,60);
    AddTemplate(52,INVTYPE_2HWEAPON,150,150); AddTemplate(53,INVTYPE_2HWEAPON,170,170);
    {
        // A two-hander must beat the main hand and the off hand it displaces together.
        Player p; p.dual=false; PlayerbotAI ai{&p}; EquipUpgradeAction equip(&p,&ai,&chat);
        p.Add(50,0,true,EQUIPMENT_SLOT_MAINHAND); auto* shield=p.Add(51,0,true,EQUIPMENT_SLOT_OFFHAND);
        auto* weak=p.Add(52);
        assert(ai.Upgrade("52")==ITEM_USAGE_NONE && equip.Execute({}) && p.equips.empty());
        equip.EquipItem(weak); assert(p.equips.empty());
        auto* strong=p.Add(53);
        assert(ai.Upgrade("53")==ITEM_USAGE_EQUIP && equip.Execute({}));
        assert(p.equipped.at(EQUIPMENT_SLOT_MAINHAND)==strong && !p.equipped.contains(EQUIPMENT_SLOT_OFFHAND));
        assert(!shield->IsEquipped() && p.equips.size()==1);
    }
    AddTemplate(54,INVTYPE_2HWEAPON,100,100); templates[54].SubClass=ITEM_SUBCLASS_WEAPON_STAFF;
    AddTemplate(55,INVTYPE_WEAPON,70,70); AddTemplate(56,INVTYPE_HOLDABLE,40,40);
    {
        // A caster leaves a staff for a one-hander when an owned off-hand item completes the pair.
        Player p; p.cls=CLASS_MAGE; p.dual=false; PlayerbotAI ai{&p}; EquipUpgradeAction equip(&p,&ai,&chat);
        p.Add(54,0,true,EQUIPMENT_SLOT_MAINHAND); auto* dagger=p.Add(55); auto* orb=p.Add(56);
        assert(ai.Upgrade("55")==ITEM_USAGE_EQUIP && equip.Execute({}));
        assert(p.equipped.at(EQUIPMENT_SLOT_MAINHAND)==dagger && p.equipped.at(EQUIPMENT_SLOT_OFFHAND)==orb);
        assert(p.equips.size()==2);
    }
    AddTemplate(57,INVTYPE_2HWEAPON,200,200); AddTemplate(58,INVTYPE_WEAPON,120,120);
    AddTemplate(59,INVTYPE_WEAPON,100,100); AddTemplate(60,INVTYPE_WEAPON,150,150);
    {
        // A dual wielder takes two owned one-handers over a weaker two-hander.
        Player p; PlayerbotAI ai{&p}; EquipUpgradeAction equip(&p,&ai,&chat);
        p.Add(57,0,true,EQUIPMENT_SLOT_MAINHAND); auto* main=p.Add(58); auto* off=p.Add(59);
        assert(equip.Execute({}));
        assert(p.equipped.at(EQUIPMENT_SLOT_MAINHAND)==main && p.equipped.at(EQUIPMENT_SLOT_OFFHAND)==off);
    }
    {
        // The candidate cannot also count as its own off hand.
        Player p; PlayerbotAI ai{&p}; EquipUpgradeAction equip(&p,&ai,&chat);
        auto* great=p.Add(57,0,true,EQUIPMENT_SLOT_MAINHAND); p.Add(60);
        assert(ai.Upgrade("60")==ITEM_USAGE_NONE && equip.Execute({}));
        assert(p.equipped.at(EQUIPMENT_SLOT_MAINHAND)==great && p.equips.empty());
    }
    AddTemplate(64,INVTYPE_WEAPON,10,10); templates[64].slotScores[EQUIPMENT_SLOT_MAINHAND]=30;
    AddTemplate(65,INVTYPE_WEAPON,20,20); AddTemplate(66,INVTYPE_SHIELD,5,5);
    {
        // A shield tank compares one-handers in the main hand, where the worn one keeps its slot value.
        Player p; p.tank=true; PlayerbotAI ai{&p}; EquipUpgradeAction equip(&p,&ai,&chat);
        auto* worn=p.Add(64,0,true,EQUIPMENT_SLOT_MAINHAND); p.Add(66,0,true,EQUIPMENT_SLOT_OFFHAND); p.Add(65);
        assert(equip.Execute({}) && p.equipped.at(EQUIPMENT_SLOT_MAINHAND)==worn && p.equips.empty());
    }
    AddTemplate(61,INVTYPE_FINGER,40,40); templates[61].slotScores[EQUIPMENT_SLOT_FINGER1]=70;
    AddTemplate(62,INVTYPE_FINGER,45,45); AddTemplate(63,INVTYPE_FINGER,60,60);
    {
        // A ring replaces the slot it improves most, keeping a set piece in its own slot.
        Player p; PlayerbotAI ai{&p}; EquipUpgradeAction equip(&p,&ai,&chat);
        auto* set=p.Add(61,0,true,EQUIPMENT_SLOT_FINGER1); p.Add(62,0,true,EQUIPMENT_SLOT_FINGER2);
        auto* upgrade=p.Add(63);
        assert(ai.Upgrade("63")==ITEM_USAGE_REPLACE && equip.Execute({}));
        assert(p.equipped.at(EQUIPMENT_SLOT_FINGER1)==set && p.equipped.at(EQUIPMENT_SLOT_FINGER2)==upgrade);
    }
}
void AddBagTemplate(uint32 id,uint32 size,uint32 itemClass=ITEM_CLASS_CONTAINER,uint32 subclass=ITEM_SUBCLASS_CONTAINER) {
    AddTemplate(id,itemClass==ITEM_CLASS_QUIVER?INVTYPE_QUIVER:INVTYPE_BAG,0,0);
    auto& proto=templates.at(id); proto.Class=itemClass; proto.SubClass=subclass; proto.ContainerSlots=size;
}
void BagTests(Chat& chat) {
    AddBagTemplate(200,6); AddBagTemplate(201,8); AddBagTemplate(202,10); AddBagTemplate(203,4);
    AddBagTemplate(204,2,ITEM_CLASS_QUIVER,ITEM_SUBCLASS_QUIVER);
    AddBagTemplate(205,4,ITEM_CLASS_CONTAINER,ITEM_SUBCLASS_HERB_CONTAINER);
    AddBagTemplate(206,2,ITEM_CLASS_QUIVER,ITEM_SUBCLASS_AMMO_POUCH);
    AddBagTemplate(207,0);
    for(uint32 special:{204u,205u,206u}) {
        Player p; p.cls=CLASS_HUNTER; PlayerbotAI ai{&p}; EquipUpgradeAction equip(&p,&ai,&chat);
        auto* preserved=p.Add(special,0,true,INVENTORY_SLOT_BAG_START);
        auto* small=p.Add(200,0,true,INVENTORY_SLOT_BAG_START+1);
        p.Add(201,0,true,INVENTORY_SLOT_BAG_START+2); p.Add(201,0,true,INVENTORY_SLOT_BAG_START+3);
        auto* upgrade=p.Add(202); auto sourceSlot=upgrade->slot;
        assert(EquipAction::GetSmallestBagSlot(&p)==INVENTORY_SLOT_BAG_START+1);
        assert(equip.Execute({}) && p.swapCalls==1 && p.owned.size()==5);
        assert(p.equipped.at(INVENTORY_SLOT_BAG_START)==preserved);
        assert(p.equipped.at(INVENTORY_SLOT_BAG_START+1)==upgrade &&
            small->bag==INVENTORY_SLOT_BAG_0 && small->slot==sourceSlot);
        equip.Execute({}); assert(p.swapCalls==1);
    }
    {
        // The first equipped bag participates; a later large bag cannot hide its upgrade.
        Player p; PlayerbotAI ai{&p}; EquipUpgradeAction equip(&p,&ai,&chat);
        p.Add(200,0,true,INVENTORY_SLOT_BAG_START);
        for(uint8 slot=INVENTORY_SLOT_BAG_START+1;slot<INVENTORY_SLOT_BAG_END;++slot) p.Add(202,0,true,slot);
        auto* upgrade=p.Add(201);
        assert(ai.Upgrade("201")==ITEM_USAGE_EQUIP && equip.Execute({}));
        assert(p.equipped.at(INVENTORY_SLOT_BAG_START)==upgrade && p.swapCalls==1);
        p.Add(201); p.Add(203); assert(equip.Execute({}) && p.swapCalls==1);
    }
    {
        // Fill a free slot before replacing an existing general bag.
        Player p; PlayerbotAI ai{&p}; EquipUpgradeAction equip(&p,&ai,&chat);
        auto* first=p.Add(200,0,true,INVENTORY_SLOT_BAG_START); auto* upgrade=p.Add(201);
        assert(EquipAction::GetSmallestBagSlot(&p)==INVENTORY_SLOT_BAG_START+1);
        assert(equip.Execute({}) && p.equipped.at(INVENTORY_SLOT_BAG_START)==first);
        assert(p.equipped.at(INVENTORY_SLOT_BAG_START+1)==upgrade);
        assert(ai.Upgrade("207")==ITEM_USAGE_NONE);
    }
    {
        // All-special slots have no general-bag destination, including direct commands.
        Player p; p.cls=CLASS_HUNTER; PlayerbotAI ai{&p}; EquipUpgradeAction equip(&p,&ai,&chat);
        for(uint8 slot=INVENTORY_SLOT_BAG_START;slot<INVENTORY_SLOT_BAG_END;++slot) p.Add(205,0,true,slot);
        auto* upgrade=p.Add(202);
        assert(EquipAction::GetSmallestBagSlot(&p)==NULL_SLOT && ai.Upgrade("202")==ITEM_USAGE_NONE);
        assert(equip.Execute({}) && !p.swapCalls && p.equips.empty());
        equip.EquipItem(upgrade); assert(!p.swapCalls && p.equips.empty());
    }
    for(bool inside:{false,true}) {
        // Native refusal or a bag inside its destination leaves every item in place.
        Player p; PlayerbotAI ai{&p}; EquipUpgradeAction equip(&p,&ai,&chat);
        auto* first=p.Add(200,0,true,INVENTORY_SLOT_BAG_START);
        for(uint8 slot=INVENTORY_SLOT_BAG_START+1;slot<INVENTORY_SLOT_BAG_END;++slot) p.Add(202,0,true,slot);
        auto* upgrade=p.Add(201);
        if(inside) { upgrade->bag=INVENTORY_SLOT_BAG_START; upgrade->slot=0; } else p.rejectSwap=true;
        auto oldBag=upgrade->bag,oldSlot=upgrade->slot;
        assert(equip.Execute({}) && p.swapCalls==1 && p.equips.empty());
        assert(p.equipped.at(INVENTORY_SLOT_BAG_START)==first && upgrade->bag==oldBag && upgrade->slot==oldSlot);
    }
}
int main() {
    Chat chat;
    AddTemplate(10,INVTYPE_HEAD,10,100);
    AddTemplate(11,INVTYPE_HEAD,100,10);
    AddTemplate(12,INVTYPE_HEAD,50,50);
    AddTemplate(99,INVTYPE_HEAD,30,30);
    AddTemplate(90,INVTYPE_HEAD,500,500,CLASS_MAGE);
    AddTemplate(91,INVTYPE_HEAD,500,500,0,80);
    for(bool tank:{false,true}) {
        Player p; p.tank=tank; PlayerbotAI ai{&p}; EquipUpgradeAction equip(&p,&ai,&chat);
        p.Add(99,0,true); p.Add(10); p.Add(11); p.Add(12); p.Add(90); p.Add(91);
        assert(equip.Execute({}));
        assert(p.equipped.at(EQUIPMENT_SLOT_HEAD)->entry==(tank?11u:10u));
        assert(p.equips.size()==1 && p.owned.size()==6);
        auto count=p.equips.size(); equip.Execute({}); assert(p.equips.size()==count);
    }
    {
        Player p; PlayerbotAI ai{&p}; EquipUpgradeAction equip(&p,&ai,&chat);
        p.Add(99,0,true); p.Add(10); p.combat=true;
        assert(!equip.Execute({}) && p.equips.empty() && p.bagScans==0);
    }
    {
        Player p; PlayerbotAI ai{&p}; EquipUpgradesPacketAction equip(&p,&ai,&chat);
        p.Add(99,0,true); p.Add(10);
        assert(!equip.Execute({}) && p.equips.empty());
        p.random=true; assert(equip.Execute({}) && p.equipped.at(EQUIPMENT_SLOT_HEAD)->entry==10);
    }
    AddTemplate(20,INVTYPE_2HWEAPON,1000,1000);
    AddTemplate(21,INVTYPE_WEAPON,10,100);
    AddTemplate(22,INVTYPE_SHIELD,5,0);
    AddTemplate(23,INVTYPE_2HWEAPON,2000,2000);
    for(uint8 cls:{uint8(CLASS_WARRIOR),uint8(CLASS_PALADIN)}) {
        Player p; p.cls=cls; p.tank=true; PlayerbotAI ai{&p}; EquipUpgradeAction equip(&p,&ai,&chat);
        p.Add(20,0,true,EQUIPMENT_SLOT_MAINHAND); auto* shield=p.Add(22); auto* sword=p.Add(21); p.Add(23);
        equip.Execute({});
        assert(p.equipped.contains(EQUIPMENT_SLOT_OFFHAND));
        assert(p.equipped.at(EQUIPMENT_SLOT_MAINHAND)==sword && p.equipped.at(EQUIPMENT_SLOT_OFFHAND)==shield);
        assert(p.equips.size()==2);
        equip.Execute({}); assert(p.equips.size()==2);
    }
    {
        Player p; p.tank=true; PlayerbotAI ai{&p}; EquipUpgradeAction equip(&p,&ai,&chat);
        p.Add(20,0,true,EQUIPMENT_SLOT_MAINHAND); p.Add(22); auto* better=p.Add(23);
        equip.Execute({}); assert(p.equipped.at(EQUIPMENT_SLOT_MAINHAND)==better);
    }
    {
        Player p; p.tank=true; PlayerbotAI ai{&p}; EquipUpgradeAction equip(&p,&ai,&chat);
        p.Add(99,0,true); auto* broken=p.Add(11); broken->broken=true;
        equip.Execute({}); assert(p.equips.empty());
    }
    templates[12].dps[1]=80; templates[12].dps[-2]=120;
    {
        Player p; PlayerbotAI ai{&p}; EquipUpgradeAction equip(&p,&ai,&chat);
        p.Add(12,0,true); p.Add(12,1); auto* best=p.Add(12,-2);
        equip.Execute({}); assert(p.equipped.at(EQUIPMENT_SLOT_HEAD)==best && p.equips.size()==1);
    }
    AddTemplate(30,INVTYPE_FINGER,20,50);
    templates[30].dps[1]=100; templates[30].dps[2]=80; templates[30].dps[3]=99.5f;
    {
        Player p; PlayerbotAI ai{&p}; EquipUpgradeAction equip(&p,&ai,&chat);
        auto* strong=p.Add(30,1,true,EQUIPMENT_SLOT_FINGER1); p.Add(30,0,true,EQUIPMENT_SLOT_FINGER2);
        auto* upgrade=p.Add(30,2);
        equip.Execute({});
        assert(p.equipped.at(EQUIPMENT_SLOT_FINGER1)==strong && p.equipped.at(EQUIPMENT_SLOT_FINGER2)==upgrade);
    }
    {
        Player p; PlayerbotAI ai{&p}; EquipUpgradeAction equip(&p,&ai,&chat);
        auto* strong=p.Add(30,1,true,EQUIPMENT_SLOT_FINGER1);
        auto* almost=p.Add(30,3,true,EQUIPMENT_SLOT_FINGER2); p.Add(30,1);
        equip.Execute({});
        assert(p.equips.empty() && p.equipped.at(EQUIPMENT_SLOT_FINGER1)==strong &&
            p.equipped.at(EQUIPMENT_SLOT_FINGER2)==almost);
    }
    {
        Player p; PlayerbotAI ai{&p}; EquipUpgradeAction equip(&p,&ai,&chat);
        p.Add(21,0,true,EQUIPMENT_SLOT_MAINHAND); auto* strong=p.Add(10);
        assert(equip.Execute({}) && p.equipped.at(EQUIPMENT_SLOT_HEAD)==strong);
    }
    BagTests(chat);
    ScoringTests(chat);
    std::cout<<"Profile equipment: native role scores, owned instances, shield combinations, random suffixes, slot scores, hand pairs, empty-slot and threshold gates, bag selection, combat and packet opt-out passed\n";
}
'''

fixture = FIXTURE.replace('// ENUMS', enums).replace('// PRODUCTION', production)
mutations = (
    ('combat guard', '    if (bot->IsInCombat())\n        return false;\n', ''),
    ('best candidate ordering', 'return left.second > right.second;', 'return left.second < right.second;'),
    ('mainhand before shield', 'return mainHand(left.first);', 'return !mainHand(left.first);'),
    ('tank shield preference', 'bool const preferShield = shieldTank && haveShield && haveOnehand;',
     'bool const preferShield = shieldTank && haveShield && haveOnehand && false;'),
    ('broken inventory exclusion', ' || item->IsBroken()', ''),
    ('random suffix identity', 'EquipItem(item, forcedSlot);', 'EquipItem(&*std::find_if(bot->owned.begin(), bot->owned.end(), [&](auto const& owned) { return owned.GetEntry() == item->GetEntry(); }), forcedSlot);'),
    ('variant classification', ' ||\n             randomPropertyId != oldItem->GetInt32Value(ITEM_FIELD_RANDOM_PROPERTIES_ID)', ''),
    ('paired suffix slot', '        possibleSlots = 2;', '        possibleSlots = 1;'),
    ('suffix upgrade threshold', 'itemScore > oldScore * sPlayerbotAIConfig.EquipUpgradeThreshold', 'itemScore > oldScore'),
    ('first bag slot ignored', 'uint8 bag = INVENTORY_SLOT_BAG_START;', 'uint8 bag = INVENTORY_SLOT_BAG_START + 1;'),
    ('special bag replacement', 'if (proto->Class != ITEM_CLASS_CONTAINER || proto->SubClass != ITEM_SUBCLASS_CONTAINER)',
     'if ((proto->Class != ITEM_CLASS_CONTAINER || proto->SubClass != ITEM_SUBCLASS_CONTAINER) && false)'),
    ('largest bag replacement', 'curSlots < pBag->GetBagSize()', 'curSlots > pBag->GetBagSize()'),
    ('all-special fallback', '        if (newBagSlot == NULL_SLOT)\n            return;\n', ''),
    ('equal bag accepted', '(bag ? bag->GetBagSize() : 0) >= itemProto->ContainerSlots',
     '(bag ? bag->GetBagSize() : 0) > itemProto->ContainerSlots'),
    ('slotless candidate score', 'calculator.CalculateItem(itemProto->ItemId, randomPropertyId, slot)',
     'calculator.CalculateItem(itemProto->ItemId, randomPropertyId, -1)'),
    ('slotless equipped score', 'oldItem->GetInt32Value(ITEM_FIELD_RANDOM_PROPERTIES_ID), slot)',
     'oldItem->GetInt32Value(ITEM_FIELD_RANDOM_PROPERTIES_ID), -1)'),
    ('non-positive empty slot', '            if (!isBetter)\n                return ITEM_USAGE_NONE;\n', ''),
    ('broken replacement score', 'oldItemIsBroken && !itemIsBroken && itemScore > 0', 'oldItemIsBroken && !itemIsBroken'),
    ('per-hand weapon scores', 'calculator.SetWeaponPairs(true);', ''),
    ('displaced off hand', 'if (fillsBothHands && offhand)', 'if (fillsBothHands && offhand && false)'),
    ('owned off hand', 'itemScore += EquipAction::BestOffhandScore(botAI, calculator, itemProto->ItemId);',
     'itemScore += 0;'),
    ('equip displaced off hand', 'betterThanMH = newItemScore > mainHandScore + offHandScore;',
     'betterThanMH = newItemScore > mainHandScore;'),
    ('equip owned off hand', 'betterThanMH = newItemScore + BestOffhandScore(botAI, calculator, itemId) > mainHandScore;',
     'betterThanMH = newItemScore > mainHandScore;'),
    ('candidate as own off hand', 'item->GetEntry() == candidateId || ', '(candidateId && false) || '),
    ('two-hander without Titan Grip', '(!bot->CanTitanGrip() || (', '(bot->CanTitanGrip() || ('),
    ('slotless shield preference', 'current->GetItemRandomPropertyId(), forcedSlot)',
     'current->GetItemRandomPropertyId(), -1)'),
    ('ring slot gain', 'equippedItems[i]->GetItemRandomPropertyId(), dstSlot + i)',
     'equippedItems[i]->GetItemRandomPropertyId(), -1)'),
)
with tempfile.TemporaryDirectory(prefix='profile-equipment-') as temporary:
    work = Path(temporary)
    for label, before, after in (('production', '', ''), *mutations):
        body = fixture
        if before:
            if before not in body:
                raise AssertionError('Missing production equipment guard: ' + label)
            body = body.replace(before, after)
        cpp, binary = work / 'fixture.cpp', work / 'fixture'
        cpp.write_text(body)
        subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', *SANITIZER_FLAGS,
                        '-no-pie', str(cpp), '-o', str(binary)], check=True)
        result = run_fixture([str(binary)], 'combat profile equipment ' + label)
        if label == 'production':
            assert result.returncode == 0, result.stdout + result.stderr
            print(result.stdout.strip())
        elif result.returncode == 0:
            raise AssertionError('Equipment regression did not reject ' + label)
        else:
            assert 'Assertion' in result.stderr, result.stdout + result.stderr
            print('Equipment mutation rejected:', label)
