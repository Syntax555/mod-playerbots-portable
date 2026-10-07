"""Exercise strict earned progression production functions under ASan/UBSan.

The core fixtures supply reward eligibility, quest rewards and per-character
settings. Production functions decide which milestones and talents are allowed.
These isolated checks do not start a realm or replace the real-header build.
"""

import argparse
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
from PreparedSources import prepared_core


repo = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path,
                    default=prepared_core(repo) / 'modules/mod-individual-progression',
                    help='prepared Individual Progression module directory')
args = parser.parse_args()
module = args.source
production = (module / 'src/IndividualProgression.cpp').read_text()
player_source = (module / 'src/IndividualProgressionPlayer.cpp').read_text()
header = (module / 'src/IndividualProgression.h').read_text()
commands = (module / 'src/cs_individualProgression.cpp').read_text()


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


enums = '\n'.join(function(header, 'enum ' + name) + ';' for name in
                  ('ProgressionState', 'ProgressionBossIDs', 'ProgressionQuestIDs',
                   'ProgressionAchievements'))
functions = '\n'.join(function(production, signature) for signature in (
    'uint8 IndividualProgression::GetPlayerProgressionFromQuests(',
    'bool IndividualProgression::IsStrictDefaultProgression(',
    'bool IndividualProgression::HasStrictEarnedMilestone(',
    'bool IndividualProgression::IsEligibleStrictKill(',
    'void IndividualProgression::UpdateProgressionState(',
    'void IndividualProgression::checkIPProgression(',
    'void IndividualProgression::checkKillProgression(',
    'bool IndividualProgression::isExcludedAccount(',
    'bool IndividualProgression::isBotAccount(',
    'bool IndividualProgression::isNormalAccount(',
    'void IndividualProgression::UpdateRNDbotSpells(',
))
hooks = '\n'.join(function(player_source, signature).replace(' override', '')
                  for signature in ('    bool OnPlayerCanLearnTalent(',
                                    '    void OnPlayerCreatureKillCredit(',
                                    '    void OnPlayerCompleteQuest(',
                                    '    bool CanAccountCreateCharacter('))

# Keep the actual entry checks of commands/helpers that otherwise need a live
# database or inventory. A sentinel observes whether execution passes them.
guard_functions = []
for signature, boundary in (
    ('void IndividualProgression::SyncBotsProgressionToLeader(', '    if (!group)'),
    ('void IndividualProgression::UpdateGroupAttunement(', '    if (location.empty())'),
    ('void IndividualProgression::UpdateAccountReputation(', '    Group* group'),
):
    body = function(production, signature)
    unused = '    (void)group;\n' if 'SyncBots' in signature else (
        '    (void)location;\n' if 'Attunement' in signature else '')
    guard_functions.append(body[:body.index(boundary)] + unused + '    ++unguardedCalls;\n}')
command_guards = []
for signature in ('    static bool HandleSetBotIndividualProgressionCommand(',
                  '    static bool HandleSetRepIndividualProgressionCommand(',
                  '    static bool HandleAttuneIndividualProgressionCommand('):
    body = function(commands, signature)
    unused = '        (void)location;\n' if 'Attune' in signature else ''
    command_guards.append(body[:body.index('        Player* player =')] +
                          unused + '        ++unguardedCalls;\n        return true;\n    }')

