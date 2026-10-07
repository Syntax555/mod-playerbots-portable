"""Check earned historical talents with isolated production-code fixtures.

Requires PrepareModules.cmake and a C++20 compiler. No realm or database is started.
The fixtures execute production era/point policy and the ordered persistence queue;
real-header compilation and release builds separately check integration with the core.
"""

import argparse
from pathlib import Path
import subprocess
import tempfile

from PreparedSources import prepared_core

repo = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--module-source', type=Path,
                    default=prepared_core(repo) / 'modules/mod-era-talents')
parser.add_argument('--core-source', type=Path, default=prepared_core(repo))
args = parser.parse_args()
module = args.module_source
src = module / 'src'
core = args.core_source


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def compile_run(directory, name, source, includes=()):
    cpp = directory / (name + '.cpp')
    binary = directory / name
    cpp.write_text(source)
    subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-no-pie', '-pthread',
                    *[flag for include in includes for flag in ('-I', str(include))],
                    str(cpp), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)


with tempfile.TemporaryDirectory(prefix='portable-era-talents-') as temporary:
    directory = Path(temporary)
    era_policy = function((src / 'EraTalentIP.cpp').read_text(), 'EraId EraFromIP(')
    points = function((src / 'EraTalents.cpp').read_text(), '    int AvailablePoints(')
    policy_fixture = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <iostream>
using uint8=uint8_t; using uint32=uint32_t;
enum EraId : uint8 { ERA_VANILLA=0, ERA_TBC=1, ERA_WOTLK=2 };
constexpr uint8 PROGRESSION_NAXX40=7, PROGRESSION_TBC_TIER_4=12;
struct Player {
    uint8 stage=0, level=1; int spent=0; bool bot=false;
    uint8 GetLevel() const { return level; }
};
struct Progression { uint8 GetPlayerProgressionFromQuests(Player* p) const { return p->stage; } } progression;
auto* sIndividualProgression=&progression;
''' + era_policy + r'''
namespace EraTalents {
int SpentPoints(Player* p, EraId) { return p->spent; }
''' + points + r'''
}
int main() {
    Player human, bot; bot.bot=true;
    for (uint8 stage=0; stage<=18; ++stage) {
        human.stage=bot.stage=stage;
        EraId expected=stage<=7 ? ERA_VANILLA : stage<=12 ? ERA_TBC : ERA_WOTLK;
        for (uint8 level : {1,10,60,70,80}) {
            human.level=bot.level=level;
            assert(EraFromIP(&human)==expected && EraFromIP(&bot)==expected);
        }
    }
    assert(EraFromIP(nullptr)==ERA_WOTLK);
    for (int level=1; level<=80; ++level) {
        human.level=level;
        for (EraId era : {ERA_VANILLA,ERA_TBC,ERA_WOTLK}) {
            int earned=std::max(0,level-9);
            if (era==ERA_VANILLA) earned=std::min(earned,51);
            if (era==ERA_TBC) earned=std::min(earned,61);
            for (int spent : {0,1,20,51,61,71,255}) {
                human.spent=spent;
                assert(EraTalents::AvailablePoints(&human,era)==std::max(0,earned-spent));
            }
        }
    }
    std::cout << "Era talents: earned tier selects era independently of level; point budgets passed\n";
}
'''
    compile_run(directory, 'era-policy', policy_fixture)

    fake = directory / 'fake'
    fake.mkdir()
    (fake / 'DatabaseEnv.h').write_text(r'''
#pragma once
#include <cassert>
#include <chrono>
#include <deque>
#include <functional>
#include <future>
#include <memory>
#include <string>
#include <utility>
#include <vector>
struct Transaction {
    std::vector<std::string> statements;
    void Append(std::string const& value) { statements.push_back(value); }
};
using CharacterDatabaseTransaction=std::shared_ptr<Transaction>;
struct TransactionCallback {
    std::future<bool> m_future;
    std::function<void(bool)> m_callback;
    explicit TransactionCallback(std::future<bool>&& future) : m_future(std::move(future)) {}
    TransactionCallback(TransactionCallback&&)=default;
    void AfterComplete(std::function<void(bool)> callback) & { m_callback=std::move(callback); }
    bool InvokeIfReady() {
        if (m_future.wait_for(std::chrono::seconds(0))!=std::future_status::ready) return false;
        bool success=m_future.get(); m_callback(success); return true;
    }
};
struct Database {
    struct Pending { CharacterDatabaseTransaction transaction; std::promise<bool> promise; };
    std::deque<Pending> pending;
    std::vector<std::vector<std::string>> attempts;
    std::vector<std::string> committed;
    bool immediate=false, success=true;
    CharacterDatabaseTransaction BeginTransaction() { return std::make_shared<Transaction>(); }
    TransactionCallback AsyncCommitTransaction(CharacterDatabaseTransaction transaction) {
        attempts.push_back(transaction->statements);
        assert(transaction->statements.size()<=200); // at most 100 two-statement snapshots
        std::promise<bool> promise; auto future=promise.get_future();
        if (immediate) {
            if (success) committed.insert(committed.end(),transaction->statements.begin(),transaction->statements.end());
            promise.set_value(success);
        } else {
            assert(pending.empty()); // a later batch must never overtake an in-flight batch
            pending.push_back({transaction,std::move(promise)});
        }
        return TransactionCallback(std::move(future));
    }
    void Complete(bool success) {
        assert(pending.size()==1);
        Pending& first=pending.front();
        if (success) committed.insert(committed.end(),first.transaction->statements.begin(),first.transaction->statements.end());
        first.promise.set_value(success); pending.pop_front();
    }
} CharacterDatabase;
''')
    (fake / 'Transaction.h').write_text('#pragma once\n#include "DatabaseEnv.h"\n')
    (fake / 'Log.h').write_text('#pragma once\n#define LOG_ERROR(...) ((void)0)\n')
    persistence = '#include "' + str(src / 'EraPersistence.cpp') + '"\n' + r'''
