"""Run Dungeon Clear's death recovery decisions with native-shaped doubles.

The production stay-dead gate, rez verdict kernel, party readiness walks,
episode close and resurrect-offer step compile against small engine doubles.
A body stays only while the party can raise it; otherwise the bot releases, and
the tank waits until released members are back. A wipe or the leader's corpse
still ends the run, and a real player answers a resurrection offer themselves.
Mutation checks remove each gate and confirm that the fixture rejects them.
"""

import argparse
from pathlib import Path
import re
import subprocess
import tempfile

from FixtureSupport import (
    SANITIZER_FLAGS,
    TIMEOUT,
    cxx,
    function,
    prepared_core,
    source_argument,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, help='prepared Dungeon Clear src directory')
source_argument(parser, 'core', help='prepared core source directory')
args = parser.parse_args()
core = args.core or prepared_core(Path(__file__).resolve().parents[2])
source = args.source or core / 'modules/mod-dungeon-clear/src'
dc = source / 'Ai/Dungeon/DungeonClear'
stay = (dc / 'Action/StayDeadAction.cpp').read_text()
recovery = (dc / 'Util/DcRezRecovery.cpp').read_text()
recovery_header = (dc / 'Util/DcRezRecovery.h').read_text()
party = (dc / 'Util/DcPartyState.cpp').read_text()
follower = (dc / 'Action/DcFollowerActions.cpp').read_text()

# The doubles model a released ghost as the core does: dead while a ghost, its
# body remembered by map, moved off the instance by the release and raised on
# entering the instance that holds its body.
assert ('bool isDead() const { return (m_deathState == DeathState::Dead || m_deathState == DeathState::Corpse); }'
        in (core / 'src/server/game/Entities/Unit/Unit.h').read_text())
player_header = (core / 'src/server/game/Entities/Player/Player.h').read_text()
assert '_corpseLocation.GetMapId() != MAPID_INVALID' in function(player_header, 'bool HasCorpse() const')
assert 'return _corpseLocation;' in function(player_header, 'WorldLocation GetCorpseLocation() const')
worldport = function((core / 'src/server/game/Handlers/MovementHandler.cpp').read_text(),
                     'void WorldSession::HandleMoveWorldportAck()')
assert 'if (mEntry->IsDungeon())\n        {\n            GetPlayer()->ResurrectPlayer(0.5f);' in worldport
# Earned recovery raises the dead only by a party member's own spell: the raid
# regroup's spell-free revive at the entrance stays refused.
assert 'if (DcEarnedPlay::Active())\n            return false;' in function(recovery, 'bool RegroupAtEntrance(')
evaluate = function(recovery, 'DcRezRecovery::Plan EvaluateImpl(Player* bot, bool mutate)')
assert 'in.corpseRunWhenUnrecoverable = DcEarnedPlay::Active();' in evaluate
assert 'plan.verdict = DcRezDecision::Decide(in, members);' in evaluate
assert 'return DcSettings::GetBool(bot, "PostCombatRez");' in function(recovery, 'bool Enabled(Player* bot)')
rez_action = function(follower, 'bool DungeonClearRezPartyAction::Execute(Event /*event*/)')
assert 'botAI->CastSpell(rezAction, target)' in rez_action

parts = {
    'kernel': (dc / 'Util/DcRezDecision.h').read_text(),
    'plan': re.search(r'    struct Plan\n    \{.*?\n    \};', recovery_header, re.DOTALL).group(0),
    'keeps': function(recovery, '    bool KeepsCorpse(Player* dead)'),
    'stay': function(stay, 'bool DungeonClearStayDeadAction::isUseful()'),
    'released': function(party, 'bool DcPartyState::IsReleasedHere(') + '\n' +
                function(party, 'bool DcPartyState::AnyMemberReleasedHere('),
    'ready': function(party, 'bool DcPartyState::IsPartyReady('),
    'describe': function(party, 'std::string DcPartyState::DescribePartyNotReady('),
    'close': function(evaluate, '        if (!anyDead)'),
    'offer': function(rez_action, '    if (target->isResurrectRequestedBy(bot->GetGUID()))'),
}

