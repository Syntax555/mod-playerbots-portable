"""Check native proxy index widths and battleground announcement timestamps.

Compile the production proxy loop and battleground spam protection. Large
indices round-trip through the actual proxy declarations without allocating
billions of sockets; announcement delays run beyond the 32-bit Unix limit.
"""

import argparse
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from FixtureSupport import (
    cxx,
    function,
    prepared_core,
    reject_mutants,
    run_fixture,
    source_argument,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, default=prepared_core(), help='prepared core directory')
args = parser.parse_args()
core = args.source
network = (core / 'src/server/shared/Network/NetworkThread.h').read_text()
proxy = function(network, 'void HandleNewSocketsProxyReadingOnConnect()')
declarations = '\n'.join(re.search(pattern, proxy)[0] for pattern in (
    r'std::size_t index = 0;', r'std::vector<[^>]+> newSocketsToRemoveIndexes;'))
insert = re.search(r'newSocketsToRemoveIndexes\.emplace_back\(index\);', proxy)[0]
socket = (core / 'src/server/shared/Network/Socket.h').read_text()
shared = (core / 'src/server/shared/SharedDefines.h').read_text()
dbc = (core / 'src/server/shared/DataStores/DBCEnums.h').read_text()
defines = (core / 'src/common/Define.h').read_text()
world = (core / 'src/server/game/World/World.h').read_text()
# Keep the configuration double's return width and parameter type native.
config_signature = re.search(r'uint32 getIntConfig\(ServerConfigs index\) const', world)[0]

stub = r'''
#pragma once
#include <cstdint>
#include <functional>
#include <unordered_map>
#define AC_GAME_API
TYPEDEFS
'''.replace('TYPEDEFS', '\n'.join(re.search(r'typedef std::' + name + r'_t ' + name + ';', defines)[0]
                                for name in ('uint8', 'uint32')))

object_guid = r'''
#pragma once
#include "Define.h"
struct ObjectGuid
{
    std::uint64_t value;
    bool operator==(ObjectGuid const&) const = default;
};
template<> struct std::hash<ObjectGuid>
{
    std::size_t operator()(ObjectGuid guid) const { return std::hash<std::uint64_t>{}(guid.value); }
};
'''

world_stub = r'''
#pragma once
#include "Define.h"
enum ServerConfigs
{
    CONFIG_BATTLEGROUND_QUEUE_ANNOUNCER_SPAM_DELAY,
    CONFIG_BATTLEGROUND_QUEUE_ANNOUNCER_LIMIT_MIN_LEVEL,
    CONFIG_BATTLEGROUND_QUEUE_ANNOUNCER_LIMIT_MIN_PLAYERS
};
struct World
{
    CONFIG_SIGNATURE { return index == CONFIG_BATTLEGROUND_QUEUE_ANNOUNCER_SPAM_DELAY ? 30 : 0; }
};
inline World world;
inline World* sWorld = &world;
'''.replace('CONFIG_SIGNATURE', config_signature)

proxy_stub = r'''
PROXY_ENUM;
struct SocketType
{
    bool open = true;
    ProxyHeaderReadingState state = PROXY_HEADER_READING_STATE_NOT_STARTED;
    int reads = 0, starts = 0;
    bool IsOpen() const { return open; }
    ProxyHeaderReadingState GetProxyHeaderReadingState() const { return state; }
    void AsyncReadProxyHeader() { ++reads; state = PROXY_HEADER_READING_STATE_STARTED; }
    void Start() { ++starts; }
};
struct ProxyFixture
{
    std::vector<std::shared_ptr<SocketType>> _newSockets, _sockets, removed;
    int _connections = 0;
    void SocketRemoved(std::shared_ptr<SocketType> const& sock) { removed.push_back(sock); }
    PROXY_LOOP
};
void TestIndexWidth()
{
    static_assert(sizeof(std::size_t) > sizeof(std::uint32_t));
    for (std::size_t large : {std::size_t(INT_MAX) + 1, std::size_t(UINT32_MAX) + 1})
    {
        INDEX_DECLARATIONS
        index = large;
        INDEX_INSERT
        assert(std::size_t(newSocketsToRemoveIndexes.back()) == large);
    }
}
'''.replace('PROXY_ENUM', function(socket, 'enum ProxyHeaderReadingState')) \
   .replace('PROXY_LOOP', proxy).replace('INDEX_DECLARATIONS', declarations).replace('INDEX_INSERT', insert)

