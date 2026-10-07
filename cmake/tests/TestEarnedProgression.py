"""Exercise patched production account gates and creation/login/XP paths with isolated core fixtures.

Run cmake -P cmake/PrepareModules.cmake first. Requires a C++20 g++ compiler.
The source snippets run with fake database/session APIs; the full server build
still checks integration with the real core. No realm or database is started.
"""

from pathlib import Path
import subprocess
import sys
import tempfile
from PreparedSources import prepared_core

root = prepared_core(Path(__file__).resolve().parents[2]) / 'modules'
ip = root / 'mod-individual-progression/src'
pb = root / 'mod-playerbots/src'

def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]

account = function((ip/'IndividualProgressionPlayer.cpp').read_text(), '    bool CanAccountCreateCharacter(')
progress = function((ip/'IndividualProgression.cpp').read_text(), 'uint8 IndividualProgression::GetAccountProgression(')
enum = function((ip/'IndividualProgression.h').read_text(), 'enum ProgressionState') + ';'
factory_source = (pb/'Bot/Factory/RandomPlayerbotFactory.cpp').read_text()
valid = function(factory_source, 'bool RandomPlayerbotFactory::IsValidRaceClassCombination(')
creation = function(factory_source, 'Player* RandomPlayerbotFactory::CreateRandomBot(')
creation = creation[:creation.index('    const uint8 gender')] + '    (void)nameCache;\n    return new Player{race};\n}'
login = function((pb/'Bot/PlayerbotMgr.cpp').read_text(), 'void PlayerbotHolder::HandlePlayerBotLoginCallback(')
login = login[:login.index('    botSession->HandlePlayerLoginFromDB')] + '    botSession->loaded = true;\n}'
xp = function((ip/'IndividualProgressionPlayer.cpp').read_text(), '    void OnPlayerGiveXP(').replace(' override', '')
reward_source = (ip/'IndividualProgressionPlayer.cpp').read_text()
reward = reward_source[reward_source.index('        case INTO_THE_BREACH:'):reward_source.index('        case QUEST_MORROWGRAIN:', reward_source.index('        case INTO_THE_BREACH:'))]
talents_source = (pb/'Bot/Factory/PlayerbotFactory.cpp').read_text()
resets = []
for method in ['uint32 PlayerbotFactory::InitTalentsTree(', 'void PlayerbotFactory::InitTalentsBySpecNo(',
               'void PlayerbotFactory::InitTalentsByParsedSpecLink(']:
    body = function(talents_source, method)
    resets.append(function(body, '    if (reset'))
fallback = function(talents_source, 'void PlayerbotFactory::InitTalents(uint32 specNo)')
fallback = fallback[fallback.index('        if (sPlayerbotAIConfig.limitTalentsExpansion'):fallback.index('        spells[talentInfo->Row]')]

prelude = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <map>
#include <memory>
#include <regex>
#include <string>
#include <unordered_map>
#include <vector>
using uint8 = uint8_t; using uint32 = uint32_t;
constexpr uint8 RACE_HUMAN=1, RACE_BLOODELF=10, RACE_DRAENEI=11, CLASS_DEATH_KNIGHT=6, MAX_CLASSES=12;
constexpr uint32 EXPANSION_THE_BURNING_CRUSADE=1, EXPANSION_WRATH_OF_THE_LICH_KING=2;
constexpr int CONFIG_EXPANSION=0, CONFIG_CHARACTER_CREATING_DISABLED_RACEMASK=1,
    CONFIG_CHARACTER_CREATING_DISABLED_CLASSMASK=2, XPSOURCE_KILL=0, INTO_THE_BREACH=10259;
struct Field { uint32 value; template<class T> T Get() const { return static_cast<T>(value); } };
struct Rows {
    std::vector<uint32> quests; size_t index=0;
    Field operator[](int) const { return {quests[index]}; }
    bool NextRow() { return ++index < quests.size(); }
};
using QueryResult = std::shared_ptr<Rows>;
struct Database {
    std::map<uint32, std::vector<uint32>> rewarded;
    QueryResult Query(char const*, uint32 account, uint32 lower, uint32 upper) {
        auto rows = std::make_shared<Rows>();
        for (auto quest : rewarded[account]) if (quest >= lower && quest <= upper) rows->quests.push_back(quest);
        return rows->quests.empty() ? nullptr : rows;
    }
} CharacterDatabase;
int nameQueries=0;
struct AccountMgr { static bool GetName(uint32 account, std::string& name) {
    ++nameQueries; name = "RNDBOT" + std::to_string(account); return true; } };
