"""Run IP command target, console and permission checks against production handlers."""

import argparse
from pathlib import Path
import subprocess
import tempfile

from FixtureSupport import (
    SANITIZER_FLAGS,
    cxx,
    function,
    prepared_core,
    source_argument,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, default=prepared_core() / 'modules/mod-individual-progression')
args = parser.parse_args()
core = prepared_core()
commands = (args.source / 'src/cs_individualProgression.cpp').read_text()
chat = (core / 'src/server/game/Chat/Chat.cpp').read_text()
tags = (core / 'src/server/game/Chat/ChatCommands/ChatCommandTags.h').read_text()
assert 'Player* GetConnectedPlayer() const { return _player; }' in tags
security = function(chat, 'bool ChatHandler::HasLowerSecurityAccount(')
assert 'if (!m_session)\n        return false;' in security
assert 'm_session->GetSecurity() < target_ac_sec' in security
sql = (args.source / 'data/sql/world/base/cs_individualProgression.sql').read_text()
assert 'Syntax: .ip set [$player] $progressionLevel' in sql
assert 'Syntax: .ip tele [$player] $location' in sql

handlers = []
for name in ('Get', 'Set', 'Tele', 'SetBot', 'SetRep', 'Attune'):
    body = function(commands, '    static bool Handle' + name + 'IndividualProgressionCommand(')
    if name in ('SetBot', 'SetRep'):
        body = body[:body.index('        Group* group')] + '        ++entered;\n        return true;\n    }'
    handlers.append(body)

