"""Check that Raid Clear grants no aura, object state or cheat outside natural progression gates."""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

from FixtureSupport import (
    REPOSITORY,
    cxx,
    function,
    prepared_core,
    reject_mutants,
    run_fixture,
    source_argument,
)


# Calls that change the world for a bot instead of letting it play: free auras,
# forced object states, relocation, items, health, immunity and cheat masks.
SHORTCUTS = re.compile(r'\b(AddAura|SetGoState|TeleportTo|NearTeleportTo|AddItem|StoreNewItem|ModifyMoney|SetHealth|'
                       r'SetFullHealth|ResurrectPlayer|ApplySpellImmune|HasCheat|SetSpeed|DealDamage|Kill|'
                       r'learnSpell|RemoveAurasDueToSpell)\s*\(')
# The refusal leaves the function before the shortcut can run.
GATE = re.compile(r'if \(sPlayerbotAIConfig\.naturalProgression\)\s*return\b')
BWL = 'Raids/BlackwingLair/BwlRaidClear.cpp'
ZG = 'Raids/ZulGurub/ZgRaidClear.cpp'
CHARMED = 'Common/Charmed.cpp'
DISCIPLINE = 'Common/RaidDiscipline.cpp'
# Each reviewed shortcut and the function that must refuse it under natural progression.
REVIEWED = {
    (BWL, 'HasCheat'): 'bool MayDisarm(PlayerbotAI* botAI, Player* bot)',
    (BWL, 'SetGoState'): 'bool RcBwlDisarmSuppressionAction::Execute(',
    (BWL, 'AddAura'): 'void OnPlayerResurrect(',
    (DISCIPLINE, 'learnSpell'): 'void TeachRaidSpells(Player* bot)',
    (CHARMED, 'RemoveAurasDueToSpell'): 'bool RcControlCharmedAction::Execute(',
}
# Each mutation adds an unreviewed shortcut or turns a refusal into a no-op.
MUTATIONS = (
    ('ungated aura next to a reviewed one', BWL, 'bool RcBwlSuppressionDeviceTrigger::IsActive()\n{\n',
     'bool RcBwlSuppressionDeviceTrigger::IsActive()\n{\n    bot->AddAura(12345, bot);\n'),
    ('cloak refusal that only logs', BWL, 'if (sPlayerbotAIConfig.naturalProgression)\n            return;',
     'if (sPlayerbotAIConfig.naturalProgression)\n            LOG_DEBUG("module", "natural progression");'),
    ('device state change without a refusal', BWL,
     '    if (sPlayerbotAIConfig.naturalProgression)\n        return false;\n    std::list<GameObject*> armed;',
     '    std::list<GameObject*> armed;'),
)


def audit(sources):
    """The first problem in Raid Clear's {relative path: source}, or None."""
    found = set()
    for relative, text in sorted(sources.items()):
        text = re.sub(r'//[^\n]*', '', text)
        for match in SHORTCUTS.finditer(text):
            call = match.group(1)
            signature = REVIEWED.get((relative, call))
            start = text.find(signature) if signature else -1
            if start < 0 or not start <= match.start() < start + len(function(text, signature)):
                return f'Unreviewed Raid Clear shortcut {call} in {relative}'
            found.add((relative, call))
    for (relative, call), signature in REVIEWED.items():
        if (relative, call) not in found:
            return f'Reviewed Raid Clear shortcut disappeared; update this audit: {call} in {relative}'
        body = function(re.sub(r'//[^\n]*', '', sources[relative]), signature)
        if call == 'RemoveAurasDueToSpell':
            # Both the trigger and action use this selection; run it below to
            # check the refusal and the core's caster ownership contract.
            body = function(sources[relative], 'std::vector<std::pair<Player*, uint32>> ControlsToLetGo(')
            call = 'GetGroup'
        gate = GATE.search(body)
        if not gate or gate.start() > body.find(call + '('):
            return f'{call} in {signature} is not refused under natural progression'
    return None