#include <algorithm>
#include <cassert>
#include <iostream>
#include <thread>
#include <vector>
int main() {
    EraPersistence::Queue({}); EraPersistence::Update();
    assert(CharacterDatabase.attempts.empty());
    EraPersistence::Queue({"earned-rank-1"}); EraPersistence::Update();
    assert(CharacterDatabase.attempts.size()==1);
    EraPersistence::Queue({"paid-reset","earned-rank-2"});
    for (int i=0;i<50;++i) EraPersistence::Update();
    assert(CharacterDatabase.attempts.size()==1 && CharacterDatabase.committed.empty());
    CharacterDatabase.Complete(false); EraPersistence::Update();
    assert(CharacterDatabase.attempts.size()==1); // failed DB work backs off instead of hammering every tick
    g_retryAfter={}; EraPersistence::Update(); // fixture advances the retry deadline without sleeping
    assert(CharacterDatabase.attempts.back()==std::vector<std::string>({"earned-rank-1","paid-reset","earned-rank-2"}));
    CharacterDatabase.Complete(true); EraPersistence::Update();
    assert(CharacterDatabase.committed==std::vector<std::string>({"earned-rank-1","paid-reset","earned-rank-2"}));
    assert(CharacterDatabase.pending.empty());

    CharacterDatabase.attempts.clear(); CharacterDatabase.committed.clear();
    for (int i=0;i<205;++i) EraPersistence::Queue({std::to_string(i)});
    EraPersistence::Update();
    assert(CharacterDatabase.attempts.back().size()==100);
    CharacterDatabase.Complete(true); EraPersistence::Update();
    assert(CharacterDatabase.attempts.back().size()==100);
    CharacterDatabase.Complete(true); EraPersistence::Update();
    assert(CharacterDatabase.attempts.back().size()==5);
    CharacterDatabase.Complete(true); EraPersistence::Update();
    assert(CharacterDatabase.pending.empty() && CharacterDatabase.committed.size()==205);
    for (int i=0;i<205;++i) assert(CharacterDatabase.committed[i]==std::to_string(i));

    CharacterDatabase.committed.clear();
    std::vector<std::thread> workers;
    for (int player=0;player<16;++player) workers.emplace_back([player] {
        for (int mutation=0;mutation<20;++mutation) {
            std::string id=std::to_string(player)+":"+std::to_string(mutation);
            EraPersistence::Queue({id+"-reset",id+"-learn"});
        }
    });
    for (auto& worker : workers) worker.join();
    CharacterDatabase.immediate=true; EraPersistence::Flush();
    assert(CharacterDatabase.committed.size()==640);
    for (size_t i=0;i<CharacterDatabase.committed.size();i+=2) {
        std::string const& reset=CharacterDatabase.committed[i];
        std::string const& learn=CharacterDatabase.committed[i+1];
        assert(reset.substr(0,reset.size()-6)==learn.substr(0,learn.size()-6));
        assert(reset.ends_with("-reset") && learn.ends_with("-learn"));
    }
    // A failed shutdown flush retains the earned snapshot for a later retry.
    CharacterDatabase.success=false; EraPersistence::Queue({"last-earned-change"});
    EraPersistence::Flush();
    assert(CharacterDatabase.committed.back()!="last-earned-change");
    CharacterDatabase.success=true; EraPersistence::Flush();
    assert(CharacterDatabase.committed.back()=="last-earned-change");
    EraPersistence::Update(); assert(CharacterDatabase.pending.empty());
    std::cout << "Era persistence: one async batch, ordered failure retry, bounded batches, concurrent snapshots and shutdown flush passed\n";
}
'''
    compile_run(directory, 'era-persistence', persistence, (fake,))

    player_core = (core / 'src/server/game/Entities/Player/Player.cpp').read_text()
    reset_cost = function(player_core, 'uint32 Player::resetTalentsCost(')
    record_reset = function(player_core, 'void Player::RecordTalentReset(')
    complete_reset = function(player_core, 'void Player::CompleteCustomTalentReset(')
    native_reset = function(player_core, 'bool Player::resetTalents(')
    native_reset = native_reset[:native_reset.index('    // xinef: get max available talent points amount')] + '    ++nativeFalls;\n    return false;\n}'
    reset_hook = function((src / 'EraTalentPin.cpp').read_text(), '    void OnPlayerTalentsReset(')
    native_gate = function((src / 'EraTalentPin.cpp').read_text(), '    bool OnPlayerCanLearnTalent(')
    reset_fixture = r'''
#include <algorithm>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <string>
using uint8=uint8_t; using uint32=uint32_t; using uint64=uint64_t; using int32=int32_t;
constexpr int GOLD=10000, MONTH=30*24*60*60;
constexpr int CONFIG_NO_RESET_TALENT_COST=0, BUY_ERR_NOT_ENOUGHT_MONEY=1, AT_LOGIN_RESET_TALENTS=2;
constexpr int ACHIEVEMENT_CRITERIA_TYPE_GOLD_SPENT_FOR_TALENTS=2,
    ACHIEVEMENT_CRITERIA_TYPE_NUMBER_OF_TALENT_RESETS=3;
enum EraId : uint8 { ERA_VANILLA=0, ERA_TBC=1, ERA_WOTLK=2 };
namespace GameTime { int64_t now=1700000000; std::chrono::seconds GetGameTime() { return std::chrono::seconds(now); } }
struct TalentEntry {};
struct Player {
    uint32 m_resetTalentsCost=0; int64_t m_resetTalentsTime=0;
    int64_t money=100*GOLD; uint32 level=60; EraId era=ERA_VANILLA, stored=ERA_VANILLA;
    int spent=51, goldCriteria=0, resetsCriteria=0, errors=0, visuals=0, syncs=0, nativeSpent=0;
    uint8 cls=1; bool enabled=true, bot=false, combat=false, internalReset=false;
    uint32 resetTalentsCost() const;
    void RecordTalentReset(uint32);
    void CompleteCustomTalentReset();
    bool resetTalents(bool);
    bool m_customTalentsResetCompleted=false; int nativeFalls=0;
    bool HasAtLoginFlag(int) const { return false; }
    void RemoveAtLoginFlag(int,bool) { assert(false); }
    bool HasEnoughMoney(uint32 value) const { return money>=value; }
    void ModifyMoney(int32 value) { money+=value; assert(money>=0); }
    void SendBuyError(int code, int, int, int) { assert(code==BUY_ERR_NOT_ENOUGHT_MONEY); ++errors; }
    void UpdateAchievementCriteria(int criteria, uint32 value) {
        if (criteria==ACHIEVEMENT_CRITERIA_TYPE_GOLD_SPENT_FOR_TALENTS) goldCriteria+=value;
        else { assert(criteria==ACHIEVEMENT_CRITERIA_TYPE_NUMBER_OF_TALENT_RESETS); resetsCriteria+=value; }
    }
    bool IsInCombat() const { return combat; }
    void CastSpell(Player* target, int id, bool triggered) {
        assert(target==this && id==14867 && triggered); ++visuals;
    }
};
struct World { bool noCost=false; bool getBoolConfig(int key) const { assert(key==0); return noCost; } } world;
auto* sWorld=&world;
bool EnabledFor(Player* p) { return p && p->enabled; }
EraId EraFromIP(Player* p) { return p->era; }
bool EraHasTalentTrees(Player* p, EraId e) { return p->cls!=6 && e!=ERA_WOTLK; }
namespace EraTalentBots {
    bool IsEraManaged(Player* p) {
        return p && p->enabled && (EraHasTalentTrees(p,p->era)||EraHasTalentTrees(p,p->stored));
    }
}
namespace EraTransition {
    bool NativeResetActive(Player* p) { return p->internalReset; }
    EraId StoredEra(Player* p) { return p->stored; }
    void StripNativeTalents(Player* p, EraId) { p->nativeSpent=0; }
}
namespace EraTalents {
    int SpentPoints(Player* p, EraId) { return p->spent; }
    void Reset(Player* p, EraId) { p->spent=0; }
}
namespace EraTalentsComms { void SendSync(Player* p) { ++p->syncs; } }
struct PlayerScript {
    virtual ~PlayerScript()=default;
    virtual void OnPlayerTalentsReset(Player*,bool) {}
    virtual bool OnPlayerCanLearnTalent(Player*,TalentEntry const*,uint32) { return true; }
};
''' + reset_cost + '\n' + record_reset + r'''
struct ResetHook : PlayerScript {
''' + reset_hook + '\n' + native_gate + r'''
} hook;
struct ScriptMgr { void OnPlayerTalentsReset(Player* p,bool noCost) { hook.OnPlayerTalentsReset(p,noCost); } } scriptMgr;
auto* sScriptMgr=&scriptMgr;
''' + complete_reset + '\n' + native_reset + r'''
int main() {
    Player p;
    for (uint32 expected : {1u,5u,10u,15u,20u,25u,30u,35u,40u,45u,50u,50u}) {
        assert(p.resetTalentsCost()==expected*GOLD);
        p.RecordTalentReset(expected*GOLD);
        assert(p.m_resetTalentsCost==expected*GOLD && p.m_resetTalentsTime==GameTime::now);
    }
    assert(p.resetsCriteria==12 && p.goldCriteria==326*GOLD);
    p.m_resetTalentsCost=30*GOLD; p.m_resetTalentsTime=GameTime::now-MONTH;
    assert(p.resetTalentsCost()==25*GOLD);
    p.m_resetTalentsTime=GameTime::now-1000LL*MONTH;
    assert(p.resetTalentsCost()==10*GOLD); // elapsed reduction must not underflow persisted unsigned cost
    p.m_resetTalentsCost=40*GOLD; p.m_resetTalentsTime=GameTime::now+10LL*MONTH;
    assert(p.resetTalentsCost()==45*GOLD); // a future timestamp cannot manufacture monthly decay

    for (bool bot : {false,true}) {
        Player t; t.bot=bot; t.nativeSpent=40;
        t.resetTalents(false);
        assert(t.money==99*GOLD && t.spent==0 && t.nativeSpent==0);
        assert(t.m_resetTalentsCost==GOLD && t.resetsCriteria==1 && t.goldCriteria==GOLD);
        assert(t.visuals==0 && t.syncs==1 && !t.m_customTalentsResetCompleted && t.nativeFalls==0);
        t.resetTalents(false); // no allocated era points: no charge, no free new allocation
        assert(t.money==99*GOLD && t.resetsCriteria==1);
        t.spent=51; t.money=5*GOLD-1;
        t.resetTalents(false);
        assert(t.errors==1 && t.spent==51 && t.money==5*GOLD-1 && t.resetsCriteria==1);
        t.money=5*GOLD; t.resetTalents(false);
        assert(t.money==0 && t.spent==0 && t.m_resetTalentsCost==5*GOLD && t.resetsCriteria==2);
        t.spent=51; t.resetTalents(true);
        assert(t.spent==0 && t.money==0 && t.resetsCriteria==2); // explicit administrative no-cost reset
        t.spent=51; t.internalReset=true;
        t.resetTalents(true); assert(t.spent==51); // internal native teardown cannot erase the new era build
        t.internalReset=false; t.combat=true;
        t.resetTalents(false); assert(t.spent==51);
        t.combat=false; t.era=ERA_TBC; t.stored=ERA_VANILLA;
        t.resetTalents(false); assert(t.spent==51);
    }
    TalentEntry talent;
    Player t;
    assert(!hook.OnPlayerCanLearnTalent(&t,&talent,0)); // even a forged native learn packet is denied
    t.era=ERA_WOTLK;
    assert(!hook.OnPlayerCanLearnTalent(&t,&talent,0)); // historical passives still active during pending transition
    t.stored=ERA_WOTLK;
    assert(hook.OnPlayerCanLearnTalent(&t,&talent,0));
    t.era=t.stored=ERA_VANILLA; t.cls=6;
    assert(hook.OnPlayerCanLearnTalent(&t,&talent,0)); // existing class without authored historical trees is preserved
    t.cls=1; t.enabled=false;
    assert(hook.OnPlayerCanLearnTalent(&t,&talent,0));
    std::cout << "Era resets: native persisted price escalation/decay, future timestamps, real-money payment and native learn denial passed\n";
}
'''
    compile_run(directory, 'era-resets', reset_fixture)

    glyph_code = '\n'.join(line for line in (src / 'EraGlyphGate.cpp').read_text().splitlines()
                            if not line.startswith('#include'))
    glyph_fixture = r'''