prelude = r'''
#include <cassert>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <map>
#include <regex>
#include <set>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>
#include "StrictEarnedProgressionPolicy.h"
using uint8=std::uint8_t; using uint16=std::uint16_t; using uint32=std::uint32_t; using int32=std::int32_t;
constexpr int QUEST_STATUS_REWARDED=3, QUEST_STATUS_COMPLETE=2, CONFIG_GROUP_XP_DISTANCE=0;
constexpr int SEC_PLAYER=0, SEC_GAMEMASTER=2;
constexpr int COPPER=1, SILVER=100, GOLD=10000, RATE_REWARD_BONUS_MONEY=0;
constexpr uint8 RACE_DRAENEI=11, RACE_BLOODELF=10, CLASS_DEATH_KNIGHT=6,
    CLASS_DRUID=11, CLASS_PALADIN=2, CLASS_WARLOCK=9;
struct WorldObject {
    bool inWorld=true; uint32 map=1, instance=1, phase=1; float x=0, y=0, z=0;
};
struct Corpse : WorldObject {};
struct Session { uint32 account=1; int security=0;
    uint32 GetAccountId() const { return account; }
    int GetSecurity() const { return security; }
};
struct Quest { uint32 id=0; uint32 GetQuestId() const { return id; }
    int GetQuestLevel() const { return 60; } int XPValue(int) const { return 0; }
};
struct Player;
struct GroupReference { Player* player=nullptr; GroupReference* following=nullptr;
    Player* GetSource() const { return player; }
    GroupReference* next() const { return following; }
};
struct Group { std::vector<GroupReference> members;
    void SetMembers(std::initializer_list<Player*> players) {
        members.clear(); members.reserve(players.size());
        for (auto* player : players) members.push_back({player,nullptr});
        for (size_t i=0; i+1<members.size(); ++i) members[i].following=&members[i+1];
    }
    GroupReference* GetFirstMember() { return members.empty() ? nullptr : &members[0]; }
};
struct PlayerSetting { uint32 value=0; bool HasFlag(uint32 flag) const { return (value & flag)!=0; } };
struct Creature;
struct Player : WorldObject {
    Session session; bool alive=true, allowedReward=true, gm=false;
    Corpse* corpse=nullptr; Group* group=nullptr; uint8 cls=1; uint32 level=1;
    std::map<uint32,int> quests; std::map<std::pair<std::string,uint32>,uint32> settings;
    std::set<uint32> spells, achievements; std::vector<uint32> rewarded;
    int settingWrites=0, spellGrants=0;
    bool IsInWorld() const { return inWorld; } bool IsAlive() const { return alive; }
    bool IsGameMaster() const { return gm; } Corpse* GetCorpse() const { return corpse; }
    Session* GetSession() { return &session; } Group* GetGroup() const { return group; }
    bool IsAtLootRewardDistance(Creature*) const { return allowedReward; }
    int GetQuestStatus(uint32 id) const { auto it=quests.find(id); return it==quests.end()?0:it->second; }
    PlayerSetting GetPlayerSetting(std::string const& source,uint32 index) { return {settings[{source,index}]}; }
    void UpdatePlayerSetting(std::string const& source,uint32 index,uint32 value) {
        ++settingWrites; settings[{source,index}]=value;
    }
    void AddQuest(Quest const* quest,void*) { quests[quest->id]=1; }
    void CompleteQuest(uint32 id) { quests[id]=QUEST_STATUS_COMPLETE; }
    void RewardQuest(Quest const* quest,int,Player*,bool,bool) {
        quests[quest->id]=QUEST_STATUS_REWARDED; rewarded.push_back(quest->id);
    }
    bool HasAchieved(uint32 id) const { return achievements.contains(id); }
    uint8 getClass() const { return cls; } uint32 GetLevel() const { return level; }
    bool HasSpell(uint32 id) const { return spells.contains(id); }
    void learnSpell(uint32 id,bool) { ++spellGrants; spells.insert(id); }
    void ModifyMoney(int32) {} void RemoveRewardedQuest(uint32 id) { quests.erase(id); }
};
struct Creature : WorldObject {
    bool alive=false, damageEnough=true, disabledLoot=false; uint32 entry=11502;
    Player* tapped=nullptr; Group* tappedGroup=nullptr;
    bool IsInWorld() const { return inWorld; } bool IsAlive() const { return alive; }
    bool IsDamageEnoughForLootingAndReward() const { return damageEnough; }
    bool IsLootRewardDisabled() const { return disabledLoot; }
    bool isTappedBy(Player const* player) const { return tapped==player || (tappedGroup && tappedGroup==player->group); }
    bool IsWithinDistInMap(WorldObject const* other,float distance,bool threeD,bool ownReach,bool targetReach) const {
        assert(threeD && !ownReach && !targetReach);
        return map==other->map && instance==other->instance && (phase & other->phase) &&
            std::sqrt((x-other->x)*(x-other->x)+(y-other->y)*(y-other->y)+(z-other->z)*(z-other->z)) < distance;
    }
    uint32 GetEntry() const { return entry; } Group* GetLootRecipientGroup() { return tappedGroup; }
};
struct World { float getFloatConfig(int) const { return 100.f; } float getRate(int) const { return 1.f; } } world;
auto* sWorld=&world;
struct ObjectMgr {
    std::map<uint32,Quest> quests; std::set<uint32> unavailable;
    Quest const* GetQuestTemplate(uint32 id) {
        if (unavailable.contains(id)) return nullptr;
        return &quests.emplace(id,Quest{id}).first->second;
    }
} objects;
auto* sObjectMgr=&objects;
struct AccountMgr { inline static int queries=0;
    static bool GetName(uint32 account,std::string& name) {
        ++queries; name="RNDBOT"+std::to_string(account); return true;
    }
};
struct TalentEntry { uint32 Row=0; };
int unguardedCalls=0;
struct ChatHandler { Session* session=nullptr; int messages=0;
    Session* GetSession() const { return session; }
    void SendSysMessage(char const*) { ++messages; }
    template<class... Args> void PSendSysMessage(char const*,Args...) { ++messages; }
};
'''

