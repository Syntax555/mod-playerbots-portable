"""Run production EY/WS score, timer and flag-pickup methods under ASan/UBSan.

The methods and era fields come unchanged from the prepared core. Fixture
services supply players, map objects, timed events, packets and rewards.
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
zones = parser.parse_args().source / 'src/server/game/Battlegrounds/Zones'
ey = (zones / 'BattlegroundEY.cpp').read_text()
ws = (zones / 'BattlegroundWS.cpp').read_text()
ey_header = (zones / 'BattlegroundEY.h').read_text()
ws_header = (zones / 'BattlegroundWS.h').read_text()


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


ey_methods = '\n'.join(function(ey, 'void BattlegroundEY::' + name + '(')
                       for name in ('ConfigureScoreLimit', 'Init', 'AddPoints'))
ws_methods = '\n'.join(function(ws, 'void BattlegroundWS::' + name + '(')
                       for name in ('ConfigureEraRules', 'Init', 'StartingEventOpenDoors',
                                    'PostUpdateImpl', 'EventPlayerClickedOnFlag',
                                    'FillInitialWorldStates'))
ws_methods += '\n' + function(ws, 'uint32 BattlegroundWS::GetAssaultSpellId(')
methods = ey_methods + ws_methods
headers = ey_header + ws_header
constants = []
for token in sorted(set(re.findall(r'\b(?:BG_EY_|BG_WS_|BG_OBJECT_|WS_EVENT_)[A-Z_0-9]+\b',
                                  methods))):
    definition = re.search(r'constexpr Milliseconds ' + token + r'\s*=\s*[^;]+;', headers)
    if definition:
        constants.append(definition[0])
        continue
    definition = re.search(r'\b' + token + r'\s*=\s*([^,\n]+)', headers)
    assert definition is not None, 'Missing native constant: ' + token
    constants.append('constexpr uint32 ' + token + '=' + definition[1].split('//')[0].strip() + ';')
for index, token in enumerate(sorted(set(re.findall(r'\bWORLD_STATE_[A-Z_0-9]+\b', methods)))):
    constants.append('constexpr uint32 ' + token + '=' + str(index + 1) + ';')


def field(header, name):
    return re.search(r'^\s+(?:uint32|bool)\s+' + name + r'[^;]*;',
                     header, re.MULTILINE)[0].strip()


ey_fields = field(ey_header, '_configurableMaxTeamScore')
ey_getter = function(ey_header, '    [[nodiscard]] uint32 GetConfiguredMaxScore(')
ws_fields = '\n'.join(field(ws_header, name) for name in
                      ('_timeLimitEnabled', '_assaultDebuffsEnabled', '_configurableMaxTeamScore'))
ws_timer_getter = function(ws_header, '    uint32 GetMatchTime(')

prelude = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <map>
#include <vector>
using uint8=std::uint8_t; using uint32=std::uint32_t; using int32=std::int32_t;
using TeamId=uint8; using Milliseconds=std::chrono::milliseconds;
using namespace std::chrono_literals;
constexpr TeamId TEAM_ALLIANCE=0, TEAM_HORDE=1, TEAM_NEUTRAL=2;
constexpr uint8 STATUS_WAIT_JOIN=1, STATUS_IN_PROGRESS=2, STATUS_WAIT_LEAVE=3;
constexpr uint32 MINUTE=60, IN_MILLISECONDS=1000, RESPAWN_IMMEDIATELY=0, RESPAWN_ONE_DAY=86400;
constexpr uint32 ACHIEVEMENT_TIMED_TYPE_EVENT=0, ACHIEVEMENT_TIMED_TYPE_SPELL_TARGET=1;
constexpr uint32 AURA_INTERRUPT_FLAG_ENTER_PVP_COMBAT=0, SPELL_AURA_MOUNTED=0, SCORE_FLAG_RETURNS=0;
constexpr uint32 CHAT_MSG_BG_SYSTEM_NEUTRAL=0, CHAT_MSG_BG_SYSTEM_ALLIANCE=1, CHAT_MSG_BG_SYSTEM_HORDE=2;
constexpr uint32 CONFIG_BATTLEGROUND_EYEOFTHESTORM_CAPTUREPOINTS=0, CONFIG_BATTLEGROUND_WARSONG_FLAGS=1;
struct ObjectGuid {
    uint32 id=0;
    static ObjectGuid Empty;
    void Clear() { id=0; }
    explicit operator bool() const { return id!=0; }
    bool operator==(ObjectGuid const&) const=default;
};
ObjectGuid ObjectGuid::Empty{};
struct GameObject {
    ObjectGuid guid; uint32 entry;
    ObjectGuid GetGUID() const { return guid; }
    uint32 GetEntry() const { return entry; }
};
struct Player {
    ObjectGuid guid; TeamId team; bool mounted=false;
    std::vector<uint32> spells, removals;
    ObjectGuid GetGUID() const { return guid; }
    TeamId GetTeamId() const { return team; }
    void CastSpell(Player*,uint32 spell,bool) { spells.push_back(spell); }
    void RemoveAurasDueToSpell(uint32 spell) { removals.push_back(spell); }
    void RemoveAurasWithInterruptFlags(uint32) {}
    void StartTimedAchievement(uint32,uint32) {}
    bool IsMounted() const { return mounted; }
    void Dismount() { mounted=false; }
    void RemoveAurasByType(uint32) {}
    bool IsWithinDistInMap(GameObject*,float) const { return true; }
};
namespace ObjectAccessor {
    std::map<uint32,Player*> online;
    Player* GetPlayer(void*,ObjectGuid guid) {
        auto it=online.find(guid.id); return it==online.end()?nullptr:it->second;
    }
}
struct EventMap {
    uint32 now=0;
    std::multimap<uint32,uint32> events;
    void Reset() { now=0; events.clear(); }
    void Update(uint32 diff) { now+=diff; }
    void ScheduleEvent(uint32 event,Milliseconds delay) { events.emplace(now+delay.count(),event); }
    void CancelEvent(uint32 event) {
        for (auto it=events.begin();it!=events.end();) {
            if (it->second==event) it=events.erase(it); else ++it;
        }
    }
    void RescheduleEvent(uint32 event,Milliseconds delay) { CancelEvent(event); ScheduleEvent(event,delay); }
    uint32 ExecuteEvent() {
        if (events.empty() || events.begin()->first>now) return 0;
        auto it=events.begin(); uint32 result=it->second; events.erase(it); return result;
    }
    bool HasTimeUntilEvent(uint32 event) const {
        return std::any_of(events.begin(),events.end(),[event](auto const& entry) {return entry.second==event;});
    }
};
struct World {
    uint32 eyScore=1600, wsFlags=3;
    uint32 getIntConfig(uint32 config) const {
        return config==CONFIG_BATTLEGROUND_EYEOFTHESTORM_CAPTUREPOINTS?eyScore:wsFlags;
    }
} world;
World* sWorld=&world;
namespace WorldPackets::WorldState {
struct InitWorldStates { std::vector<std::pair<uint32,int32>> Worldstates; };
}
struct Battleground {
    uint32 instance=1, started=0, players=0, finishes=0;
    uint8 status=STATUS_WAIT_JOIN;
    int32 m_TeamScores[2]{};
    TeamId winner=TEAM_NEUTRAL;
    std::map<uint32,int32> updates;
    uint32 GetInstanceID() const { return instance; }
    uint8 GetStatus() const { return status; }
    uint32 GetStartTime() const { return started; }
    uint32 GetPlayersSize() const { return players; }
    void Init() { m_TeamScores[0]=m_TeamScores[1]=0; }
    int32 GetTeamScore(TeamId team) const { return m_TeamScores[team]; }
    void UpdateWorldState(uint32 id,int32 value) { updates[id]=value; }
    void EndBattleground(TeamId team) { ++finishes; winner=team; status=STATUS_WAIT_LEAVE; }
    void RewardHonorToTeam(uint32,TeamId) {}
    uint32 GetBonusHonorFromKill(uint32 n) const { return n; }
    void SpawnBGObject(uint32,uint32) {}
    void DoorOpen(uint32) {}
    void StartTimedAchievement(uint32,uint32) {}
    void PlaySoundToAll(uint32) {}
    void SendBroadcastText(uint32,uint32,Player* =nullptr) {}
    void UpdatePlayerScore(Player*,uint32,uint32) {}
    void* FindBgMap() const { return nullptr; }
};
'''

ey_fixture = r'''
struct BattlegroundEY : Battleground {
    EventMap _bgEvents;
    uint8 _ownedPointsCount[2]{};
    ObjectGuid _flagKeeperGUID, _droppedFlagGUID;
    uint32 _flagState=0, _flagCapturedObject=0, _honorTics=260;
    void ConfigureScoreLimit(uint32); void Init(); void AddPoints(TeamId,uint32);
'''
ws_fixture = r'''
struct BattlegroundWS : Battleground {
    EventMap _bgEvents;
    ObjectGuid _flagKeepers[2], _droppedFlagGUID[2];
    uint32 _flagState[2]{};
    TeamId _lastFlagCaptureTeam=TEAM_NEUTRAL;
    std::array<ObjectGuid,18> BgObjects{};
    void ConfigureEraRules(uint8); void Init(); void StartingEventOpenDoors();
    void PostUpdateImpl(uint32); void EventPlayerClickedOnFlag(Player*,GameObject*);
    void FillInitialWorldStates(WorldPackets::WorldState::InitWorldStates&);
    uint32 GetAssaultSpellId() const;
    ObjectGuid GetFlagPickerGUID(TeamId team) const { return _flagKeepers[team]; }
    uint32 GetFlagState(TeamId team) const { return _flagState[team]; }
    void SetFlagPicker(ObjectGuid guid,TeamId team) { _flagKeepers[team]=guid; }
    void UpdateFlagState(TeamId team,uint32 state) { _flagState[team]=state; }
    void SetDroppedFlagGUID(ObjectGuid guid,TeamId team) { _droppedFlagGUID[team]=guid; }
    void RemoveAssaultAuras() {} void CheckFlagKeeperInArea(TeamId) {}
    void RespawnFlagAfterDrop(TeamId) {}
    void Advance(uint32 diff) {
        started+=diff; PostUpdateImpl(diff);
        for (int i=0;i<32 && status==STATUS_IN_PROGRESS;++i) PostUpdateImpl(0);
    }
};
'''

checks = r'''
void AssertTimerUI(BattlegroundWS& bg,bool expected) {
    WorldPackets::WorldState::InitWorldStates packet; bg.FillInitialWorldStates(packet);
    std::map<uint32,int32> fields(packet.Worldstates.begin(),packet.Worldstates.end());
    assert(fields.at(WORLD_STATE_BATTLEGROUND_WS_STATE_TIMER_ACTIVE)==int32(expected));
    assert((fields.at(WORLD_STATE_BATTLEGROUND_WS_STATE_TIMER)>0)==expected);
}
bool HasSpell(Player const& player,uint32 spell) {
    return std::find(player.spells.begin(),player.spells.end(),spell)!=player.spells.end();
}
void StartWS(BattlegroundWS& bg) {
    bg.status=STATUS_IN_PROGRESS; bg.started=2*MINUTE*IN_MILLISECONDS;
    bg.StartingEventOpenDoors();
}
int main() {
    BattlegroundEY tbc, wrath;
    tbc.Init(); wrath.Init(); tbc.ConfigureScoreLimit(2000); wrath.ConfigureScoreLimit(1600);
    assert(tbc.GetConfiguredMaxScore()==2000 && wrath.GetConfiguredMaxScore()==1600);
    tbc.status=wrath.status=STATUS_IN_PROGRESS;
    tbc.AddPoints(TEAM_ALLIANCE,1600); wrath.AddPoints(TEAM_HORDE,1600);
    assert(tbc.finishes==0 && tbc.GetTeamScore(TEAM_ALLIANCE)==1600);
    assert(wrath.finishes==1 && wrath.winner==TEAM_HORDE);
    tbc.ConfigureScoreLimit(1600); assert(tbc.GetConfiguredMaxScore()==2000);
    tbc.AddPoints(TEAM_ALLIANCE,450);
    assert(tbc.finishes==1 && tbc.GetTeamScore(TEAM_ALLIANCE)==2000);
    assert(tbc.updates.at(WORLD_STATE_BATTLEGROUND_EY_ALLIANCE_RESOURCES)==2000);
    BattlegroundEY invalid;
    invalid.Init(); invalid.ConfigureScoreLimit(0); invalid.ConfigureScoreLimit(0x80000000);
    assert(invalid.GetConfiguredMaxScore()==1600);
    for (int guard=0;guard<4;++guard) {
        BattlegroundEY ey; ey.Init();
        if (guard==0) ey.instance=0;
        if (guard==1) ey.status=STATUS_IN_PROGRESS;
        if (guard==2) ey.started=1;
        if (guard==3) ey.players=1;
        ey.ConfigureScoreLimit(2000); assert(ey.GetConfiguredMaxScore()==1600);
    }
    world.eyScore=1900; tbc.Init(); assert(tbc.GetConfiguredMaxScore()==1900);
    world.eyScore=0; tbc.Init(); assert(tbc.GetConfiguredMaxScore()==BG_EY_MAX_TEAM_SCORE);
    world.eyScore=1600;

    Player alliance{{101},TEAM_ALLIANCE,false,{},{}}, horde{{102},TEAM_HORDE,false,{},{}};
    ObjectAccessor::online[101]=&alliance; ObjectAccessor::online[102]=&horde;
    GameObject allianceBase{{201},0}, hordeBase{{202},0};
    GameObject allianceGround{{203},BG_OBJECT_A_FLAG_GROUND_WS_ENTRY};
    GameObject hordeGround{{204},BG_OBJECT_H_FLAG_GROUND_WS_ENTRY};
    for (uint8 era=0;era<3;++era) {
        BattlegroundWS bg; bg.Init(); bg.ConfigureEraRules(era); StartWS(bg);
        bg.ConfigureEraRules(2-era); // A progressed refill cannot change a running instance.
        assert(bg._bgEvents.HasTimeUntilEvent(BG_WS_EVENT_NO_TIME_LEFT)==(era==2));
        AssertTimerUI(bg,era==2);
        bg.BgObjects[BG_WS_OBJECT_A_FLAG]=allianceBase.guid;
        bg.BgObjects[BG_WS_OBJECT_H_FLAG]=hordeBase.guid;
        alliance.spells.clear(); horde.spells.clear();
        bg.EventPlayerClickedOnFlag(&horde,&allianceBase);
        bg.EventPlayerClickedOnFlag(&alliance,&hordeBase);
        assert(bg._bgEvents.HasTimeUntilEvent(BG_WS_EVENT_BOTH_FLAGS_KEPT10)==(era>=1));
        assert(bg._bgEvents.HasTimeUntilEvent(BG_WS_EVENT_BOTH_FLAGS_KEPT15)==(era>=1));
        bg.Advance(600000);
        assert(HasSpell(alliance,BG_WS_SPELL_FOCUSED_ASSAULT)==(era>=1));
        assert(HasSpell(horde,BG_WS_SPELL_FOCUSED_ASSAULT)==(era>=1));
        assert(bg.GetAssaultSpellId()==(era>=1?BG_WS_SPELL_FOCUSED_ASSAULT:0));
        // Both ground pickup branches must preserve the earned era's penalty policy.
        bg._flagState[TEAM_ALLIANCE]=BG_WS_FLAG_STATE_ON_GROUND;
        bg._flagState[TEAM_HORDE]=BG_WS_FLAG_STATE_ON_GROUND;
        alliance.spells.clear(); horde.spells.clear();
        bg.EventPlayerClickedOnFlag(&horde,&allianceGround);
        bg.EventPlayerClickedOnFlag(&alliance,&hordeGround);
        assert(HasSpell(alliance,BG_WS_SPELL_FOCUSED_ASSAULT)==(era>=1));
        assert(HasSpell(horde,BG_WS_SPELL_FOCUSED_ASSAULT)==(era>=1));
        bg.Advance(300000);
        assert(HasSpell(alliance,BG_WS_SPELL_BRUTAL_ASSAULT)==(era>=1));
        assert(HasSpell(horde,BG_WS_SPELL_BRUTAL_ASSAULT)==(era>=1));
        assert(bg.GetAssaultSpellId()==(era>=1?BG_WS_SPELL_BRUTAL_ASSAULT:0));
        bg.m_TeamScores[TEAM_ALLIANCE]=2;
        bg.Advance(600000);
        assert(bg.finishes==(era==2?1u:0u));
        if (era==2) assert(bg.winner==TEAM_ALLIANCE);
        else { bg.Advance(3600000); assert(bg.finishes==0); AssertTimerUI(bg,false); }
        // Stale manually queued events must also fail closed for Vanilla.
        if (era==0) {
            alliance.spells.clear(); horde.spells.clear();
            bg._bgEvents.ScheduleEvent(BG_WS_EVENT_UPDATE_GAME_TIME,0ms);
            bg._bgEvents.ScheduleEvent(BG_WS_EVENT_NO_TIME_LEFT,0ms);
            bg._bgEvents.ScheduleEvent(BG_WS_EVENT_BOTH_FLAGS_KEPT10,0ms);
            bg._bgEvents.ScheduleEvent(BG_WS_EVENT_BOTH_FLAGS_KEPT15,0ms);
            bg.Advance(0); assert(bg.finishes==0);
            assert(bg.updates.at(WORLD_STATE_BATTLEGROUND_WS_STATE_TIMER)==0);
            assert(!bg._bgEvents.HasTimeUntilEvent(BG_WS_EVENT_UPDATE_GAME_TIME));
            assert(!HasSpell(alliance,BG_WS_SPELL_FOCUSED_ASSAULT));
            assert(!HasSpell(horde,BG_WS_SPELL_BRUTAL_ASSAULT));
        }
    }
    // Reverse base pickup order exercises the other penalty scheduling branch.
    for (uint8 era=0;era<3;++era) {
        BattlegroundWS bg; bg.Init(); bg.ConfigureEraRules(era); StartWS(bg);
        bg.BgObjects[BG_WS_OBJECT_A_FLAG]=allianceBase.guid;
        bg.BgObjects[BG_WS_OBJECT_H_FLAG]=hordeBase.guid;
        bg.EventPlayerClickedOnFlag(&alliance,&hordeBase);
        bg.EventPlayerClickedOnFlag(&horde,&allianceBase);
        assert(bg._bgEvents.HasTimeUntilEvent(BG_WS_EVENT_BOTH_FLAGS_KEPT10)==(era>=1));
        assert(bg._bgEvents.HasTimeUntilEvent(BG_WS_EVENT_BOTH_FLAGS_KEPT15)==(era>=1));
    }
    for (int guard=0;guard<5;++guard) {
        BattlegroundWS bg; bg.Init();
        if (guard==0) bg.instance=0;
        if (guard==1) bg.status=STATUS_IN_PROGRESS;
        if (guard==2) bg.started=1;
        if (guard==3) bg.players=1;
        bg.ConfigureEraRules(guard==4?3:0); StartWS(bg); AssertTimerUI(bg,true);
        assert(bg._bgEvents.HasTimeUntilEvent(BG_WS_EVENT_NO_TIME_LEFT));
    }
    BattlegroundWS reset; reset.Init(); reset.ConfigureEraRules(0); reset.Init();
    StartWS(reset); AssertTimerUI(reset,true);
    // Native tie resolution and default unconfigured behavior remain intact.
    reset.BgObjects[BG_WS_OBJECT_A_FLAG]=allianceBase.guid;
    reset.BgObjects[BG_WS_OBJECT_H_FLAG]=hordeBase.guid;
    alliance.spells.clear(); horde.spells.clear();
    reset.EventPlayerClickedOnFlag(&horde,&allianceBase);
    reset.EventPlayerClickedOnFlag(&alliance,&hordeBase);
    reset.Advance(600000);
    assert(HasSpell(alliance,BG_WS_SPELL_FOCUSED_ASSAULT));
    assert(HasSpell(horde,BG_WS_SPELL_FOCUSED_ASSAULT));
    reset._lastFlagCaptureTeam=TEAM_HORDE; reset.Advance(900000);
    assert(reset.finishes==1 && reset.winner==TEAM_HORDE);
    ObjectAccessor::online.clear();
    std::cout<<"EY scores and WS era timers, UI, flag penalties, immutable starts and native resets passed.\n";
}
'''

with tempfile.TemporaryDirectory(prefix='earned-era-pvp-rules-') as directory:
    folder = Path(directory)
    source = folder / 'fixture.cpp'
    source.write_text(prelude + '\n'.join(constants) + ey_fixture + ey_fields + ey_getter + '};\n' +
                      ws_fixture.rstrip()[:-2] + ws_fields + ws_timer_getter + '};\n' +
                      methods + checks)
    binary = folder / 'fixture'
    subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-g',
                    str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