#include <array>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <map>
#include <set>
using uint8=uint8_t; using uint32=uint32_t;
constexpr uint8 MAX_GLYPH_SLOT_INDEX=6, CLASS_DEATH_KNIGHT=6;
constexpr int PLAYER_FIELD_GLYPHS_1=0, ITEM_CLASS_GLYPH=16, EQUIP_ERR_CANT_DO_RIGHT_NOW=1;
constexpr uint32 TRIGGERED_FULL_MASK=255, TRIGGERED_IGNORE_SHAPESHIFT=1, TRIGGERED_IGNORE_CASTER_AURASTATE=2;
using TriggerCastFlags=uint32; using InventoryResult=int;
enum EraId : uint8 { ERA_VANILLA=0, ERA_TBC=1, ERA_WOTLK=2 };
struct SpellInfo { uint32 Id; };
struct Aura { SpellInfo* trigger; SpellInfo const* GetTriggeredByAuraSpellInfo() const { return trigger; } };
struct Player;
struct WorldObject { virtual ~WorldObject()=default; virtual Player* ToPlayer() { return nullptr; } };
struct Unit : WorldObject { using AuraMap=std::map<int,Aura*>; };
struct GlyphPropertiesEntry { uint32 SpellId; uint32 TypeFlags; };
struct GlyphSlotEntry { uint32 TypeFlags; };
struct GlyphStore {
    std::map<uint32,GlyphPropertiesEntry> entries{{101,{301,0}},{102,{302,0}},{103,{303,1}}};
    GlyphPropertiesEntry const* LookupEntry(uint32 id) const {
        auto it=entries.find(id); return it==entries.end() ? nullptr : &it->second;
    }
} sGlyphPropertiesStore;
struct SlotStore { GlyphSlotEntry entry{0}; GlyphSlotEntry const* LookupEntry(uint32) const { return &entry; } } sGlyphSlotStore;
struct SpellMgr {
    std::map<uint32,SpellInfo> entries{{301,{301}},{302,{302}},{303,{303}}};
    SpellInfo const* GetSpellInfo(uint32 id) const {
        auto it=entries.find(id); return it==entries.end() ? nullptr : &it->second;
    }
} spells;
auto* sSpellMgr=&spells;
struct Player : Unit {
    uint8 cls=1, active=0; EraId era=ERA_VANILLA, stored=ERA_VANILLA;
    std::array<std::array<uint32,6>,2> glyphs{};
    std::array<uint32,6> visible{}; std::set<uint32> auras;
    AuraMap owned; int saves=0, casts=0, syncs=0;
    Player* ToPlayer() override { return this; }
    uint8 getClass() const { return cls; }
    uint32 GetGlyph(uint8 slot) const { return glyphs[active][slot]; }
    uint32 GetGlyphSlot(uint8) const { return 1; }
    uint32 GetUInt32Value(uint32 field) const { return visible[field]; }
    void SetUInt32Value(uint32 field,uint32 value) { visible[field]=value; }
    void SetGlyph(uint8 slot,uint32 glyph,bool save) { glyphs[active][slot]=glyph; visible[slot]=glyph; saves+=save; }
    bool HasAura(uint32 spell) const { return auras.contains(spell); }
    void CastSpell(Player* target,uint32 spell,TriggerCastFlags flags) {
        assert(target==this && !(flags & TRIGGERED_IGNORE_SHAPESHIFT)); ++casts; auras.insert(spell);
    }
    void RemoveAurasDueToSpell(uint32 spell) { auras.erase(spell); }
    AuraMap& GetOwnedAuras() { return owned; }
    void RemoveOwnedAura(AuraMap::iterator& it) { it=owned.erase(it); }
    void SendTalentsInfoData(bool pet) { assert(!pet); ++syncs; }
};
struct Config { bool enabled=true, glyphGate=true; bool Enabled() const { return enabled; } bool GlyphGate() const { return glyphGate; } } config;
auto* sEraTalentsConfig=&config;
namespace EraTalentBots { EraId EraFor(Player* p) { return p->era; } }
namespace EraTransition { EraId StoredEra(Player* p) { return p->stored; } }
struct ItemTemplate { int Class; };
struct SpellCastTargets {}; struct AuraEffect {};
struct Spell { WorldObject* caster; SpellInfo info; WorldObject* GetCaster() const { return caster; } SpellInfo const* GetSpellInfo() const { return &info; } };
struct PlayerScript {
    explicit PlayerScript(char const*) {}
    virtual ~PlayerScript()=default;
    virtual bool OnPlayerCanUseItem(Player*,ItemTemplate const*,InventoryResult&) { return true; }
    virtual void OnPlayerLogin(Player*) {}
    virtual void OnPlayerAfterSpecSlotChanged(Player*,uint8) {}
};
struct AllSpellScript {
    explicit AllSpellScript(char const*) {}
    virtual ~AllSpellScript()=default;
    virtual bool CanPrepare(Spell*,SpellCastTargets const*,AuraEffect const*) { return true; }
};
''' + glyph_code + r'''
int main() {
    era_glyph_gate hook; era_glyph_spell_gate spellHook;
    Player p; p.glyphs[0][0]=101; p.glyphs[1][0]=102;
    auto ownership=p.glyphs;
    p.visible[0]=101; p.auras.insert(301);
    SpellInfo source{301}, unrelated{999}; Aura triggered{&source}, other{&unrelated};
    p.owned={{1,&triggered},{2,&other}};
    hook.OnPlayerLogin(&p);
    assert(p.glyphs==ownership && p.saves==0 && p.visible[0]==0 && !p.HasAura(301));
    assert(p.owned.size()==1 && p.owned.begin()->second==&other);
    Spell glyph{&p,{301}}, normal{&p,{999}}; WorldObject npc; Spell nonPlayer{&npc,{301}};
    assert(!spellHook.CanPrepare(&glyph,nullptr,nullptr)); // shapeshift cannot reactivate a suppressed owned glyph
    assert(spellHook.CanPrepare(&normal,nullptr,nullptr) && spellHook.CanPrepare(&nonPlayer,nullptr,nullptr));
    ItemTemplate item{ITEM_CLASS_GLYPH}, sword{2}; InventoryResult result=0;
    assert(!hook.OnPlayerCanUseItem(&p,&item,result) && result==EQUIP_ERR_CANT_DO_RIGHT_NOW);
    assert(hook.OnPlayerCanUseItem(&p,&sword,result));

    p.active=1; p.visible[0]=102; p.auras.insert(302); // core applies the newly active spec first
    hook.OnPlayerAfterSpecSlotChanged(&p,1);
    assert(p.glyphs==ownership && p.saves==0 && p.visible[0]==0 && !p.HasAura(302));
    glyph.info.Id=302; assert(!spellHook.CanPrepare(&glyph,nullptr,nullptr));
    p.era=ERA_WOTLK; EraGlyphGate::StripIfDisallowed(&p);
    assert(p.visible[0]==0 && !p.HasAura(302)); // the earned crossing must settle before effects return
    p.stored=ERA_WOTLK; EraGlyphGate::StripIfDisallowed(&p);
    assert(p.visible[0]==102 && p.HasAura(302) && p.glyphs==ownership && p.saves==0);
    assert(spellHook.CanPrepare(&glyph,nullptr,nullptr) && hook.OnPlayerCanUseItem(&p,&item,result));
    int casts=p.casts; EraGlyphGate::StripIfDisallowed(&p); assert(p.casts==casts); // idempotent, no duplicate grants
    p.active=0; p.auras.clear(); p.visible[0]=101;
    hook.OnPlayerAfterSpecSlotChanged(&p,0);
    assert(p.visible[0]==101 && p.HasAura(301) && p.glyphs==ownership && p.saves==0);
    p.era=p.stored=ERA_TBC; EraGlyphGate::StripIfDisallowed(&p);
    assert(p.visible[0]==0 && !p.HasAura(301) && p.glyphs==ownership);
    config.glyphGate=false; EraGlyphGate::StripIfDisallowed(&p);
    assert(p.visible[0]==101 && p.HasAura(301)); // disabled policy restores existing owned glyphs
    config.glyphGate=true;
    Player fresh; fresh.era=fresh.stored=ERA_WOTLK;
    EraGlyphGate::StripIfDisallowed(&fresh); assert(fresh.casts==0 && fresh.glyphs==decltype(fresh.glyphs){});
    p.cls=CLASS_DEATH_KNIGHT; assert(EraGlyphGate::Allowed(&p));
    std::cout << "Era glyphs: both specs retain earned ownership, early effects suppressed, shape/spec recasts gated and Wrath restoration passed\n";
}
'''
    compile_run(directory, 'era-glyphs', glyph_fixture)

    # Execute the complete production training gate/converter against its generated
    # ownership map. Core trainer costs and prerequisite checks run before learning;
    # this module must only restrict those checks or translate already earned spells.
    training_code = '\n'.join(line for line in (src / 'EraEarnedTraining.cpp').read_text().splitlines()
                               if not line.startswith('#include'))
    learn_hook = function((src / 'EraTalentPin.cpp').read_text(), '    void OnPlayerLearnSpell(')
    (fake / 'Define.h').write_text('#pragma once\n#include <cstdint>\nusing uint8=uint8_t; using uint32=uint32_t;\n')
    training_fixture = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <limits>
#include <map>
#include <set>
#include <unordered_set>
#include <vector>
#include "EraEarnedTrainingData.gen.h"
constexpr uint8 CLASS_SHAMAN=7, TEAM_HORDE=1, TEAM_ALLIANCE=0;
enum EraId : uint8 { ERA_VANILLA=0, ERA_TBC=1, ERA_WOTLK=2 };
struct Player {
    uint8 cls=1, team=TEAM_HORDE, level=80; EraId era=ERA_VANILLA, stored=ERA_VANILLA;
    std::set<uint32> known, quests; std::map<uint32,uint8> talents;
    int learns=0, invalidates=0; bool combat=false;
    uint8 getClass() const { return cls; }
    uint8 GetTeamId() const { return team; }
    uint8 GetLevel() const { return level; }
    bool HasSpell(uint32 id) const { return known.contains(id); }
    bool GetQuestRewardStatus(uint32 id) const { return quests.contains(id); }
    bool IsInCombat() const { return combat; }
    void learnSpell(uint32 id) { assert(!HasSpell(id)); known.insert(id); ++learns; }
};
struct SpellInfo {};
struct SpellMgr {
    SpellInfo entry; std::map<uint32,uint32> roots; std::set<uint32> missing, talentRoots;
    uint32 GetFirstSpellInChain(uint32 id) const {
        auto it=roots.find(id); return it==roots.end() ? id : it->second;
    }
    SpellInfo const* GetSpellInfo(uint32 id) const { return missing.contains(id) ? nullptr : &entry; }
    bool IsAdditionalTalentSpell(uint32 id) const { return talentRoots.contains(id); }
} spells;
auto* sSpellMgr=&spells;
uint32 GetTalentSpellCost(uint32 id) { return spells.talentRoots.contains(id) ? 1 : 0; }
namespace EraTalents {
constexpr uint32 ERA_CUSTOM_BAND_LOW=920000, ERA_CUSTOM_BAND_HIGH=950000;
uint8 CurrentRank(Player* p,EraId,uint32 id) { return p->talents[id]; }
int reconciles=0;
void ReconcileBaselineSpells(Player*,EraId) { ++reconciles; }
}
namespace EraBandClassifier {
struct Result { bool verdict; };
bool legit=true;
Result Classify(Player*,EraId,uint32) { return {legit}; }
bool IsLegit(bool verdict) { return verdict; }
}
namespace EraTalentBots {
EraId EraFor(Player* p) { return p->era; }
void InvalidateSpecCache(Player* p) { ++p->invalidates; }
}
namespace EraTransition { EraId StoredEra(Player* p) { return p->stored; } }
struct Config { bool enabled=true; bool Enabled() const { return enabled; } } config;
auto* sEraTalentsConfig=&config;
bool EnabledFor(Player* p) { return p && config.enabled; }
namespace Trainer { enum class SpellState { Available, Unavailable }; }
namespace WorldPackets::NPC {
struct TrainerListSpell { int SpellID; };
struct TrainerList { std::vector<TrainerListSpell> Spells; };
}
struct Creature {};
struct PlayerScript {
    explicit PlayerScript(char const*) {}
    virtual ~PlayerScript()=default;
    virtual void OnPlayerGetTrainerSpellState(Player const*,uint32,uint32,Trainer::SpellState&) {}
    virtual void OnPlayerBeforeReceiveSpellListFromTrainer(Player*,Creature*,WorldPackets::NPC::TrainerList&) {}
    virtual void OnPlayerLearnSpell(Player*,uint32) {}
};
''' + training_code + '\nstruct LearnHook : PlayerScript { LearnHook() : PlayerScript("fixture") {}\n' + learn_hook + r'''
};
int main() {
    era_earned_training hook;
    Player p;
    auto nothing=EraEarnedTraining::Snapshot(&p);
    assert(nothing.empty());
    for (EraId era : {ERA_VANILLA,ERA_TBC,ERA_WOTLK}) EraEarnedTraining::Restore(&p,era,nothing);
    assert(p.known.empty() && p.learns==0); // high level alone earns no trainer variants

    p.known.insert(23881); // one learned Wrath Bloodthirst rank has several older equivalents
    auto acquired=EraEarnedTraining::Snapshot(&p);
    assert(acquired==std::vector<uint32>({23881}));
    EraEarnedTraining::Restore(&p,ERA_VANILLA,acquired);
    assert(p.HasSpell(932829) && !p.HasSpell(932830) && !p.HasSpell(932831));
    assert(p.learns==1 && p.invalidates==1); // choose only the lowest proven rank
    EraEarnedTraining::Restore(&p,ERA_VANILLA,acquired);
    assert(p.learns==1 && p.invalidates==1);
    Player low; low.level=47; low.known.insert(23881);
    EraEarnedTraining::Restore(&low,ERA_VANILLA,EraEarnedTraining::Snapshot(&low));
    assert(low.learns==0);
    spells.missing.insert(932829);
    Player absent; absent.known.insert(23881);
    EraEarnedTraining::Restore(&absent,ERA_VANILLA,EraEarnedTraining::Snapshot(&absent));
    assert(absent.learns==0); spells.missing.clear();
    EraBandClassifier::legit=false;
    Player gated; gated.known.insert(23881);
    EraEarnedTraining::Restore(&gated,ERA_VANILLA,EraEarnedTraining::Snapshot(&gated));
    assert(gated.learns==0); EraBandClassifier::legit=true;
    Player root; root.era=root.stored=ERA_WOTLK; root.known.insert(932829);
    spells.talentRoots.insert(23881);
    EraEarnedTraining::Restore(&root,ERA_WOTLK,EraEarnedTraining::Snapshot(&root));
    assert(root.learns==0); // an older cast rank cannot manufacture a missing talent root
    spells.talentRoots.clear();

    // Every explicit variant uses the current earned era, including shared old ranks.
    for (auto const& variant : EraEarnedTrainingData::kVariants) {
        Player owner; owner.cls=variant.classId;
        for (uint32 id : variant.spell) if (id) {
            for (EraId era : {ERA_VANILLA,ERA_TBC,ERA_WOTLK}) {
                bool offered=false;
                for (auto const& other : EraEarnedTrainingData::kVariants)
                    offered=offered || (other.classId==owner.cls && other.spell[uint8(era)]==id);
                if (!offered) assert(!EraEarnedTraining::CanTrain(&owner,era,id));
            }
        }
    }
    Player shaman; shaman.cls=CLASS_SHAMAN;
    assert(!EraEarnedTraining::CanTrain(&shaman,ERA_VANILLA,931020));
    shaman.quests.insert(1518);
    assert(EraEarnedTraining::CanTrain(&shaman,ERA_VANILLA,931020));
    shaman.quests.clear(); shaman.known.insert(8071);
    assert(EraEarnedTraining::CanTrain(&shaman,ERA_VANILLA,931020)); // prior earned quest spell survives a conversion
    assert(!EraEarnedTraining::CanTrain(&shaman,ERA_TBC,931020));
    Player paladin; paladin.cls=2;
    assert(EraEarnedTraining::CanTrain(&paladin,ERA_TBC,946080));
    assert(!EraEarnedTraining::CanTrain(&paladin,ERA_TBC,946084));
    paladin.team=TEAM_ALLIANCE;
    assert(!EraEarnedTraining::CanTrain(&paladin,ERA_TBC,946080));
    assert(EraEarnedTraining::CanTrain(&paladin,ERA_TBC,946084));
    Player mage; mage.cls=8;
    assert(!EraEarnedTraining::CanTrain(&mage,ERA_VANILLA,45438));
    mage.talents[18046]=1;
    assert(EraEarnedTraining::CanTrain(&mage,ERA_VANILLA,45438));
    assert(EraEarnedTraining::CanTrain(&mage,ERA_TBC,45438));
    Trainer::SpellState state=Trainer::SpellState::Available;
    p.combat=true; hook.OnPlayerGetTrainerSpellState(&p,1,123,state);
    assert(state==Trainer::SpellState::Unavailable);
    p.combat=false; p.era=ERA_TBC; state=Trainer::SpellState::Available;
    hook.OnPlayerGetTrainerSpellState(&p,1,123,state);
    assert(state==Trainer::SpellState::Unavailable); // forged buy while crossing cannot bypass the list
    p.stored=ERA_TBC; state=Trainer::SpellState::Available;
    hook.OnPlayerGetTrainerSpellState(&p,1,932829,state);
    assert(state==Trainer::SpellState::Unavailable);
    WorldPackets::NPC::TrainerList list{{{932829},{947513},{123}}};
    hook.OnPlayerBeforeReceiveSpellListFromTrainer(&p,nullptr,list);
    assert(list.Spells.size()==2 && list.Spells[0].SpellID==947513 && list.Spells[1].SpellID==123);
    LearnHook learned;
    int invalidates=p.invalidates;
    learned.OnPlayerLearnSpell(&p,947513);
    assert(p.invalidates==invalidates+1 && EraTalents::reconciles==0); // a paid custom rank refreshes a cached miss immediately
    learned.OnPlayerLearnSpell(&p,23922);
    assert(p.invalidates==invalidates+2 && EraTalents::reconciles==1);
    config.enabled=false; learned.OnPlayerLearnSpell(&p,947513);
    assert(p.invalidates==invalidates+2 && EraTalents::reconciles==1);
    std::cout << "Era training: no level grants, lowest owned conversion, prerequisites, factions, quests and pending/combat buy denial passed\n";
}
'''
    compile_run(directory, 'era-training', training_fixture, (fake, src))

    learn_code = function((src / 'EraTalents.cpp').read_text(), '    bool TryLearn(')
    learn_fixture = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <map>
