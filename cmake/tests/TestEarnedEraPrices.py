"""Check production earned-era trainer quotes and charges with ASan/UBSan.

The actual IP pricing translation unit and core trainer methods decide prices.
Fixtures model ordinary trainer availability and money deductions, without
starting a realm or substituting a historical price multiplier.
"""

import argparse
from pathlib import Path
import subprocess
import tempfile
from PreparedSources import prepared_core


repo = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--core', type=Path, default=prepared_core(repo))
parser.add_argument('--module', type=Path)
args = parser.parse_args()
module = args.module or args.core / 'modules/mod-individual-progression'
trainer_source = (args.core / 'src/server/game/Entities/Creature/Trainer.cpp').read_text()


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


trainer_methods = '\n'.join(function(trainer_source, signature) for signature in (
    '    void Trainer::SendSpells(', '    uint32 Trainer::GetSpellCost(',
    '    void Trainer::TeachSpell('))
stub = r'''
#pragma once
#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <limits>
#include <string>
#include <vector>
using uint8=std::uint8_t; using uint16=std::uint16_t; using uint32=std::uint32_t;
using int32=std::int32_t; using LocaleConstant=int;
constexpr uint32 MAX_MONEY_AMOUNT=0x7fffffff, SPELL_EFFECT_LEARN_SPELL=1;
constexpr int PLAYERHOOK_ON_GET_TRAINER_SPELL_COST=0;
template<class T> uint32 AsUnderlyingType(T value) { return uint32(value); }
struct Creature {
    int GetGUID() const { return 1; }
    void SendPlaySpellVisual(int) {} void SendPlaySpellImpact(int,int) {}
};
namespace WorldPackets::NPC {
struct TrainerListSpell {
    uint32 SpellID=0,Usable=0,ReqSkillLine=0,ReqSkillRank=0;
    int32 MoneyCost=0,PointCost[2]{}; std::array<int32,3> ReqAbility{}; uint8 ReqLevel=0;
};
struct TrainerList {
    int TrainerGUID=0; uint32 TrainerType=0; std::string Greeting;
    std::vector<TrainerListSpell> Spells;
    TrainerList const* Write() const { return this; }
};
}
struct Player {
    uint8 stage=0; bool inWorld=true,available=true,learnAllowed=true;
    uint32 money=0; float discount=1;
    int charges=0,learned=0,failures=0,successes=0,afterTrain=0; int32 displayed=0;
    bool IsInWorld() const { return inWorld; }
    int GetGUID() const { return 2; }
    float GetReputationPriceDiscount(Creature const*) const { return discount; }
    bool IsSpellFitByClassAndRace(uint32) const { return true; }
    bool HasEnoughMoney(uint32 cost) const { return money>=cost; }
    void ModifyMoney(int32 change) { assert(change<=0 && money>=uint32(-change)); money-=uint32(-change); ++charges; }
    void learnSpell(uint32,bool) { ++learned; } void CastSpell(Player*,uint32,bool) { ++learned; }
    void SendDirectMessage(WorldPackets::NPC::TrainerList const* packet) {
        assert(packet->Spells.size()==1); displayed=packet->Spells[0].MoneyCost;
    }
};
class PlayerScript;
inline PlayerScript* pricingHook=nullptr;
class PlayerScript {
public:
    PlayerScript(char const*,std::vector<uint16>) { pricingHook=this; }
    virtual ~PlayerScript()=default;
    virtual void OnPlayerGetTrainerSpellCost(Player const*,Creature const*,uint32,uint32&) {}
};
struct IndividualProgression {
    bool strict=true; bool IsStrictDefaultProgression() const { return strict; }
    uint8 GetPlayerProgressionFromQuests(Player* player) const { return player->stage; }
} progression;
inline auto* sIndividualProgression=&progression;
struct ScriptMgr {
    void OnPlayerGetTrainerSpellCost(Player const* player,Creature const* npc,uint32 spell,uint32& cost) {
        pricingHook->OnPlayerGetTrainerSpellCost(player,npc,spell,cost);
    }
    void OnPlayerBeforeReceiveSpellListFromTrainer(Player*,Creature*,WorldPackets::NPC::TrainerList&) {}
    bool OnPlayerCanLearnSpell(Player* player,uint32) const { return player->learnAllowed; }
    void OnPlayerAfterTrainSpell(Player* player,Creature*,uint32) { ++player->afterTrain; }
} scripts;
inline auto* sScriptMgr=&scripts;
struct SpellEffectInfo {
    uint32 TriggerSpell=0; bool IsEffect(uint32) const { return false; }
};
struct SpellInfo {
    std::vector<SpellEffectInfo> effects;
    std::vector<SpellEffectInfo> const& GetEffects() const { return effects; }
    bool IsPrimaryProfessionFirstRank() const { return false; }
};
struct SpellMgr {
    SpellInfo info;
    SpellInfo const* AssertSpellInfo(uint32) const { return &info; }
    SpellInfo const* GetSpellInfo(uint32) const { return &info; }
} spells;
inline auto* sSpellMgr=&spells;
namespace Trainer {
enum class Type { Mount=1 }; enum class SpellState { Available=0,Unavailable=1 };
enum class FailReason { Unavailable,NotEnoughSkill,NotEnoughMoney };
struct Spell {
    uint32 SpellId=0,MoneyCost=0,ReqSkillLine=0,ReqSkillRank=0;
    std::vector<int32> ReqAbility{0,0,0}; uint8 ReqLevel=0;
    bool IsCastable() const { return false; }
};
class Trainer {
public:
    Type _type=Type::Mount; std::vector<Spell> _spells;
    std::string GetGreeting(LocaleConstant) const { return "Riding"; }
    SpellState GetSpellState(Player const* player,Spell const*) const {
        return player->available ? SpellState::Available : SpellState::Unavailable;
    }
    bool IsTrainerValidForPlayer(Player const*) const { return true; }
    bool CanTeachSpell(Player const* player,Spell const*) const { return player->available; }
    Spell const* GetSpell(uint32 id) const {
        for (auto const& spell:_spells) if (spell.SpellId==id) return &spell;
        return nullptr;
    }
    void SendTeachFailure(Creature*,Player* player,uint32,FailReason) { ++player->failures; }
    void SendTeachSucceeded(Creature*,Player* player,uint32) { ++player->successes; }
    uint32 GetSpellCost(Player const*,Creature const*,Spell const*) const;
    void SendSpells(Creature*,Player*,LocaleConstant) const;
    void TeachSpell(Creature*,Player*,uint32);
};
}
'''

