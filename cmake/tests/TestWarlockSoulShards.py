"""Check that warlock bots without Soul Shards earn one through Drain Soul.

The production trigger, its registration and the combat strategy run against
small engine stubs. Natural mode disables shard creation, so every warlock
specialization relies on this ordinary source. Mutation checks confirm that the
trigger, its cheap-first ordering and the strategy node are required.
"""

from pathlib import Path
import argparse
import re
import subprocess
import tempfile

from FixtureSupport import cxx, function, prepared_core


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, help='prepared Playerbots src directory')
args = parser.parse_args()
module = args.source or prepared_core(Path(__file__).resolve().parents[2]) / 'modules/mod-playerbots/src'
warlock = module / 'Ai/Class/Warlock'
triggers_header = (warlock / 'WarlockTriggers.h').read_text()
triggers_source = (warlock / 'WarlockTriggers.cpp').read_text()
context = (warlock / 'WarlockAiObjectContext.cpp').read_text()
strategy = (warlock / 'Strategy/GenericWarlockStrategy.cpp').read_text()
actions = (warlock / 'WarlockActions.cpp').read_text()
generic = (module / 'Ai/Base/Trigger/GenericTriggers.cpp').read_text()
generic_header = (module / 'Ai/Base/Trigger/GenericTriggers.h').read_text()

registration = re.search(r'creators\["([^"]+)"\] = &WarlockTriggerFactoryInternal::drain_soul_for_shard;', context)
assert registration, 'Drain Soul shard trigger is not registered'
assert 'static Trigger* drain_soul_for_shard(PlayerbotAI* botAI) { return new DrainSoulForShardTrigger(botAI); }' \
    in context
for guard in ('bool CreateSoulShardAction::Execute(', 'bool CreateSoulShardAction::isUseful('):
    body = function(actions, guard)
    assert body.index('if (sPlayerbotAIConfig.naturalProgression)\n        return false;') < body.index('Player* bot')

production = {
    'classes': '\n'.join([
        re.search(r'class TwoTriggers : public Trigger\n\{.*?\n\};', generic_header, re.S).group(0),
        re.search(r'class OutOfSoulShardsTrigger : public Trigger\n\{.*?\n\};', triggers_header, re.S).group(0),
        re.search(r'class DrainSoulForShardTrigger : public TwoTriggers\n\{.*?\n\};', triggers_header, re.S).group(0),
    ]),
    'functions': '\n'.join([
        re.search(r'static const uint32 SOUL_SHARD_ITEM_ID = \d+;', triggers_source).group(0),
        function(triggers_source, 'uint32 GetSoulShardCount(Player* bot)'),
        function(triggers_source, 'bool OutOfSoulShardsTrigger::IsActive()'),
        function(generic, 'bool TwoTriggers::IsActive()'),
        function(generic, 'std::string const TwoTriggers::getName()'),
        function(strategy, 'void GenericWarlockStrategy::InitTriggers('),
    ]),
}