HARNESS = r'''
#include <array>
#include <cassert>
#include <cstdint>
#include <map>
#include <string>
#include <vector>
using uint8=uint8_t; using uint32=uint32_t; using int32=int32_t;
enum Classes { CLASS_HUNTER=3, CLASS_PALADIN=2, CLASS_MAGE=8 };
enum AuraType { SPELL_AURA_MOD_CONFUSE, SPELL_AURA_MOD_STUN, SPELL_AURA_MOD_CHARM, SPELL_AURA_MOD_POSSESS, SPELL_AURA_AOE_CHARM };
constexpr uint32 UNIT_STATE_CONTROLLED=1, SPELL_TRANQUILIZING_SHOT=19801;
constexpr uint8 TRANQUILIZING_SHOT_LEVEL=60;
struct { bool naturalProgression=true; } sPlayerbotAIConfig;
struct { bool teachTranquilizingShot=true; } config;
auto const& GetConfig() { return config; }
struct AuraEffect { uint32 id, caster; int32 duration=10000; uint32 GetId()const{return id;} uint32 GetCasterGUID()const{return caster;} AuraEffect const* GetBase()const{return this;} int32 GetDuration()const{return duration;} };
struct Group;
struct Player {
 uint32 guid, klass=CLASS_MAGE; uint8 level=60; bool alive=true,charmed=false,controlled=true,inMap=true,inCombat=true,los=true,knows=false; float distance=5;
 uint32 learned=0; Group* group=nullptr; std::map<AuraType,std::vector<AuraEffect const*>> effects; std::vector<std::pair<uint32,uint32>> removed;
 uint32 GetGUID()const{return guid;} uint32 getClass()const{return klass;} bool IsClass(uint32 c)const{return klass==c;} uint8 GetLevel()const{return level;}
 bool HasSpell(uint32)const{return knows;} void learnSpell(uint32 id){assert(id==SPELL_TRANQUILIZING_SHOT);++learned;knows=true;}
 Group* GetGroup()const{return group;} bool IsAlive()const{return alive;} bool IsCharmed()const{return charmed;} bool IsInMap(Player const*)const{return inMap;}
 bool IsInCombat()const{return inCombat;} bool HasUnitState(uint32)const{return controlled;} float GetDistance(Player const* p)const{return p->distance;} bool IsWithinLOSInMap(Player const* p)const{return p->los;}
 auto const& GetAuraEffectsByType(AuraType type)const{static std::vector<AuraEffect const*> empty;auto i=effects.find(type);return i==effects.end()?empty:i->second;}
 void RemoveAurasDueToSpell(uint32 id,uint32 caster){removed.emplace_back(id,caster);}
};
struct GroupReference { Player* player; GroupReference* nextRef=nullptr; Player* GetSource(){return player;} GroupReference* next(){return nextRef;} };
struct Group { GroupReference* first=nullptr; GroupReference* GetFirstMember(){return first;} };
struct PlayerbotAIBase { uint32 nextAICheckDelay=0; void SetNextCheckDelay(uint32 const delay); void ResetActionDuration(); bool CanUpdateAI(); };
struct PlayerbotAI : PlayerbotAIBase {
 bool canCast=true,canPay=true,cast=true; uint32 casts=0; std::string spell; Player* target=nullptr;
 uint32 interruptRequests=0; void RequestSpellInterrupt(){++interruptRequests;}
 bool CanCastSpell(char const*,Player*)const{return canCast;} bool CastSpell(char const* name,Player* member){++casts;spell=name;target=member;return cast;}
};
namespace RaidClear { bool CanPayFor(PlayerbotAI* ai,Player*,char const*){return ai->canPay;} }
bool claimed=false; uint32 claims=0,drops=0;
bool ControlClaimedByOther(Player const*,Player const*){return claimed;}
void ClaimControl(Player const*,Player const*){++claims;}
void DropControlClaim(Player const*){++drops;}
struct Event {};
struct RcCharmedMemberTrigger { Player* bot; PlayerbotAI* botAI; bool IsActive(); };
struct RcControlCharmedAction { Player* bot; PlayerbotAI* botAI; bool Execute(Event); };
#include "production.inc"
int main() {
 // A customized teaching option never grants the spell in natural mode.
 Player hunter{1};hunter.klass=CLASS_HUNTER;TeachRaidSpells(&hunter);assert(hunter.learned==0);
 sPlayerbotAIConfig.naturalProgression=false;TeachRaidSpells(&hunter);assert(hunter.learned==1);TeachRaidSpells(&hunter);assert(hunter.learned==1);
 hunter.knows=false;config.teachTranquilizingShot=false;TeachRaidSpells(&hunter);assert(hunter.learned==1);config.teachTranquilizingShot=true;
 hunter.level=59;TeachRaidSpells(&hunter);assert(hunter.learned==1);hunter.level=60;hunter.klass=CLASS_MAGE;TeachRaidSpells(&hunter);assert(hunter.learned==1);
 Player bot{10},ally{11},foreignAlly{12},dead{13},elsewhere{14};PlayerbotAI ai;
 AuraEffect own{118,10},foreign{118,99},stun{853,10};ally.effects[SPELL_AURA_MOD_CONFUSE]={&own,&foreign};ally.effects[SPELL_AURA_MOD_STUN]={&stun};
 foreignAlly.effects[SPELL_AURA_MOD_CONFUSE]={&foreign};dead.effects[SPELL_AURA_MOD_STUN]={&stun};dead.alive=false;elsewhere.effects[SPELL_AURA_MOD_STUN]={&stun};elsewhere.inMap=false;
 GroupReference otherMap{&elsewhere},corpse{&dead,&otherMap},otherCaster{&foreignAlly,&corpse},member{&ally,&otherCaster},self{&bot,&member};Group group{&self};bot.group=&group;
 RcCharmedMemberTrigger trigger{&bot,&ai};RcControlCharmedAction action{&bot,&ai};
 // Natural mode leaves even this bot's own hostile CC until it expires.
 sPlayerbotAIConfig.naturalProgression=true;assert(ControlsToLetGo(&bot).empty());assert(!trigger.IsActive());assert(!action.Execute({}));assert(ally.removed.empty()&&foreignAlly.removed.empty());
 // The upstream option still releases only this caster's CC outside natural mode.
 sPlayerbotAIConfig.naturalProgression=false;assert(ControlsToLetGo(&bot).size()==2);assert(trigger.IsActive());assert(!action.Execute({}));
 assert((ally.removed==std::vector<std::pair<uint32,uint32>>{{118,10},{853,10}}));assert(foreignAlly.removed.empty()&&dead.removed.empty()&&elsewhere.removed.empty());ally.removed.clear();
 ally.charmed=true;assert(ControlsToLetGo(&bot).empty());ally.controlled=false;AuraEffect charm{24327,99,10000};ally.effects[SPELL_AURA_MOD_CHARM]={&charm};
 // Normal paid casts to control a charmed member remain available in natural mode.
 sPlayerbotAIConfig.naturalProgression=true;assert(trigger.IsActive());assert(action.Execute({}));assert(ai.casts==1&&ai.spell=="polymorph"&&ai.target==&ally);assert(ally.removed.empty()&&claims==1);
 ai.canPay=false;assert(!trigger.IsActive());assert(!action.Execute({}));assert(ai.casts==1);ai.canPay=true;
 ally.controlled=true;assert(!trigger.IsActive());ally.controlled=false;
 claimed=true;assert(!trigger.IsActive());claimed=false;
 ai.canCast=false;assert(!trigger.IsActive());ai.canCast=true;
 ai.cast=false;assert(!action.Execute({}));assert(drops==1);
 // Every raid danger hook wakes the pinned AI scheduler after requesting the
 // ordinary spell interruption; it does not advance time or clear a spell/GCD.
 uint32 requests=ai.interruptRequests;
 for(auto wake:{WakeRaidBot0,WakeRaidBot1,WakeRaidBot2,WakeRaidBot3,WakeRaidBot4,WakeRaidBot5,WakeRaidBot6}) {
  ai.SetNextCheckDelay(5000);assert(!ai.CanUpdateAI());wake(&ai);
  assert(ai.CanUpdateAI()&&ai.interruptRequests==++requests);
 }
}
'''