program = r'''
#include <cassert>
#include <cstdint>
#include <iostream>
#include <string>
#include <utility>
#include <vector>
using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
#define LOG_INFO(...) ((void)0)

@@KERNEL@@

struct ObjectGuid
{
    std::uint64_t raw = 0;
    bool IsEmpty() const { return !raw; }
    bool operator==(ObjectGuid const&) const = default;
};
namespace DcRezRecovery
{
@@PLAN@@
}

enum Powers { POWER_MANA = 0, POWER_RAGE = 1 };
struct Position { float x = 0, y = 0; };
struct WorldLocation { uint32 map = 0xFFFFFFFF; uint32 GetMapId() const { return map; } };
struct Map
{
    bool dungeon = true, raid = false;
    bool IsDungeon() const { return dungeon; }
    bool IsRaid() const { return raid; }
};
class Group;
class PlayerbotAI;
class Player
{
public:
    std::string name;
    uint32 mapId = 36;
    bool dead = false, moving = false, ai = true, tank = false, healer = false;
    float x = 0, health = 100;
    Powers power = POWER_MANA;
    uint32 mana = 100, maxMana = 100;
    WorldLocation corpse;
    Map* map = nullptr;
    Group* group = nullptr;
    ObjectGuid guid;
    std::string GetName() const { return name; }
    ObjectGuid GetGUID() const { return guid; }
    uint32 GetMapId() const { return mapId; }
    Map* GetMap() const { return map; }
    Group* GetGroup() const { return group; }
    bool isDead() const { return dead; }
    bool isMoving() const { return moving; }
    bool HasCorpse() const { return corpse.map != 0xFFFFFFFF; }
    WorldLocation GetCorpseLocation() const { return corpse; }
    float GetDistance(Player const* other) const { return other->x > x ? other->x - x : x - other->x; }
    float GetDistance(Position const& at) const { return at.x > x ? at.x - x : x - at.x; }
    float GetHealthPct() const { return health; }
    Powers getPowerType() const { return power; }
    uint32 GetPower(Powers) const { return mana; }
    uint32 GetMaxPower(Powers) const { return maxMana; }
    // The offer step: an open resurrection offer, answered by the client or the bot.
    bool offered = false, accepted = false;
    bool isResurrectRequestedBy(ObjectGuid) const { return offered; }
    void ResurectUsingRequestData() { accepted = true; }
};
class GroupReference
{
public:
    Player* source = nullptr;
    GroupReference* following = nullptr;
    Player* GetSource() const { return source; }
    GroupReference* next() const { return following; }
};
class Group
{
public:
    std::vector<GroupReference> refs;
    explicit Group(std::vector<Player*> const& members) : refs(members.size())
    {
        for (std::size_t i = 0; i < members.size(); ++i)
        {
            refs[i].source = members[i];
            refs[i].following = i + 1 < members.size() ? &refs[i + 1] : nullptr;
            members[i]->group = this;
        }
    }
    GroupReference* GetFirstMember() { return refs.empty() ? nullptr : &refs[0]; }
};
class PlayerbotAI
{
public:
    static bool IsTank(Player* p) { return p->tank; }
    static bool IsHeal(Player* p) { return p->healer; }
};
PlayerbotAI sharedAI;
#define GET_PLAYERBOT_AI(p) ((p)->ai ? &sharedAI : nullptr)

namespace DcEarnedPlay { bool active = true; inline bool Active() { return active; } }
namespace DcSettings
{
bool preventRelease = true;
bool GetBool(Player*, std::string const& key) { assert(key == "PreventBotRelease"); return preventRelease; }
uint32 GetUInt(Player*, std::string const& key) { assert(key == "RaidReadyQuorumPct"); return 80; }
}
std::vector<std::string> addonLines;
namespace DcStatusPublisher
{
void SendAddonMessage(PlayerbotAI*, std::string const& line) { addonLines.push_back(line); }
}

// The verdict EvaluateImpl hands the gates: the production kernel over the party
// snapshot, with corpse runs exactly when earned play is active.
std::vector<DcRezDecision::Member> snapshot;
DcRezDecision::Inputs inputs;
namespace
{
DcRezRecovery::Plan EvaluateImpl(Player*, bool mutate)
{
    assert(!mutate);  // the stay-dead gate is read-only
    DcRezRecovery::Plan plan;
    DcRezDecision::Inputs in = inputs;
    in.corpseRunWhenUnrecoverable = DcEarnedPlay::Active();
    plan.verdict = DcRezDecision::Decide(in, snapshot);
    return plan;
}
}
namespace DcRezRecovery
{
@@KEEPS@@
}

class AutoReleaseSpiritAction
{
public:
    virtual ~AutoReleaseSpiritAction() = default;
    virtual bool isUseful() { return stockRelease; }
    Player* bot = nullptr;
    bool stockRelease = true;
};
class DungeonClearStayDeadAction : public AutoReleaseSpiritAction
{
public:
    bool isUseful() override;
};
@@STAY@@

class DcPartyState
{
public:
    static bool IsReleasedHere(Player const* member, Player const* bot);
    static bool AnyMemberReleasedHere(Player* bot);
    static bool IsPartyReady(Player* bot, float minHpPct, float minMpPct, float maxSpread,
                             Position const* spreadAnchor, float maxTankGap);
    static std::string DescribePartyNotReady(Player* bot, float minHpPct, float minMpPct, float maxSpread,
                                             Position const* spreadAnchor, float maxTankGap);
};
@@RELEASED@@
@@READY@@
@@DESCRIBE@@

struct Run { uint32 rezPendingSinceMs = 0, rezAnnounceMs = 0, noRezzerSinceMs = 0, noRezzerQuietSinceMs = 0; };
DcRezRecovery::Plan CloseEpisode(Player* bot, Run& run)
{
    DcRezRecovery::Plan plan;
    bool const anyDead = false, mutate = true;
@@CLOSE@@
    return plan;
}

bool OfferStep(Player* bot, Player* target)
{
@@OFFER@@
    return false;
}

using Member = DcRezDecision::Member;
Member Alive(bool rez = false, bool healer = false) { Member m; m.canRezClass = rez; m.isHealerRole = healer; m.isBot = true; return m; }

bool Stays(bool stockRelease = true)
{
    Map dungeon;
    Player corpse;
    corpse.dead = true;
    corpse.map = &dungeon;
    DungeonClearStayDeadAction action;
    action.bot = &corpse;
    action.stockRelease = stockRelease;
    return !action.isUseful();
}

int main()
{
    // A SelfBot warrior leads; the stock release follows its lead and releases.
    Member leader = Alive();
    leader.isLeader = true;
    leader.isTankRole = true;
    Member healer = Alive(true, true), dps = Alive();
    Member deadHealer = healer, deadDps = dps;
    deadHealer.isDead = deadDps.isDead = true;

    // A living healer raises the dead: the body stays and the run holds.
    snapshot = {leader, healer, deadDps, dps, dps};
    assert(DcRezDecision::Decide(inputs, snapshot).outcome == DcRezDecision::Outcome::Hold);
    assert(Stays());

    // Nobody left can raise them: the fight is finished first, then they run back
    // and the run waits for them instead of ending.
    snapshot = {leader, deadHealer, deadDps, dps, dps};
    inputs.partyEngaged = true;
    assert(Stays());
    inputs.partyEngaged = false;
    DcRezDecision::Inputs earned = inputs;
    earned.corpseRunWhenUnrecoverable = true;
    assert(DcRezDecision::Decide(earned, snapshot).outcome == DcRezDecision::Outcome::None);
    assert(DcRezDecision::Decide(earned, snapshot).reason == DcRezDecision::Reason::NoRezzer);
    assert(!Stays() && Stays(false));

    // The rez timed out: release and run back too.
    snapshot = {leader, healer, deadDps, dps, dps};
    inputs.pendingSinceMs = 1;
    inputs.nowMs = 1 + inputs.timeoutMs;
    assert(DcRezDecision::Decide(inputs, snapshot).outcome == DcRezDecision::Outcome::Disable);
    earned = inputs;
    earned.corpseRunWhenUnrecoverable = true;
    assert(DcRezDecision::Decide(earned, snapshot).outcome == DcRezDecision::Outcome::None);
    assert(!Stays());
    inputs.pendingSinceMs = inputs.nowMs = 0;

    // Everyone dead, or the leader's own corpse with no rezzer: the run ends and all release.
    Member deadLeader = leader;
    deadLeader.isDead = true;
    snapshot = {deadLeader, deadHealer, deadDps, deadDps, deadDps};
    earned = inputs;
    earned.corpseRunWhenUnrecoverable = true;
    assert(DcRezDecision::Decide(earned, snapshot).reason == DcRezDecision::Reason::Wipe);
    assert(!Stays());
    snapshot = {deadLeader, deadHealer, dps, dps, dps};
    assert(DcRezDecision::Decide(earned, snapshot).outcome == DcRezDecision::Outcome::Disable);
    assert(!Stays());

    // An encounter that forbids the spell keeps the body for the rez that follows.
    snapshot = {leader, healer, deadDps, dps, dps};
    inputs.rezBlocked = true;
    assert(Stays());
    inputs.rezBlocked = false;

    // Without earned play the module keeps every body; without the flag, stock decides.
    DcEarnedPlay::active = false;
    snapshot = {leader, deadHealer, deadDps, dps, dps};
    assert(Stays());
    DcEarnedPlay::active = true;
    DcSettings::preventRelease = false;
    snapshot = {leader, healer, deadDps, dps, dps};
    assert(!Stays() && Stays(false));
    DcSettings::preventRelease = true;

    // The tank waits for a member running back to a body in this instance.
    Map dungeon;
    Player tank, priest, mage;
    tank.name = "Testi"; priest.name = "Ley"; mage.name = "Gbe";
    tank.power = POWER_RAGE;
    for (Player* p : {&tank, &priest, &mage})
        p->map = &dungeon;
    Group group({&tank, &priest, &mage});
    assert(DcPartyState::IsPartyReady(&tank, 50, 50, 30, nullptr, 0));
    priest.dead = true;
    priest.mapId = 0;
    priest.corpse.map = 36;
    assert(DcPartyState::IsReleasedHere(&priest, &tank) && DcPartyState::AnyMemberReleasedHere(&tank));
    assert(!DcPartyState::IsPartyReady(&tank, 50, 50, 30, nullptr, 0));
    assert(DcPartyState::DescribePartyNotReady(&tank, 50, 50, 30, nullptr, 0) == "Waiting on Ley (running back)");
    // A body elsewhere, or a member alive outside, is not this instance's wait.
    priest.corpse.map = 33;
    assert(!DcPartyState::IsReleasedHere(&priest, &tank) && DcPartyState::IsPartyReady(&tank, 50, 50, 30, nullptr, 0));
    priest.corpse.map = 36;
    priest.dead = false;
    assert(DcPartyState::IsPartyReady(&tank, 50, 50, 30, nullptr, 0));
    // Back inside: the ordinary floors take over until they have drunk up.
    priest.mapId = 36;
    priest.corpse.map = 0xFFFFFFFF;
    priest.mana = 10;
    assert(DcPartyState::DescribePartyNotReady(&tank, 50, 50, 30, nullptr, 0) == "Waiting on Ley (low mana)");
    priest.mana = 100;
    // A dead member still in the instance is the rez recovery's wait, not this walk's.
    mage.dead = true;
    assert(DcPartyState::IsPartyReady(&tank, 50, 50, 30, nullptr, 0));
    mage.dead = false;

    // The recovery's "restored" line waits until the released are back.
    Run run;
    run.rezPendingSinceMs = 5;
    run.rezAnnounceMs = 5;
    priest.dead = true;
    priest.mapId = 0;
    priest.corpse.map = 36;
    CloseEpisode(&tank, run);
    assert(addonLines.empty() && run.rezAnnounceMs == 5 && run.rezPendingSinceMs == 0);
    priest.dead = false;
    priest.mapId = 36;
    priest.corpse.map = 0xFFFFFFFF;
    CloseEpisode(&tank, run);
    assert(addonLines.size() == 1 && addonLines[0].find("Party restored") != std::string::npos && !run.rezAnnounceMs);

    // A bot's offer is accepted on its behalf; a player answers in their own client.
    Player rezzer;
    priest.offered = true;
    assert(OfferStep(&rezzer, &priest) && priest.accepted);
    Player human;
    human.ai = false;
    human.offered = true;
    assert(OfferStep(&rezzer, &human) && !human.accepted);

    std::cout << "Dungeon death recovery: bodies wait for a rezzer, otherwise run back while the tank waits\n";
}
'''