declarations = r'''
struct IndividualProgression {
    bool enabled=true, strictEarnedProgression=true, disableDefaultProgression=false;
    bool questMoneyAtLevelCap=false, repeatableVanillaQuestsXp=false;
    uint8 progressionLimit=0, tbcRacesProgressionLevel=8, deathKnightProgressionLevel=13;
    std::map<uint32,uint8> customProgressionMap;
    std::string botAccountsRegex="RNDBOT.*", excludedAccountsRegex="RNDBOT.*";
    static std::map<uint32,uint8> accounts;
    static uint8 GetAccountProgression(uint32 account) { return accounts[account]; }
    uint8 GetPlayerProgressionFromQuests(Player*) const;
    bool IsStrictDefaultProgression() const;
    bool HasStrictEarnedMilestone(Player*,uint8) const;
    static bool IsEligibleStrictKill(Player*,Creature*);
    void UpdateProgressionState(Player*,ProgressionState) const;
    void checkIPProgression(Player*);
    void checkKillProgression(Player*,Creature*);
    bool isExcludedAccount(Player*);
    bool isBotAccount(Player*);
    bool isNormalAccount(Player*);
    bool hasPassedProgression(Player* player,ProgressionState stage) {
        return GetPlayerProgressionFromQuests(player)>=stage;
    }
    void UpdateRNDbotSpells(Player*);
    void SyncBotsProgressionToLeader(Group*);
    void UpdateGroupAttunement(Player*,std::string);
    void UpdateAccountReputation(uint32,uint32,Player*);
    void UpdateProgressionAchievements(Player* player,uint16 id) { player->achievements.insert(id); }
};
std::map<uint32,uint8> IndividualProgression::accounts;
IndividualProgression progression;
auto* sIndividualProgression=&progression;
'''

