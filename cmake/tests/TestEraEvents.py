"""Exercise production Era Events gates, scheduling and phases with native IP milestones.

The manager methods and IP quest accessor execute with recording player/session
services. No realm, database or map spawns are needed to check who may participate.
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


repository = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, 'core', default=prepared_core(repository))
source_argument(parser, 'module')
args = parser.parse_args()
module = args.module or args.core / 'modules/mod-era-events'
production = (module / 'src/EraEvents.cpp').read_text()
# FixtureSupport's brace extractor expects the first brace to open the body.
production = production.replace('std::string instigator = {}', 'std::string instigator = std::string()')
production = production.replace('std::string const& text = {}', 'std::string const& text = std::string()')
header = (module / 'src/EraEvents.h').read_text()
ip = args.core / 'modules/mod-individual-progression/src'
ip_source = (ip / 'IndividualProgression.cpp').read_text()
ip_header = (ip / 'IndividualProgression.h').read_text()
session_header = (args.core / 'src/server/game/Server/WorldSession.h').read_text()
assert 'bool IsHeadless() const { return _headless; }' in session_header
zombie_source = (module / 'src/events/ZombieInfestation.cpp').read_text()
mob_source = (module / 'src/EraEventMobs.cpp').read_text()
aura_header = (args.core / 'src/server/game/Spells/Auras/SpellAuras.h').read_text()
aura_source = (args.core / 'src/server/game/Spells/Auras/SpellAuras.cpp').read_text()
assert 'time_t GetApplyTime() const { return m_applyTime; }' in aura_header
assert 'm_applyTime(GameTime::GetGameTime().count())' in aura_source
session_source = (args.core / 'src/server/game/Server/WorldSession.cpp').read_text()
logout = function(session_source, 'void WorldSession::LogoutPlayer(')
assert logout.index('OnPlayerBeforeLogout(_player)') < logout.index('_player->SaveToDB(')

# Use the actual native producer, including its rewarded-quest and in-world
# contracts. A synthetic account, leader or level never supplies the tier.
native = function(ip_header, 'enum ProgressionState') + ';\n'
native += function(ip_source, 'uint8 IndividualProgression::GetPlayerProgressionFromQuests(') + '\n'
native += function(ip_source, 'bool IndividualProgression::IsStrictDefaultProgression(')
helpers = production[production.index('        template <typename Session, typename = void>'):
                     production.index('        enum class State')]
settings = '\n'.join(function(production, signature) + ';' for signature in (
    '        struct EventSettings', '        struct Config', '        enum class State', '        struct Slot'))
methods = '\n'.join(function(production, signature) for signature in (
    '            EventSettings const& Settings(',
    '            bool IsAvailable(',
    '            std::vector<Player*> GetCohort(',
    '            std::vector<Player*> GetAudience(',
    '            bool IsEventParticipant(',
    '            void UpdatePlayerPhases(',
    '            bool ForceStart(',
    '            void ForceStop(',
    '            int64 RollInterval(',
    '            static void SetAura(',
    '            int64 RunTime(',
    '            static std::string StartText(',
    '            void UpdateSlot(',
    '            void TryAnnounce(',
    '            bool Begin(',
    '            void Finish(',
    '            void Reschedule(',
    '            void RefreshAllPhases(',
    '            void RewardParticipants('))
shared = '\n'.join(function(production, signature) for signature in (
    '        void LoadConfig(', '    uint8 GetPlayerTier(', '    bool IsRealPlayer(',
    '    bool IsEventParticipant(Player* player, EventType type)',
    '    void EraEvent::Stop(', '    void EraEvent::SetRun('))
zombie_shared = function(zombie_source, '        enum Entries') + ';\n'
zombie_shared += function(zombie_source, '        enum Spells') + ';\n'
zombie_shared += '\n'.join(function(zombie_source, signature) for signature in (
    '        void SetTimed(', '        bool IsZombie(', '        void Infect(',
    '        void StripPlague(', '    void ClearZombieInfection('))
zombie_check = '\n'.join(function(zombie_source, signature) for signature in (
    '            void CheckPlayers(', '            static Creature* NearestHealer('))
groan = function(zombie_source, '    void HandleAfterCast(')
melee = function(mob_source, '    void DamageDealt(').replace(' override', '')
crate = function(zombie_source, 'struct go_era_plagued_crate') + ';'
zombie_player = function(zombie_source, 'class EraEventsZombiePlayerScript') + ';'
zombie_registration = function(zombie_source, 'void AddEraEventZombieScripts(')
tiers = []
for source, name, event_type in (
        ('AQWar', 'AQ', 'EVENT_AQ_WAR'),
        ('ScourgeInvasion', 'Scourge', 'EVENT_SCOURGE_INVASION'),
        ('LegionIncursion', 'Legion', 'EVENT_LEGION_INCURSION'),
        ('ZombieInfestation', 'Zombie', 'EVENT_ZOMBIE_INFESTATION')):
    event_source = (module / ('src/events/' + source + '.cpp')).read_text()
    tier = function(event_source, '            uint8 GetTier() const override')
    tiers.append(f'struct {name}Event : FixtureEvent {{ {name}Event() : FixtureEvent({event_type}) {{}} {tier} }};')

stub = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <list>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>
using uint8=std::uint8_t; using uint32=std::uint32_t; using int32=std::int32_t; using int64=std::int64_t;
constexpr uint32 MINUTE=60, IN_MILLISECONDS=1000, GOLD=10000, QUEST_STATUS_REWARDED=6;
struct ObjectGuid { uint32 value=0; void Clear(){value=0;} auto operator<=>(ObjectGuid const&) const=default; };
struct Position {};
namespace GameTime { inline int64 now=1000; std::chrono::seconds GetGameTime() {return std::chrono::seconds(now);} }
struct Aura {
    int64 applied=GameTime::now; int32 maxDuration=0,duration=0;
    int64 GetApplyTime() const {return applied;}
    void SetMaxDuration(int32 value) {maxDuration=value;} void SetDuration(int32 value) {duration=value;}
};
class Player;
class Unit {
public:
    virtual ~Unit()=default;
    virtual bool HasAura(uint32) const {return false;}
    virtual Player* ToPlayer() {return nullptr;} bool IsPlayer() {return ToPlayer()!=nullptr;}
    virtual Aura* AddAura(uint32 spell,Unit* target) {return target->AddAura(spell,target);}
};
class Creature : public Unit {
public:
    bool alive=true,near=false; uint32 heals=0;
    std::list<Creature*> healers;
    void DespawnOrUnsummon() {} bool IsAlive() const {return alive;}
    bool IsWithinDist(Player*,float) const {return near;}
    void GetCreatureListWithEntryInGrid(std::list<Creature*>& list,uint32,float) {list=healers;}
    void CastSpell(Player*,uint32,bool) {++heals;}
};
class GameObject {
public:
    bool spawned=true; uint32 despawns=0;
    void DespawnOrUnsummon() {spawned=false;++despawns;} bool isSpawned() const {return spawned;}
};
class Map { public: Creature* GetCreature(ObjectGuid) {return nullptr;} GameObject* GetGameObject(ObjectGuid) {return nullptr;} };
struct WorldSession { bool headless=false; bool IsHeadless() const {return headless;} };
struct FactionEntry {};
struct ReputationMgr { int calls=0; void ModifyReputation(FactionEntry const*,float) {++calls;} };
class Player : public Unit {
public:
    bool inWorld=true,gm=false,alive=true; uint32 map=0,zone=1519,area=77,level=80;
    uint32 money=12345,itemGrants=0,casts=0; std::map<uint32,uint32> quests; std::set<uint32> auras;
    WorldSession session; ReputationMgr reputation; bool hasSession=true;
    std::map<uint32,Aura> auraData;
    Player* ToPlayer() override {return this;}
    bool IsInWorld() const {return inWorld;} bool IsGameMaster() const {return gm;}
    bool IsAlive() const {return alive;} uint32 GetMapId() const {return map;}
    uint32 GetZoneId() const {return zone;} uint32 GetAreaId() const {return area;}
    WorldSession* GetSession() {return hasSession?&session:nullptr;}
    uint32 GetQuestStatus(uint32 quest) const {auto it=quests.find(quest);return it==quests.end()?0:it->second;}
    bool HasAura(uint32 spell) const override {return auras.contains(spell);}
    Aura* AddAura(uint32 spell,Unit* target) override {
        assert(target==this);auras.insert(spell);auraData[spell]=Aura{};return &auraData[spell];
    }
    Aura* GetAura(uint32 spell) {return HasAura(spell)?&auraData[spell]:nullptr;}
    void CastSpell(Player* target,uint32 spell,bool triggered) {assert(target==this&&triggered);auras.insert(spell);++casts;}
    void RemoveAurasDueToSpell(uint32 spell) {auras.erase(spell);}
    void ModifyMoney(uint32 amount) {money+=amount;}
    ReputationMgr& GetReputationMgr() {return reputation;}
};
struct IndividualProgression {
    bool enabled=true,strictEarnedProgression=true,disableDefaultProgression=false;
    std::map<uint32,uint8> customProgressionMap; int progressionLimit=0;
    uint8 GetPlayerProgressionFromQuests(Player*) const; bool IsStrictDefaultProgression() const;
} progression;
inline auto* sIndividualProgression=&progression;
NATIVE_IP
namespace ObjectAccessor {
inline std::map<uint32,Player*> players;
auto const& GetPlayers() {return players;}
}
namespace Acore {
inline std::string StringFormat(std::string text) {return text;}
template<class T,class... Rest> std::string StringFormat(std::string text,T const& value,Rest const&... rest) {
    auto position=text.find("{}");assert(position!=std::string::npos);
    std::ostringstream out;out<<value;text.replace(position,2,out.str());return StringFormat(text,rest...);
}
}
struct ConfigMgr {
    std::map<std::string,int64> values;
    template<class T> T GetOption(std::string const& key,T fallback,bool=true) const {
        auto it=values.find(key);return it==values.end()?fallback:T(it->second);
    }
} configMgr;
inline auto* sConfigMgr=&configMgr;
struct FactionStore {FactionEntry row;FactionEntry const* LookupEntry(uint32) const {return &row;}} sFactionStore;
inline uint32 urand(uint32 low,uint32 high) {assert(high>=low);return low;}
#define LOG_INFO(...) ((void)0)
#define LOG_WARN(...) ((void)0)
#define LOG_ERROR(...) ((void)0)
#include "EraEvents.h"
#include "EraEventMobs.h"
namespace EraEvents {
constexpr uint32 MINUTE_MS=MINUTE*IN_MILLISECONDS;
constexpr uint32 INFECTION_MS=60000,ZOMBIE_MS=180000;
constexpr float HEAL_RANGE=8.f,GROAN_RANGE=12.f;
SETTINGS
Config config;
SESSION_HELPERS
std::string FormatMinutes(uint32 ms) {return std::to_string(ms/MINUTE_MS);}
void Tell(Player*,std::string const&,bool) {}
void TellPlayer(Player*,std::string const&) {}
ZOMBIE_SHARED
class Manager {
public:
    std::array<Slot,MAX_ERA_EVENTS> _slots; bool _phasesDirty=false;
    MANAGER_METHODS
    void GiveItem(Player* player,EraEvent const&,uint32,uint32) {++player->itemGrants;}
};
Manager manager;
Manager& Mgr() {return manager;}
SHARED_METHODS
class FixtureEvent : public EraEvent {
public:
    explicit FixtureEvent(EventType type):EraEvent(type) {}
    uint32 starts=0,stops=0,updates=0,prepares=0;
    bool prepareResult=true,startResult=true;
    char const* GetKey() const override {return "fixture";}
    char const* GetName() const override {return "Fixture event";}
    char const* GetConfigName() const override {return "Fixture";}
    bool Prepare(std::vector<Player*> const&) override {++prepares;return prepareResult;}
    std::string GetWarningText(uint32) const override {return "warning";}
    std::string GetStartText() const override {return "started";}
    std::string GetEndText(bool) const override {return "ended";}
    bool IsEventArea(uint32 map,uint32 zone,uint32 area) const override {return map==0&&zone==1519&&area==77;}
    bool Start() override {++starts;return startResult;}
    void Update(uint32) override {++updates;}
    void OnStop() override {++stops;}
    void Win() {MarkWon();} void Reward() {RewardNow();}
};
EVENT_TIERS
struct ZombieCheck {
    Creature* anchor=nullptr; Creature* GetAnchor() {return anchor;}
    ZOMBIE_CHECK
};
}
namespace Acore {
struct AnyPlayerInObjectRangeCheck {AnyPlayerInObjectRangeCheck(Unit*,float) {}};
template<class Check> struct PlayerListSearcher {
    std::list<Player*>& players; PlayerListSearcher(Unit*,std::list<Player*>& out,Check const&) : players(out) {}
};
}
namespace Cell {
template<class Searcher> void VisitObjects(Unit*,Searcher& searcher,float) {
    for(auto [guid,player]:ObjectAccessor::GetPlayers()) if(player) searcher.players.push_back(player);
}
}
using namespace EraEvents;
struct Groan {
    Unit* caster=nullptr; Unit* GetCaster() {return caster;}
    GROAN_METHOD
};
enum DamageEffectType {DIRECT_DAMAGE,OTHER_DAMAGE}; using SpellSchoolMask=int;
// A successful native roll lets the fixture exercise the guarded melee effect.
bool roll_chance_i(uint8 chance) {return chance>0;}
namespace EraEvents {
std::map<uint32,MobDef> mobDefinitions;
void RegisterMob(uint32 entry,MobDef definition) {mobDefinitions[entry]=std::move(definition);}
MobDef const* FindMob(uint32 entry) {return &mobDefinitions.at(entry);}
}
struct Melee {
    MobDef const* _def=FindMob(NPC_PLAGUE_ZOMBIE); Creature creature; Creature* me=&creature;
    MELEE
};
constexpr int PLAYERHOOK_ON_LOGIN=1,PLAYERHOOK_ON_BEFORE_LOGOUT=2;
class PlayerScript;
std::vector<PlayerScript*> registeredPlayers;
struct PlayerScript {
    std::vector<int> hooks;
    PlayerScript(char const*,std::vector<int> value):hooks(std::move(value)) {registeredPlayers.push_back(this);}
    virtual ~PlayerScript()=default;
    virtual void OnPlayerLogin(Player*) {} virtual void OnPlayerBeforeLogout(Player*) {}
};
struct GameObjectAI {
    GameObject* me;
    explicit GameObjectAI(GameObject* object):me(object) {} virtual ~GameObjectAI()=default;
    virtual bool GossipHello(Player*,bool) {return true;}
};
uint32 objectUses=0;
namespace EraEvents {void NotifyObjectUsed(GameObject*) {++objectUses;}}
CRATE
ZOMBIE_PLAYER
uint32 registeredGroans=0,registeredCrates=0;
#define RegisterSpellScript(...) (++registeredGroans)
#define RegisterGameObjectAI(...) (++registeredCrates)
ZOMBIE_REGISTRATION
'''

tests = r'''
using namespace EraEvents;
void Mark(Player& player,uint8 stage,uint32 status=QUEST_STATUS_REWARDED) {
    player.quests.clear();if(stage)player.quests[66000+stage]=status;
}
void Reset() {
    ObjectAccessor::players.clear();configMgr.values.clear();progression={};
    configMgr.values["IndividualProgression.Enable"]=1;
    manager=Manager{};LoadConfig();GameTime::now=1000;objectUses=0;
    manager._slots[EVENT_AQ_WAR].event=std::make_unique<AQEvent>();
    manager._slots[EVENT_SCOURGE_INVASION].event=std::make_unique<ScourgeEvent>();
    manager._slots[EVENT_LEGION_INCURSION].event=std::make_unique<LegionEvent>();
    manager._slots[EVENT_ZOMBIE_INFESTATION].event=std::make_unique<ZombieEvent>();
}
FixtureEvent& Event(EventType type) {return static_cast<FixtureEvent&>(*manager._slots[type].event);}
bool Participates(Player& player,EventType type) {return IsEventParticipant(&player,type);}
void EarnedStagesAndPhases() {
    for(int ceiling:{0,1,4,6,7,8,12,13,18}) for(uint8 stage=0;stage<=18;++stage) {
        Reset();progression.progressionLimit=ceiling;config.ipLimit=ceiling;
        Player player;Mark(player,stage);auto quests=player.quests;
        for(auto& slot:manager._slots) slot.state=State::Running;
        uint8 expected=ceiling>0&&stage>ceiling?uint8(ceiling):stage;
        assert(GetPlayerTier(&player)==expected);
        manager.UpdatePlayerPhases(&player,player.zone,player.area);
        for(auto& slot:manager._slots) {
            auto type=slot.event->GetType();bool eligible=expected==slot.event->GetTier();
            assert(Participates(player,type)==eligible);
            assert(player.HasAura(slot.event->GetPhaseSpell())==eligible);
        }
        assert(player.quests==quests&&player.money==12345&&player.itemGrants==0);
    }
    Reset();Player player;Mark(player,12);
    for(uint32 status:{0u,1u,2u,3u,4u,5u,QUEST_STATUS_REWARDED}) {
        Mark(player,12,status);assert(GetPlayerTier(&player)==(status==QUEST_STATUS_REWARDED?12:0));
    }
    player.quests={{66004,QUEST_STATUS_REWARDED},{66012,QUEST_STATUS_REWARDED},{66018,QUEST_STATUS_REWARDED}};
    assert(GetPlayerTier(&player)==18);
    player.inWorld=false;assert(GetPlayerTier(&player)==255);assert(GetPlayerTier(nullptr)==255);
}
void MembershipGatesAndCleanup() {
    for(uint32 state=0;state<12;++state) {
        Reset();Player player;Mark(player,12);auto& slot=manager._slots[EVENT_ZOMBIE_INFESTATION];
        slot.state=State::Running;ObjectAccessor::players[1]=&player;
        player.auras={EVENT_PHASE_SPELLS[EVENT_ZOMBIE_INFESTATION],43958,43869,44281};
        switch(state) {
            case 0: slot.state=State::Idle;break;
            case 1: slot.state=State::Warning;break;
            case 2: player.map=1;break;
            case 3: player.zone=1637;break;
            case 4: player.area=99;break;
            case 5: Mark(player,13);break;
            case 6: config.enabled=false;break;
            case 7: config.events[EVENT_ZOMBIE_INFESTATION].enabled=false;break;
            case 8: config.ipEnabled=false;break;
            case 9: progression.enabled=false;break;
            case 10: progression.disableDefaultProgression=true;break;
            case 11: progression.customProgressionMap[123]=12;break;
        }
        assert(!Participates(player,EVENT_ZOMBIE_INFESTATION));
        manager.UpdatePlayerPhases(&player,player.zone,player.area);
        assert(player.auras.empty());
    }
    Reset();Player player;Mark(player,12);
    manager._slots[EVENT_ZOMBIE_INFESTATION].state=State::Running;
    progression.strictEarnedProgression=false;
    assert(GetPlayerTier(&player)==255&&!Participates(player,EVENT_ZOMBIE_INFESTATION));
    progression.strictEarnedProgression=true;player.inWorld=false;
    assert(!Participates(player,EVENT_ZOMBIE_INFESTATION));
    assert(!IsEventParticipant(nullptr,EVENT_ZOMBIE_INFESTATION));
    player.inWorld=true;manager._slots[EVENT_ZOMBIE_INFESTATION].event.reset();
    assert(!Participates(player,EVENT_ZOMBIE_INFESTATION));
}
void HumanPopulationAndBots() {
    Reset();Player human,altbot,selfbot,random,gm,offline,noSession;
    for(auto* player:{&human,&altbot,&selfbot,&random,&gm,&offline,&noSession}) Mark(*player,4);
    altbot.session.headless=true;random.session.headless=true;gm.gm=true;offline.inWorld=false;noSession.hasSession=false;
    ObjectAccessor::players={{1,&human},{2,&altbot},{3,&selfbot},{4,&random},{5,&gm},{6,&offline},{7,&noSession},{8,nullptr}};
    auto population=manager.GetCohort(4,true);
    assert((population==std::vector<Player*>{&human,&selfbot}));
    auto participants=manager.GetCohort(4,false);
    assert(participants.size()==6&&std::find(participants.begin(),participants.end(),&random)!=participants.end());
    auto& slot=manager._slots[EVENT_AQ_WAR];slot.timer=0;config.minRealPlayers=3;
    manager.UpdateSlot(slot,1);assert(slot.state==State::Idle&&Event(EVENT_AQ_WAR).prepares==0);
    config.minRealPlayers=2;config.events[EVENT_AQ_WAR].warning=0;
    manager.UpdateSlot(slot,uint32(slot.timer));
    assert(slot.state==State::Running&&Event(EVENT_AQ_WAR).starts==1);
    assert(random.HasAura(EVENT_PHASE_SPELLS[EVENT_AQ_WAR]));
    assert(altbot.HasAura(EVENT_PHASE_SPELLS[EVENT_AQ_WAR]));
    assert(!offline.HasAura(EVENT_PHASE_SPELLS[EVENT_AQ_WAR]));
}
void StrictSettingsAndRewards() {
    Reset();
    for(char const* name:{"AQWar","ScourgeInvasion","LegionIncursion","ZombieInfestation"}) {
        std::string prefix=std::string("EraEvents.")+name+".";
        for(char const* key:{"RealmWideMinutes","RewardGold","RewardFaction","RewardReputation","RewardItem","RewardItemCount"})
            configMgr.values[prefix+key]=99;
    }
    // The module's config hook runs before IP has initialized its strict mode.
    progression.strictEarnedProgression=false;LoadConfig();progression.strictEarnedProgression=true;
    for(auto const& settings:config.events) {
        assert(settings.realmWide==0&&settings.rewardGold==0&&settings.rewardFaction==0);
        assert(settings.rewardReputation==0&&settings.rewardItem==0&&settings.rewardItemCount==0);
    }
    Player player;Mark(player,4);ObjectAccessor::players[1]=&player;
    auto& slot=manager._slots[EVENT_AQ_WAR];std::string error;
    assert(!manager.ForceStart(slot,error,true));assert(Event(EVENT_AQ_WAR).starts==0);
    assert(manager.ForceStart(slot,error));assert(player.HasAura(EVENT_PHASE_SPELLS[EVENT_AQ_WAR]));
    Event(EVENT_AQ_WAR).Reward();manager.UpdateSlot(slot,1);
    Event(EVENT_AQ_WAR).Win();manager.UpdateSlot(slot,1);
    assert(player.money==12345&&player.itemGrants==0&&player.reputation.calls==0&&player.quests.size()==1);
    assert(slot.state==State::Idle&&!player.HasAura(EVENT_PHASE_SPELLS[EVENT_AQ_WAR]));
}
void ReloadAndScheduledStart() {
    for(State state:{State::Warning,State::Running}) for(uint32 gate=0;gate<5;++gate) {
        Reset();Player player;Mark(player,12);ObjectAccessor::players[1]=&player;
        auto& slot=manager._slots[EVENT_ZOMBIE_INFESTATION];slot.state=state;slot.timer=1000;
        player.auras={EVENT_PHASE_SPELLS[EVENT_ZOMBIE_INFESTATION],43958,43869,44281};
        switch(gate) {
            case 0:configMgr.values["EraEvents.Enable"]=0;break;
            case 1:configMgr.values["EraEvents.ZombieInfestation.Enable"]=0;break;
            case 2:configMgr.values["IndividualProgression.Enable"]=0;break;
            case 3:progression.customProgressionMap[123]=12;break;
            case 4:configMgr.values["IndividualProgression.ProgressionLimit"]=7;progression.progressionLimit=7;break;
        }
        LoadConfig();manager.UpdateSlot(slot,1);
        assert(slot.state==State::Idle&&Event(EVENT_ZOMBIE_INFESTATION).updates==0);
        assert(Event(EVENT_ZOMBIE_INFESTATION).stops==1&&player.auras.empty());
        std::string error;assert(!manager.ForceStart(slot,error));
        assert(Event(EVENT_ZOMBIE_INFESTATION).starts==0);
    }
    Reset();Player player;Mark(player,6);ObjectAccessor::players[1]=&player;
    auto& slot=manager._slots[EVENT_SCOURGE_INVASION];config.minRealPlayers=1;slot.timer=0;
    manager.UpdateSlot(slot,1);assert(slot.state==State::Warning);
    manager.UpdateSlot(slot,uint32(slot.timer)-1);assert(slot.state==State::Warning);
    manager.UpdateSlot(slot,1);assert(slot.state==State::Running&&player.HasAura(EVENT_PHASE_SPELLS[EVENT_SCOURGE_INVASION]));
    Mark(player,7);manager.UpdatePlayerPhases(&player,player.zone,player.area);
    assert(!player.HasAura(EVENT_PHASE_SPELLS[EVENT_SCOURGE_INVASION]));
}
void ZombieParticipantsAndEffects() {
    for(uint32 state=0;state<9;++state) {
        Reset();Player target;Mark(target,12);
        auto& slot=manager._slots[EVENT_ZOMBIE_INFESTATION];slot.state=State::Running;
        switch(state) {
            case 1:Mark(target,13);break;
            case 2:target.zone=1637;break;
            case 3:slot.state=State::Idle;break;
            case 4:config.enabled=false;break;
            case 5:target.gm=true;break;
            case 6:target.alive=false;break;
            case 7:target.AddAura(SPELL_YOURE_A_ZOMBIE,&target);break;
            case 8:target.session.headless=true;break;
        }
        Infect(&target);
        assert(target.HasAura(SPELL_YOURE_INFECTED)==(state==0||state==8));
    }
    Reset();Player caster,target,bystander;Mark(caster,12);Mark(target,12);Mark(bystander,13);
    manager._slots[EVENT_ZOMBIE_INFESTATION].state=State::Running;
    ObjectAccessor::players={{1,&caster},{2,&target},{3,&bystander}};
    caster.AddAura(SPELL_YOURE_A_ZOMBIE,&caster);Groan groan;groan.caster=&caster;
    Mark(caster,13);groan.HandleAfterCast();assert(!target.HasAura(SPELL_YOURE_INFECTED));
    Mark(caster,12);groan.HandleAfterCast();
    assert(target.HasAura(SPELL_YOURE_INFECTED)&&!bystander.HasAura(SPELL_YOURE_INFECTED));
    assert(!caster.HasAura(SPELL_YOURE_INFECTED));
    target.RemoveAurasDueToSpell(SPELL_YOURE_INFECTED);
    Melee melee;uint32 damage=1;
    melee.DamageDealt(&bystander,damage,DIRECT_DAMAGE,0);assert(!bystander.HasAura(SPELL_YOURE_INFECTED));
    melee.DamageDealt(&target,damage,OTHER_DAMAGE,0);assert(!target.HasAura(SPELL_YOURE_INFECTED));
    melee.DamageDealt(&target,damage,DIRECT_DAMAGE,0);assert(target.HasAura(SPELL_YOURE_INFECTED));
    GameObject crate;go_era_plagued_crate ai(&crate);
    ai.GossipHello(&bystander,false);assert(crate.spawned&&objectUses==0);
    ai.GossipHello(&target,false);assert(!crate.spawned&&objectUses==1);
}
void ZombieTimerAndLifecycle() {
    Reset();Player player;Mark(player,12);ObjectAccessor::players[1]=&player;
    manager._slots[EVENT_ZOMBIE_INFESTATION].state=State::Running;
    ZombieCheck check;Infect(&player);
    GameTime::now+=59;check.CheckPlayers();
    assert(player.HasAura(SPELL_YOURE_INFECTED)&&!player.HasAura(SPELL_YOURE_A_ZOMBIE));
    // Reinfection receives a new native aura timestamp, without old elapsed state.
    player.RemoveAurasDueToSpell(SPELL_YOURE_INFECTED);Infect(&player);
    GameTime::now+=1;check.CheckPlayers();assert(!player.HasAura(SPELL_YOURE_A_ZOMBIE));
    GameTime::now+=59;check.CheckPlayers();
    assert(!player.HasAura(SPELL_YOURE_INFECTED)&&player.HasAura(SPELL_YOURE_A_ZOMBIE)&&player.HasAura(SPELL_ZOMBIE_FACTION));
    assert(player.GetAura(SPELL_YOURE_A_ZOMBIE)->duration==180000&&player.GetAura(SPELL_ZOMBIE_FACTION)->duration==180000);
    Mark(player,13);check.CheckPlayers();assert(player.auras.empty());
    Mark(player,12);Infect(&player);player.alive=false;check.CheckPlayers();assert(player.auras.empty());
    player.alive=true;Infect(&player);Creature anchor,healer;healer.near=true;
    anchor.healers={&healer};check.anchor=&anchor;check.CheckPlayers();assert(player.auras.empty()&&healer.heals==1);
    assert(registeredPlayers.size()==1&&registeredGroans==1&&registeredCrates==1);
    auto& script=*registeredPlayers[0];
    assert((script.hooks==std::vector<int>{PLAYERHOOK_ON_LOGIN,PLAYERHOOK_ON_BEFORE_LOGOUT}));
    player.auras={SPELL_YOURE_INFECTED,SPELL_YOURE_A_ZOMBIE,SPELL_ZOMBIE_FACTION};
    script.OnPlayerBeforeLogout(&player);assert(player.auras.empty());
    player.auras={SPELL_YOURE_INFECTED,SPELL_YOURE_A_ZOMBIE,SPELL_ZOMBIE_FACTION};
    script.OnPlayerLogin(&player);assert(player.auras.empty());
    ClearZombieInfection(nullptr);
}
int main() {
    AddEraEventZombieScripts();
    EarnedStagesAndPhases();MembershipGatesAndCleanup();HumanPopulationAndBots();StrictSettingsAndRewards();ReloadAndScheduledStart();
    ZombieParticipantsAndEffects();ZombieTimerAndLifecycle();
    for(auto* script:registeredPlayers) delete script;
    std::cout<<"Era Events: native stages, strict phases/rewards, population, reload and zombie infection/lifecycle passed\n";
}
'''


def build(directory, executable):
    return [cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-g', '-O1',
            *SANITIZER_FLAGS, '-no-pie',
            '-I', str(directory), str(directory / 'fixture.cpp'), '-o', str(executable)]


with tempfile.TemporaryDirectory(prefix='portable-era-events-') as temporary:
    work = Path(temporary)
    for name in ('Define.h', 'ObjectGuid.h', 'Position.h'):
        (work / name).write_text('#pragma once\n')
    (work / 'EraEvents.h').write_text(header)
    (work / 'EraEventMobs.h').write_text((module / 'src/EraEventMobs.h').read_text())
    source = stub.replace('NATIVE_IP', native).replace('SETTINGS', settings).replace('SESSION_HELPERS', helpers)
    source = source.replace('MANAGER_METHODS', methods).replace('SHARED_METHODS', shared)
    source = source.replace('EVENT_TIERS', '\n'.join(tiers)).replace('ZOMBIE_SHARED', zombie_shared)
    source = source.replace('ZOMBIE_CHECK', zombie_check).replace('GROAN_METHOD', groan).replace('MELEE', melee)
    source = source.replace('\nCRATE\n', '\n' + crate + '\n').replace('ZOMBIE_PLAYER', zombie_player) + tests
    source = source.replace('ZOMBIE_REGISTRATION', zombie_registration)
    (work / 'fixture.cpp').write_text(source)
    executable = work / 'fixture'
    subprocess.run(build(work, executable), check=True)
    result = run_fixture([str(executable)])
    print(result.stdout + result.stderr, end='')
    assert result.returncode == 0
    reject_mutants(work, (
        ('own-earned-tier', 'fixture.cpp', 'GetPlayerTier(player) == slot.event->GetTier()', 'true'),
        ('active-event', 'fixture.cpp', 'slot.state == State::Running &&', 'true &&'),
        ('event-area', 'fixture.cpp', 'slot.event->IsEventArea(player->GetMapId(), zoneId, areaId)', '(void(zoneId), void(areaId), true)'),
        ('realm-ceiling', 'fixture.cpp', 'state = uint8(std::min<int>(state, sIndividualProgression->progressionLimit));', 'state = state;'),
        ('strict-default', 'fixture.cpp', '!sIndividualProgression->IsStrictDefaultProgression()', 'false'),
        ('headless-population', 'fixture.cpp', 'return session->IsHeadless();', 'return false;'),
        ('passive-rewards', 'fixture.cpp', 's.rewardGold = 0;', ''),
        ('realm-wide-clamp', 'fixture.cpp', 's.realmWide = 0;', ''),
        ('reload-stop', 'fixture.cpp', 'if (!IsAvailable(event))\n                {\n                    if (slot.state != State::Idle)', 'if (false)\n                {\n                    if (slot.state != State::Idle)'),
        ('start-recheck', 'fixture.cpp', 'if (!IsAvailable(event))\n                    return false;', 'if (false)\n                    return false;'),
        ('infection-target', 'fixture.cpp', '!IsEventParticipant(player, EVENT_ZOMBIE_INFESTATION) || player->IsGameMaster()', 'player->IsGameMaster()'),
        ('groan-caster', 'fixture.cpp', '!IsEventParticipant(caster->ToPlayer(), EVENT_ZOMBIE_INFESTATION)', 'false'),
        ('melee-target', 'fixture.cpp', 'if (!IsEventParticipant(victim->ToPlayer(), EVENT_ZOMBIE_INFESTATION))', 'if (false)'),
        ('infection-elapsed', 'fixture.cpp', 'GameTime::GetGameTime().count() - infection->GetApplyTime() < INFECTION_MS / IN_MILLISECONDS', '(void(infection), false)'),
        ('plague-logout', 'fixture.cpp', 'void OnPlayerBeforeLogout(Player* player) override\n    {\n        ClearZombieInfection(player);',
         'void OnPlayerBeforeLogout(Player* player) override\n    {\n        (void)player;'),
        ('plague-login', 'fixture.cpp', 'void OnPlayerLogin(Player* player) override\n    {\n        ClearZombieInfection(player);',
         'void OnPlayerLogin(Player* player) override\n    {\n        (void)player;'),
    ), build, 'Era Events')