struct Pet { void GivePetXP(uint32) {} };
struct Player {
    uint8 race=1; uint32 level=1; uint8 state=0;
    int resets=0;
    void resetTalents(bool) { ++resets; state=0; }
    bool IsInWorld() const { return true; }
    uint32 GetLevel() const { return level; }
    Pet* GetPet() const { return nullptr; }
    void* GetGroup() const { return nullptr; }
};
struct Unit {};
struct IndividualProgression {
    bool enabled=true, disableDefaultProgression=false, strictEarnedProgression=false;
    uint8 tbcRacesProgressionLevel=8, deathKnightProgressionLevel=13, BotAccountsMaxLevel=80;
    std::string botAccountsRegex, excludedAccountsRegex;
    static uint8 GetAccountProgression(uint32);
    bool isExcludedAccount(Player*) { return false; }
    bool isBotAccount(Player*) { return false; }
    bool hasPassedProgression(Player* player, int stage) { return player->state >= stage; }
    void UpdateProgressionState(Player* player, int stage) { player->state = stage; }
} progression;
auto* sIndividualProgression = &progression;
struct AccountScript { virtual bool CanAccountCreateCharacter(uint32, uint8, uint8) = 0; };
'''

middle = r'''
struct ScriptMgr { bool CanAccountCreateCharacter(uint32 a, uint8 r, uint8 c) {
    return accountHook.CanAccountCreateCharacter(a,r,c); } } scripts;
auto* sScriptMgr = &scripts;
struct World { uint32 expansion=2, raceMask=0, classMask=0;
    uint32 getIntConfig(int key) { return key==0 ? expansion : (key==1 ? raceMask : classMask); } } world;
