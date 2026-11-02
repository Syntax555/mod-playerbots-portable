"""Exercise original raid entrance hooks with each member's own era and attunements."""

import argparse
from pathlib import Path
import re
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
source = args.source / 'src'
header = (source / 'IndividualProgression.h').read_text()
for name, value in (('PROGRESSION_TBC_TIER_5', 13), ('PROGRESSION_WOTLK_TIER_5', 18), ('ITEM_DRAKEFIRE_AMULET', 16309)):
    assert re.search(r'\b' + name + r'\s*=\s*' + str(value) + r'\b', header)
assert re.search(r'NAXX40_ENTRANCE_FLAG\s*=\s*9378\b',
                 (source / 'naxx40Scripts/naxxramas_40.h').read_text())
onyxia = function((source / 'vanillaScripts/instance_onyxias_lair.cpp').read_text(), '    bool OnTrigger(').replace(' override', '')
naxx = function((source / 'naxx40Scripts/custom_gameobjects_40.cpp').read_text(), '    bool OnGossipHello(').replace(' override', '')
harness = r'''
#include <cassert>
#include <cstdint>
#include <string>
#include <vector>
constexpr int PROGRESSION_TBC_TIER_5=13, PROGRESSION_WOTLK_TIER_5=18;
constexpr int RAID_DIFFICULTY_10MAN_HEROIC=2, RAID_DIFFICULTY_10MAN_NORMAL=0;
constexpr int ITEM_DRAKEFIRE_AMULET=16309, NAXX40_ENTRANCE_FLAG=9378, QUEST_STATUS_REWARDED=6, GENDER_MALE=0;
struct Player;
struct GroupReference {Player* player;GroupReference* following;Player* GetSource(){return player;}GroupReference* next(){return following;}};
struct Group {
    int difficulty=0;std::vector<GroupReference> members;
    void SetRaidDifficulty(int d){difficulty=d;}
    GroupReference* GetFirstMember(){return members.empty()?nullptr:&members[0];}
    void Add(Player* p){members.push_back({p,nullptr});for(size_t i=0;i+1<members.size();++i)members[i].following=&members[i+1];}
};
struct Session {};
struct Player {
    int level=60,stage=7,guid=1,difficulty=0,map=1,teleports=0;
    bool world=true,amulet=true,attuned=true,entrance=true,gm=false;
    Group* group=nullptr;Session session;
    bool IsInWorld(){return world;}Session* GetSession(){return &session;}Group* GetGroup(){return group;}
    int GetLevel(){return level;}int GetGUID(){return guid;}int getGender(){return GENDER_MALE;}
    std::string GetName(){return std::to_string(guid);}
    bool HasItemCount(int item){assert(item==ITEM_DRAKEFIRE_AMULET);return amulet;}
    int GetQuestStatus(int quest){assert(quest==NAXX40_ENTRANCE_FLAG);return entrance?QUEST_STATUS_REWARDED:0;}
    bool IsGameMaster(){return gm;}void SetRaidDifficulty(int d){difficulty=d;}
    bool TeleportTo(int m,float,float,float,float){++teleports;map=m;return true;}
    int GetMapId(){return map;}float GetDistance(Player*){return 10;}
};
struct ChatHandler {explicit ChatHandler(Session*){}template<class... Args>void PSendSysMessage(char const*,Args&&...) {}};
struct IndividualProgression {
    bool requireNaxxStrath=true;
    bool hasPassedProgression(Player* p,int stage){return p->stage>=stage;}
    bool isBotAccount(Player*){return false;} // strict mode disables account exemptions
    bool isAttuned(Player* p){return p->attuned;}
} progression;
auto* sIndividualProgression=&progression;
struct AreaTrigger{};struct GameObject{};
struct Onyxia { @ONYXIA@ };
struct Naxx { @NAXX@ };
int main() {
    Onyxia onyxia;Naxx naxx;
    Player leader;leader.stage=18;leader.level=49;
    assert(!onyxia.OnTrigger(&leader,nullptr)&&leader.difficulty==0);
    leader.level=75;leader.amulet=false;
    assert(!onyxia.OnTrigger(&leader,nullptr)&&leader.teleports==0);
    leader.amulet=true;
    assert(onyxia.OnTrigger(&leader,nullptr)&&leader.teleports==1&&leader.difficulty==2);
    for(int stage:{7,13,18}) for(bool attuned:{false,true}) for(bool entrance:{false,true}) {
        Player owner,member;Group group;
        owner.stage=18;owner.level=80;owner.group=&group;
        member.guid=2;member.stage=stage;member.attuned=attuned;member.entrance=entrance;
        group.Add(&owner);group.Add(&member);
        assert(naxx.OnGossipHello(&owner,nullptr));
        assert(owner.teleports==1);
        assert((member.teleports==1)==((stage<13||stage>=18)&&attuned&&entrance));
    }
    for(bool attuned:{false,true})for(bool entrance:{false,true}) {
        Player owner;owner.level=80;owner.stage=18;owner.attuned=attuned;owner.entrance=entrance;
        assert(naxx.OnGossipHello(&owner,nullptr)==(attuned&&entrance));
        assert((owner.teleports==1)==(attuned&&entrance));
    }
}
'''.replace('@ONYXIA@', onyxia).replace('@NAXX@', naxx)
assert 'if (enabled && strictEarnedProgression)\n        return false;' in function(
    (source / 'IndividualProgression.cpp').read_text(), 'bool IndividualProgression::isBotAccount(const Player*')
mutations = (
    ('Onyxia minimum level', 'player->GetLevel() < 50', 'false'),
    ('Onyxia return amulet', 'player->HasItemCount(ITEM_DRAKEFIRE_AMULET))\n                {', 'true)\n                {'),
    ('member era copied from leader', 'hasPassedProgression(member, PROGRESSION_WOTLK_TIER_5)', 'hasPassedProgression(player, PROGRESSION_WOTLK_TIER_5)'),
    ('Naxx personal attunement', '!sIndividualProgression->isAttuned(member)', 'false'),
    ('Naxx personal entrance', 'sIndividualProgression->requireNaxxStrath && member->GetQuestStatus(NAXX40_ENTRANCE_FLAG) != QUEST_STATUS_REWARDED', 'false'),
)
with tempfile.TemporaryDirectory(prefix='portable-era-raid-entrances-') as temporary:
    directory = Path(temporary)
    for label, old, new in (('production', '', ''), *mutations):
        variant = harness
        if old:
            assert old in variant, label
            variant = variant.replace(old, new)
        cpp = directory / 'entrance.cpp'
        cpp.write_text(variant)
        executable = directory / 'entrance'
        subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                        *SANITIZER_FLAGS, str(cpp), '-o', str(executable)], check=True)
        result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=60, check=False)
        assert (result.returncode == 0) == (label == 'production'), (label, result.stderr)
        print('Era raid entrances: ' + label + (' passed' if not old else ' mutation rejected'))