def native_checks(sources):
    core = prepared_core()
    effects = (core / 'src/server/game/Spells/Auras/SpellAuraEffects.h').read_text()
    assert 'ObjectGuid GetCasterGUID() const { return GetBase()->GetCasterGUID(); }' in effects
    remove = function((core / 'src/server/game/Entities/Unit/Unit.cpp').read_text(),
                      'void Unit::RemoveAurasDueToSpell(')
    assert '(!casterGUID || aura->GetCasterGUID() == casterGUID)' in remove
    playerbots = core / 'modules/mod-playerbots/src'
    base = (playerbots / 'Bot/Engine/PlayerbotAIBase.cpp').read_text()
    ai = (playerbots / 'Bot/PlayerbotAI.cpp').read_text()
    interrupt = function(ai, 'void PlayerbotAI::RequestSpellInterrupt()')
    assert 'SPELL_STATE_PREPARING' in interrupt and 'CURRENT_CHANNELED_SPELL' in interrupt
    assert 'spellInterruptRequested = true;' in interrupt and 'InterruptSpell(' not in interrupt
    update = function(ai, 'void PlayerbotAI::UpdateAI(')
    assert update.index('if (!CanUpdateAI())') < update.index('if (spellInterruptRequested)')
    assert 'bot->InterruptSpell(currentSpell->GetCurrentContainer());' in update
    wakeups = []
    for index, relative in enumerate(('Raids/BlackwingLair/BwlPositions.cpp', 'Raids/MoltenCore/McRaidClear.cpp',
                                      'Raids/OnyxiasLair/OnyRaidClear.cpp', ZG,
                                      'Raids/AhnQiraj/AqRaidClear.cpp', 'Raids/AhnQiraj/Aq40TwinEmperors.cpp',
                                      'Raids/AhnQiraj/Aq40Skeram.cpp')):
        text = sources[relative]
        calls = re.findall(r'(?:botAI|nearestCasting)->RequestSpellInterrupt\(\);\s*'
                           r'(?:botAI|nearestCasting)->ResetActionDuration\(\);', text)
        assert len(calls) == 1, f'{relative} must wake the pinned AI scheduler after requesting interruption'
        wake = calls[0].replace('nearestCasting->', 'botAI->')
        wakeups.append(f'void WakeRaidBot{index}(PlayerbotAI* botAI) {{ {wake} }}')
    charmed = sources[CHARMED]
    # Compile the changed functions and their real trigger, action and member
    # selection. Aura-effect ownership and removal match the native contract.
    controls = charmed[charmed.index('    struct Control\n'):charmed.index('    struct ControlClaim\n')]
    production = controls + '\n'.join(function(text, signature) for text, signature in (
        (base, 'void PlayerbotAIBase::SetNextCheckDelay('), (base, 'void PlayerbotAIBase::ResetActionDuration()'),
        (base, 'bool PlayerbotAIBase::CanUpdateAI()'),
        (sources[DISCIPLINE], 'void TeachRaidSpells(Player* bot)'),
        (charmed, 'int32 CharmLeftMs('), (charmed, 'Player* MemberToControl('),
        (charmed, 'std::vector<std::pair<Player*, uint32>> ControlsToLetGo('),
        (charmed, 'bool ControlsCharmed('), (charmed, 'bool RcCharmedMemberTrigger::IsActive()'),
        (charmed, 'bool RcControlCharmedAction::Execute('),
    )) + '\n' + '\n'.join(wakeups)
    with tempfile.TemporaryDirectory(prefix='raid-clear-earned-') as directory:
        work = Path(directory)
        (work / 'fixture.cpp').write_text(HARNESS)
        (work / 'production.inc').write_text(production)

        def build(tree, output):
            return [cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-Wno-missing-field-initializers',
                    str(tree / 'fixture.cpp'), '-o', str(output)]

        executable = work / 'fixture'
        subprocess.run(build(work, executable), check=True)
        result = run_fixture([str(executable)])
        if result.returncode:
            raise SystemExit(result.stdout + result.stderr)
        reject_mutants(work, (
            ('free spell teaching', 'production.inc',
             'if (sPlayerbotAIConfig.naturalProgression)\n            return;', ''),
            ('free release of the bot\'s own CC', 'production.inc',
             'if (sPlayerbotAIConfig.naturalProgression)\n            return spells;', ''),
            ('release of another caster\'s CC', 'production.inc',
             'effect->GetCasterGUID() == bot->GetGUID()', 'true'),
            ('removal without caster ownership', 'production.inc',
             'RemoveAurasDueToSpell(spellId, bot->GetGUID())', 'RemoveAurasDueToSpell(spellId, 0)'),
            ('raid danger leaves the bot asleep', 'production.inc',
             'botAI->ResetActionDuration();', 'botAI->SetNextCheckDelay(5000);'),
        ), build, 'Raid Clear earned play')


