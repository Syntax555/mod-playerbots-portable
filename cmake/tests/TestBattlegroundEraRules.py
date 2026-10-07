"""Exercise production per-match AB/AV scoring under ASan/UBSan.

Setters, AB's complete score event loop, native reset methods and AV's complete
score update run unchanged. The small AV packet fragment comes directly from
FillInitialWorldStates; scenery, rewards and network sends are fixture services.
"""

import argparse
from pathlib import Path
import re
import subprocess
import tempfile
from PreparedSources import prepared_core


repo = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, default=prepared_core(repo))
args = parser.parse_args()
zones = args.source / 'src/server/game/Battlegrounds/Zones'
ab = (zones / 'BattlegroundAB.cpp').read_text()
av = (zones / 'BattlegroundAV.cpp').read_text()
ab_header = (zones / 'BattlegroundAB.h').read_text()
av_header = (zones / 'BattlegroundAV.h').read_text()


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


ab_methods = '\n'.join(function(ab, 'void BattlegroundAB::' + name + '(')
                       for name in ('ConfigureScoreLimit', 'Init', 'PostUpdateImpl',
                                    'FillInitialWorldStates'))
av_methods = '\n'.join(function(av, 'void BattlegroundAV::' + name + '(')
                       for name in ('ConfigureReinforcements', 'ResetBGSubclass',
                                    'UpdateScore', 'StartingEventOpenDoors'))
av_packet = function(av, 'void BattlegroundAV::FillInitialWorldStates(')
av_packet = av_packet[av_packet.index('    packet.Worldstates.emplace_back('
                                    'WORLD_STATE_BATTLEGROUND_AV_ALLIANCE_SCORE'):
                      av_packet.index('    SendMineWorldStates(')]
av_methods += ('\nvoid BattlegroundAV::FillScoreWorldStates('
               'WorldPackets::WorldState::InitWorldStates& packet)\n{\n' + av_packet + '}')

# Numeric map constants and score fields also come from the pinned core.
native_header = ab_header + av_header
tokens = set(re.findall(r'\b(?:BG_AB_|BG_AV_|AV_|SEND_MSG_)[A-Z_0-9]+\b',
                        ab_methods + av_methods))
native_constants = []
for token in sorted(tokens):
    value = re.search(r'\b' + token + r'\s*=\s*(\d+)\b', native_header)
    if value is None:
        value = re.search(r'^#define\s+' + token + r'\s+(\d+)\b',
                          native_header, re.MULTILINE)
    assert value is not None, 'Missing native constant: ' + token
    native_constants.append('constexpr int ' + token + '=' + value[1] + ';')
for token in ('BG_AB_TickPoints', 'BG_AB_TickIntervals'):
    native_constants.append(re.search(r'^const .*\b' + token + r'\[.*?;',
                                     ab_header, re.MULTILINE)[0])
worldstates = sorted(set(re.findall(r'\bWORLD_STATE_[A-Z_0-9]+\b',
                                   ab_methods + av_methods)))
fixture_ids = ['constexpr uint32 ' + token + '=' + str(index + 1) + ';'
               for index, token in enumerate(worldstates)]


def field(source, name):
    return re.search(r'^\s+(?:uint32|int32|bool)\s+' + name + r'[^;]*;',
                     source, re.MULTILINE)[0].strip()


score_fields = '\n'.join(field(ab_header, name) for name in
                         ('_configurableMaxTeamScore', '_configurableNearVictoryScore'))
reinforcement_fields = '\n'.join(field(av_header, name) for name in
                                 ('m_Team_Scores', '_initialReinforcements',
                                  'm_IsInformedNearVictory'))
ab_getters = '\n'.join(function(ab_header, '    [[nodiscard]] uint32 ' + name + '(')
                       for name in ('GetConfiguredMaxScore', 'GetConfiguredNearVictoryScore'))
av_getter = function(av_header, '    [[nodiscard]] uint32 GetInitialReinforcements(')