def build(directory, values, name):
    text = program
    for key, value in values.items():
        text = text.replace(f'@@{key.upper()}@@', value)
    (directory / (name + '.cpp')).write_text(text)
    executable = directory / name
    subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                    '-Wno-unused-variable', *SANITIZER_FLAGS, str(directory / (name + '.cpp')),
                    '-o', str(executable)], check=True)
    return subprocess.run([str(executable)], capture_output=True, text=True, check=False, timeout=TIMEOUT)


mutations = [
    ('rez-coming body released', 'stay', '        if (DcRezRecovery::KeepsCorpse(bot))\n            return false;\n', ''),
    ('rez hold not kept', 'keeps', 'plan.verdict.outcome == DcRezDecision::Outcome::Hold ||', 'false ||'),
    ('blocked encounter body released', 'keeps',
     'plan.verdict.reason == DcRezDecision::Reason::BlockedStandDown ||', 'false ||'),
    ('unrecoverable death ends the run', 'kernel',
     'in.corpseRunWhenUnrecoverable && !LeaderCorpse(members) ? Outcome::None', 'false ? Outcome::None'),
    ("leader's corpse left behind", 'kernel', 'in.corpseRunWhenUnrecoverable && !LeaderCorpse(members)',
     'in.corpseRunWhenUnrecoverable'),
    ('tank ignores released members', 'ready', 'bool const released = IsReleasedHere(member, bot);',
     'bool const released = false;'),
    ('released member not reported', 'describe', 'reason = "running back";', 'continue;'),
    ('body on another map waited for', 'released',
     ' &&\n           member->HasCorpse() && member->GetCorpseLocation().GetMapId() == bot->GetMapId()', ''),
    ('party restored before the run back', 'close', 'if (mutate && runningBack)', 'if (false)'),
    ("player's resurrection accepted for them", 'offer',
     '        if (!GET_PLAYERBOT_AI(target))\n            return true;\n', ''),
]

with tempfile.TemporaryDirectory(prefix='portable-dungeon-death-recovery-') as temporary:
    temporary = Path(temporary)
    result = build(temporary, parts, 'recovery')
    print(result.stdout + result.stderr, end='')
    if result.returncode:
        raise SystemExit(f'Dungeon death recovery fixture failed (exit {result.returncode})')
    for label, key, old, new in mutations:
        mutated = dict(parts)
        mutated[key] = parts[key].replace(old, new)
        if mutated[key] == parts[key]:
            raise SystemExit(f'{label} mutation was not applied')
        if not build(temporary, mutated, 'mutant').returncode:
            raise SystemExit(f'Dungeon death recovery fixture did not reject: {label}')
        print(f'Dungeon death recovery mutation rejected: {label}')
