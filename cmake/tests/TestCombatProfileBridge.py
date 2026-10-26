"""Exercise the production combat-profile protocol and native access checks."""

import argparse
from pathlib import Path
import re
import subprocess
import tempfile

from FixtureSupport import SANITIZER_FLAGS, cxx, function, prepared_core, run_fixture


ROOT = Path(__file__).resolve().parents[2]

FIXTURE = r'''
#include <algorithm>
#include <cassert>
#include <cctype>
#include <cstdint>
#include <sstream>
#include <string>
#include <vector>
using uint8 = uint8_t;
using ChatMsg = int;
constexpr int PLAYERBOT_SECURITY_ALLOW_ALL = 3;
// WIRE_CONSTANTS
struct Player;
struct Security {
    bool allowed = true;
    bool CheckLevelFor(int level, bool silent, Player*) {
        assert(level == PLAYERBOT_SECURITY_ALLOW_ALL && silent);
        return allowed;
    }
};
struct PlayerbotAI {
    Security security;
    bool hasSecurity = true;
    Security* GetSecurity() { return hasSecurity ? &security : nullptr; }
};
struct Player {
    std::string name, mode = "auto", effective = "arms";
    bool session = true, world = true, alive = true, combat = false, teleport = false;
    PlayerbotAI* ai = nullptr;
    int talents = 51, gold = 123, items = 8;
    bool GetSession() const { return session; }
    bool IsInWorld() const { return world; }
    bool IsInCombat() const { return combat; }
    bool IsAlive() const { return alive; }
    bool IsBeingTeleported() const { return teleport; }
    std::string GetName() const { return name; }
    uint8 getClass() const { return 1; }
};
Player* visible = nullptr;
int writes = 0;
bool rate = true;
Player* FindBotByName(Player*, std::string const& name) {
    return visible && name == visible->name ? visible : nullptr;
}
PlayerbotAI* GetBotAI(Player* bot) { return bot ? bot->ai : nullptr; }
bool ConsumeStrategyMutationRateLimit(Player*) { return rate; }
namespace AiFactory {
std::vector<std::string> GetCombatProfiles(uint8) { return {"auto", "arms", "fury", "prot"}; }
std::string GetCombatProfile(Player* bot) { return bot->mode; }
std::string GetEffectiveCombatProfile(Player* bot) { return bot->effective; }
bool SetCombatProfile(Player* bot, std::string const& mode) {
    auto modes = GetCombatProfiles(bot->getClass());
    if (std::find(modes.begin(), modes.end(), mode) == modes.end()) return false;
    ++writes; bot->mode = mode; bot->effective = mode == "auto" ? "arms" : mode;
    return true;
}
}
std::string packet, packetType;
// WIRE_HELPERS
void SendAddonPacket(Player*, ChatMsg, std::string const& opcode, std::string const& payload) {
    assert(IsAddonPacketWithinBudget(opcode, payload));
    packetType = opcode; packet = payload;
}
// PROTOCOL_ERROR
// PRODUCTION
bool Dispatch(Player* player, std::string const& normalized, std::vector<std::string> const& fields) {
    ChatMsg replyType = 0;
    if (fields.empty()) return false;
    auto requestType = fields[0];
    if (normalized == "GET") {
        // GET_DISPATCH
    } else if (normalized == "RUN") {
        // RUN_DISPATCH
    }
    return false;
}
int main() {
    PlayerbotAI ai;
    Player owner; owner.name = "Owner";
    Player bot; bot.name = "Altbot"; bot.ai = &ai;
    visible = &bot;
    auto list = [&] { assert(Dispatch(&owner,"GET",{"COMBAT_PROFILES","Altbot","list1"})); };
    auto apply = [&](std::string mode = "prot") { assert(Dispatch(&owner,"RUN",{"COMBAT_PROFILE","apply1","Altbot",mode})); };
    auto error = [&](std::string reason) {
        assert(packetType == "COMBAT_PROFILE_RESULT");
        assert(packet.find("~ERR~" + reason + "~") != std::string::npos);
    };
    list();
    assert(packetType == "COMBAT_PROFILES" && packet == "list1~Altbot~auto~arms~auto,arms,fury,prot");
    assert(writes == 0);
    apply(); assert(packet == "apply1~Altbot~OK~OK~prot~prot" && writes == 1);
    apply("auto"); assert(bot.mode == "auto" && bot.effective == "arms" && writes == 2);
    int prior = writes;
    bot.teleport = true; apply(); error("BOT_UNAVAILABLE"); bot.teleport = false;
    bot.combat = true; apply(); error("IN_COMBAT"); bot.combat = false;
    bot.alive = false; apply(); error("DEAD"); bot.alive = true;
    ai.security.allowed = false; apply(); error("FORBIDDEN"); list(); error("FORBIDDEN"); ai.security.allowed = true;
    ai.hasSecurity = false; apply(); error("FORBIDDEN"); ai.hasSecurity = true;
    bot.ai = nullptr; apply(); error("NO_AI"); bot.ai = &ai;
    bot.world = false; apply(); error("BOT_UNAVAILABLE"); bot.world = true;
    bot.session = false; apply(); error("BOT_UNAVAILABLE"); bot.session = true;
    rate = false; apply(); error("RATE_LIMIT"); list(); error("RATE_LIMIT"); rate = true;
    visible = nullptr; apply(); error("NO_BOT"); list(); error("NO_BOT"); visible = &bot;
    apply("shadow"); error("BAD_PROFILE");
    assert(writes == prior && bot.mode == "auto");
    assert(bot.talents == 51 && bot.gold == 123 && bot.items == 8);
    assert(Dispatch(&owner,"RUN",{"COMBAT_PROFILE","self1","Owner","fury"})); error("NO_AI");
    owner.ai = &ai;
    assert(Dispatch(&owner,"RUN",{"COMBAT_PROFILE","self2","Owner","fury"}));
    assert(owner.mode == "fury" && writes == prior+1);
    for (auto fields : std::vector<std::vector<std::string>>{
        {"COMBAT_PROFILE"}, {"COMBAT_PROFILE","bad~token","Altbot","prot"},
        {"COMBAT_PROFILE","tok","%broken","prot"}, {"COMBAT_PROFILE","tok"," Altbot","prot"},
        {"COMBAT_PROFILE","tok","Altbot",""}, {"COMBAT_PROFILE","tok","Altbot",std::string(17,'a')},
        {"COMBAT_PROFILE","tok","Altbot","prot","extra"}}) {
        assert(Dispatch(&owner,"RUN",fields)); assert(packetType == "ERR");
    }
    for (auto fields : std::vector<std::vector<std::string>>{
        {"COMBAT_PROFILES"}, {"COMBAT_PROFILES","Altbot","bad~token"},
        {"COMBAT_PROFILES","%broken","tok"}, {"COMBAT_PROFILES"," Altbot","tok"}}) {
        assert(Dispatch(&owner,"GET",fields)); assert(packetType == "ERR");
    }
    assert(writes == prior+1);
    // Native request token grammar permits all of these characters and 64 bytes.
    std::string longToken = "ABC-_.:" + std::string(kMaxTokenLength-7, '9');
    assert(IsValidRequestToken(longToken) && !IsValidRequestToken(longToken + '9'));
    assert(Dispatch(&owner,"GET",{"COMBAT_PROFILES","Altbot",longToken}));
    assert(packetType == "COMBAT_PROFILES" && packet.starts_with(longToken + "~Altbot~"));
    bot.name = "Alt~%bot";
    assert(Dispatch(&owner,"GET",{"COMBAT_PROFILES",UrlEncodeField(bot.name),"encoded"}));
    assert(packetType == "COMBAT_PROFILES" && packet.starts_with("encoded~Alt%7E%25bot~"));
    for (auto invalid : {std::string("%00"), std::string("%7F"), std::string(kMaxBotNameLength+1,'a')}) {
        assert(Dispatch(&owner,"GET",{"COMBAT_PROFILES",invalid,"invalid"}));
        assert(packetType == "ERR" && packet == "GET~COMBAT_PROFILES~invalid~BAD_BOT_NAME");
    }
    // A legal request can expand beyond the reply budget; keep its token in ERR.
    bot.name = std::string(kMaxBotNameLength, '~');
    std::string encodedName = UrlEncodeField(bot.name), budgetToken(21,'T');
    assert(IsAddonPacketWithinBudget("GET", "COMBAT_PROFILES~" + encodedName + '~' + budgetToken));
    assert(Dispatch(&owner,"GET",{"COMBAT_PROFILES",encodedName,budgetToken}));
    assert(packetType == "ERR" && packet == "GET~COMBAT_PROFILES~" + budgetToken + "~TOO_LARGE");
    ai.security.allowed = false;
    assert(Dispatch(&owner,"GET",{"COMBAT_PROFILES",encodedName,budgetToken}));
    assert(packetType == "ERR" && packet == "GET~COMBAT_PROFILES~" + budgetToken + "~TOO_LARGE");
    ai.security.allowed = true;
    assert(IsAddonPacketWithinBudget("RUN", "COMBAT_PROFILE~" + budgetToken + '~' + encodedName + "~prot"));
    assert(Dispatch(&owner,"RUN",{"COMBAT_PROFILE",budgetToken,encodedName,"prot"}));
    assert(packetType == "ERR" && packet == "RUN~COMBAT_PROFILE~" + budgetToken + "~TOO_LARGE");
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bridge', type=Path,
                        default=prepared_core(ROOT) / 'modules/mod-multibot-bridge/src/MultiBotBridge.cpp')
    args = parser.parse_args()
    source = args.bridge.read_text()
    definitions = ('Player* FindCombatProfileTarget(', 'void SendCombatProfileResult(',
                   'void SendCombatProfiles(', 'void RunCombatProfileCommand(')
    production = '\n'.join(function(source, name) for name in definitions)
    dispatch = function(source, 'bool HandleBridgeOpcode(')
    get_case = function(dispatch, '        if (requestType == "COMBAT_PROFILES")')
    run_case = function(dispatch, '    if (requestType == "COMBAT_PROFILE")')
    assert dispatch.index(get_case) < dispatch.index('UNKNOWN_GET') < dispatch.index(run_case)
    assert 'kCombatProfileCapability,' in function(source, 'bool SendCapabilitiesPackets(')
    fixture = FIXTURE.replace('// GET_DISPATCH', get_case).replace('// RUN_DISPATCH', run_case)
    constants = ('kAddonEnvelope', 'kFieldSeparator', 'kMaxBridgeWireLength', 'kMaxOpcodeLength',
                 'kMaxRequestTypeLength', 'kMaxBotNameLength', 'kMaxTokenLength', 'kMaxEncodedFieldLength')
    wire_constants = '\n'.join(re.search(r'(?m)^.*\b' + name + r'\s*=.*;$', source)[0] for name in constants)
    helpers = ('std::string Trim(', 'std::string ToUpper(', 'std::size_t GetAddonWireLength(',
               'bool IsAddonPacketWithinBudget(', 'bool HasControlCharacter(', 'bool IsValidProtocolName(',
               'bool IsValidRawField(', 'bool IsValidCanonicalRawField(', 'bool IsValidRequestToken(',
               'int HexDigitValue(', 'bool TryUrlDecodeField(', 'std::string UrlEncodeField(',
               'std::string GetSafeErrorToken(')
    fixture = fixture.replace('// WIRE_CONSTANTS', wire_constants)
    fixture = fixture.replace('// WIRE_HELPERS', '\n'.join(function(source, name) for name in helpers))
    # The first match in the module is a declaration; extract the implementation.
    protocol_error = function(source[source.rindex('bool SendProtocolError('):], 'bool SendProtocolError(')
    fixture = fixture.replace('// PROTOCOL_ERROR', protocol_error)
    mutations = (
        ('native permission', '!ai->GetSecurity()->CheckLevelFor(PLAYERBOT_SECURITY_ALLOW_ALL, true, requester)', 'false'),
        ('missing security', '!ai->GetSecurity() ||', 'false ||'),
        ('combat', 'else if (bot->IsInCombat())', 'else if (false)'),
        ('death', 'else if (!bot->IsAlive())', 'else if (false)'),
        ('missing bot AI', 'else if (!ai)', 'else if (false)'),
        ('unavailable character', '!bot->IsInWorld() || !bot->GetSession()', 'false'),
        ('rate limit', '!ConsumeStrategyMutationRateLimit(requester)', 'false'),
        ('teleport', 'else if (bot->IsBeingTeleported())', 'else if (false)'),
        ('reply budget', '!IsAddonPacketWithinBudget(', 'false && !IsAddonPacketWithinBudget('),
    )
    with tempfile.TemporaryDirectory(prefix='combat-profile-bridge-') as temporary:
        directory = Path(temporary)
        for label, before, after in (('production', '', ''), *mutations):
            code = production
            if before:
                assert before in code, label
                code = code.replace(before, after)
            cpp, executable = directory / 'fixture.cpp', directory / 'fixture'
            cpp.write_text(fixture.replace('// PRODUCTION', code))
            subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror',
                            *SANITIZER_FLAGS, '-no-pie', str(cpp), '-o', str(executable)], check=True)
            result = run_fixture([str(executable)])
            if label == 'production':
                assert result.returncode == 0, result.stdout + result.stderr
                print('Combat profile bridge: actual packet fields, owner/SelfBot permissions and unchanged talents passed')
            else:
                assert result.returncode != 0, f'{label} guard mutation survived'
                null_guard = label in ('missing security', 'missing bot AI')
                rejected_null = (null_guard and 'runtime error: member' in result.stderr
                                 and 'FindCombatProfileTarget' in result.stderr)
                assert 'Assertion' in result.stderr or rejected_null, (
                    f'{label} failed outside its guard: {result.stderr}')
                print('Combat profile bridge mutation rejected:', label)


if __name__ == '__main__':
    main()