tests = r'''
void Credit(Player& player,uint8 stage) {
    uint32 const earned=player.GetPlayerSetting(StrictEarnedProgressionPolicy::SettingsSource,0).value;
    player.UpdatePlayerSetting(StrictEarnedProgressionPolicy::SettingsSource,0,
                              earned|StrictEarnedProgressionPolicy::BossCredit(stage));
}
uint8 Stage(Player& player) { return progression.GetPlayerProgressionFromQuests(&player); }
int main() {
    using namespace StrictEarnedProgressionPolicy;
    static_assert(NextStage(0)==1 && NextStage(10)==12 && NextStage(11)==12 && NextStage(18)==0);
    assert(BossStage(10184)==0 && BossStage(23863)==0 && BossCredit(4)==0 && BossCredit(11)==0);
    for (auto [entry,stage] : std::vector<std::pair<uint32,uint8>>{
        {RAGNAROS,1}, {ONYXIA_40,2}, {NEFARIAN,3}, {CTHUN,6}, {KELTHUZAD_40,7},
        {MALCHEZAAR,9}, {KAELTHAS,10}, {ILLIDAN,12}, {KILJAEDEN,13}, {KELTHUZAD,14},
        {YOGGSARON,15}, {ANUBARAK,16}, {LICH_KING,17}, {HALION,18}}) {
        assert(BossStage(entry)==stage && BossCredit(stage)==(uint32{1}<<stage));
    }
    Script hook;
    Player player;
    player.achievements.insert(HALION_KILL); // achievements never synthesize strict milestones
    progression.checkIPProgression(&player);
    assert(Stage(player)==0 && player.rewarded.empty());
    player.quests[INTO_THE_BREACH]=QUEST_STATUS_REWARDED;
    progression.checkIPProgression(&player);
    assert(Stage(player)==0); // an earned transition cannot skip Vanilla

    Creature boss; boss.entry=NEFARIAN; boss.tapped=&player;
    progression.checkKillProgression(&player,&boss);
    assert(Stage(player)==0 && player.rewarded.empty() && player.settingWrites==1);
    progression.checkKillProgression(&player,&boss);
    assert(player.settingWrites==1); // repeated kills do not rewrite unchanged credit
    Player reloaded;
    reloaded.settings=player.settings; reloaded.quests=player.quests;
    boss.tapped=&reloaded; boss.entry=RAGNAROS;
    progression.checkKillProgression(&reloaded,&boss);
    assert(Stage(reloaded)==1 && reloaded.rewarded==std::vector<uint32>{66001});
    boss.entry=ONYXIA_40;
    progression.checkKillProgression(&reloaded,&boss);
    assert(Stage(reloaded)==3 && reloaded.rewarded==std::vector<uint32>({66001,66002,66003}));
    assert(reloaded.GetQuestStatus(66000)!=QUEST_STATUS_REWARDED);
    assert(reloaded.GetQuestStatus(66011)!=QUEST_STATUS_REWARDED);
    reloaded.quests[SIMPLY_BANG_A_GONG]=QUEST_STATUS_COMPLETE;
    Quest gong{SIMPLY_BANG_A_GONG}; hook.OnPlayerCompleteQuest(&reloaded,&gong);
    assert(Stage(reloaded)==3); // objectives without turn-in are insufficient
    reloaded.quests[SIMPLY_BANG_A_GONG]=QUEST_STATUS_REWARDED;
    hook.OnPlayerCompleteQuest(&reloaded,&gong);
    assert(Stage(reloaded)==4);
    Credit(reloaded,6); Credit(reloaded,7);
    progression.checkIPProgression(&reloaded);
    assert(Stage(reloaded)==4);
    reloaded.quests[CHAOS_AND_DESTRUCTION]=QUEST_STATUS_REWARDED;
    Quest war{CHAOS_AND_DESTRUCTION}; hook.OnPlayerCompleteQuest(&reloaded,&war);
    assert(Stage(reloaded)==8);

    progression.progressionLimit=10;
    for (uint8 stage : {9,10,12,13,14,15,16,17,18}) Credit(reloaded,stage);
    progression.checkIPProgression(&reloaded);
    assert(Stage(reloaded)==10 && !reloaded.quests.contains(66011));
    progression.progressionLimit=0;
    progression.checkIPProgression(&reloaded);
    assert(Stage(reloaded)==18 && !reloaded.quests.contains(66011));
    assert(reloaded.rewarded.size()==17);
    progression.checkIPProgression(&reloaded);
    assert(reloaded.rewarded.size()==17);
    Player another; another.session.account=reloaded.session.account;
    progression.checkIPProgression(&another);
    assert(Stage(another)==0 && another.GetPlayerSetting(SettingsSource,0).value==0); // same account does not copy credit

    Player saved; saved.quests[66013]=QUEST_STATUS_REWARDED;
    progression.checkIPProgression(&saved);
    assert(Stage(saved)==13 && saved.rewarded.empty()); // preserve installed tiers/admin overrides
    Credit(saved,14); objects.unavailable.insert(66014);
    progression.checkIPProgression(&saved);
    assert(Stage(saved)==13);
    objects.unavailable.clear(); progression.checkIPProgression(&saved);
    assert(Stage(saved)==14);

    Player eligible; boss=Creature{}; boss.tapped=&eligible;
    assert(progression.IsEligibleStrictKill(&eligible,&boss));
    eligible.x=1000;
    assert(!progression.IsEligibleStrictKill(&eligible,&boss)); // dungeon-wide loot range is insufficient
    Corpse corpse; eligible.alive=false; eligible.corpse=&corpse;
    assert(progression.IsEligibleStrictKill(&eligible,&boss)); // dead participant's nearby corpse qualifies
    corpse.z=101; assert(!progression.IsEligibleStrictKill(&eligible,&boss)); corpse.z=0;
    corpse.map=2; assert(!progression.IsEligibleStrictKill(&eligible,&boss)); corpse.map=1;
    corpse.instance=2; assert(!progression.IsEligibleStrictKill(&eligible,&boss)); corpse.instance=1;
    corpse.phase=2; assert(!progression.IsEligibleStrictKill(&eligible,&boss)); corpse.phase=1;
    eligible.allowedReward=false; assert(!progression.IsEligibleStrictKill(&eligible,&boss)); eligible.allowedReward=true;
    boss.disabledLoot=true; assert(!progression.IsEligibleStrictKill(&eligible,&boss)); boss.disabledLoot=false;
    boss.damageEnough=false; assert(!progression.IsEligibleStrictKill(&eligible,&boss)); boss.damageEnough=true;
    boss.alive=true; assert(!progression.IsEligibleStrictKill(&eligible,&boss)); boss.alive=false;
    boss.inWorld=false; assert(!progression.IsEligibleStrictKill(&eligible,&boss)); boss.inWorld=true;
    eligible.inWorld=false; assert(!progression.IsEligibleStrictKill(&eligible,&boss)); eligible.inWorld=true;
    boss.tapped=nullptr; assert(!progression.IsEligibleStrictKill(&eligible,&boss));
    assert(!progression.IsEligibleStrictKill(nullptr,&boss) && !progression.IsEligibleStrictKill(&eligible,nullptr));

    Player owner, member, remote, outsider;
    Group tapped, finishing; tapped.SetMembers({&owner,&member,&remote,nullptr}); finishing.SetMembers({&outsider});
    owner.group=&tapped; member.group=&tapped; remote.group=&tapped; outsider.group=&finishing; remote.x=1000;
    boss=Creature{}; boss.tappedGroup=&tapped;
    hook.OnPlayerCreatureKillCredit(&outsider,&boss);
    assert(Stage(owner)==1 && Stage(member)==1 && Stage(remote)==0 && Stage(outsider)==0);
    Player petOwner; boss=Creature{}; boss.tapped=&petOwner;
    hook.OnPlayerCreatureKillCredit(&petOwner,&boss); // core resolves pets/totems to actual tapped player
    assert(Stage(petOwner)==1);

    for (uint8 stage=0; stage<=18; ++stage) {
        Player learner; if (stage) learner.quests[66000+stage]=QUEST_STATUS_REWARDED;
        for (uint32 row=0; row<=10; ++row) {
            TalentEntry talent{row};
            assert(hook.OnPlayerCanLearnTalent(&learner,&talent,0)==
                   (row <= (stage<8 ? 6u : stage<13 ? 8u : 10u)));
        }
    }
    assert(!hook.OnPlayerCanLearnTalent(nullptr,nullptr,0));
    player.gm=true; TalentEntry wrathRow{10}; assert(hook.OnPlayerCanLearnTalent(&player,&wrathRow,0)); player.gm=false;

    assert(!progression.isExcludedAccount(&player) && !progression.isBotAccount(&player));
    assert(AccountMgr::queries==0);
    player.cls=CLASS_WARLOCK; player.level=60;
    progression.UpdateRNDbotSpells(&player); assert(player.spellGrants==0);
    progression.SyncBotsProgressionToLeader(&tapped);
    progression.UpdateGroupAttunement(&player,"mc");
    progression.UpdateAccountReputation(1,1,&player);
    assert(unguardedCalls==0);
    ChatHandler handler{&player.session};
    assert(!Command::HandleSetBotIndividualProgressionCommand(&handler));
    assert(!Command::HandleSetRepIndividualProgressionCommand(&handler));
    assert(!Command::HandleAttuneIndividualProgressionCommand(&handler,"mc"));
    assert(unguardedCalls==0 && handler.messages==3);
    player.session.security=SEC_GAMEMASTER;
    assert(Command::HandleSetBotIndividualProgressionCommand(&handler));
    assert(Command::HandleSetRepIndividualProgressionCommand(&handler));
    assert(Command::HandleAttuneIndividualProgressionCommand(&handler,"mc"));
    progression.UpdateGroupAttunement(&player,"mc");
    progression.UpdateAccountReputation(1,1,&player);
    assert(unguardedCalls==5);
    ChatHandler console;
    assert(!Command::HandleAttuneIndividualProgressionCommand(&console,"mc"));

    for (uint8 stage=0; stage<=18; ++stage) {
        progression.accounts[1]=stage;
        assert(hook.CanAccountCreateCharacter(1,1,1));
        assert(hook.CanAccountCreateCharacter(1,10,2)==(stage>=8));
        assert(hook.CanAccountCreateCharacter(1,11,7)==(stage>=8));
        assert(!hook.CanAccountCreateCharacter(1,1,6)); // no fresh level-55 hero-class shortcut
    }
    assert(AccountMgr::queries==0); // account regex cannot unlock races or the hero class
    progression.customProgressionMap[123]=5;
    assert(!progression.IsStrictDefaultProgression());
    assert(hook.OnPlayerCanLearnTalent(nullptr,nullptr,0));
    progression.customProgressionMap.clear(); progression.strictEarnedProgression=false;
    Player legacy; progression.UpdateProgressionState(&legacy,PROGRESSION_BLACKWING_LAIR);
    assert(Stage(legacy)==3); // feature-off upstream advancement still works
    assert(progression.isBotAccount(&player));
    progression.UpdateRNDbotSpells(&player); assert(player.spellGrants==1);
    progression.enabled=false; assert(hook.CanAccountCreateCharacter(1,1,6));
    std::cout << "Strict earned progression: sequential milestones, saved credits, physical tapped-party kills, talent and bypass checks passed\n";
}
'''

