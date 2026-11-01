"""Exercise real hunter taming selection, movement and casting with native-shaped pets.

The production action, trigger and strategy run against small engine adapters.
Core contracts establish that saved pets survive login and Tame Beast uses the
ordinary checked channel and persistence path. Mutants remove earned-play gates.
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
    source_argument,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, help='Playerbots src directory')
args = parser.parse_args()
core = prepared_core(Path(__file__).resolve().parents[2])
module = args.source or core / 'modules/mod-playerbots/src'
hunter = module / 'Ai/Class/Hunter'
actions = (hunter / 'HunterActions.cpp').read_text()
action_header = (hunter / 'HunterActions.h').read_text()
triggers = (hunter / 'HunterTriggers.cpp').read_text()
trigger_header = (hunter / 'HunterTriggers.h').read_text()
context = (hunter / 'HunterAiObjectContext.cpp').read_text()
strategy = (hunter / 'Strategy/GenericHunterNonCombatStrategy.cpp').read_text()
pet_defines = (core / 'src/server/game/Entities/Pet/PetDefines.h').read_text()
player_source = (core / 'src/server/game/Entities/Player/Player.cpp').read_text()
spell_effects = (core / 'src/server/game/Spells/SpellEffects.cpp').read_text()
spell_scripts = (core / 'src/server/scripts/Spells/spell_hunter.cpp').read_text()

# PetStable is the real shape loaded from character_pet, including unsummoned pets.
loader = function(player_source, 'void Player::_LoadPetStable(')
for assignment in ('m_petStable->CurrentPet = std::move(petInfo);',
                   'm_petStable->StabledPets[slot - 1] = std::move(petInfo);',
                   'm_petStable->UnslottedPets.push_back(std::move(petInfo));'):
    assert assignment in loader, assignment
native_cast = function((module / 'Bot/PlayerbotAI.cpp').read_text(),
                       'bool PlayerbotAI::CastSpell(uint32 spellId, Unit* target, Item* itemTarget)')
assert 'new Spell(bot, spellInfo, TRIGGERED_NONE)' in native_cast
native_tame = function(spell_scripts, 'class spell_hun_tame_beast')
for gate in ('target->GetLevel() > player->GetLevel()',
             'target->GetCreatureTemplate()->IsTameable(player->CanTameExoticPets())',
             'petStable->CurrentPet', 'petStable->GetUnslottedHunterPet()',
             'player->GetCharmGUID()', 'target->GetOwnerGUID()'):
    assert gate in native_tame, gate
effect = function(spell_effects, 'void Spell::EffectTameCreature(')
for step in ('CreateTamedPetFrom(creatureTarget, m_spellInfo->Id)',
             'creatureTarget->DespawnOrUnsummon();', 'unitCaster->SetMinion(pet, true);',
             'pet->SavePetToDB(PET_SAVE_AS_CURRENT);'):
    assert step in effect, step

for registration in (
        'creators["hunter needs pet"] = &HunterTriggerFactoryInternal::hunter_needs_pet;',
        'return new HunterNeedsPetTrigger(botAI);',
        'creators["tame beast"] = &HunterAiObjectContextInternal::tame_beast;',
        'return new TameBeastAction(botAI);'):
    assert registration in context, registration

nearby = (module / 'Ai/Base/Value/NearestNpcsValue.cpp').read_text()
assert 'Acore::AnyUnitInObjectRangeCheck' in function(nearby, 'void NearestNpcsValue::FindUnits(')
assert 'return !unit->IsPlayer();' in function(nearby, 'bool NearestNpcsValue::AcceptUnit(')
assert 'creators["nearest npcs"] = &ValueContext::nearest_npcs;' in (module / 'Ai/Base/ValueContext.h').read_text()

production = {
    'types': '\n'.join((function(pet_defines, 'enum PetType : uint8') + ';',
                        re.search(r'constexpr auto MAX_PET_STABLES = \d+;', pet_defines).group(),
                        function(pet_defines, 'class PetStable') + ';')),
    'classes': '\n'.join((function(action_header, 'class TameBeastAction :') + ';',
                          function(trigger_header, 'class HunterNeedsPetTrigger :') + ';')),
    'needed': function(actions, 'bool TameBeastAction::CanAcquirePet('),
    'known': function(actions, 'bool TameBeastAction::IsNeeded('),
    'execute': function(actions, 'bool TameBeastAction::Execute('),
    'trigger': function(triggers, 'bool HunterNeedsPetTrigger::IsActive()'),
    'strategy': function(strategy, 'void HunterPetStrategy::InitTriggers('),
}
assert re.search(r'constexpr uint32 SPELL_TAME_BEAST = 1515;', actions)
assert re.search(r'constexpr uint32 SPELL_FEED_PET = 6991;', actions)
assert re.search(r'constexpr uint32 SPELL_REVIVE_PET = 982;', actions)
for forbidden in ('CreateTamedPetFrom', 'CreateBaseAtCreature', 'RemovePet(', 'SetHealth(',
                  'SetHappiness', 'learnSpell(', 'TeleportTo(', 'SetPosition(', 'Relocate('):
    assert forbidden not in production['execute'], forbidden

prelude = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <functional>
#include <iostream>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <utility>
#include <vector>
using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
template<class T> using Optional = std::optional<T>;
enum ReactStates : uint8 { REACT_PASSIVE };
@@TYPES@@
constexpr uint32 CLASS_HUNTER = 3, SPELL_TAME_BEAST = 1515;
constexpr uint32 SPELL_FEED_PET = 6991, SPELL_REVIVE_PET = 982;
constexpr int UNIT_STATE_LOST_CONTROL = 1, CURRENT_CHANNELED_SPELL = 1;
constexpr float ACTION_NORMAL = 10.0f;
struct ObjectGuid {
    uint32 value = 0;
    explicit operator bool() const { return value != 0; }
};
using GuidVector = std::vector<ObjectGuid>;
struct Spell {};
struct Event {};
struct Map { bool dungeon = false; bool IsDungeon() const { return dungeon; } };
struct Session { bool headless = true; bool IsHeadless() const { return headless; } };
struct Creature;
struct Unit {
    virtual ~Unit() = default;
    virtual Creature* ToCreature() { return nullptr; }
};
struct CreatureTemplate {
    bool tameable = true, exotic = false;
    bool IsTameable(bool canExotic) const { return tameable && (!exotic || canExotic); }
};
enum PathType { PATHFIND_NORMAL = 1, PATHFIND_NOPATH = 2, PATHFIND_INCOMPLETE = 4,
                PATHFIND_NOT_USING_PATH = 8 };
struct Creature : Unit {
    bool inWorld = true, removing = false, alive = true, sameMap = true, samePhase = true,
         pet = false, summon = false, combat = false, loot = false, attackable = true,
         visible = true, los = true, path = true;
    uint32 level = 10;
    ObjectGuid owner, charmer;
    CreatureTemplate proto;
    float x = 10.0f;
    PathType pathType = PATHFIND_NORMAL;
    Creature* ToCreature() override { return this; }
    bool IsInWorld() const { return inWorld; }
    bool IsDuringRemoveFromWorld() const { return removing; }
    bool IsAlive() const { return alive; }
    bool IsPet() const { return pet; }
    bool IsSummon() const { return summon; }
    ObjectGuid GetOwnerGUID() const { return owner; }
    ObjectGuid GetCharmerGUID() const { return charmer; }
    bool IsInCombat() const { return combat; }
    bool hasLootRecipient() const { return loot; }
    uint32 GetLevel() const { return level; }
    CreatureTemplate const* GetCreatureTemplate() const { return &proto; }
    float GetPositionX() const { return x; }
    float GetPositionY() const { return 0; }
    float GetPositionZ() const { return 0; }
};
struct Player {
    uint32 cls = CLASS_HUNTER, level = 10, temporaryPet = 0;
    bool random = true, hasSession = true, group = false, alive = true, inWorld = true,
         teleport = false, battleground = false, arena = false, combat = false,
         mounted = false, flight = false, flying = false, transport = false, vehicle = false,
         lostControl = false, casting = false, knowsTame = true, knowsFeed = true, knowsRevive = true,
         pet = false, exotic = false;
    Map map;
    Session session;
    ObjectGuid petGuid, charmGuid;
    std::unique_ptr<PetStable> stable;
    Spell channel;
    int stops = 0;
    uint32 getClass() const { return cls; }
    Session* GetSession() { return hasSession ? &session : nullptr; }
    bool GetGroup() const { return group; }
    bool IsAlive() const { return alive; }
    bool IsInWorld() const { return inWorld; }
    bool IsBeingTeleported() const { return teleport; }
    Map* GetMap() { return &map; }
    bool InBattleground() const { return battleground; }
    bool InArena() const { return arena; }
    bool IsInCombat() const { return combat; }
    bool IsMounted() const { return mounted; }
    bool IsInFlight() const { return flight; }
    bool IsFlying() const { return flying; }
    bool GetTransport() const { return transport; }
    bool GetVehicle() const { return vehicle; }
    bool HasUnitState(int state) const { assert(state == UNIT_STATE_LOST_CONTROL); return lostControl; }
    bool IsNonMeleeSpellCast(bool skip) const { assert(skip); return casting; }
    bool HasSpell(uint32 spell) const {
        if (spell == SPELL_TAME_BEAST) return knowsTame;
        if (spell == SPELL_FEED_PET) return knowsFeed;
        assert(spell == SPELL_REVIVE_PET); return knowsRevive;
    }
    bool GetPet() const { return pet; }
    ObjectGuid GetPetGUID() const { return petGuid; }
    ObjectGuid GetCharmGUID() const { return charmGuid; }
    uint32 GetTemporaryUnsummonedPetNumber() const { return temporaryPet; }
    PetStable const* GetPetStable() const { return stable.get(); }
    bool IsInMap(Creature* c) const { return c->sameMap; }
    bool InSamePhase(Creature* c) const { return c->samePhase; }
    uint32 GetLevel() const { return level; }
    bool CanTameExoticPets() const { return exotic; }
    bool IsValidAttackTarget(Creature* c) const { return c->attackable; }
    bool CanSeeOrDetect(Creature* c) const { return c->visible; }
    bool IsWithinLOSInMap(Creature* c) const { return c->los; }
    float GetDistance(Creature* c) const { return std::abs(c->x); }
    bool IsWithinDistInMap(Creature* c, float range) const { return GetDistance(c) <= range; }
    void StopMoving() { ++stops; }
    Spell* GetCurrentSpell(int slot) { assert(slot == CURRENT_CHANNELED_SPELL); return &channel; }
};
struct Config { bool naturalProgression = true; float SightDistance = 100.0f; } sPlayerbotAIConfig;
struct RandomMgr { bool IsRandomBot(Player* p) const { return p->random; } } sRandomPlayerbotMgr;
struct SpellInfo {
    float range = 30.0f;
    float GetMaxRange(bool positive, Player*) const { assert(!positive); return range; }
};
struct SpellMgr {
    bool available = true;
    SpellInfo info;
    SpellInfo const* GetSpellInfo(uint32 id) const {
        assert(id == SPELL_TAME_BEAST); return available ? &info : nullptr;
    }
} spellMgr;
auto* sSpellMgr = &spellMgr;
struct Context { GuidVector nearby; };
#define AI_VALUE(type, name) (context->nearby)
struct PlayerbotAI {
    Player* bot;
    Context context;
    bool master = false, castResult = true, moveResult = true;
    int scans = 0, casts = 0, waits = 0, moves = 0;
    Unit* castTarget = nullptr;
    Creature* moveTarget = nullptr;
    float moveRange = 0;
    std::map<uint32, Unit*> units;
    Player* GetBot() const { return bot; }
    bool GetMaster() const { return master; }
    Unit* GetUnit(ObjectGuid guid) { ++scans; return units.contains(guid.value) ? units.at(guid.value) : nullptr; }
    bool CastSpell(uint32 id, Unit* target) {
        assert(id == SPELL_TAME_BEAST && target && bot->stops); ++casts; castTarget = target; return castResult;
    }
    void WaitForSpellCast(Spell* spell) { assert(spell == &bot->channel); ++waits; }
};
struct MovementAction {
    PlayerbotAI* botAI;
    Player* bot;
    Context* context;
    std::string name;
    MovementAction(PlayerbotAI* ai, std::string name) : botAI(ai), bot(ai->bot), context(&ai->context),
                                                     name(std::move(name)) {}
    virtual ~MovementAction() = default;
    virtual bool isUseful() { return true; }
    virtual bool Execute(Event) { return false; }
    bool MoveTo(Creature* target, float range) {
        ++botAI->moves; botAI->moveTarget = target; botAI->moveRange = range; return botAI->moveResult;
    }
};
struct Trigger {
    PlayerbotAI* botAI;
    std::string name;
    int interval;
    Trigger(PlayerbotAI* ai, std::string name, int interval) : botAI(ai), name(std::move(name)), interval(interval) {}
    virtual ~Trigger() = default;
    virtual bool IsActive() { return false; }
};
std::vector<Creature*> pathCreatures;
int pathCalls = 0;
struct PathGenerator {
    Creature* target = nullptr;
    explicit PathGenerator(Player*) {}
    bool CalculatePath(float x, float y, float z, bool force) {
        assert(!force && y == 0 && z == 0); ++pathCalls;
        for (Creature* c : pathCreatures) if (c->x == x) { target = c; return c->path; }
        assert(false); return false;
    }
    PathType GetPathType() const { assert(target); return target->pathType; }
};
struct NextAction {
    std::string name;
    float relevance;
    NextAction(std::string name, float relevance) : name(std::move(name)), relevance(relevance) {}
};
struct TriggerNode {
    std::string name;
    std::vector<NextAction> actions;
    TriggerNode(std::string name, std::vector<NextAction> actions) : name(std::move(name)), actions(std::move(actions)) {}
};
struct HunterPetStrategy { void InitTriggers(std::vector<TriggerNode*>&); };
@@CLASSES@@
@@NEEDED@@
@@KNOWN@@
@@EXECUTE@@
@@TRIGGER@@
@@STRATEGY@@
'''

tests = r'''
struct Scenario {
    Player bot;
    PlayerbotAI ai{&bot};
    TameBeastAction action{&ai};
    HunterNeedsPetTrigger trigger{&ai};
    Creature beast;
    Scenario() {
        sPlayerbotAIConfig = {}; spellMgr = {}; pathCalls = 0; pathCreatures = {&beast};
        ai.units[1] = &beast; ai.context.nearby = {{1}};
    }
    bool Run() { return action.Execute(Event{}); }
    void Refused() {
        assert(!action.isUseful() && !trigger.IsActive() && !Run());
        assert(ai.scans == 0 && ai.casts == 0 && ai.moves == 0 && bot.stops == 0);
    }
    void NoTarget() {
        assert(action.isUseful() && trigger.IsActive() && !Run());
        assert(ai.casts == 0 && ai.moves == 0 && bot.stops == 0);
    }
};
int main() {
    {
        Scenario s;
        assert(s.action.name == "tame beast" && s.trigger.name == "hunter needs pet" && s.trigger.interval == 5);
        assert(s.action.isUseful() && s.trigger.IsActive() && s.Run());
        assert(s.ai.castTarget == &s.beast && s.ai.casts == 1 && s.ai.waits == 1 && s.ai.moves == 0 && pathCalls == 0);
        // The action starts an ordinary channel; only the core effect may award a pet.
        assert(!s.bot.pet && !s.bot.petGuid && !s.bot.stable);
        s.ai.castResult = false;
        assert(!s.Run() && s.ai.casts == 2 && s.ai.waits == 1);
    }
    for (auto gate : std::vector<std::function<void(Scenario&)>>{
        [](auto&) { sPlayerbotAIConfig.naturalProgression = false; },
        [](auto& s) { s.bot.cls = 1; }, [](auto& s) { s.bot.random = false; },
        [](auto& s) { s.bot.hasSession = false; }, [](auto& s) { s.bot.session.headless = false; },
        [](auto& s) { s.ai.master = true; }, [](auto& s) { s.bot.group = true; },
        [](auto& s) { s.bot.alive = false; }, [](auto& s) { s.bot.inWorld = false; },
        [](auto& s) { s.bot.teleport = true; }, [](auto& s) { s.bot.map.dungeon = true; },
        [](auto& s) { s.bot.battleground = true; }, [](auto& s) { s.bot.arena = true; },
        [](auto& s) { s.bot.combat = true; }, [](auto& s) { s.bot.mounted = true; },
        [](auto& s) { s.bot.flight = true; }, [](auto& s) { s.bot.flying = true; },
        [](auto& s) { s.bot.transport = true; }, [](auto& s) { s.bot.vehicle = true; },
        [](auto& s) { s.bot.lostControl = true; }, [](auto& s) { s.bot.casting = true; },
        [](auto& s) { s.bot.knowsTame = false; }, [](auto& s) { s.bot.knowsFeed = false; },
        [](auto& s) { s.bot.knowsRevive = false; }, [](auto& s) { s.bot.pet = true; },
        [](auto& s) { s.bot.petGuid = {2}; }, [](auto& s) { s.bot.charmGuid = {2}; },
        [](auto& s) { s.bot.temporaryPet = 2; },
    }) { Scenario s; gate(s); s.Refused(); }
    {
        Scenario s; s.ai.bot = nullptr; s.Refused();
    }
    for (int slot = -2; slot < int(MAX_PET_STABLES); ++slot) {
        Scenario s; s.bot.stable = std::make_unique<PetStable>();
        PetStable::PetInfo owned; owned.PetNumber = 17; owned.Health = 0; owned.Type = HUNTER_PET;
        if (slot == -2) s.bot.stable->CurrentPet = owned;
        else if (slot == -1) s.bot.stable->UnslottedPets.push_back(owned);
        else s.bot.stable->StabledPets[slot] = owned;
        s.Refused();
        assert((slot == -2 ? s.bot.stable->CurrentPet->PetNumber :
                slot == -1 ? s.bot.stable->UnslottedPets[0].PetNumber :
                             s.bot.stable->StabledPets[slot]->PetNumber) == 17);
    }
    {
        Scenario s; s.bot.stable = std::make_unique<PetStable>(); assert(s.Run());
    }
    for (auto reject : std::vector<std::function<void(Scenario&)>>{
        [](auto&) { spellMgr.available = false; }, [](auto& s) { s.ai.context.nearby.clear(); },
        [](auto& s) { s.ai.units.clear(); }, [](auto& s) { s.beast.inWorld = false; },
        [](auto& s) { s.beast.removing = true; }, [](auto& s) { s.beast.alive = false; },
        [](auto& s) { s.beast.sameMap = false; }, [](auto& s) { s.beast.samePhase = false; },
        [](auto& s) { s.beast.pet = true; }, [](auto& s) { s.beast.summon = true; },
        [](auto& s) { s.beast.owner = {2}; }, [](auto& s) { s.beast.charmer = {2}; },
        [](auto& s) { s.beast.combat = true; }, [](auto& s) { s.beast.loot = true; },
        [](auto& s) { ++s.beast.level; }, [](auto& s) { s.beast.proto.tameable = false; },
        [](auto& s) { s.beast.proto.exotic = true; }, [](auto& s) { s.beast.attackable = false; },
        [](auto& s) { s.beast.visible = false; }, [](auto& s) { s.beast.los = false; },
        [](auto& s) { s.beast.x = sPlayerbotAIConfig.SightDistance + 1; },
    }) { Scenario s; reject(s); s.NoTarget(); }
    {
        Scenario s; Unit player; s.ai.units[1] = &player; s.NoTarget();
    }
    {
        Scenario s; s.beast.proto.exotic = true; s.bot.exotic = true; assert(s.Run());
    }
    for (PathType type : {PATHFIND_NORMAL, PATHFIND_NOPATH, PATHFIND_INCOMPLETE, PATHFIND_NOT_USING_PATH}) {
        Scenario s; s.beast.x = 50; s.beast.pathType = type;
        assert(s.Run() == (type == PATHFIND_NORMAL));
        assert(pathCalls == 1 && s.ai.casts == 0 && s.bot.stops == 0);
        if (type == PATHFIND_NORMAL) {
            assert(s.ai.moves == 1 && s.ai.moveTarget == &s.beast && s.ai.moveRange == spellMgr.info.range * 0.8f);
            s.ai.moveResult = false; assert(!s.Run() && s.ai.casts == 0);
        } else assert(s.ai.moves == 0);
    }
    {
        Scenario s; s.beast.x = 50; s.beast.path = false; s.NoTarget(); assert(pathCalls == 1);
    }
    {
        // A closer unreachable beast cannot conceal a farther reachable candidate.
        Scenario s; Creature second; s.beast.x = 40; s.beast.pathType = PATHFIND_INCOMPLETE; second.x = 50;
        pathCreatures.push_back(&second); s.ai.units[2] = &second; s.ai.context.nearby.push_back({2});
        assert(s.Run() && s.ai.moveTarget == &second && s.ai.casts == 0);
    }
    {
        Scenario s; Creature second; second.x = 20;
        s.ai.units[2] = &second; s.ai.context.nearby = {{2}, {1}};
        assert(s.Run() && s.ai.castTarget == &s.beast);
    }
    std::vector<TriggerNode*> nodes; HunterPetStrategy().InitTriggers(nodes);
    int matches = 0;
    for (TriggerNode* node : nodes) {
        if (node->name == "hunter needs pet") {
            ++matches;
            assert(node->actions.size() == 1 && node->actions[0].name == "tame beast" &&
                   node->actions[0].relevance == ACTION_NORMAL + 1);
        }
        delete node;
    }
    assert(matches == 1);
    std::cout << "Hunter taming: ownership, learned spell, live targets, reachable routes, native channel and strategy passed\n";
}
'''

path_calculation = re.search(
    r'!path\.CalculatePath\(creature->GetPositionX\(\), creature->GetPositionY\(\), '
    r'creature->GetPositionZ\(\),\s*false\)', production['execute']).group()

mutations = (
    ('natural mode required', 'needed', '!sPlayerbotAIConfig.naturalProgression || ', ''),
    ('random bots only', 'needed', '!sRandomPlayerbotMgr.IsRandomBot(bot) ||', ''),
    ('human clients excluded', 'needed', '!bot->GetSession()->IsHeadless() || ', ''),
    ('controlled companions excluded', 'needed', 'botAI->GetMaster() || ', ''),
    ('earned Tame Beast required', 'known', ' && botAI->GetBot()->HasSpell(SPELL_TAME_BEAST)', ''),
    ('earned Feed Pet required', 'known', 'botAI->GetBot()->HasSpell(SPELL_FEED_PET) && ', ''),
    ('earned Revive Pet required', 'known', ' && botAI->GetBot()->HasSpell(SPELL_REVIVE_PET)', ''),
    ('current companion retained', 'needed', 'stable->CurrentPet || ', ''),
    ('unslotted companion retained', 'needed', '!stable->UnslottedPets.empty()', 'false'),
    ('stabled companion retained', 'needed', 'if (pet)', 'if (false && pet)'),
    ('temporarily unsummoned companion retained', 'needed', 'bot->GetTemporaryUnsummonedPetNumber()', 'false'),
    ('execution revalidates ownership', 'execute', 'if (!isUseful())', 'if (false)'),
    ('foreign owned target rejected', 'execute', 'creature->GetOwnerGUID() || ', ''),
    ('claimed target rejected', 'execute', 'creature->hasLootRecipient() || ', ''),
    ('target fighting rejected', 'execute', 'creature->IsInCombat() ||', ''),
    ('higher-level beast rejected', 'execute', 'creature->GetLevel() > bot->GetLevel() ||', ''),
    ('exotic permission required', 'execute', 'IsTameable(bot->CanTameExoticPets())', 'IsTameable(true)'),
    ('hidden creature rejected', 'execute', '!bot->CanSeeOrDetect(creature) || ', ''),
    ('complete route required', 'execute', 'path.GetPathType() != PATHFIND_NORMAL', 'false'),
    ('failed path rejected', 'execute', path_calculation, '(false && ' + path_calculation + ')'),
    ('unreachable channel never started', 'execute', 'return MoveTo(target, range * 0.8f);', 'return true;'),
    ('ordinary cast result respected', 'execute', 'if (!botAI->CastSpell(SPELL_TAME_BEAST, target))',
     'if (botAI->CastSpell(SPELL_TAME_BEAST, target) && false)'),
    ('channel protected from ordinary actions', 'execute',
     'botAI->WaitForSpellCast(bot->GetCurrentSpell(CURRENT_CHANNELED_SPELL));', ''),
    ('trigger respects ownership', 'trigger', 'return TameBeastAction::IsNeeded(botAI);', 'return true;'),
    ('autonomous strategy enabled', 'strategy', '"hunter needs pet"', '"unused tame trigger"'),
)


def build(directory, parts, name):
    source = prelude
    for key, body in parts.items():
        source = source.replace('@@' + key.upper() + '@@', body)
    path = directory / (name + '.cpp')
    path.write_text(source + tests)
    executable = directory / name
    subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-Wno-missing-field-initializers',
                    *SANITIZER_FLAGS, str(path), '-o', str(executable)], check=True)
    return run_fixture([str(executable)])


with tempfile.TemporaryDirectory(prefix='portable-hunter-taming-') as temporary:
    temporary = Path(temporary)
    result = build(temporary, production, 'taming')
    print(result.stdout + result.stderr, end='')
    if result.returncode:
        raise SystemExit(f'Hunter taming fixture failed (exit {result.returncode})')

    def rejected(numbered):
        index, (label, key, old, new) = numbered
        match = re.search(r'\s+'.join(re.escape(token) for token in old.split()), production[key])
        if not match:
            raise SystemExit(f'{label} mutation was not applied')
        mutant = {**production, key: production[key].replace(match.group(), new)}
        result = build(temporary, mutant, f'mutant-{index}')
        return result.returncode != 0 and 'Assertion' in result.stderr

    for (label, *_), rejected_mutant in zip(mutations, in_parallel(rejected, enumerate(mutations))):
        if not rejected_mutant:
            raise SystemExit(f'Hunter taming fixture did not reject: {label}')
        print(f'Hunter taming mutation rejected: {label}')