fixture = r'''
#include <cassert>
#include <climits>
#include <iostream>
#include <memory>
#include <vector>
#include "BattlegroundSpamProtect.cpp"
#include "ProxyFixture.h"

Seconds fixtureTime;
Seconds GameTime::GetGameTime() { return fixtureTime; }

void TestAnnouncementDelay()
{
    static_assert(sizeof(Seconds::rep) > sizeof(uint32));
    Player player{ObjectGuid{1}}, other{ObjectGuid{2}};
    Battleground bg{BATTLEGROUND_WS};
    auto* spam = BGSpamProtect::instance();
    auto const first = Seconds::rep(UINT32_MAX) + 120;
    fixtureTime = Seconds(first);
    assert(spam->CanAnnounce(&player, &bg, 20, 10));
    assert(spam->CanAnnounce(&bg, BG_BRACKET_ID_FIRST, 20, 10));
    assert(!spam->CanAnnounce(&player, &bg, 20, 10));
    assert(!spam->CanAnnounce(&bg, BG_BRACKET_ID_FIRST, 20, 10));
    // Another character and bracket keep independent announcement delays.
    assert(spam->CanAnnounce(&other, &bg, 20, 10));
    assert(spam->CanAnnounce(&bg, BG_BRACKET_ID_LAST, 80, 10));
    fixtureTime = Seconds(first + 29);
    assert(!spam->CanAnnounce(&player, &bg, 20, 10));
    assert(!spam->CanAnnounce(&bg, BG_BRACKET_ID_FIRST, 20, 10));
    fixtureTime = Seconds(first + 30);
    assert(spam->CanAnnounce(&player, &bg, 20, 10));
    assert(spam->CanAnnounce(&bg, BG_BRACKET_ID_FIRST, 20, 10));
    fixtureTime = Seconds(first + 31);
    assert(!spam->CanAnnounce(&player, &bg, 20, 10));
    assert(!spam->CanAnnounce(&bg, BG_BRACKET_ID_FIRST, 20, 10));
}

void TestProxyRemoval()
{
    auto closed = std::make_shared<SocketType>();
    closed->open = false;
    auto fresh = std::make_shared<SocketType>();
    auto reading = std::make_shared<SocketType>();
    reading->state = PROXY_HEADER_READING_STATE_STARTED;
    auto ready = std::make_shared<SocketType>();
    ready->state = PROXY_HEADER_READING_STATE_FINISHED;
    auto failed = std::make_shared<SocketType>();
    failed->state = PROXY_HEADER_READING_STATE_FAILED;
    ProxyFixture thread;
    thread._newSockets = {closed, fresh, ready, reading, failed};
    thread._connections = 5;
    thread.HandleNewSocketsProxyReadingOnConnect();
    assert(thread._newSockets == (std::vector{fresh, reading}));
    assert(thread._sockets == (std::vector{ready}));
    assert(thread.removed == (std::vector{closed, failed}));
    assert(thread._connections == 3);
    assert(fresh->reads == 1 && fresh->starts == 0);
    assert(reading->reads == 0 && reading->starts == 0);
    assert(ready->reads == 0 && ready->starts == 1);
    thread.HandleNewSocketsProxyReadingOnConnect();
    assert(thread._newSockets == (std::vector{fresh, reading}));
    assert(fresh->reads == 1 && thread._connections == 3);
}

int main()
{
    TestIndexWidth();
    TestAnnouncementDelay();
    TestProxyRemoval();
    std::cout << "Core widths: large proxy indices, native proxy removal and player/bracket delays beyond UINT32_MAX passed\n";
}
'''


def build(directory, executable):
    return [cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror',
            str(directory / 'fixture.cpp'), '-o', str(executable)]


mutations = [
    ('proxy indices narrowed to int', 'ProxyFixture.h',
     'std::vector<std::size_t> newSocketsToRemoveIndexes;', 'std::vector<int> newSocketsToRemoveIndexes;'),
    ('player timestamps narrowed to uint32', 'BattlegroundSpamProtect.cpp',
     'Seconds::rep /*time*/> _players;', 'uint32 /*time*/> _players;'),
    ('bracket timestamps narrowed to uint32', 'BattlegroundSpamProtect.cpp',
     'Seconds::rep /*time*/> _brackets;', 'uint32 /*time*/> _brackets;'),
    ('player time return narrowed to uint32', 'BattlegroundSpamProtect.cpp',
     'Seconds::rep GetTime(ObjectGuid guid)', 'uint32 GetTime(ObjectGuid guid)'),
    ('bracket time return narrowed to uint32', 'BattlegroundSpamProtect.cpp',
     'Seconds::rep GetTime(uint32 key)', 'uint32 GetTime(uint32 key)'),
]

with tempfile.TemporaryDirectory(prefix='portable-core-build-warnings-') as temporary:
    work = Path(temporary)
    for name in ('BattlegroundSpamProtect.cpp', 'BattlegroundSpamProtect.h'):
        shutil.copyfile(core / 'src/server/game/Battlegrounds' / name, work / name)
    shutil.copyfile(core / 'src/server/game/Time/GameTime.h', work / 'GameTime.h')
    shutil.copyfile(core / 'src/common/Utilities/Duration.h', work / 'Duration.h')
    files = {
        'Define.h': stub,
        'ObjectGuid.h': object_guid,
        'Player.h': '#pragma once\n#include "ObjectGuid.h"\n'
                    'struct Player { ObjectGuid guid; ObjectGuid GetGUID() const { return guid; } };\n',
        'DBCEnums.h': '#pragma once\n#include "Define.h"\n'
                      + function(dbc, 'enum BattlegroundBracketId') + ';\n'
                      + re.search(r'#define MAX_BATTLEGROUND_BRACKETS\s+\d+', dbc)[0] + '\n',
        'Battleground.h': '#pragma once\n#include "Define.h"\n'
                          + function(shared, 'enum BattlegroundTypeId') + ';\n'
                          + 'struct Battleground { BattlegroundTypeId type; '
                          'BattlegroundTypeId GetBgTypeID() const { return type; } };\n',
        'World.h': world_stub,
        'ProxyFixture.h': proxy_stub,
        'fixture.cpp': fixture,
    }
    for name, text in files.items():
        (work / name).write_text(text)
    executable = work / 'fixture'
    subprocess.run(build(work, executable), check=True)
    result = run_fixture([str(executable)], 'TestCoreBuildWarnings')
    print(result.stdout + result.stderr, end='')
    assert result.returncode == 0, 'core build warnings fixture failed'
    reject_mutants(work, mutations, build, 'Core build warnings')
