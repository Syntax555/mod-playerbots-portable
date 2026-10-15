"""Check production earned-era trainer quotes and charges with ASan/UBSan.

The actual IP pricing translation unit and core trainer methods decide prices.
Fixtures model ordinary trainer availability and money deductions, without
starting a realm or substituting a historical price multiplier.
"""

import argparse
from pathlib import Path
import subprocess
import tempfile

from FixtureSupport import cxx, function, in_parallel, prepared_core, run_fixture


repo = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--core', type=Path, default=prepared_core(repo))
parser.add_argument('--module', type=Path)
args = parser.parse_args()
module = args.module or args.core / 'modules/mod-individual-progression'
trainer_source = (args.core / 'src/server/game/Entities/Creature/Trainer.cpp').read_text()
ip_source = (module / 'src/IndividualProgression.cpp').read_text()
ip_header = (module / 'src/IndividualProgression.h').read_text()
earned_era = function(ip_source, 'uint8 IndividualProgression_GetEarnedEra(')
progression_enum = function(ip_header, 'enum ProgressionState') + ';'


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
PROGRESSION_ENUM
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
    int progressionLimit=0;
    bool strict=true; bool IsStrictDefaultProgression() const { return strict; }
    uint8 GetPlayerProgressionFromQuests(Player* player) const { return player->stage; }
} progression;
inline auto* sIndividualProgression=&progression;
EARNED_ERA_HELPER
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
        for (int limit:{0,1,7,8,12,13,18})
        for (uint8 stage=0;stage<=18;++stage) for (float discount:{1.f,.9f,.8f}) {
            progression.progressionLimit=limit;
            Player player; player.stage=stage; player.discount=discount;
            uint8 const cappedStage=limit>0 && stage>limit ? uint8(limit) : stage;
            uint32 const expected=uint32((cappedStage<8 ? entry.vanilla : cappedStage<13 ? entry.tbc : entry.wrath)*discount);
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
    progression.progressionLimit=0;
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
    wrath.stage=255;
    assert(trainer.GetSpellCost(&wrath,&npc,&trainer._spells[0])==10000000);
    wrath.stage=13;
    for (float discount:{-1.f,std::numeric_limits<float>::infinity(),std::numeric_limits<float>::quiet_NaN()}) {
        wrath.discount=discount;
        assert(trainer.GetSpellCost(&wrath,&npc,&trainer._spells[0])==MAX_MONEY_AMOUNT);
    }
    assert(trainer.GetSpellCost(nullptr,&npc,&trainer._spells[0])==MAX_MONEY_AMOUNT);
    assert(trainer.GetSpellCost(&wrath,nullptr,&trainer._spells[0])==MAX_MONEY_AMOUNT);
    assert(trainer.GetSpellCost(&wrath,&npc,nullptr)==MAX_MONEY_AMOUNT);
    trainer._spells={{12345,UINT32_MAX}}; wrath.discount=1;
    assert(trainer.GetSpellCost(&wrath,&npc,&trainer._spells[0])==MAX_MONEY_AMOUNT);
    std::cout << "Earned riding prices: per-character eras, realm ceiling, displayed/charged quote, reputation and affordability checks passed\n";
}
'''

with tempfile.TemporaryDirectory(prefix='portable-era-prices-') as temporary:
    path = Path(temporary)
    stub = stub.replace('PROGRESSION_ENUM', progression_enum).replace('EARNED_ERA_HELPER', earned_era)
    source = '#include "EarnedEraRidingPrices.cpp"\nnamespace Trainer {\n' + trainer_methods + '\n}\n' + tests
    clamp = 'if (limit > 0 && stage > limit)'
    sentinel = 'if (era > 2)'
    policy = (module / 'src/EarnedEraRidingPricesPolicy.h').read_text()
    assert stub.count(clamp) == 1 and policy.count(sentinel) == 1
    variants = (
        ('patched', stub, policy, None),
        ('realm-ceiling', stub.replace(clamp, 'if (limit > 0 && false)'), policy, 'trainer.GetSpellCost'),
        ('unavailable-era', stub, policy.replace(sentinel, 'if (false)'), '==10000000'),
    )

    def build_and_run(variant):
        name, header, pricing, _ = variant
        variant_path = path / name
        variant_path.mkdir()
        (variant_path / 'IndividualProgression.h').write_text(header)
        (variant_path / 'EarnedEraRidingPrices.cpp').write_text((module / 'src/EarnedEraRidingPrices.cpp').read_text())
        (variant_path / 'EarnedEraRidingPricesPolicy.h').write_text(pricing)
        (variant_path / 'prices.cpp').write_text(source)
        executable = variant_path / 'prices'
        subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-g',
                        '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-no-pie',
                        str(variant_path / 'prices.cpp'), '-o', str(executable)], check=True)
        return run_fixture([str(executable)])

    for (name, *_, expected_failure), result in zip(variants, in_parallel(build_and_run, variants)):
        if expected_failure is None:
            print(result.stdout + result.stderr, end='')
            assert result.returncode == 0, name
        else:
            assert result.returncode != 0 and expected_failure in result.stderr, result
            print(name + ': the unsafe variant fails its riding-price regression as expected')