source = prelude + enums + declarations + functions + '\n' + '\n'.join(guard_functions)
source += '\nstruct Script {\n' + hooks + '\n};\n'
source += '\nstruct Command {\n' + '\n'.join(command_guards) + '\n};\n' + tests
with tempfile.TemporaryDirectory(prefix='portable-strict-earned-') as temporary:
    target = Path(temporary) / 'strict.cpp'
    executable = Path(temporary) / 'strict'
    target.write_text(source)
    subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror', '-g',
                    '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                    '-I', str(module / 'src'), str(target), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True)

# Execute the production update twice against isolated condition rows. Check
# that every targeted old gate moves to 12 and unrelated gates remain intact.
update = (module / 'data/sql/world/updates/2026_10_06_00_reserved_progression_stage.sql').read_text()
targets = {tuple(map(int, match.split(','))) for match in
           re.findall(r'\((\d+(?:,\s*\d+){5})\)', update)}
assert len(targets) == 62
connection = sqlite3.connect(':memory:')
columns = ('SourceTypeOrReferenceId', 'SourceGroup', 'SourceEntry', 'SourceId',
           'ElseGroup', 'ConditionTarget', 'ConditionTypeOrReference', 'ConditionValue1',
           'ConditionValue2', 'ConditionValue3', 'NegativeCondition')