def main():
    parser = argparse.ArgumentParser()
    source_argument(parser, help='mod-raid-clear/src to check instead of the prepared one')
    args = parser.parse_args()
    source = args.source or prepared_core() / 'modules/mod-raid-clear/src'
    if not source.is_dir():
        raise SystemExit('PrepareModules.cmake must prepare mod-raid-clear first')
    sources = {path.relative_to(source).as_posix(): path.read_text() for path in source.rglob('*.[ch]*')}
    problem = audit(sources)
    if problem:
        raise SystemExit(problem)
    for label, relative, old, new in MUTATIONS:
        if sources[relative].count(old) != 1:
            raise SystemExit(f'{label} mutation was not applied')
        if not audit({**sources, relative: sources[relative].replace(old, new)}):
            raise SystemExit(f'Raid Clear audit did not reject the {label} mutation')
    native_checks(sources)
    profile = (REPOSITORY / 'cmd/startup/profiles/playerbots.conf').read_text()
    if not re.search(r'^Playerbots\.ApplyInstanceStrategies\s*=\s*1\s*$', profile, re.MULTILINE):
        raise SystemExit('Raid Clear needs playerbots instance strategies enabled in the portable profile')
    profile = (REPOSITORY / 'cmd/startup/profiles/mod_raid_clear.conf').read_text()
    assert re.search(r'^RaidClear\.Bots\.TeachTranquilizingShot\s*=\s*0\s*$', profile, re.MULTILINE)
    print('Raid Clear earned play: disarm cheats, forced device states, free cloak auras, spell grants and '
          'free CC release refused; native casts preserved and every audit/behaviour mutation rejected')


if __name__ == '__main__':
    main()