#include <mutex>
#include <set>
#include <string>
#include <vector>
using uint8=uint8_t; using uint32=uint32_t;
constexpr uint32 SPEC_MASK_ALL=255;
#define LOG_INFO(...) ((void)0)
enum EraId : uint8 { ERA_VANILLA=0, ERA_TBC=1, ERA_WOTLK=2 };
struct Guid { uint32 GetCounter() const { return 42; } };
struct Player {
    uint8 cls=1, level=10; EraId era=ERA_VANILLA, stored=ERA_VANILLA;
    bool combat=false; std::set<uint32> known; int learns=0, removals=0, invalidates=0;
    int money=123456, xp=987, gear=17;
    uint8 getClass() const { return cls; }
    uint8 GetLevel() const { return level; }
    Guid GetGUID() const { return {}; }
    bool IsInCombat() const { return combat; }
    std::string GetName() const { return "earned-player"; }
    void learnSpell(uint32 id) { known.insert(id); ++learns; }
    void removeSpell(uint32 id,uint32 mask,bool disabled) {
        assert(mask==SPEC_MASK_ALL && !disabled); known.erase(id); ++removals;
    }
};
struct EraTalentNode {
    uint32 id=0; uint8 eraId=0, classId=1, tab=1, maxRank=0;
    uint32 prereqTalentId=0; uint8 prereqPoints=0; std::vector<uint32> rankSpell;
};
struct Content {
    std::map<uint32,EraTalentNode> nodes;
    EraTalentNode const* Node(uint32 id) const { auto it=nodes.find(id); return it==nodes.end() ? nullptr : &it->second; }
    std::vector<EraTalentNode const*> NodesFor(uint8 era,uint8 cls) const {
        std::vector<EraTalentNode const*> result;
        for (auto const& [id,node] : nodes) if (node.eraId==era && node.classId==cls) result.push_back(&node);
        return result;
    }
} content;
auto* sEraTalentContent=&content;
struct SpellMgr { std::set<uint32> missing; int info=0;
    int const* GetSpellInfo(uint32 id) const { return missing.contains(id) ? nullptr : &info; }
} spells;
auto* sSpellMgr=&spells;
struct Config { bool Debug() const { return false; } } config;
auto* sEraTalentsConfig=&config;
namespace EraTalentBots {
EraId EraFor(Player* p) { return p->era; }
void InvalidateSpecCache(Player* p) { ++p->invalidates; }
}
namespace EraTransition { EraId StoredEra(Player* p) { return p->stored; } }
namespace EraPersistence { std::vector<std::vector<std::string>> snapshots;
void Queue(std::vector<std::string> rows) { snapshots.push_back(std::move(rows)); }
}
void EraMasterDemonologist_Refresh(Player*) {}
namespace EraTalents {
std::map<uint32,uint8> ranks;
std::mutex g_rankCacheMutex;
std::map<uint32,uint8>& LoadRanks(Player*,EraId) { return ranks; }
bool InBotBuild(Player*) { return false; }
uint8 CurrentRank(Player*,EraId,uint32 id) { auto it=ranks.find(id); return it==ranks.end() ? 0 : it->second; }
int SpentPoints(Player*,EraId) { int result=0; for (auto [id,rank] : ranks) result+=rank; return result; }
void ReconcileBaselineSpells(Player*,EraId) {}
''' + points + '\n' + learn_code + r'''
}
void Fresh() { EraTalents::ranks.clear(); content.nodes.clear(); EraPersistence::snapshots.clear(); spells.missing.clear(); }
EraTalentNode Node(uint32 id,uint8 cls,uint8 era,uint8 tab,uint8 max=5) {
    EraTalentNode node{id,era,cls,tab,max,0,0,{}};
    for (uint8 rank=1;rank<=max;++rank) node.rankSpell.push_back(100000+100*id+rank);
    return node;
}
int main() {
    std::string error;
    for (uint8 cls : {1,2,3,4,5,7,8,9,11}) for (EraId era : {ERA_VANILLA,ERA_TBC}) {
        Fresh(); Player p; p.cls=cls; p.era=p.stored=era; p.level=80;
        for (uint32 id=1;id<=15;++id) content.nodes[id]=Node(id,cls,uint8(era),1);
        int expected=era==ERA_VANILLA ? 51 : 61;
        for (uint32 id=1;id<=15;++id) while (EraTalents::TryLearn(&p,id,error)) {}
        assert(EraTalents::SpentPoints(&p,era)==expected && p.learns==expected);
        assert(EraPersistence::snapshots.size()==size_t(expected));
        int learns=p.learns, removals=p.removals;
        for (uint32 id=1;id<=15;++id) assert(!EraTalents::TryLearn(&p,id,error));
        assert(p.learns==learns && p.removals==removals);
        assert(p.money==123456 && p.xp==987 && p.gear==17);
    }
    Fresh(); Player p; content.nodes[1]=Node(1,1,ERA_VANILLA,1);
    content.nodes[2]=Node(2,1,ERA_VANILLA,2);
    content.nodes[3]=Node(3,1,ERA_VANILLA,1);
    content.nodes[3].prereqPoints=5;
    content.nodes[4]=Node(4,1,ERA_VANILLA,1);
    content.nodes[4].prereqTalentId=1;
    assert(!EraTalents::TryLearn(&p,999,error));
    p.combat=true; assert(!EraTalents::TryLearn(&p,1,error));
    p.combat=false; p.stored=ERA_TBC; assert(!EraTalents::TryLearn(&p,1,error));
    p.stored=ERA_VANILLA; p.era=ERA_TBC; assert(!EraTalents::TryLearn(&p,1,error));
    p.era=ERA_VANILLA; p.cls=2; assert(!EraTalents::TryLearn(&p,1,error));
    p.cls=1; assert(!EraTalents::TryLearn(&p,3,error));
    assert(!EraTalents::TryLearn(&p,4,error));
    p.level=9; assert(!EraTalents::TryLearn(&p,1,error));
    assert(EraTalents::ranks.empty() && EraPersistence::snapshots.empty() && p.learns==0);
    p.level=10; assert(EraTalents::TryLearn(&p,1,error));
    assert(!EraTalents::TryLearn(&p,1,error)); // only one level-earned point
    p.level=20;
    assert(EraTalents::TryLearn(&p,2,error));
    assert(!EraTalents::TryLearn(&p,3,error)); // spending another tab does not unlock this tab
    assert(!EraTalents::TryLearn(&p,4,error)); // rank 1 of 5 is not a fulfilled prerequisite
    for (int i=0;i<4;++i) assert(EraTalents::TryLearn(&p,1,error));
    assert(!EraTalents::TryLearn(&p,1,error));
    assert(EraTalents::TryLearn(&p,3,error) && EraTalents::TryLearn(&p,4,error));
    assert(p.known.contains(content.nodes[1].rankSpell[4]) && !p.known.contains(content.nodes[1].rankSpell[0]));
    auto before=EraTalents::ranks; size_t queued=EraPersistence::snapshots.size(); int learned=p.learns;
    content.nodes[5]=Node(5,1,ERA_VANILLA,1); content.nodes[5].rankSpell.clear();
    assert(!EraTalents::TryLearn(&p,5,error));
    content.nodes[5].rankSpell={0}; assert(!EraTalents::TryLearn(&p,5,error));
    content.nodes[5].rankSpell={123}; spells.missing.insert(123);
    assert(!EraTalents::TryLearn(&p,5,error));
    assert(EraTalents::ranks==before && EraPersistence::snapshots.size()==queued && p.learns==learned);
    std::cout << "Era talent learning: all authored classes respect earned budgets, same-tree/full-rank prerequisites and atomic malformed-spell rejection passed\n";
}
'''
    compile_run(directory, 'era-learning', learn_fixture)

    bot_source = (src / 'EraTalentBots.cpp').read_text()
    factory_code = function(bot_source, '    bool FactoryReconcile(')
    bot_login_code = function(bot_source, '    void OnBotLogin(')
    bot_level_code = function(bot_source, '    void OnBotLevelChanged(')
    bot_fixture = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <vector>
using uint8=uint8_t; using uint32=uint32_t;
constexpr uint8 CLASS_DRUID=11;
#define LOG_DEBUG(...) ((void)0)
enum EraId : uint8 { ERA_VANILLA=0, ERA_TBC=1, ERA_WOTLK=2 };
struct Guid { uint32 GetCounter() const { return 2; } };
struct Player {
    uint8 cls=1, level=1; EraId era=ERA_VANILLA, stored=ERA_VANILLA;
    bool bot=true, combat=false, cat=false, bear=false;
    int spent=0, builds=0, lastSpec=-1, freePoints=0, infos=0, invalidates=0, reconciles=0, reapplies=0;
    int nativeSpent=0, nativeBuilds=0, money=123456, xp=987, gear=17;
    std::array<uint32,3> tabs{};
    uint8 getClass() const { return cls; }
    uint8 GetLevel() const { return level; }
    Guid GetGUID() const { return {}; }
    bool IsInCombat() const { return combat; }
    char const* GetName() const { return "earned-bot"; }
    void SetFreeTalentPoints(int value) { freePoints=value; }
    void SendTalentsInfoData(bool pet) { assert(!pet); ++infos; }
};
bool EraHasTalentTrees(EraId era) { return era!=ERA_WOTLK; }
bool EraHasTalentTrees(Player* p,EraId era) { return p->cls!=6 && EraHasTalentTrees(era); }
struct Config { bool enabled=true, bots=true; bool Enabled() const { return enabled; } bool BotTalents() const { return bots; } } config;
auto* sEraTalentsConfig=&config;
bool Gated(Player* p) { return !p || !p->bot || !config.enabled || !config.bots; }
struct Content { std::vector<int> NodesFor(uint8,uint8 cls) { return cls==6 ? std::vector<int>{} : std::vector<int>{1}; } } content;
auto* sEraTalentContent=&content;
namespace EraTransition {
void Detect(Player*) {}
EraId StoredEra(Player* p) { return p->stored; }
void StripNativeTalents(Player*,EraId) {}
}
namespace EraGlyphGate { void StripIfDisallowed(Player*) {} }
namespace EraTalents {
int SpentPoints(Player* p,EraId) { return p->spent; }
''' + points + r'''
uint8 CurrentRank(Player* p,EraId,uint32 id) { return (id==18717||id==20122) ? p->cat : p->bear; }
void ReconcileBaselineSpells(Player* p,EraId) { ++p->reconciles; }
void ReapplyOnLogin(Player* p,EraId) { ++p->reapplies; }
}
bool EraTalentBots_SpecTabs(Player* p,uint32* tabs) {
    for (int tab=0;tab<3;++tab) tabs[tab]=p->tabs[tab];
    return true;
}
void InvalidateSpecTabs(Player* p) { ++p->invalidates; }
void StripTbcSealIfPaladin(Player*,EraId) {}
void SpendBuild(Player* p,EraId era,int tab) {
    int available=EraTalents::AvailablePoints(p,era);
    assert(available>0); ++p->builds; p->lastSpec=tab;
    p->spent+=available; p->tabs[tab==3 ? 1 : tab]+=available;
}
struct PlayerbotFactory {
    Player* p;
    PlayerbotFactory(Player* player,uint8 level) : p(player) { assert(level==p->level); }
    void InitTalentsTree(bool incremental,bool useSpec,bool reset) {
        assert(incremental && useSpec && !reset); ++p->nativeBuilds;
        p->nativeSpent=std::max(p->nativeSpent,std::max(0,int(p->level)-9));
    }
};
namespace EraTalentBots {
EraId BotEra(Player* p) { return p->era; }
EraId EraFor(Player* p) { return p->era; }
''' + factory_code + '\n' + bot_login_code + '\n' + bot_level_code + r'''
}
int main() {
    Player p;
    assert(EraTalentBots::FactoryReconcile(&p,1));
    assert(p.spent==0 && p.builds==0);
    p.level=10;
    assert(EraTalentBots::FactoryReconcile(&p,1));
    assert(p.spent==1 && p.tabs[1]==1 && p.lastSpec==1);
    for (int i=0;i<100;++i) assert(EraTalentBots::FactoryReconcile(&p,0));
    assert(p.spent==1 && p.builds==1 && p.tabs[1]==1); // maintenance cannot respec to another requested tab
    p.level=19; EraTalentBots::OnBotLevelChanged(&p);
    assert(p.spent==10 && p.tabs[1]==10 && p.lastSpec==1);
    EraTalentBots::OnBotLogin(&p);
    assert(p.spent==10 && p.builds==2 && p.reapplies==1);
    p.level=80; EraTalentBots::OnBotLevelChanged(&p);
    assert(p.era==ERA_VANILLA && p.spent==51 && p.tabs[1]==51);
    assert(p.money==123456 && p.xp==987 && p.gear==17);

    Player pending=p; pending.era=ERA_TBC;
    int builds=pending.builds, infos=pending.infos;
    assert(EraTalentBots::FactoryReconcile(&pending,0));
    EraTalentBots::OnBotLevelChanged(&pending); EraTalentBots::OnBotLogin(&pending);
    assert(pending.spent==51 && pending.builds==builds && pending.infos==infos);
    pending.stored=ERA_TBC; pending.combat=true;
    assert(EraTalentBots::FactoryReconcile(&pending,0));
    EraTalentBots::OnBotLevelChanged(&pending); EraTalentBots::OnBotLogin(&pending);
    assert(pending.spent==51 && pending.builds==builds);
    pending.combat=false; assert(EraTalentBots::FactoryReconcile(&pending,0));
    assert(pending.spent==61 && pending.lastSpec==1);

    Player druid; druid.cls=CLASS_DRUID; druid.level=20; druid.spent=5; druid.tabs[1]=5; druid.cat=true;
    assert(EraTalentBots::FactoryReconcile(&druid,0));
    assert(druid.lastSpec==3 && druid.spent==11);
    Player dk; dk.cls=6; dk.level=55;
    assert(!EraTalentBots::FactoryReconcile(&dk,0) && dk.spent==0);
    Player human; human.bot=false;
    assert(!EraTalentBots::FactoryReconcile(&human,0));
    Player wrath; wrath.era=wrath.stored=ERA_WOTLK; wrath.level=70; wrath.nativeSpent=60;
    EraTalentBots::OnBotLevelChanged(&wrath);
    assert(wrath.nativeSpent==61 && wrath.nativeBuilds==1 && wrath.builds==0);
    wrath.level=80; EraTalentBots::OnBotLevelChanged(&wrath);
    assert(wrath.nativeSpent==71 && wrath.nativeBuilds==2);
    std::cout << "Era bots: maintenance/login retain builds, levels extend earned points, pending/combat transitions stop mutation and native factory never resets passed\n";
}
'''
    compile_run(directory, 'era-bots', bot_fixture)

    transition_code = '\n'.join(line for line in (src / 'EraTransition.cpp').read_text().splitlines()
                                 if not line.startswith('#include'))
    transition_fixture = r'''
#include <array>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>
using uint8=uint8_t; using uint32=uint32_t;
#define LOG_INFO(...) ((void)0)
enum EraId : uint8 { ERA_VANILLA=0, ERA_TBC=1, ERA_WOTLK=2 };
struct ObjectGuid { uint32 value=0; uint32 GetCounter() const { return value; } bool operator==(ObjectGuid const&) const = default; };
namespace std { template<> struct hash<ObjectGuid> { size_t operator()(ObjectGuid const& guid) const { return guid.value; } }; }
constexpr int PLAYERSPELL_REMOVED=2;
struct FakeTalent { int State=0; };
struct Player {
    ObjectGuid guid{1}; uint8 earnedEra=0, activeSpec=0, specs=2, classId=1;
    bool combat=false;
    int nativeResets=0, initializes=0, syncs=0, restores=0, reconciles=0;
    uint32 freePoints=0, money=123456, xp=789;
    std::vector<uint32> inventory{100,200}; int spent[3]{10,0,0}, resets[3]{0,0,0};
    std::unordered_map<uint32,FakeTalent*> talents;
    ObjectGuid GetGUID() const { return guid; }
    uint8 GetSpecsCount() const { return specs; }
    uint8 GetActiveSpec() const { return activeSpec; }
    void ActivateSpec(uint8 spec) { activeSpec=spec; }
    bool resetTalents(bool noCost);
    void InitTalentForLevel() { ++initializes; freePoints=71; }
    void SetFreeTalentPoints(uint32 points) { freePoints=points; }
    void SendTalentsInfoData(bool) { ++syncs; }
    bool IsInCombat() const { return combat; }
    auto const& GetTalentMap() const { return talents; }
    char const* GetName() const { return "fixture"; }
    uint8 getClass() const { return classId; }
};
struct Field { uint32 value=0; template<class T> T Get() const { return T(value); } };
struct FakeQueryResult {
    std::vector<std::array<Field,2>> rows; size_t index=0;
    Field* Fetch() { return rows[index].data(); }
    bool NextRow() { return ++index<rows.size(); }
};
using QueryResult=std::shared_ptr<FakeQueryResult>;
struct Database {
    QueryResult stateRows; int queries=0;
    QueryResult Query(char const*) { ++queries; return stateRows; }
} CharacterDatabase;
struct Config { bool Enabled() const { return true; } bool Debug() const { return false; } } config;
auto* sEraTalentsConfig=&config;
EraId EraFromIP(Player* p) { return EraId(p->earnedEra); }
bool EraHasTalentTrees(EraId era) { return era<ERA_WOTLK; }
bool EraHasTalentTrees(Player* p,EraId era) { return p && p->classId!=6 && EraHasTalentTrees(era); }
namespace EraTransition { EraId StoredEra(Player*); bool NativeResetActive(Player*); }
namespace EraPersistence {
std::vector<std::vector<std::string>> snapshots;
void Queue(std::vector<std::string> rows) { snapshots.push_back(std::move(rows)); }
}
namespace EraTalents {
void Reset(Player* p,EraId era) { ++p->resets[era]; p->spent[era]=0; }
void ReconcileBaselineSpells(Player* p,EraId era) { assert(EraTransition::StoredEra(p)==era); ++p->reconciles; }
}
namespace EraTalentsComms { void SendSync(Player* p) { assert(EraTransition::StoredEra(p)==EraFromIP(p)); ++p->syncs; } }
namespace EraGlyphGate { void StripIfDisallowed(Player*) {} }
namespace EraEarnedTraining {
std::vector<uint32> Snapshot(Player* p) { return p->inventory; }
void Restore(Player* p,EraId era,std::vector<uint32> const& acquired) {
    assert(EraTransition::StoredEra(p)==era && acquired==p->inventory); ++p->restores;
}
}
''' + transition_code + r'''
bool Player::resetTalents(bool noCost) {
    assert(noCost && EraTransition::NativeResetActive(this)); ++nativeResets; talents.clear(); return true;
}
int main() {
    CharacterDatabase.stateRows=std::make_shared<FakeQueryResult>();
    CharacterDatabase.stateRows->rows.push_back({Field{1},Field{0}});
    EraTransition::LoadCache(); assert(CharacterDatabase.queries==1);
    Player p;
    EraTransition::Run(&p,ERA_VANILLA,ERA_VANILLA);
    assert(p.resets[0]==0 && p.nativeResets==0);
    for (int i=0;i<5000;++i) assert(!EraTransition::Detect(&p));
    assert(CharacterDatabase.queries==1 && EraPersistence::snapshots.empty());
    p.earnedEra=ERA_TBC; p.combat=true;
    assert(!EraTransition::Detect(&p));
    assert(EraTransition::StoredEra(&p)==ERA_VANILLA && p.spent[0]==10);
    p.earnedEra=ERA_VANILLA; p.combat=false;
    EraTransition::FlushCombat(&p);
    assert(p.resets[0]==0); // a withdrawn pending target is not authority
    p.earnedEra=ERA_TBC; p.combat=true;
    assert(!EraTransition::Detect(&p));
    p.combat=false; EraTransition::FlushCombat(&p);
    assert(p.resets[0]==1 && p.nativeResets==2 && p.activeSpec==0);
    assert(EraTransition::StoredEra(&p)==ERA_TBC && p.restores==1);
    assert(!EraTransition::NativeResetActive(&p));
    p.spent[1]=20;
    EraTransition::Run(&p,ERA_VANILLA,ERA_TBC); // stale from arguments cannot refund the current build
    assert(p.resets[1]==0 && p.spent[1]==20);
    EraTransition::Run(&p,ERA_TBC,ERA_WOTLK);
    assert(p.resets[1]==0 && EraTransition::StoredEra(&p)==ERA_TBC);
    EraTransition::OnLogout(&p);
    assert(EraTransition::StoredEra(&p)==ERA_TBC);
    p.earnedEra=ERA_WOTLK; p.combat=true;
    assert(!EraTransition::Detect(&p));
    EraTransition::OnLogout(&p); p.combat=false;
    EraTransition::FlushCombat(&p); assert(p.resets[1]==0);
    assert(EraTransition::Detect(&p));
    assert(p.resets[1]==1 && p.freePoints==71 && p.initializes==1);
    assert(p.money==123456 && p.xp==789 && (p.inventory==std::vector<uint32>{100,200}));
    auto resets=p.nativeResets;
    assert(!EraTransition::Detect(&p) && p.nativeResets==resets && CharacterDatabase.queries==1);
    Player dk; dk.guid={2}; dk.classId=6;
    FakeTalent existing; dk.talents.emplace(500,&existing);
    EraTransition::StripNativeTalents(&dk,ERA_VANILLA);
    assert(dk.nativeResets==0 && dk.talents.size()==1);
    dk.earnedEra=ERA_TBC; EraTransition::SetStoredEra(&dk,ERA_VANILLA);
    assert(EraTransition::Detect(&dk) && dk.nativeResets==0 && dk.talents.size()==1);
    Player fresh; fresh.guid={3}; fresh.earnedEra=ERA_TBC;
    EraTransition::Run(&fresh,ERA_VANILLA,ERA_TBC);
    assert(fresh.nativeResets==0 && fresh.resets[0]==0);
    assert(EraTransition::StoredEra(&fresh)==ERA_TBC); // a first sighting adopts earned state without a bonus reset
    std::cout << "Era transitions: cached polling, earned target revalidation, combat/logout cancellation, one crossing refund, all specs and unchanged gold/XP/items passed\n";
}
'''
    compile_run(directory, 'era-transitions', transition_fixture)
