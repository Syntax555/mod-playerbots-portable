"""Check upstream Playerbots crash, chat, RPG, ignored-quest and weapon-stone guards.

The production chat hooks, queued command dispatch, RPG quest-giver search and
smart item destruction run against small engine stubs. Destroyed items are
freed at once, as AzerothCore frees unsaved items, and the fixture runs under
AddressSanitizer. Ignored quest configuration reloads use the native parser and
quest selection gates. Weapon stones run through the real stone choice and imbue
action, so a shield is never mistaken for a polearm. Mutation checks remove the
guards or restore the previous item loop and confirm that the fixture rejects
them.
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


def declaration(source, opening):
    return re.search(re.escape(opening) + r'\n\{.*?\n\};', source, re.DOTALL).group(0)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, help='prepared Playerbots src directory')
args = parser.parse_args()
core = prepared_core(Path(__file__).resolve().parents[2])
module = args.source or core / 'modules/mod-playerbots/src'
ai_header = (module / 'Bot/PlayerbotAI.h').read_text()
ai_source = (module / 'Bot/PlayerbotAI.cpp').read_text()
security = (module / 'Mgr/Security/PlayerbotSecurity.h').read_text()
scripts = (module / 'Script/Playerbots.cpp').read_text()
rpg = (module / 'Ai/World/Rpg/Action/NewRpgBaseAction.cpp').read_text()
destroy = (module / 'Ai/Base/Actions/DestroyItemAction.cpp').read_text()
visitors = (module / 'Mgr/Item/ItemVisitors.h').read_text()
usage = (module / 'Ai/Base/Value/ItemUsageValue.h').read_text()

hooks = [function(scripts, 'bool OnPlayerCanUseChat(Player* player, uint32 type, uint32 lang, std::string& msg, ' + target)
         for target in ('Player* receiver)', 'Group* group)', 'Guild* /*guild*/)')]
production = {
    'enums': '\n'.join([
        declaration(security, 'enum PlayerbotSecurityLevel : uint32'),
        declaration(usage, 'enum ItemUsage : uint32'),
    ]),
    'types': '\n'.join([
        declaration(ai_header, 'class ChatCommandHolder'),
        declaration(visitors, 'class FindItemVisitor : public IterateItemsVisitor'),
        declaration(visitors, 'class FindItemByIdVisitor : public FindItemVisitor'),
    ]),
    'hooks': '\n'.join(hook.replace(') override\n', ')\n', 1) for hook in hooks),
    'functions': '\n'.join([
        function(ai_source, 'void PlayerbotAI::HandleCommands()'),
        function(rpg, 'bool NewRpgBaseAction::SearchQuestGiverAndAcceptOrReward()'),
        re.search(r'namespace\n\{\n.*?\n\}  // namespace', destroy, re.DOTALL).group(0),
        function(destroy, 'void DestroyItemAction::DestroyItem(FindItemVisitor* visitor)'),
        function(destroy, 'bool SmartDestroyItemAction::Execute(Event /*event*/)'),
        function(destroy, 'bool SmartDestroyItemAction::DestroyUntilBagSpace('),
    ]),
}

source = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <ctime>
#include <iostream>
#include <list>
#include <map>
#include <sstream>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>
using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;

enum ChatMsg : uint32 { CHAT_MSG_PARTY = 2, CHAT_MSG_GUILD = 4, CHAT_MSG_WHISPER = 7 };
enum Language : uint32 { LANG_UNIVERSAL = 0, LANG_ADDON = 0xFFFFFFFF };
enum IterateItemsMask : uint32 { ITERATE_ITEMS_IN_BAGS = 1 };
enum ItemQualities : uint32 { ITEM_QUALITY_POOR = 0 };
''' + 'ENUMS\n' + r'''

class ObjectGuid
{
public:
    ObjectGuid() = default;
    explicit ObjectGuid(uint64 raw) : raw(raw) {}
    explicit operator bool() const { return raw != 0; }
    bool operator<(ObjectGuid const& other) const { return raw < other.raw; }
private:
    uint64 raw = 0;
};

struct ItemTemplate { uint32 ItemId; };
class Item
{
public:
    Item(uint32 entry, uint8 slot, ItemUsage usage) : proto{entry}, slot(slot), usage(usage) {}
    uint32 GetEntry() const { return proto.ItemId; }
    ItemTemplate const* GetTemplate() const { return &proto; }
    uint8 GetBagSlot() const { return 255; }
    uint8 GetSlot() const { return slot; }
    ItemTemplate proto;
    uint8 slot;
    ItemUsage usage;
};
class IterateItemsVisitor
{
public:
    virtual ~IterateItemsVisitor() = default;
    virtual bool Visit(Item* item) = 0;
};
struct WorldObject { bool questGiver; };

class PlayerbotAI;
class Player
{
public:
    explicit Player(uint64 guid, uint32 guildId = 0) : guid(guid), guildId(guildId) {}
    ObjectGuid GetGUID() const { return guid; }
    uint32 GetGuildId() const { return guildId; }
    // Like Player::CanInteractWithQuestGiver, this reads the object it is given.
    bool CanInteractWithQuestGiver(WorldObject* object) const { return object->questGiver; }
    // Unsaved items are deleted synchronously by the core, so later reads are use-after-free.
    void DestroyItem(uint8 bag, uint8 slot, bool update)
    {
        assert(bag == 255 && update);
        auto item = std::find_if(items.begin(), items.end(), [slot](Item* i) { return i->GetSlot() == slot; });
        assert(item != items.end());
        delete *item;
        items.erase(item);
    }
    ObjectGuid guid;
    uint32 guildId;
    uint32 securityLevel = 3;
    uint32 capacity = 20;
    std::vector<Item*> items;
};

std::map<ObjectGuid, Player*> onlinePlayers;
std::map<ObjectGuid, WorldObject*> worldObjects;
namespace ObjectAccessor
{
Player* FindPlayer(ObjectGuid guid) { return onlinePlayers.count(guid) ? onlinePlayers[guid] : nullptr; }
WorldObject* GetWorldObject(Player const&, ObjectGuid guid) { return worldObjects.count(guid) ? worldObjects[guid] : nullptr; }
}

''' + 'TYPES\n' + r'''

class FindItemsToTradeByQualityVisitor : public FindItemVisitor
{
public:
    FindItemsToTradeByQualityVisitor(uint32, uint32) {}
protected:
    bool Accept(ItemTemplate const*) override { return false; }
};
class PlayerbotSecurity
{
public:
    // Like the production check, the sender's current relation to the bot decides.
    bool CheckLevelFor(PlayerbotSecurityLevel level, bool silent, Player* from) const
    {
        assert(silent);
        return from->securityLevel >= level;
    }
};
class AiObjectContext {};
std::vector<std::pair<std::string, Player*>> dispatched;
class ExternalEventHelper
{
public:
    explicit ExternalEventHelper(AiObjectContext*) {}
    bool ParseChatCommand(std::string const command, Player* owner)
    {
        dispatched.emplace_back(command, owner);
        return owner->GetGUID() ? true : false;
    }
};
class PlayerbotAI
{
public:
    std::list<ChatCommandHolder> chatCommands;
    std::vector<std::string> heard;
    std::vector<std::string> told;
    AiObjectContext* aiObjectContext = nullptr;
    PlayerbotSecurity security;
    PlayerbotSecurity* GetSecurity() { return &security; }
    void HandleCommand(uint32, std::string const text, Player*) { heard.push_back(text); }
    void HandleCommands();
    bool TellMaster(std::ostringstream& out) { told.push_back(out.str()); return true; }
    bool HasGameClientMaster() { return false; }
    bool IsInRealGuild() { return false; }
};
using PlayerBotMap = std::map<ObjectGuid, Player*>;
class PlayerbotMgr
{
public:
    PlayerBotMap bots;
    PlayerBotMap::const_iterator GetPlayerBotsBegin() const { return bots.begin(); }
    PlayerBotMap::const_iterator GetPlayerBotsEnd() const { return bots.end(); }
};
class PlayerbotsMgr
{
public:
    static PlayerbotsMgr& instance() { static PlayerbotsMgr manager; return manager; }
    PlayerbotAI* GetPlayerbotAI(Player* player) { return ais.count(player) ? ais[player] : nullptr; }
    PlayerbotMgr* GetPlayerbotMgr(Player* player) { return managers.count(player) ? managers[player] : nullptr; }
    std::map<Player*, PlayerbotAI*> ais;
    std::map<Player*, PlayerbotMgr*> managers;
};
class GroupReference
{
public:
    GroupReference(Player* source, GroupReference* following) : source(source), following(following) {}
    Player* GetSource() { return source; }
    GroupReference* next() { return following; }
private:
    Player* source;
    GroupReference* following;
};
class Group
{
public:
    explicit Group(GroupReference* first) : first(first) {}
    GroupReference* GetFirstMember() { return first; }
private:
    GroupReference* first;
};
class Guild {};
struct ChatHooks
{
''' + 'HOOKS\n' + r'''
};

class NewRpgBaseAction
{
public:
    explicit NewRpgBaseAction(Player* bot) : bot(bot) {}
    bool SearchQuestGiverAndAcceptOrReward();
    ObjectGuid chosen;
    int interactions = 0, waits = 0, moves = 0;
private:
    void OrganizeQuestLog() {}
    ObjectGuid ChooseNpcOrGameObjectToInteract(bool questgiverOnly, float distance)
    {
        assert(questgiverOnly && distance > 0.0f);
        return chosen;
    }
    void InteractWithNpcOrGameObjectForQuest(ObjectGuid) { ++interactions; }
    void ForceToWait(uint32) { ++waits; }
    bool MoveWorldObjectTo(ObjectGuid) { ++moves; return true; }
    Player* bot;
};

struct Event {};
class ChatHelper
{
public:
    std::string FormatItem(ItemTemplate const* proto) { return std::to_string(proto->ItemId); }
};
#define AI_VALUE(type, name) Value<type>(name)
#define AI_VALUE2(type, name, param) Values(name, param)
class DestroyItemAction
{
public:
    DestroyItemAction(PlayerbotAI* botAI, Player* bot) : botAI(botAI), bot(bot) {}
protected:
    void DestroyItem(FindItemVisitor* visitor);
    void IterateItems(IterateItemsVisitor* visitor, IterateItemsMask = ITERATE_ITEMS_IN_BAGS)
    {
        for (Item* item : std::vector<Item*>(bot->items))
            visitor->Visit(item);
    }
    template <class T>
    T Value(std::string const& name)
    {
        if constexpr (std::is_same_v<T, uint8>)
        {
            assert(name == "bag space");
            return uint8(bot->items.size() * 100 / bot->capacity);
        }
        else
        {
            assert(name == "can sell" || name == "should get money");
            return false;
        }
    }
    std::vector<Item*> Values(std::string const& name, std::string const& param)
    {
        assert(name == "inventory items" && param.rfind("usage ", 0) == 0);
        std::vector<Item*> matches;
        for (Item* item : bot->items)
            if (std::to_string(uint32(item->usage)) == param.substr(6))
                matches.push_back(item);
        return matches;
    }
    PlayerbotAI* botAI;
    Player* bot;
    ChatHelper chatHelper;
    ChatHelper* chat = &chatHelper;
};
class SmartDestroyItemAction : public DestroyItemAction
{
public:
    using DestroyItemAction::DestroyItemAction;
    bool Execute(Event event);
private:
    bool DestroyUntilBagSpace(std::vector<uint32> const& itemIds);
};

''' + 'FUNCTIONS\n' + r'''

void TestChatHooks()
{
    Player master(1, 7), botPlayer(2, 7);
    PlayerbotAI bot;
    PlayerbotMgr manager;
    manager.bots[botPlayer.GetGUID()] = &botPlayer;
    PlayerbotsMgr::instance().ais[&botPlayer] = &bot;
    PlayerbotsMgr::instance().managers[&master] = &manager;
    GroupReference second(&botPlayer, nullptr), first(&master, &second);
    Group group(&first);
    Guild guild;
    ChatHooks hooks;
    std::string trade = "back ore stone";
    // Addon traffic on every bot-command channel is not a bot command.
    assert(hooks.OnPlayerCanUseChat(&master, CHAT_MSG_WHISPER, LANG_ADDON, trade, &botPlayer));
    assert(hooks.OnPlayerCanUseChat(&master, CHAT_MSG_PARTY, LANG_ADDON, trade, &group));
    assert(hooks.OnPlayerCanUseChat(&master, CHAT_MSG_GUILD, LANG_ADDON, trade, &guild));
    assert(bot.heard.empty());
    // Ordinary chat still commands the bot on each channel.
    assert(hooks.OnPlayerCanUseChat(&master, CHAT_MSG_WHISPER, LANG_UNIVERSAL, trade, &botPlayer));
    assert(hooks.OnPlayerCanUseChat(&master, CHAT_MSG_PARTY, LANG_UNIVERSAL, trade, &group));
    assert(hooks.OnPlayerCanUseChat(&master, CHAT_MSG_GUILD, LANG_UNIVERSAL, trade, &guild));
    assert(bot.heard.size() == 3);
}

void TestQueuedCommands()
{
    Player master(1), leaver(2), demoted(3);
    onlinePlayers = {{master.GetGUID(), &master}, {demoted.GetGUID(), &demoted}};
    PlayerbotAI bot;
    bot.chatCommands.push_back(ChatCommandHolder("follow", master.GetGUID(), PLAYERBOT_SECURITY_ALLOW_ALL));
    bot.chatCommands.push_back(ChatCommandHolder("stay", leaver.GetGUID(), PLAYERBOT_SECURITY_ALLOW_ALL));
    bot.chatCommands.push_back(ChatCommandHolder("give", demoted.GetGUID(), PLAYERBOT_SECURITY_ALLOW_ALL));
    bot.chatCommands.push_back(ChatCommandHolder("who", demoted.GetGUID(), PLAYERBOT_SECURITY_TALK));
    bot.chatCommands.push_back(ChatCommandHolder("later", master.GetGUID(), PLAYERBOT_SECURITY_ALLOW_ALL,
                                                 CHAT_MSG_WHISPER, time(nullptr) + 3600));
    // The sender logged out and the demoted sender lost the rights the command needed.
    demoted.securityLevel = PLAYERBOT_SECURITY_TALK;
    bot.HandleCommands();
    assert(dispatched.size() == 2);
    assert(dispatched[0].first == "follow" && dispatched[0].second == &master);
    assert(dispatched[1].first == "who" && dispatched[1].second == &demoted);
    assert(bot.chatCommands.size() == 1 && bot.chatCommands.front().GetCommand() == "later");
}

void TestDespawnedQuestGiver()
{
    Player botPlayer(1);
    WorldObject giver{true};
    worldObjects = {{ObjectGuid(20), &giver}};
    NewRpgBaseAction action(&botPlayer);
    action.chosen = ObjectGuid(21);
    assert(!action.SearchQuestGiverAndAcceptOrReward());
    assert(action.interactions == 0 && action.moves == 0);
    action.chosen = ObjectGuid(20);
    assert(action.SearchQuestGiverAndAcceptOrReward());
    assert(action.interactions == 1 && action.waits == 1);
}

void TestSmartDestroy()
{
    Player botPlayer(1);
    PlayerbotAI ai;
    // Two stacks of one useless id at full bags: destroying the id frees both stacks.
    botPlayer.items = {new Item(100, 0, ITEM_USAGE_NONE), new Item(100, 1, ITEM_USAGE_NONE),
                       new Item(200, 2, ITEM_USAGE_VENDOR)};
    for (uint8 slot = 3; slot < 20; ++slot)
        botPlayer.items.push_back(new Item(300 + slot, slot, ITEM_USAGE_KEEP));
    SmartDestroyItemAction action(&ai, &botPlayer);
    assert(action.Execute(Event()));
    assert(botPlayer.items.size() == 17);
    assert(ai.told == std::vector<std::string>({"100 destroyed", "100 destroyed", "200 destroyed"}));
    for (Item* item : botPlayer.items)
        delete item;
}

int main()
{
    TestChatHooks();
    TestQueuedCommands();
    TestDespawnedQuestGiver();
    TestSmartDestroy();
    std::cout << "Playerbots upstream fixes: addon chat ignored, queued senders resolved, despawned quest givers "
                 "and freed items never read\n";
}
'''


def build(directory, parts, name):
    text = source.replace('ENUMS', parts['enums']).replace('TYPES', parts['types']).replace('HOOKS', parts['hooks'])
    text = text.replace('FUNCTIONS', parts['functions'])
    (directory / (name + '.cpp')).write_text(text)
    executable = directory / name
    # The pre-fix chat hooks ignore their language parameter, so mutants must still compile.
    subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                    *SANITIZER_FLAGS, str(directory / (name + '.cpp')),
                    '-o', str(executable)], check=True)
    return subprocess.run([str(executable)], capture_output=True, text=True, check=False, timeout=TIMEOUT)


previous_destroy_loop = '''for (Item* item : items)
        {
            FindItemByIdVisitor visitor(item->GetTemplate()->ItemId);
            DestroyItem(&visitor);
            if (AI_VALUE(uint8, "bag space") < BAG_SPACE_DESTROY_THRESHOLD)
                return true;
        }'''
mutations = [
    ('addon whispers command bots', 'hooks', 'if (type != CHAT_MSG_WHISPER || lang == LANG_ADDON)',
     'if (type != CHAT_MSG_WHISPER)'),
    ('addon party messages command bots', 'hooks', 'if (lang == LANG_ADDON)\n            return true;\n', ''),
    ('addon guild messages command bots', 'hooks', 'if (type != CHAT_MSG_GUILD || lang == LANG_ADDON)',
     'if (type != CHAT_MSG_GUILD)'),
    ('logged-out sender dispatched', 'functions', 'if (!owner || !GetSecurity()', 'if (!GetSecurity()'),
    ('sender rights not rechecked', 'functions',
     'if (!owner || !GetSecurity()->CheckLevelFor(it->GetRequiredLevel(), true, owner))', 'if (!owner)'),
    ('despawned quest giver read', 'functions', 'if (!object)\n            return false;\n', ''),
    ('freed item read after destroy', 'functions',
     'if (DestroyUntilBagSpace(DistinctItemIds(items)))\n            return true;', previous_destroy_loop),
]

with tempfile.TemporaryDirectory(prefix='portable-playerbot-upstream-fixes-') as temporary:
    temporary = Path(temporary)
    result = build(temporary, production, 'fixes')
    print(result.stdout + result.stderr, end='')
    if result.returncode:
        raise SystemExit(f'Playerbots upstream fixes fixture failed (exit {result.returncode})')
    for label, key, old, new in mutations:
        mutated = dict(production)
        mutated[key] = production[key].replace(old, new)
        if mutated[key] == production[key]:
            raise SystemExit(f'{label} mutation was not applied')
        if not build(temporary, mutated, 'mutant').returncode:
            raise SystemExit(f'Playerbots upstream fixes fixture did not reject: {label}')
        print(f'Playerbots upstream fixes mutation rejected: {label}')


# The ignored list replaces the previous value on a bot configuration reload.
# Compile its real parser and selection gates so removed IDs become eligible again.
config = (module / 'PlayerbotAIConfig.cpp').read_text()
initialize = function(config, 'bool PlayerbotAIConfig::Initialize()')
load_ignored = re.search(r'(?:    IgnoredQuests.clear\(\);\n)?    LoadSet<std::set<uint32>>\([^\n]+IgnoredQuests\);', initialize)
assert load_ignored, 'IgnoredQuests configuration must load through the native set parser'
assert 'std::set<uint32> IgnoredQuests;' in (module / 'PlayerbotAIConfig.h').read_text()
assert 'Playerbots.IgnoredQuests = ""' in (module.parent / 'conf/playerbots.conf.dist').read_text()
helpers = (module / 'Util/Helpers.cpp').read_text()
quest = (module / 'Ai/Base/Actions/QuestAction.cpp').read_text()
player_header = (core / 'src/server/game/Entities/Player/Player.h').read_text()
assert 'uint8 GetLevel() const' in (core / 'src/server/game/Entities/Unit/Unit.h').read_text()
assert 'uint32 getIntConfig(ServerConfigs index) const' in (core / 'src/server/game/World/World.h').read_text()
ignored_parts = {
    'parser': '\n'.join([
        function(helpers, 'std::vector<std::string>& split(std::string const s, char delim,'),
        function(helpers, 'std::vector<std::string> split(std::string const s, char delim)'),
        'template <class T>\n' + function(config, 'void LoadSet('),
    ]),
    'load': load_ignored.group(0),
    'quest_level': function(player_header, 'int32 GetQuestLevel(Quest const* quest) const'),
    'band': re.search(r'static constexpr int32 GREY_QUEST_LEVEL_BAND = \d+;',
                      (module / 'Ai/Base/Actions/QuestAction.h').read_text()).group(0),
    'accept': function(quest, 'bool QuestAction::CanAcceptQuest('),
    'worth': function(rpg, 'bool NewRpgBaseAction::IsQuestWorthDoing('),
}
ignored_source = r'''
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <set>
#include <sstream>
#include <string>
#include <vector>
using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
using int32 = std::int32_t;
PARSER
struct ConfigMgr
{
    std::string current;
    template<class T> T GetOption(char const* key, char const* fallback)
    {
        assert(std::string(key) == "Playerbots.IgnoredQuests" && !*fallback);
        return current;
    }
} manager;
auto* sConfigMgr = &manager;
struct Config
{
    std::set<uint32> IgnoredQuests;
    void Reload()
    {
LOAD
    }
} sPlayerbotAIConfig;
struct Quest
{
    uint32 id = 1;
    int32 level = 20;
    bool repeatable = false, seasonal = false;
    uint32 GetQuestId() const { return id; }
    int32 GetQuestLevel() const { return level; }
    bool IsRepeatable() const { return repeatable; }
    bool IsSeasonal() const { return seasonal; }
};
struct Player
{
    uint8 level = 20;
    bool eligible = true;
    uint8 GetLevel() const { return level; }
    QUEST_LEVEL
    bool CanTakeQuest(Quest const*, bool showError) const { assert(!showError); return eligible; }
};
struct World
{
    uint32 getIntConfig(int key) const { assert(key == 0); return 10; }
} world;
auto* sWorld = &world;
constexpr int CONFIG_QUEST_LOW_LEVEL_HIDE_DIFF = 0;
struct QuestAction
{
    BAND
    static bool CanAcceptQuest(Player*, Quest const*);
};
struct NewRpgBaseAction
{
    Player* bot;
    bool IsQuestWorthDoing(Quest const*);
};
ACCEPT
WORTH
int main()
{
    Player player;
    Quest first{1}, second{2};
    NewRpgBaseAction rpg{&player};
    auto accepted = [&](Quest const& quest) { return QuestAction::CanAcceptQuest(&player, &quest); };
    auto worth = [&](Quest const& quest) { return rpg.IsQuestWorthDoing(&quest); };
    sPlayerbotAIConfig.Reload();
    assert(sPlayerbotAIConfig.IgnoredQuests.empty() && accepted(first) && worth(first));
    manager.current = "1,1";
    sPlayerbotAIConfig.Reload();
    assert(sPlayerbotAIConfig.IgnoredQuests == std::set<uint32>({1}));
    assert(!accepted(first) && !worth(first) && accepted(second) && worth(second));
    manager.current = "2";
    sPlayerbotAIConfig.Reload();
    assert(accepted(first) && worth(first) && !accepted(second) && !worth(second));
    manager.current.clear();
    sPlayerbotAIConfig.Reload();
    assert(sPlayerbotAIConfig.IgnoredQuests.empty() && accepted(second) && worth(second));
    player.eligible = false;
    assert(!accepted(first));
    player.eligible = true;
    player.level = 31;
    assert(!accepted(first) && !worth(first));
    assert(!QuestAction::CanAcceptQuest(nullptr, &first) && !QuestAction::CanAcceptQuest(&player, nullptr));
    std::cout << "Ignored quests: current configuration replaces old IDs and preserves native eligibility\n";
}
'''


def build_ignored(directory, parts):
    text = ignored_source
    for key, value in parts.items():
        text = text.replace(key.upper(), value)
    source_path = directory / 'ignored.cpp'
    source_path.write_text(text)
    executable = directory / 'ignored'
    subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', *SANITIZER_FLAGS,
                    str(source_path), '-o', str(executable)], check=True)
    return subprocess.run([str(executable)], capture_output=True, text=True, check=False, timeout=TIMEOUT)


with tempfile.TemporaryDirectory(prefix='portable-playerbot-ignored-quests-') as temporary:
    temporary = Path(temporary)
    result = build_ignored(temporary, ignored_parts)
    print(result.stdout + result.stderr, end='')
    if result.returncode:
        raise SystemExit(f'Ignored quests fixture failed (exit {result.returncode})')
    for label, key, old, new in (
        ('removed IDs remain ignored', 'load', 'IgnoredQuests.clear();', ''),
        ('ignored quest accepted', 'accept', ' || sPlayerbotAIConfig.IgnoredQuests.contains(quest->GetQuestId())', ''),
        ('ignored quest selected for RPG', 'worth', '    if (sPlayerbotAIConfig.IgnoredQuests.contains(quest->GetQuestId()))\n        return false;\n', ''),
    ):
        mutated = dict(ignored_parts)
        mutated[key] = ignored_parts[key].replace(old, new)
        assert mutated[key] != ignored_parts[key], label
        if not build_ignored(temporary, mutated).returncode:
            raise SystemExit(f'Ignored quests fixture did not reject: {label}')
        print(f'Ignored quests mutation rejected: {label}')


# Shields share subclass 6 with polearms. A stone chosen by subclass alone is
# cast on the shield, and the server refuses it on every out-of-combat tick.
# Compile the real stone choice and imbue action against the core item enums.
item_template = (core / 'src/server/game/Entities/Item/ItemTemplate.h').read_text()
item_header = (core / 'src/server/game/Entities/Item/Item.h').read_text()
imbue = (module / 'Ai/Base/Actions/ImbueAction.cpp').read_text()
assert re.search(r'\buint32 Class;', item_template) and re.search(r'\buint32 SubClass;', item_template)
assert re.search(r'#define INVENTORY_SLOT_BAG_0\s+255\b', player_header)
stone_parts = {
    'item_enums': '\n'.join(function(item_template, 'enum ' + name) + ';'
                            for name in ('ItemClass', 'ItemSubclassWeapon', 'ItemSubclassArmor')),
    'slots': function(player_header, 'enum EquipmentSlots') + ';\n' + function(item_header, 'enum EnchantmentSlot : uint8') + ';',
    'stone_ids': '\n'.join(function(ai_header, 'enum ' + name) + ';' for name in ('SharpeningStoneId', 'WeightstoneId')),
    'find': function(ai_source, 'Item* PlayerbotAI::FindStoneFor(Item* weapon) const'),
    'apply': function(imbue, 'bool ImbueWithStoneAction::Execute(Event /*event*/)'),
}
stone_source = r'''
#include <cassert>
#include <cstdint>
#include <iostream>
#include <iterator>
#include <utility>
#include <vector>
using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
ITEM_ENUMS
SLOTS
STONE_IDS
constexpr uint8 INVENTORY_SLOT_BAG_0 = 255;
enum UnitStandStateType : uint8 { UNIT_STAND_STATE_STAND = 0, UNIT_STAND_STATE_SIT = 1 };
enum AuraType : uint32 { SPELL_AURA_MOD_STEALTH = 16 };
static_assert(uint32(ITEM_SUBCLASS_ARMOR_SHIELD) == uint32(ITEM_SUBCLASS_WEAPON_POLEARM));

struct ItemTemplate { uint32 ItemId, Class, SubClass; };
class Item
{
public:
    Item(uint32 entry, uint32 itemClass, uint32 subClass) : proto{entry, itemClass, subClass} {}
    ItemTemplate const* GetTemplate() const { return &proto; }
    uint32 GetEnchantmentId(EnchantmentSlot slot) const { return slot == TEMP_ENCHANTMENT_SLOT ? temporary : 0; }
    ItemTemplate proto;
    uint32 temporary = 0;
};
class Player
{
public:
    bool IsInCombat() const { return false; }
    bool HasAura(uint32) const { return false; }
    void RemoveAurasByType(AuraType) {}
    uint8 getStandState() const { return stand; }
    void SetStandState(uint8 state) { stand = state; }
    Item* GetItemByPos(uint8 bag, uint8 slot) const
    {
        assert(bag == INVENTORY_SLOT_BAG_0);
        return slot == EQUIPMENT_SLOT_MAINHAND ? mainHand : slot == EQUIPMENT_SLOT_OFFHAND ? offHand : nullptr;
    }
    uint8 stand = UNIT_STAND_STATE_SIT;
    Item* mainHand = nullptr;
    Item* offHand = nullptr;
    std::vector<Item*> bags;
};
struct Event {};
using Uses = std::vector<std::pair<uint32, uint8>>;
class PlayerbotAI
{
public:
    explicit PlayerbotAI(Player* bot) : bot(bot) {}
    Item* FindStoneFor(Item* weapon) const;
    // Like the production lookup: a consumable or trade good with this entry in the bags.
    Item* FindConsumable(uint32 itemId) const
    {
        for (Item* item : bot->bags)
            if ((item->proto.Class == ITEM_CLASS_CONSUMABLE || item->proto.Class == ITEM_CLASS_TRADE_GOODS) &&
                item->proto.ItemId == itemId)
                return item;
        return nullptr;
    }
    void ImbueItem(Item* item, uint8 slot) { used.emplace_back(item->proto.ItemId, slot); }
    void SetNextCheckDelay(uint32) {}
    Player* bot;
    Uses used;
};
class ImbueWithStoneAction
{
public:
    explicit ImbueWithStoneAction(PlayerbotAI* botAI) : botAI(botAI), bot(botAI->bot) {}
    bool Execute(Event event);
private:
    PlayerbotAI* botAI;
    Player* bot;
};
FIND
APPLY

Uses Apply(Player& player)
{
    PlayerbotAI ai(&player);
    assert(ImbueWithStoneAction(&ai).Execute(Event()));
    return ai.used;
}

int main()
{
    Item sword(1, ITEM_CLASS_WEAPON, ITEM_SUBCLASS_WEAPON_SWORD), mace(2, ITEM_CLASS_WEAPON, ITEM_SUBCLASS_WEAPON_MACE);
    Item polearm(3, ITEM_CLASS_WEAPON, ITEM_SUBCLASS_WEAPON_POLEARM), dagger(4, ITEM_CLASS_WEAPON, ITEM_SUBCLASS_WEAPON_DAGGER);
    Item shield(5, ITEM_CLASS_ARMOR, ITEM_SUBCLASS_ARMOR_SHIELD);
    Item sharpening(HEAVY_SHARPENING_STONE, ITEM_CLASS_CONSUMABLE, 8), weight(HEAVY_WEIGHTSTONE, ITEM_CLASS_CONSUMABLE, 8);
    Player tank;
    tank.bags = {&sharpening, &weight};
    tank.mainHand = &sword;
    tank.offHand = &shield;
    // The blade takes its stone; the shield never gets a cast the server refuses.
    assert(Apply(tank) == Uses({{HEAVY_SHARPENING_STONE, EQUIPMENT_SLOT_MAINHAND}}));
    assert(tank.stand == UNIT_STAND_STATE_STAND);
    sword.temporary = 1;
    assert(Apply(tank).empty());
    tank.mainHand = &mace;
    assert(Apply(tank) == Uses({{HEAVY_WEIGHTSTONE, EQUIPMENT_SLOT_MAINHAND}}));
    tank.bags = {&sharpening};
    assert(Apply(tank).empty());
    // Polearms and off-hand blades still take sharpening stones.
    Player dual;
    dual.bags = {&sharpening};
    dual.mainHand = &polearm;
    dual.offHand = &dagger;
    assert(Apply(dual) == Uses({{HEAVY_SHARPENING_STONE, EQUIPMENT_SLOT_MAINHAND},
                                {HEAVY_SHARPENING_STONE, EQUIPMENT_SLOT_OFFHAND}}));
    std::cout << "Weapon stones: blades and blunt weapons take their stone; shields are never treated as polearms\n";
}
'''


def build_stones(directory, parts):
    text = stone_source
    for key, value in parts.items():
        text = text.replace(key.upper(), value)
    source_path = directory / 'stones.cpp'
    source_path.write_text(text)
    executable = directory / 'stones'
    subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', *SANITIZER_FLAGS,
                    str(source_path), '-o', str(executable)], check=True)
    return subprocess.run([str(executable)], capture_output=True, text=True, check=False, timeout=TIMEOUT)


with tempfile.TemporaryDirectory(prefix='portable-playerbot-weapon-stones-') as temporary:
    temporary = Path(temporary)
    result = build_stones(temporary, stone_parts)
    print(result.stdout + result.stderr, end='')
    if result.returncode:
        raise SystemExit(f'Weapon stones fixture failed (exit {result.returncode})')
    mutated = dict(stone_parts)
    mutated['find'] = stone_parts['find'].replace(' || item_template->Class != ITEM_CLASS_WEAPON', '')
    assert mutated['find'] != stone_parts['find'], 'shield stone mutation was not applied'
    if not build_stones(temporary, mutated).returncode:
        raise SystemExit('Weapon stones fixture did not reject: stone cast on a shield')
    print('Weapon stones mutation rejected: stone cast on a shield')
