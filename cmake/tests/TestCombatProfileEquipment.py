"""Exercise owned-inventory profile equipment through the real equip actions.

The production selection, per-item equip code and both action entry points run
with native-shaped item instances and session packets. No item is created,
bought, granted or selected from a bank.
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
player_header = (core / 'src/server/game/Entities/Player/Player.h').read_text()
shared = (core / 'src/server/shared/SharedDefines.h').read_text()

# The doubles below follow the producers these actions call: fresh upgrade
# evaluation, bag-only item instances and a session equip packet identifying GUID.
value = (args.source / 'Bot/Engine/Value/Value.h').read_text()
usage = (args.source / 'Ai/Base/Value/ItemUsageValue.cpp').read_text()
visitor = (args.source / 'Mgr/Item/ItemVisitors.h').read_text()
handler = (core / 'src/server/game/Handlers/ItemHandler.cpp').read_text()
native_handler = function(handler, 'void WorldSession::HandleAutoEquipItemSlotOpcode(')
assert 'if (checkInterval < 2)' in value and 'value = Calculate();' in value
assert 'QueryItemUsageForEquip(proto, randomPropertyId)' in function(usage, 'ItemUsage ItemUpgradeValue::Calculate()')
assert 'std::vector<Item*> items;' in function(visitor, 'class CollectItemsVisitor')
assert '_player->GetItemByGuid(packet.ItemGuid)' in native_handler
assert '_player->SwapItem(item->GetPos(), dstpos);' in native_handler
assert 'void EquipItem(Item* item, uint8 forcedSlot = NULL_SLOT);' in header

enums = '\n'.join(function(text, 'enum ' + name) + ';' for text, name in (
    (item_header, 'InventoryType'), (item_header, 'ItemClass'), (item_header, 'ItemSubclassWeapon'),
    (player_header, 'EquipmentSlots'), (player_header, 'InventorySlots'), (shared, 'Classes')))
production = '\n\n'.join(function(source, signature) for signature in (
    'void EquipAction::EquipItem(Item* item, uint8 forcedSlot)',
    'bool EquipAction::EquipUpgrades()',
    'bool EquipUpgradesPacketAction::Execute(Event event)',
    'bool EquipUpgradeAction::Execute(Event'))

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
constexpr uint32 ITERATE_ITEMS_IN_BAGS=1;
enum InventoryResult { EQUIP_ERR_OK, EQUIP_ERR_CANT_CARRY_MORE_OF_THIS, EQUIP_ERR_INVALID };
enum ItemUsage { ITEM_USAGE_NONE, ITEM_USAGE_EQUIP, ITEM_USAGE_REPLACE, ITEM_USAGE_BAD_EQUIP, ITEM_USAGE_BROKEN_EQUIP };
struct ObjectGuid { uint64 value=0; uint32 GetCounter() const { return value; } };
struct ItemTemplate {
    uint32 ItemId=0, InventoryType=INVTYPE_HEAD, Class=ITEM_CLASS_ARMOR, SubClass=0;
    uint32 allowedClass=0, level=1;
    std::map<int32,float> tank, dps;
};
std::map<uint32,ItemTemplate> templates;
struct Item {
    uint64 guid=0; uint32 entry=0; int32 property=0; uint8 bag=0,slot=0; bool broken=false;
    ItemTemplate const* GetTemplate() const { return &templates.at(entry); }
    uint32 GetEntry() const { return entry; }
    int32 GetItemRandomPropertyId() const { return property; }
    int32 GetInt32Value(uint32) const { return property; }
    ObjectGuid GetGUID() const { return {guid}; }
    uint8 GetBagSlot() const { return bag; }
    uint8 GetSlot() const { return slot; }
    bool IsEquipped() const { return bag==INVENTORY_SLOT_BAG_0 && slot<EQUIPMENT_SLOT_END; }
    bool IsBroken() const { return broken; }
};
struct Bag : Item { uint32 GetBagSize() const { return 16; } };
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
    std::list<Item> owned;
    std::map<uint8,Item*> equipped;
    std::vector<uint64> equips;
    uint32 bagScans=0;
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
            auto found=equipped.find(slot); return found==equipped.end()?nullptr:found->second;
        }
        for(auto& item:owned) if(item.bag==bag && item.slot==slot) return &item;
        return nullptr;
    }
    InventoryResult CanUseItem(ItemTemplate const* p) const {
        return (p->allowedClass && p->allowedClass!=cls) || p->level>level ? EQUIP_ERR_INVALID:EQUIP_ERR_OK;
    }
    void SetAmmo(uint32) { assert(false && "ammo is not armor"); }
    void SwapItem(uint16,uint16) { assert(false && "fixture uses no bag changes"); }
    Item* Add(uint32 entry,int32 property=0,bool equip=false,uint8 equipSlot=EQUIPMENT_SLOT_HEAD) {
        owned.push_back({owned.size()+1,entry,property,0,uint8(owned.size()+23),false});
        auto* item=&owned.back();
        if(equip) { item->bag=INVENTORY_SLOT_BAG_0; item->slot=equipSlot; equipped[equipSlot]=item; }
        return item;
    }
};
struct StatsWeightCalculator {
    Player* player; explicit StatsWeightCalculator(Player* p):player(p) {}
    void SetItemSetBonus(bool) {} void SetOverflowPenalty(bool) {} void SetPvpSpec(bool) {}
    float CalculateItem(uint32 id,int32 property=0) {
        auto const& weights=player->tank?templates.at(id).tank:templates.at(id).dps;
        auto it=weights.find(property); return it==weights.end()?weights.at(0):it->second;
    }
};
struct PlayerbotAI {
    Player* bot; static bool IsTank(Player* p) { return p->tank; }
    uint8 FindEquipSlot(ItemTemplate const* p,uint8,bool) {
        switch(p->InventoryType) {
            case INVTYPE_WEAPON: case INVTYPE_WEAPONMAINHAND: case INVTYPE_2HWEAPON:return EQUIPMENT_SLOT_MAINHAND;
            case INVTYPE_SHIELD: case INVTYPE_WEAPONOFFHAND:return EQUIPMENT_SLOT_OFFHAND;
            case INVTYPE_FINGER:return EQUIPMENT_SLOT_FINGER1;
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
    ItemUsage Upgrade(std::string const& qualifier) {
        auto comma=qualifier.find(',');
        uint32 id=std::stoul(qualifier.substr(0,comma));
        int32 property=comma==std::string::npos?0:std::stoi(qualifier.substr(comma+1));
        auto* p=&templates.at(id);
        if(bot->CanUseItem(p)!=EQUIP_ERR_OK) return ITEM_USAGE_NONE;
        uint8 slot=FindEquipSlot(p,NULL_SLOT,true);
        StatsWeightCalculator calc(bot);
        float score=calc.CalculateItem(id,property);
        uint8 possible=(p->InventoryType==INVTYPE_FINGER ||
            (slot==EQUIPMENT_SLOT_MAINHAND && bot->dual && (!bot->GetItemByPos(INVENTORY_SLOT_BAG_0,slot) ||
             bot->GetItemByPos(INVENTORY_SLOT_BAG_0,slot)->GetTemplate()->InventoryType!=INVTYPE_2HWEAPON)))?2:1;
        for(uint8 n=0;n<possible;++n) {
            auto* old=bot->GetItemByPos(INVENTORY_SLOT_BAG_0,slot+n);
            if(!old) return score>0?ITEM_USAGE_EQUIP:ITEM_USAGE_BAD_EQUIP;
            if(id!=old->entry && score>calc.CalculateItem(old->entry,old->property)*1.01f)
                return ITEM_USAGE_EQUIP;
        }
        return ITEM_USAGE_NONE;
    }
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
            off->bag=0; off->slot=99; owner->equipped.erase(EQUIPMENT_SLOT_OFFHAND);
        }
}
struct CollectItemsVisitor { std::vector<Item*> items; };
struct Chat { std::string FormatItem(ItemTemplate const* p) { return std::to_string(p->ItemId); } };
struct Config { bool AutoEquipUpgradeLoot=false; float EquipUpgradeThreshold=1.01f; } sPlayerbotAIConfig;
struct RandomMgr { bool IsRandomBot(Player* p) { return p->random; } bool IsSpecPvp(uint32,uint8) { return false; } } sRandomPlayerbotMgr;
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
    uint8 GetSmallestBagSlot() { return INVENTORY_SLOT_BAG_START; }
    void IterateItems(CollectItemsVisitor* visitor,uint32 mask) {
        assert(mask==ITERATE_ITEMS_IN_BAGS); ++bot->bagScans;
        for(auto& item:bot->owned) if(!item.IsEquipped()) visitor->items.push_back(&item);
    }
};
struct EquipUpgradesPacketAction:EquipAction { using EquipAction::EquipAction; bool Execute(Event event); };
struct EquipUpgradeAction:EquipAction { using EquipAction::EquipAction; bool Execute(Event event); };
#define AI_VALUE2(type,name,qualifier) botAI->Upgrade(qualifier)
// PRODUCTION
void AddTemplate(uint32 id,uint32 type,float tank,float dps,uint32 cls=0,uint32 level=1) {
    uint32 itemClass=(type==INVTYPE_WEAPON || type==INVTYPE_WEAPONMAINHAND || type==INVTYPE_2HWEAPON)?ITEM_CLASS_WEAPON:ITEM_CLASS_ARMOR;
    templates[id]={id,type,itemClass,ITEM_SUBCLASS_WEAPON_SWORD,cls,level,{{0,tank}},{{0,dps}}};
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
    std::cout<<"Profile equipment: native role scores, owned instances, shield combinations, random suffixes, combat and packet opt-out passed\n";
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
    ('paired suffix slot', 'forcedSlot = slot + i;', 'forcedSlot = slot;'),
    ('suffix upgrade threshold', ' && score > currentScore * sPlayerbotAIConfig.EquipUpgradeThreshold', ''),
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