source = r'''
#include <cassert>
#include <cstdint>
#include <iostream>
#include <map>
#include <memory>
#include <string>
#include <utility>
#include <vector>
using uint32 = std::uint32_t;

class Player
{
public:
    std::map<uint32, uint32> items;
    int scans = 0;
    uint32 GetItemCount(uint32 item, bool inBankAlso) { assert(!inBankAlso); ++scans; return items[item]; }
};
class PlayerbotAI;
class Trigger
{
public:
    Trigger(PlayerbotAI* botAI, std::string name = "", int = 1) : botAI(botAI), name(std::move(name)) {}
    virtual ~Trigger() = default;
    virtual bool IsActive() { return false; }
    virtual std::string const getName() { return name; }
protected:
    PlayerbotAI* botAI;
    std::string name;
};
class AiObjectContext
{
public:
    std::map<std::string, Trigger*> triggers;
    Trigger* GetTrigger(std::string const& name) { return triggers.count(name) ? triggers[name] : nullptr; }
};
class PlayerbotAI
{
public:
    Player* bot;
    AiObjectContext context;
    Player* GetBot() { return bot; }
    AiObjectContext* GetAiObjectContext() { return &context; }
};
class CriticalTarget : public Trigger
{
public:
    bool critical = false;
    using Trigger::Trigger;
    bool IsActive() override { return critical; }
};
struct NextAction
{
    std::string name;
    float relevance;
    NextAction(std::string name, float relevance = 0.0f) : name(std::move(name)), relevance(relevance) {}
};
struct TriggerNode
{
    std::string name;
    std::vector<NextAction> actions;
    TriggerNode(std::string name, std::vector<NextAction> actions) : name(std::move(name)), actions(std::move(actions)) {}
};
struct CombatStrategy
{
    void InitTriggers(std::vector<TriggerNode*>&) {}
};
struct GenericWarlockStrategy : CombatStrategy
{
    void InitTriggers(std::vector<TriggerNode*>& triggers);
};
''' + '\nCLASSES\nFUNCTIONS\n' + r'''
int main()
{
    Player bot;
    PlayerbotAI ai{&bot, {}};
    CriticalTarget target(&ai, "target critical health");
    OutOfSoulShardsTrigger noShard(&ai);
    ai.context.triggers = {{"target critical health", &target}, {"no soul shard", &noShard}};
    DrainSoulForShardTrigger trigger(&ai);
    assert(trigger.getName() == "REGISTERED");

    for (uint32 shards : {0u, 1u, 3u})
        for (bool critical : {false, true})
        {
            bot.items[SOUL_SHARD_ITEM_ID] = shards;
            target.critical = critical;
            bot.scans = 0;
            assert(trigger.IsActive() == (critical && shards == 0));
            // Healthy targets never pay for a bag scan.
            assert(bot.scans == (critical ? 1 : 0));
        }
    bot.items[SOUL_SHARD_ITEM_ID] = 0;
    target.critical = true;
    ai.context.triggers.erase("target critical health");
    assert(!trigger.IsActive());

    std::vector<TriggerNode*> nodes;
    GenericWarlockStrategy().InitTriggers(nodes);
    int matches = 0;
    for (TriggerNode* node : nodes)
    {
        if (node->name == "REGISTERED")
        {
            ++matches;
            assert(node->actions.size() == 1 && node->actions[0].name == "drain soul");
            assert(node->actions[0].relevance > 0.0f && node->actions[0].relevance < 60.0f);
        }
        delete node;
    }
    assert(matches == 1);
    std::cout << "Warlock Soul Shards: shardless bots use Drain Soul on critical-health targets\n";
}
'''


def build(directory, parts, name):
    text = source.replace('CLASSES', parts['classes']).replace('FUNCTIONS', parts['functions'])
    text = text.replace('REGISTERED', registration.group(1))
    (directory / (name + '.cpp')).write_text(text)
    executable = directory / name
    subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer', str(directory / (name + '.cpp')), '-o', str(executable)], check=True)
    return subprocess.run([str(executable)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


mutations = [
    ('bag scan before target health', 'classes', 'TwoTriggers(botAI, "target critical health", "no soul shard")',
     'TwoTriggers(botAI, "no soul shard", "target critical health")'),
    ('Drain Soul with shards in bags', 'functions', 'return GetSoulShardCount(botAI->GetBot()) == 0;',
     'return GetSoulShardCount(botAI->GetBot()) <= 3;'),
    ('strategy keeps only shard creation', 'functions', '"target critical health and no soul shard"', '"unused"'),
]

with tempfile.TemporaryDirectory(prefix='portable-warlock-shards-') as temporary:
    temporary = Path(temporary)
    result = build(temporary, production, 'shards')
    print(result.stdout + result.stderr, end='')
    if result.returncode:
        raise SystemExit(f'Warlock Soul Shard fixture failed (exit {result.returncode})')
    for label, key, old, new in mutations:
        mutated = dict(production)
        mutated[key] = production[key].replace(old, new)
        if mutated[key] == production[key]:
            raise SystemExit(f'{label} mutation was not applied')
        if not build(temporary, mutated, 'mutant').returncode:
            raise SystemExit(f'Warlock Soul Shard fixture did not reject: {label}')
        print(f'Warlock Soul Shard mutation rejected: {label}')
