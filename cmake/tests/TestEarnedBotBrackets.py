"""Exercise production earned-cap hooks and the core level loop without starting a realm."""

from pathlib import Path
import subprocess
import tempfile
from PreparedSources import prepared_core

repo = Path(__file__).resolve().parents[2]
pb = prepared_core(repo) / 'modules/mod-playerbots/src'


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


level_source = (pb / 'Bot/RandomBotLevelMgr.cpp').read_text()
hooks = '\n'.join(function(level_source, signature) for signature in [
    '    static uint8 GetEarnedLevelCap(', '    void OnPlayerGiveXP(', '    bool OnPlayerCanGiveLevel('])
core = (prepared_core(repo) / 'src/server/game/Entities/Player/Player.cpp').read_text()
xp = function(core, 'void Player::GiveXP(')
loop = xp[xp.index('    while (newXP >= nextLvlXP'):xp.rindex('}')]
legacy = []
for index, method in enumerate(['AdjustBotToRange', 'ResetBot', 'SkipBotLevel', 'Update',
                                'OnBotLogin', 'OnBotLevelChanged']):
    body = function(level_source, 'void RandomBotLevelMgr::' + method + '(')
    guard = body[body.index('{') + 1:body.index('\n\n')]
    assert 'sPlayerbotAIConfig.naturalProgression' in guard
    legacy.append('void Legacy' + str(index) + '() {\n' + guard + '\n    ++mutations;\n}')
rate = function((pb / 'Script/Playerbots.cpp').read_text(), '    void OnPlayerGiveXP(')
rate_guard = rate[rate.index('        if ('):rate.index('        // no XP multiplier')]
queue = function((pb / 'Ai/Base/Actions/BattleGroundJoinAction.cpp').read_text(), 'bool BGJoinAction::canJoinBg(')
queue_policy = function((pb / 'Bot/BattlegroundQueuePolicy.h').read_text(),
                        'constexpr bool IsPlayerbotBattlegroundQueueAllowed(')