tests = r'''
int main() {
    IndividualProgressionEraRidingPrices pricing;
    Creature npc; Trainer::Trainer trainer;
    struct Quote { uint32 spell,configured,vanilla,tbc,wrath; };
    for (auto entry:std::vector<Quote>{{33388,800000,900000,350000,40000},
         {33391,10000000,9000000,6000000,500000},
         {34090,8000000,8000000,8000000,2500000},
         {34091,50000000,50000000,50000000,50000000},
         {12345,12345,12345,12345,12345}}) {
        trainer._spells={{entry.spell,entry.configured}};
        for (uint8 stage=0;stage<=18;++stage) for (float discount:{1.f,.9f,.8f}) {
            Player player; player.stage=stage; player.discount=discount;
            uint32 const expected=uint32((stage<8 ? entry.vanilla : stage<13 ? entry.tbc : entry.wrath)*discount);
            assert(trainer.GetSpellCost(&player,&npc,&trainer._spells[0])==expected);
            trainer.SendSpells(&npc,&player,0); assert(player.displayed==int32(expected));
            player.money=expected-1;
            trainer.TeachSpell(&npc,&player,entry.spell);
            assert(player.failures==1 && player.money==expected-1 && player.charges==0 && player.learned==0);
            player.money=expected;
            trainer.TeachSpell(&npc,&player,entry.spell);
            assert(player.money==0 && player.charges==1 && player.learned==1 && player.successes==1 && player.afterTrain==1);
            assert(trainer._spells[0].MoneyCost==entry.configured); // no shared trainer mutation
        }
    }
    trainer._spells={{33391,10000000}};
    Player denied; denied.money=MAX_MONEY_AMOUNT; denied.available=false;
    trainer.TeachSpell(&npc,&denied,33391);
    assert(denied.money==MAX_MONEY_AMOUNT && denied.charges==0 && denied.learned==0 && denied.failures==1);
    trainer.TeachSpell(&npc,&denied,999);
    assert(denied.failures==2 && denied.charges==0);
    Player vanilla,tbc,wrath; tbc.stage=8; wrath.stage=13;
    assert(trainer.GetSpellCost(&vanilla,&npc,&trainer._spells[0])==9000000);
    assert(trainer.GetSpellCost(&tbc,&npc,&trainer._spells[0])==6000000);
    assert(trainer.GetSpellCost(&wrath,&npc,&trainer._spells[0])==500000);
    progression.strict=false;
    assert(trainer.GetSpellCost(&wrath,&npc,&trainer._spells[0])==10000000);
    progression.strict=true; wrath.inWorld=false;
    assert(trainer.GetSpellCost(&wrath,&npc,&trainer._spells[0])==10000000);
    wrath.inWorld=true;
    for (float discount:{-1.f,std::numeric_limits<float>::infinity(),std::numeric_limits<float>::quiet_NaN()}) {
        wrath.discount=discount;
        assert(trainer.GetSpellCost(&wrath,&npc,&trainer._spells[0])==MAX_MONEY_AMOUNT);
    }
    assert(trainer.GetSpellCost(nullptr,&npc,&trainer._spells[0])==MAX_MONEY_AMOUNT);
    assert(trainer.GetSpellCost(&wrath,nullptr,&trainer._spells[0])==MAX_MONEY_AMOUNT);
    assert(trainer.GetSpellCost(&wrath,&npc,nullptr)==MAX_MONEY_AMOUNT);
    trainer._spells={{12345,UINT32_MAX}}; wrath.discount=1;
    assert(trainer.GetSpellCost(&wrath,&npc,&trainer._spells[0])==MAX_MONEY_AMOUNT);
    std::cout << "Earned riding prices: per-character tiers, displayed/charged quote, reputation and affordability checks passed\n";
}
'''

with tempfile.TemporaryDirectory(prefix='portable-era-prices-') as temporary:
    path = Path(temporary)
    (path / 'IndividualProgression.h').write_text(stub)
    for name in ('EarnedEraRidingPrices.cpp', 'EarnedEraRidingPricesPolicy.h'):
        (path / name).write_text((module / 'src' / name).read_text())
    source = '#include "EarnedEraRidingPrices.cpp"\nnamespace Trainer {\n' + trainer_methods + '\n}\n' + tests
    (path / 'prices.cpp').write_text(source)
    subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror', '-g',
                    '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                    str(path / 'prices.cpp'), '-o', str(path / 'prices')], check=True)
    subprocess.run([str(path / 'prices')], check=True)