connection.execute('CREATE TABLE conditions (' + ','.join(name+' INTEGER' for name in columns) + ')')
connection.executemany('INSERT INTO conditions VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       [(*target, 8, 66011, 0, 0, 0) for target in targets])
connection.execute('INSERT INTO conditions VALUES (23,999,123,0,0,0,8,66011,0,0,0)')
connection.execute('INSERT INTO conditions VALUES (23,18525,33192,0,0,0,7,66011,0,0,0)')
connection.execute('INSERT INTO conditions VALUES (23,18525,33192,0,1,0,8,66011,0,0,0)')
connection.execute('INSERT INTO conditions VALUES (23,18525,33192,0,0,0,8,66011,0,0,1)')
connection.executescript(update)
connection.executescript(update)
assert connection.execute('SELECT COUNT(*) FROM conditions WHERE ConditionValue1=66012').fetchone()[0] == len(targets)
assert connection.execute('SELECT COUNT(*) FROM conditions WHERE ConditionValue1=66011').fetchone()[0] == 4
base_targets = set()
for name in ('player_progression.sql', 'tbc_vendors.sql', 'zone_shattrath.sql'):
    text = (module / 'data/sql/world/base' / name).read_text()
    assert not re.search(r'\([^\n]*,\s*8,\s*0,\s*66011,', text), name
    for match in re.findall(r'^\((\d+(?:,\s*\d+){7}),', text, re.MULTILINE):
        row = tuple(map(int, match.split(',')))
        if row[5] == 8 and row[7] == 66012:
            base_targets.add((*row[:5], row[6]))
assert targets <= base_targets
print('Strict earned progression: reserved-stage SQL migration is targeted and idempotent')