source = r'''
#include "EarnedLevelBracketPolicy.h"
#include <atomic>
#include <cassert>
#include <iostream>
#include <memory>
#include <string>
using uint8 = uint8_t; using uint32 = uint32_t;
constexpr int PLAYER_XP=0, PLAYER_NEXT_LEVEL_XP=1;
struct Unit {};
struct Guid { uint32 value; uint32 GetCounter() const { return value; } };
struct Player {
    uint32 guid=1, xp=0, money=43, item=777; uint8 level=1; bool random=true, queued=false;
    uint8 GetLevel() const { return level; }
    Guid GetGUID() const { return {guid}; }
    uint32 GetUInt32Value(int field) const { return field == PLAYER_XP ? xp : 100; }
    void SetUInt32Value(int field, uint32 value) { assert(field == PLAYER_XP); xp=value; }
    void GiveLevel(uint8);
    void Earn(uint32, bool);
    bool InBattlegroundQueueForBattlegroundQueueType(int) const { return queued; }
    bool GetBGAccessByLevel(int) const { return level >= 10 && level <= 60; }
};
struct Config {
    bool naturalProgression=true, vanillaBattlegroundsOnly=true, earnedEraBattlegrounds=false;
    float randomBotXPRate=10.0f;
    std::atomic<std::shared_ptr<EarnedLevelBracketPolicy const>> earnedLevelBrackets;
} sPlayerbotAIConfig;
struct RandomMgr { bool IsRandomBot(Player* p) const { return p->random; } } sRandomPlayerbotMgr;
struct PlayerScript {
    virtual ~PlayerScript()=default;
    virtual void OnPlayerGiveXP(Player*, uint32&, Unit*, uint8) {}
    virtual bool OnPlayerCanGiveLevel(Player*, uint8) { return true; }
};
class Hooks : public PlayerScript { public:
''' + hooks + r'''
} hooks;
void Player::GiveLevel(uint8 next) { if (hooks.OnPlayerCanGiveLevel(this, next)) level=next; }
void Player::Earn(uint32 award, bool rested) {
    hooks.OnPlayerGiveXP(this, award, nullptr, 0);
    if (!award) return;
    uint32 level=GetLevel(), maxLevel=80, nextLvlXP=GetUInt32Value(PLAYER_NEXT_LEVEL_XP);
    uint32 newXP=xp+award+(rested ? award : 0);
''' + loop + r'''
}
int mutations=0;
''' + '\n'.join(legacy) + r'''
void BotRate(Player* player, uint32& amount) {
''' + rate_guard + r'''
    amount *= 10;
}
using BattlegroundQueueTypeId=int; using BattlegroundBracketId=int; using BattlegroundTypeId=int;
constexpr int BATTLEGROUND_QUEUE_WS=1, BATTLEGROUND_QUEUE_AB=2, BATTLEGROUND_QUEUE_AV=3;
''' + queue_policy + r'''
bool IsPlayerbotBattlegroundQueueAllowed(Player*, bool vanillaOnly, bool earnedEra, BattlegroundQueueTypeId queue) {
    assert(!earnedEra); // Earned-era policy is exercised in TestPlayerbotEraBattlegrounds.py.
    return IsPlayerbotBattlegroundQueueAllowed(vanillaOnly, queue);
}
struct Battleground { uint32 GetMapId() const { return 489; } } bg;
struct BattlegroundMgr {
    static int BGTemplateId(int q) { return q; }
    Battleground* GetBattlegroundTemplate(int) { return &bg; }
} bgMgr;
auto sBattlegroundMgr=&bgMgr;
struct PvPDifficultyEntry { int bracket; int GetBracketId() const { return bracket; } } entry;
PvPDifficultyEntry const* GetBattlegroundBracketByLevel(uint32, uint8 level) {
    entry.bracket=(level-10)/10; return &entry;
}
struct BGJoinAction { Player* bot; bool canJoinBg(int, int); };
''' + queue + r'''
int main() {
    EarnedLevelBracketPolicy policy, again;
    std::string config="19:5,29:5,39:5,49:5,59:5";
    assert(policy.Load(config) && again.Load(" 19:5, 29:5 ,39:5,49:5,59:5 "));
    unsigned counts[81]{};
    for (uint32 guid=1; guid<=10000; ++guid) {
        auto cap=policy.GetCap(guid, 1);
        assert(cap == again.GetCap(guid, 1));
        ++counts[cap];
        if (cap) assert(policy.GetCap(guid, cap)==cap && policy.GetCap(guid, cap+1)==0);
    }
    for (int cap : {19,29,39,49,59}) assert(counts[cap]>450 && counts[cap]<550);
    assert(counts[0]>7400 && counts[0]<7600);
    EarnedLevelBracketPolicy extended;
    assert(extended.Load(config + ",69:5,79:5"));
    unsigned extendedCounts[81]{};
    for (uint32 guid=1; guid<=10000; ++guid) {
        auto previous=policy.GetCap(guid,1), current=extended.GetCap(guid,1);
        if (previous) assert(current==previous); // Appending preserves every lower resident.
        ++extendedCounts[current];
        if (current==69 || current==79) {
            assert(extended.GetCap(guid,1)==current); // Cap assignment grants no levels.
            assert(extended.GetCap(guid,current)==current);
            assert(extended.GetCap(guid,current+1)==0); // Existing higher characters survive.
        }
    }
    for (int cap : {19,29,39,49,59,69,79}) assert(extendedCounts[cap]>450 && extendedCounts[cap]<550);
    assert(extendedCounts[0]>6400 && extendedCounts[0]<6600);
    for (std::string bad : {"19", "19:", ":5", "19:0", "0:5", "81:5", "19:101", "19:5,",
            "19:5,,29:5", "19:5,19:1", "19:60,29:41", "-19:5", "19:-5", "19:5x", "1 9:5",
            "19:42949672960", "19:5:1"}) {
        assert(policy.Load(config) && !policy.Load(bad));
        for (uint32 guid=1; guid<=100; ++guid) assert(policy.GetCap(guid,1)==0);
    }
    assert(policy.Load("19:100"));
    sPlayerbotAIConfig.earnedLevelBrackets.store(std::make_shared<EarnedLevelBracketPolicy>(policy));
    Player bot; bot.level=18; bot.xp=90;
    bot.Earn(2000, true); // Production core loop with several levels' worth, including rested XP.
    assert(bot.level==19 && bot.money==43 && bot.item==777);
    auto savedXP=bot.xp;
    bot.Earn(9000,false); assert(bot.level==19 && bot.xp==savedXP);
    bot.GiveLevel(60); assert(bot.level==19);
    BGJoinAction action{&bot};
    assert(action.canJoinBg(BATTLEGROUND_QUEUE_WS,0));
    assert(!action.canJoinBg(BATTLEGROUND_QUEUE_WS,1));
    assert(!action.canJoinBg(99,0));
    bot.queued=true; assert(!action.canJoinBg(BATTLEGROUND_QUEUE_WS,0)); bot.queued=false;
    bot.level=1; assert(!action.canJoinBg(BATTLEGROUND_QUEUE_WS,0)); bot.level=19;
    uint32 amount=50; BotRate(&bot,amount); assert(amount==50);
    Legacy0(); Legacy1(); Legacy2(); Legacy3(); Legacy4(); Legacy5(); assert(mutations==0);
    bot.random=false; bot.Earn(100,false); assert(bot.level==20); // Human/alt excluded.
    bot.random=true; bot.Earn(100,false); assert(bot.level==21); // Higher existing bot preserved.
    bot.level=19; assert(policy.Load("29:100"));
    sPlayerbotAIConfig.earnedLevelBrackets.store(std::make_shared<EarnedLevelBracketPolicy>(policy));
    bot.Earn(100,false); assert(bot.level==20); // Raise cap: normal XP resumes.
    assert(policy.Load(""));
    sPlayerbotAIConfig.earnedLevelBrackets.store(std::make_shared<EarnedLevelBracketPolicy>(policy));
    bot.Earn(100,false); assert(bot.level==21); // Remove cap: normal XP resumes.
    assert(policy.Load("19:100"));
    sPlayerbotAIConfig.earnedLevelBrackets.store(std::make_shared<EarnedLevelBracketPolicy>(policy));
    sPlayerbotAIConfig.naturalProgression=false; bot.level=19; bot.Earn(100,false); assert(bot.level==20);
    Legacy0(); Legacy1(); Legacy2(); Legacy3(); Legacy4(); Legacy5(); assert(mutations==6);
    amount=50; BotRate(&bot,amount); assert(amount==500);
    amount=10; hooks.OnPlayerGiveXP(nullptr,amount,nullptr,0); assert(amount==10);
    std::cout << "Earned brackets: parser, stable population, XP/level caps, migration, queue and legacy guards passed\n";
}
'''

with tempfile.TemporaryDirectory(prefix='portable-earned-brackets-') as directory:
    cpp = Path(directory) / 'brackets.cpp'
    binary = Path(directory) / 'brackets'
    cpp.write_text(source)
    subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer', '-no-pie', '-I', str(pb / 'Bot'), str(cpp), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