prelude = r'''
#include <array>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <deque>
#include <iostream>
#include <map>
#include <utility>
#include <vector>
using uint8=std::uint8_t; using uint16=std::uint16_t; using uint32=std::uint32_t;
using int16=std::int16_t; using int32=std::int32_t;
using Milliseconds=std::chrono::milliseconds;
using namespace std::chrono_literals;
using TeamId=uint8; using BG_AV_Nodes=uint8;
constexpr TeamId TEAM_ALLIANCE=0, TEAM_HORDE=1, TEAM_NEUTRAL=2;
constexpr uint8 PVP_TEAMS_COUNT=2, STATUS_WAIT_JOIN=1, STATUS_IN_PROGRESS=2,
    STATUS_WAIT_LEAVE=3;
constexpr uint32 CONFIG_BATTLEGROUND_ARATHI_CAPTUREPOINTS=0,
    CONFIG_BATTLEGROUND_ALTERAC_REINFORCEMENTS=1;
constexpr uint32 CHAT_MSG_BG_SYSTEM_NEUTRAL=0, CHAT_MSG_BG_SYSTEM_ALLIANCE=1,
    CHAT_MSG_BG_SYSTEM_HORDE=2, RESPAWN_IMMEDIATELY=0, MINUTE=60,
    ACHIEVEMENT_TIMED_TYPE_EVENT=0;
#define LOG_DEBUG(...) do {} while (false)
TeamId GetOtherTeamId(TeamId team) { assert(team<2); return team^1; }
uint32 urand(uint32 low,uint32) { return low; }
struct World {
    uint32 abScore=1600, avReinforcements=600;
    uint32 getIntConfig(uint32 config) const {
        return config==CONFIG_BATTLEGROUND_ARATHI_CAPTUREPOINTS?abScore:avReinforcements;
    }
} world;
World* sWorld=&world;
namespace WorldPackets::WorldState {
struct InitWorldStates { std::vector<std::pair<uint32,int32>> Worldstates; };
}
struct EventMap {
    std::deque<uint32> events;
    void Reset() { events.clear(); }
    void Update(uint32) {}
    uint32 ExecuteEvent() {
        if (events.empty()) return 0;
        uint32 event=events.front(); events.pop_front(); return event;
    }
    void ScheduleEvent(uint32,Milliseconds) {}
};
struct Battleground {
    uint32 instance=1, started=0, players=0;
    uint8 status=STATUS_WAIT_JOIN;
    int32 m_TeamScores[2]{};
    std::map<uint32,int32> updates;
    uint32 warnings=0, sounds=0, finishes=0;
    TeamId winner=TEAM_NEUTRAL;
    uint32 GetInstanceID() const { return instance; }
    uint8 GetStatus() const { return status; }
    uint32 GetStartTime() const { return started; }
    uint32 GetPlayersSize() const { return players; }
    void Init() { m_TeamScores[0]=m_TeamScores[1]=0; }
    void UpdateWorldState(uint32 field,int32 value) { updates[field]=value; }
    void SendBroadcastText(uint32,uint32) { ++warnings; }
    void PlaySoundToAll(uint32) { ++sounds; }
    void EndBattleground(TeamId team) { ++finishes; winner=team; status=STATUS_WAIT_LEAVE; }
    uint32 GetBonusHonorFromKill(uint32 count) const { return count; }
    void RewardHonorToTeam(uint32,TeamId) {}
    void RewardReputationToTeam(uint32,uint32,TeamId) {}
    void DoorOpen(uint32) {}
    void SpawnBGObject(uint32,uint32,uint32) {}
    void StartTimedAchievement(uint32,uint32) {}
};
'''

ab_fixture = r'''
struct BattlegroundAB : Battleground {
    EventMap _bgEvents;
    struct NodeText { uint32 TextAllianceTaken=0, TextHordeTaken=0; };
    std::array<NodeText,BG_AB_DYNAMIC_NODES_COUNT> ABNodes{};
    struct Node {
        uint32 _iconNone=0, _iconCapture=0;
        uint8 _state=0; TeamId _ownerTeamId=TEAM_NEUTRAL; bool _captured=false;
    };
    std::array<Node,BG_AB_DYNAMIC_NODES_COUNT> _capturePointInfo{};
    uint8 _controlledPoints[2]{}, _honorTics=100, _reputationTics=100;
    float _abReputationRate=1;
    bool _teamScores500Disadvantage[2]{};
    void CreateBanner(uint8,bool) {} void DeleteBanner(uint8) {}
    void NodeOccupied(uint8) {} void SendNodeUpdate(uint8) {}
    void ConfigureScoreLimit(uint32,uint32);
    void Init(); void PostUpdateImpl(uint32);
    void FillInitialWorldStates(WorldPackets::WorldState::InitWorldStates&);
    void Tick(TeamId team) {
        _bgEvents.events.push_back(BG_AB_EVENT_ALLIANCE_TICK+team);
        PostUpdateImpl(1000);
    }
'''

av_fixture = r'''
struct BattlegroundAV : Battleground {
    uint32 m_Team_QuestStatus[2][9]{}, m_CaptainBuffTimer[2]{}, m_Mine_Timer=0;
    bool m_CaptainAlive[2]{};
    TeamId m_Mine_Owner[2]{};
    std::array<bool,AV_CPLACE_MAX+AV_STATICCPLACE_MAX> BgCreatures{};
    void InitNode(BG_AV_Nodes,TeamId,bool) {}
    void DelCreature(uint16 slot) { BgCreatures.at(slot)=false; }
    void ChangeMineOwner(uint8,TeamId,bool) {}
    void ConfigureReinforcements(uint32); void UpdateScore(TeamId,int16);
    void ResetBGSubclass(); void StartingEventOpenDoors();
    void FillScoreWorldStates(WorldPackets::WorldState::InitWorldStates&);
'''