harness = r'''
#include <cassert>
#include <cstdint>
#include <optional>
#include <string>
#include <utility>
using uint8=uint8_t;using uint32=uint32_t;
template<class T>using Optional=std::optional<T>;
constexpr int SEC_GAMEMASTER=2, PROGRESSION_TBC_TIER_5=13, PROGRESSION_WOTLK_TIER_5=18;
constexpr int RAID_DIFFICULTY_10MAN_HEROIC=2,ITEM_DRAKEFIRE_AMULET=16309;
enum ProgressionState:uint8 {};
struct Player;
struct Session {Player* owner=nullptr;int security=SEC_GAMEMASTER;uint32 account=1;
    Player* GetPlayer(){return owner;}int GetSecurity(){return security;}uint32 GetAccountId(){return account;}};
struct Group {void SetRaidDifficulty(int){}};
struct Player {
    Session session;std::string name="player";int stage=7,level=60,teleports=0;bool attuned=true,amulet=true;
    Player(){session.owner=this;}
    Session* GetSession(){return &session;}std::string const& GetName(){return name;}
    uint32 GetAreaId(){return 1;}uint32 GetLevel(){return level;}Group* GetGroup(){return nullptr;}
    bool HasItemCount(int id){assert(id==ITEM_DRAKEFIRE_AMULET);return amulet;}
    void SetRaidDifficulty(int){}void TeleportTo(int,float,float,float,float){++teleports;}
};
struct ChatHandler {
    Session* m_session=nullptr;Player* selected=nullptr;int messages=0,securityCalls=0;
    Session* GetSession(){return m_session;}Player* GetPlayer() const;
    void SendSysMessage(char const*){++messages;}
    template<class... Args>void PSendSysMessage(char const*,Args&&...){++messages;}
    bool HasLowerSecurity(Player* target){++securityCalls;return m_session&&m_session->GetSecurity()<target->GetSession()->GetSecurity();}
};
@GET_PLAYER@
struct PlayerIdentifier {
    Player* target;std::string name;
    std::string const& GetName(){return name;}Player* GetConnectedPlayer(){return target;}
    static Optional<PlayerIdentifier> FromTarget(ChatHandler* h){return h->selected?Optional<PlayerIdentifier>{{h->selected,h->selected->name}}:std::nullopt;}
    static Optional<PlayerIdentifier> FromSelf(ChatHandler* h){auto* p=h->GetPlayer();return p?Optional<PlayerIdentifier>{{p,p->name}}:std::nullopt;}
    @FROM_TARGET_OR_SELF@
};
struct IndividualProgression {
    bool enabled=true,strictEarnedProgression=true,AllowVanillaRaidAccess=false;int forced=0,phased=0,attunements=0;
    uint8 GetPlayerProgressionFromQuests(Player* p){return p->stage;}
    void ForceUpdateProgressionState(Player* p,ProgressionState stage){++forced;p->stage=stage;}
    void checkIPPhasing(Player*,uint32){++phased;}
    bool hasPassedProgression(Player* p,int stage){return p->stage>=stage;}
    bool isAttuned(Player* p){return p->attuned;}
    void UpdateGroupAttunement(Player*,std::string const&){++attunements;}
} progression;
auto* sIndividualProgression=&progression;
int entered=0;
struct Commands {
    static void CheckProgressionAchievements(Player*,uint8,uint32){}
    @HANDLERS@
};
int main(){
    Player actor,target;actor.name="actor";target.name="target";
    ChatHandler console,gm;gm.m_session=&actor.session;
    auto named=Optional<PlayerIdentifier>{{&target,target.name}};
    auto offline=Optional<PlayerIdentifier>{{nullptr,"offline"}};
    for(ChatHandler* h:{&console,&gm}) {
        int beforeTeleports=target.teleports,beforeForced=progression.forced;
        assert(!Commands::HandleSetIndividualProgressionCommand(h,offline,8));
        assert(!Commands::HandleTeleIndividualProgressionCommand(h,offline,"onyxia"));
        assert(target.teleports==beforeTeleports&&progression.forced==beforeForced);
        assert(Commands::HandleSetIndividualProgressionCommand(h,named,8));
        assert(target.stage==8&&actor.stage==7);target.stage=7;
        assert(Commands::HandleTeleIndividualProgressionCommand(h,named,"onyxia"));
        assert(target.teleports>0&&actor.teleports==0);
    }
    // Neither command dereferences an absent optional target from a console.
    assert(!Commands::HandleSetIndividualProgressionCommand(&console,std::nullopt,8));
    assert(!Commands::HandleTeleIndividualProgressionCommand(&console,std::nullopt,"naxx"));
    assert(Commands::HandleSetIndividualProgressionCommand(&gm,std::nullopt,8));
    assert(actor.stage==8);actor.stage=7;
    // The core's security decision must precede every state change.
    target.session.security=3;int forced=progression.forced,teleports=target.teleports;
    assert(!Commands::HandleSetIndividualProgressionCommand(&gm,named,8));
    assert(!Commands::HandleTeleIndividualProgressionCommand(&gm,named,"onyxia"));
    assert(progression.forced==forced&&target.teleports==teleports);
    assert(gm.securityCalls>=2);target.session.security=2;
    for(bool strict:{false,true})for(int security:{0,2}) {
        progression.strictEarnedProgression=strict;actor.session.security=security;
        bool allowed=!strict||security>=SEC_GAMEMASTER;
        assert(Commands::HandleSetBotIndividualProgressionCommand(&gm)==allowed);
        assert(Commands::HandleSetRepIndividualProgressionCommand(&gm)==allowed);
        assert(Commands::HandleAttuneIndividualProgressionCommand(&gm,"onyxia")==allowed);
        assert(!Commands::HandleSetBotIndividualProgressionCommand(&console));
        assert(!Commands::HandleSetRepIndividualProgressionCommand(&console));
        assert(!Commands::HandleAttuneIndividualProgressionCommand(&console,"onyxia"));
    }
    actor.session.owner=nullptr;actor.session.security=2;
    assert(!Commands::HandleSetBotIndividualProgressionCommand(&gm));
    assert(!Commands::HandleSetRepIndividualProgressionCommand(&gm));
    assert(!Commands::HandleAttuneIndividualProgressionCommand(&gm,"onyxia"));
}
'''.replace('@HANDLERS@', '\n'.join(handlers)).replace(
    '@GET_PLAYER@', function(chat, 'Player* ChatHandler::GetPlayer() const')).replace(
    '@FROM_TARGET_OR_SELF@', function(tags, '        static Optional<PlayerIdentifier> FromTargetOrSelf('))

mutations = (
    ('explicit target overwritten', 'if (!player)\n            player = PlayerIdentifier::FromTargetOrSelf(handler);',
     'player = PlayerIdentifier::FromTargetOrSelf(handler);'),
    ('target security ignored', 'if (handler->HasLowerSecurity(target))', 'if (false)'),
    ('offline target dereferenced', 'if (!target)', 'if (false)'),
    ('strict command gate removed', 'sIndividualProgression->enabled && sIndividualProgression->strictEarnedProgression &&', 'false &&'),
)
with tempfile.TemporaryDirectory(prefix='portable-ip-commands-') as temporary:
    directory = Path(temporary)
    for label, old, new in (('production', '', ''), *mutations):
        variant = harness
        if old:
            assert old in variant, label
            variant = variant.replace(old, new)
        source = directory / 'commands.cpp'
        source.write_text(variant)
        executable = directory / 'commands'
        subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                        *SANITIZER_FLAGS, str(source), '-o', str(executable)], check=True)
        result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=60, check=False)
        assert (result.returncode == 0) == (label == 'production'), (label, result.stderr)
        print('IP command safety: ' + label + (' passed' if not old else ' mutation rejected'))