auto* sWorld = &world;
struct Config { bool naturalProgression=true, limitTalentsExpansion=true; } config;
auto& sPlayerbotAIConfig = config;
struct RaceMgr { uint8 GetMaxRaces() { return 12; } } races;
auto* sRaceMgr = &races;
struct PlayerInfo {};
struct ObjectMgr { PlayerInfo const* GetPlayerInfo(uint8 race, uint8 cls) {
    static PlayerInfo info;
    if (race==9 || cls==10) return nullptr;
    if (cls==2 && race!=1 && race!=3 && race!=10) return nullptr;
    if (cls==7 && race!=2 && race!=6 && race!=8 && race!=11) return nullptr;
    return &info;
} } objects;
auto* sObjectMgr = &objects;
bool IsAlliance(uint8 race) { return race==1 || race==3 || race==4 || race==7 || race==11; }
uint32 counter=0;
uint32 urand(uint32 lower, uint32 upper) { return lower + counter++ % (upper-lower+1); }
#define LOG_DEBUG(...) ((void)0)
#define LOG_ERROR(...) ((void)0)
enum class NameRaceAndGender {};
struct WorldSession { uint32 account=1; bool loaded=false; uint32 GetAccountId() { return account; } };
struct RandomPlayerbotFactory {
    static bool IsValidRaceClassCombination(uint8, uint8, uint32);
    Player* CreateRandomBot(WorldSession*, uint8, std::unordered_map<NameRaceAndGender, std::vector<std::string>>&);
};
struct CharacterCacheEntry { uint8 Race=1, Class=1; } entry;
struct CharacterCache { CharacterCacheEntry const* GetCharacterCacheByGuid(uint32) { return &entry; } } cache;
auto* sCharacterCache = &cache;
struct PlayerbotLoginQueryHolder { uint32 GetAccountId() const { return 1; } uint32 GetGuid() const { return 99; } } holder;
struct PlayerbotHolder {
    bool abandoned=false;
    void AbandonPendingLogin(uint32) { abandoned=true; }
    void HandlePlayerBotLoginCallback(PlayerbotLoginQueryHolder const&, WorldSession*);
};
struct TalentEntry { uint32 Row, Col; };
'''

tests = r'''
int main() {
    CharacterDatabase.rewarded[2] = {66018}; // another account must not unlock account 1
    WorldSession session;
    RandomPlayerbotFactory factory;
    std::unordered_map<NameRaceAndGender, std::vector<std::string>> names;
    for (uint8 tier=0; tier<=18; ++tier) {
        CharacterDatabase.rewarded[1] = {10259,66000+uint32(tier),70000};
        assert(accountHook.CanAccountCreateCharacter(1,1,1));
        assert(accountHook.CanAccountCreateCharacter(1,10,2) == (tier>=8));
        assert(accountHook.CanAccountCreateCharacter(1,11,7) == (tier>=8));
        assert(accountHook.CanAccountCreateCharacter(1,1,6) == (tier>=13));
        for (uint8 cls : {1,2,3,4,5,7,8,9,11}) for (int iteration=0; iteration<24; ++iteration) {
            std::unique_ptr<Player> bot(factory.CreateRandomBot(&session,cls,names));
            assert(bot);
            if (tier<8) assert(bot->race!=10 && bot->race!=11);
        }
        assert(!factory.CreateRandomBot(&session,6,names));
        entry = {10,2};
        PlayerbotHolder owner;
        session.loaded=false;
        owner.HandlePlayerBotLoginCallback(holder,&session);
        assert(owner.abandoned == (tier<8));
        assert(session.loaded == (tier>=8));
    }
    assert(nameQueries==0); // empty filters must not query the login database
    assert(!accountHook.CanAccountCreateCharacter(0,10,2));
    CharacterDatabase.rewarded[1] = {66018};
    entry = {1,6};
    PlayerbotHolder owner;
    session.loaded=false;
    owner.HandlePlayerBotLoginCallback(holder,&session);
    assert(owner.abandoned && !session.loaded);
    world.classMask=1;
    assert(!factory.CreateRandomBot(&session,1,names));
    world.classMask=0; world.raceMask=1536;
    for (int i=0; i<24; ++i) {
        std::unique_ptr<Player> bot(factory.CreateRandomBot(&session,2,names));
        assert(bot && bot->race!=10 && bot->race!=11);
    }
    world.raceMask=0;
    for (uint8 tier=0; tier<=7; ++tier) {
        Player player{1,60,tier};
        RewardTransition(&player);
        assert(player.state == (tier==7 ? 8 : tier));
    }
    struct XPCase { uint32 level; uint8 tier; bool canEarn; };
    for (XPCase c : {XPCase{59,0,true}, {60,0,false}, {60,7,false}, {60,8,true},
                    {69,8,true}, {70,8,false}, {70,12,false}, {70,13,true}}) {
        Player player{1,c.level,c.tier}; uint32 xp=200;
        xpHook.OnPlayerGiveXP(&player,xp,nullptr,XPSOURCE_KILL);
        assert(xp == (c.canEarn ? 200u : 0u));
    }
    Player trained{1,60,7};
    for (auto allocate : {TreeReset0,TreeReset1,TreeReset2}) {
        allocate(&trained,true);
        assert(trained.resets==0 && trained.state==7);
    }
    TalentEntry vanillaCap{6,1}, tbcTalent{7,0}, tbcCap{8,1}, wrathTalent{9,0};
    assert(AllowedFallbackTalent(&trained,&vanillaCap));
    assert(!AllowedFallbackTalent(&trained,&tbcTalent));
    assert(!AllowedFallbackTalent(&trained,&tbcCap));
    trained.level=70;
    assert(AllowedFallbackTalent(&trained,&tbcTalent));
    assert(AllowedFallbackTalent(&trained,&tbcCap));
    assert(!AllowedFallbackTalent(&trained,&wrathTalent));
    trained.level=80;
    assert(AllowedFallbackTalent(&trained,&wrathTalent));
    config.naturalProgression=false;
    TreeReset0(&trained,true);
    assert(trained.resets==1); // feature-off behavior remains available upstream
    std::cout << "Earned progression: account isolation, all tiers, creation/login, transition, XP and talent checks passed\n";
}
'''

source = prelude + enum + '\n' + progress + '\nstruct AccountHook : AccountScript {\n' + account + '\n} accountHook;\n'
source += 'struct XPHook {\n' + xp + '\n} xpHook;\n'
source += 'void RewardTransition(Player* player) { switch (INTO_THE_BREACH) {\n' + reward + '} }\n'
source += middle + valid + '\n' + creation + '\n' + login + '\n'
for index, reset in enumerate(resets):
    source += f'void TreeReset{index}(Player* bot, bool reset) {{\n' + reset + '\n}\n'
source += 'bool AllowedFallbackTalent(Player* bot, TalentEntry const* talentInfo) { do {\n'
source += fallback + ' return true; } while (false); return false; }\n' + tests
with tempfile.TemporaryDirectory(prefix='portable-earned-progression-') as temporary:
    target = Path(temporary) / 'regression.cpp'
    executable = Path(temporary) / 'regression'
    target.write_text(source)
    subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror', '-g',
                    '-fsanitize=address,undefined', str(target), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True)

subprocess.run([sys.executable, str(Path(__file__).with_name('TestEarnedBotBrackets.py'))], check=True)
subprocess.run([sys.executable, str(Path(__file__).with_name('TestEarnedAuctions.py'))], check=True)
subprocess.run([sys.executable, str(Path(__file__).with_name('TestStrictEarnedProgression.py'))], check=True)
subprocess.run([sys.executable, str(Path(__file__).with_name('TestEarnedEraPrices.py'))], check=True)
subprocess.run([sys.executable, str(Path(__file__).with_name('TestEraTalents.py'))], check=True)