checks = r'''
int32 State(WorldPackets::WorldState::InitWorldStates const& packet,uint32 id) {
    for (auto const& [field,value]:packet.Worldstates) if (field==id) return value;
    assert(false); return -1;
}
void AssertAB(BattlegroundAB& bg,uint32 max,uint32 near) {
    assert(bg.GetConfiguredMaxScore()==max && bg.GetConfiguredNearVictoryScore()==near);
    WorldPackets::WorldState::InitWorldStates packet;
    bg.FillInitialWorldStates(packet);
    assert(State(packet,WORLD_STATE_BATTLEGROUND_AB_RESOURCES_MAX)==int32(max));
    assert(State(packet,WORLD_STATE_BATTLEGROUND_AB_RESOURCES_WARNING)==int32(near));
}
void AssertAVUI(BattlegroundAV& bg,int32 shown) {
    WorldPackets::WorldState::InitWorldStates packet;
    bg.FillScoreWorldStates(packet);
    assert(State(packet,WORLD_STATE_BATTLEGROUND_AV_SHOW_ALLIANCE_SCORE)==shown);
    assert(State(packet,WORLD_STATE_BATTLEGROUND_AV_SHOW_HORDE_SCORE)==shown);
    assert(State(packet,WORLD_STATE_BATTLEGROUND_AV_ALLIANCE_SCORE)==bg.m_Team_Scores[0]);
    assert(State(packet,WORLD_STATE_BATTLEGROUND_AV_HORDE_SCORE)==bg.m_Team_Scores[1]);
}
int main() {
    // Native configuration remains the fallback when no era override runs.
    BattlegroundAB vanilla, tbc, wrath, fallback;
    for (auto* bg:{&vanilla,&tbc,&wrath,&fallback}) bg->Init();
    AssertAB(fallback,1600,1400);
    world.abScore=2000; fallback.Init(); AssertAB(fallback,2000,1400);
    world.abScore=0; fallback.Init(); AssertAB(fallback,1600,1400);
    world.abScore=1600;
    vanilla.ConfigureScoreLimit(2000,1800); tbc.ConfigureScoreLimit(2000,1800);
    wrath.ConfigureScoreLimit(1600,1400);
    AssertAB(vanilla,2000,1800); AssertAB(tbc,2000,1800); AssertAB(wrath,1600,1400);
    for (auto invalid:std::vector<std::pair<uint32,uint32>>{
            {0,1800},{2000,0},{2000,2000},{2000,2001},{0xffffffff,1800}}) {
        vanilla.ConfigureScoreLimit(invalid.first,invalid.second); AssertAB(vanilla,2000,1800);
    }
    for (auto* bg:{&vanilla,&tbc,&wrath}) {
        uint32 max=bg->GetConfiguredMaxScore(), near=bg->GetConfiguredNearVictoryScore();
        bg->instance=0; bg->ConfigureScoreLimit(3000,2800); AssertAB(*bg,max,near); bg->instance=1;
        bg->status=STATUS_IN_PROGRESS; bg->ConfigureScoreLimit(3000,2800); AssertAB(*bg,max,near);
        bg->status=STATUS_WAIT_JOIN; bg->started=1;
        bg->ConfigureScoreLimit(3000,2800); AssertAB(*bg,max,near); bg->started=0; bg->players=1;
        bg->ConfigureScoreLimit(3000,2800); AssertAB(*bg,max,near); bg->players=0;
        TeamId team=bg==&tbc?TEAM_HORDE:TEAM_ALLIANCE;
        bg->status=STATUS_IN_PROGRESS; bg->_controlledPoints[team]=1;
        bg->m_TeamScores[team]=int32(near)-10;
        bg->Tick(team); assert(bg->m_TeamScores[team]==int32(near));
        assert(bg->warnings==1 && bg->sounds==1 && bg->finishes==0);
        bg->Tick(team); assert(bg->warnings==1 && bg->finishes==0);
        bg->m_TeamScores[team]=int32(max)-10; bg->Tick(team);
        assert(bg->finishes==1 && bg->winner==team && bg->m_TeamScores[team]==int32(max));
    }
    AssertAB(vanilla,2000,1800); AssertAB(tbc,2000,1800); AssertAB(wrath,1600,1400);
    vanilla.Init(); AssertAB(vanilla,1600,1400); AssertAB(tbc,2000,1800);

    BattlegroundAV oldAV, tbcAV, wrathAV, fallbackAV;
    for (auto* bg:{&oldAV,&tbcAV,&wrathAV,&fallbackAV}) bg->ResetBGSubclass();
    assert(fallbackAV.GetInitialReinforcements()==600);
    world.avReinforcements=0; fallbackAV.ResetBGSubclass();
    assert(fallbackAV.GetInitialReinforcements()==0 && fallbackAV.m_Team_Scores[0]==0);
    world.avReinforcements=600;
    oldAV.ConfigureReinforcements(0); tbcAV.ConfigureReinforcements(600);
    wrathAV.ConfigureReinforcements(600);
    for (auto* bg:{&oldAV,&tbcAV,&wrathAV}) {
        uint32 count=bg->GetInitialReinforcements();
        bg->ConfigureReinforcements(0x80000000); assert(bg->GetInitialReinforcements()==count);
        bg->instance=0; bg->ConfigureReinforcements(999); bg->instance=1;
        assert(bg->GetInitialReinforcements()==count);
        bg->status=STATUS_IN_PROGRESS; bg->ConfigureReinforcements(999);
        assert(bg->GetInitialReinforcements()==count); bg->status=STATUS_WAIT_JOIN;
        bg->started=1; bg->ConfigureReinforcements(999); bg->started=0;
        assert(bg->GetInitialReinforcements()==count); bg->players=1;
        bg->ConfigureReinforcements(999); bg->players=0;
        assert(bg->GetInitialReinforcements()==count && bg->m_Team_Scores[0]==int32(count));
        AssertAVUI(*bg,0); bg->status=STATUS_IN_PROGRESS;
        AssertAVUI(*bg,count?1:0); bg->StartingEventOpenDoors();
        assert(bg->updates.count(WORLD_STATE_BATTLEGROUND_AV_SHOW_ALLIANCE_SCORE)==(count?1:0));
        assert(bg->updates.count(WORLD_STATE_BATTLEGROUND_AV_SHOW_HORDE_SCORE)==(count?1:0));
    }
    oldAV.UpdateScore(TEAM_ALLIANCE,-1); oldAV.UpdateScore(TEAM_HORDE,-600);
    oldAV.UpdateScore(TEAM_ALLIANCE,1);
    assert(oldAV.m_Team_Scores[0]==0 && oldAV.m_Team_Scores[1]==0);
    assert(oldAV.finishes==0 && oldAV.warnings==0 && oldAV.updates.empty());
    for (auto* bg:{&tbcAV,&wrathAV}) {
        TeamId team=bg==&wrathAV?TEAM_HORDE:TEAM_ALLIANCE;
        TeamId other=GetOtherTeamId(team);
        bg->UpdateScore(team,-1); assert(bg->m_Team_Scores[team]==599);
        bg->UpdateScore(team,-479); assert(bg->m_Team_Scores[team]==120 && bg->warnings==0);
        bg->UpdateScore(team,-1); assert(bg->m_Team_Scores[team]==119 && bg->warnings==1);
        bg->UpdateScore(team,1); bg->UpdateScore(team,-1);
        assert(bg->warnings==1 && bg->sounds==1); // Warn only once even after a mine increment.
        bg->UpdateScore(team,-119);
        assert(bg->m_Team_Scores[team]==0 && bg->winner==other && bg->finishes==1);
        assert(bg->m_Team_Scores[other]==600); AssertAVUI(*bg,0);
        bg->ConfigureReinforcements(600); assert(bg->m_Team_Scores[team]==0); // Refills cannot reset combat.
    }
    // Global hot reload cannot change an already created Vanilla instance.
    world.avReinforcements=900; oldAV.UpdateScore(TEAM_ALLIANCE,-1);
    assert(oldAV.GetInitialReinforcements()==0 && oldAV.finishes==0);
    tbcAV.ResetBGSubclass(); assert(tbcAV.GetInitialReinforcements()==900);
    assert(tbcAV.m_Team_Scores[0]==900 && tbcAV.m_Team_Scores[1]==900);
    assert(!tbcAV.m_IsInformedNearVictory[0] && !tbcAV.m_IsInformedNearVictory[1]);
    assert(wrathAV.GetInitialReinforcements()==600 && oldAV.GetInitialReinforcements()==0);
    std::cout<<"AB/AV native fallback, historical per-match rules, score UI, warnings, wins and immutable refills passed.\n";
}
'''

with tempfile.TemporaryDirectory(prefix='earned-era-bg-rules-') as directory:
    folder = Path(directory)
    source = folder / 'fixture.cpp'
    source.write_text(prelude + '\n'.join(native_constants + fixture_ids) +
                      ab_fixture + score_fields + ab_getters + '};\n' +
                      av_fixture + reinforcement_fields + av_getter + '};\n' +
                      ab_methods + av_methods + checks)
    binary = folder / 'fixture'
    subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-g',
                    str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
