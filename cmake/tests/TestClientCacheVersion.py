"""Exercise native SQL update tracking and client cache version propagation.

Compile the real UpdateFetcher with isolated database/hash adapters, replay its
applied SQL in SQLite, and compile the native DB-version reader and packet sender.
This checks update/restart behavior without starting a realm or a WoW client.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
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
source_argument(parser, 'core', default=prepared_core())
core = parser.parse_args().core


def read(path):
    return (core / path).read_text(encoding='utf-8')


updater = read('src/server/database/Updater/UpdateFetcher.cpp')
header = read('src/server/database/Updater/UpdateFetcher.h')
world = read('src/server/game/World/World.cpp')
session = read('src/server/game/Server/WorldSession.cpp')
auth = read('src/server/game/Handlers/AuthHandler.cpp')
module = core / 'modules/mod-individual-progression/data/sql/world/updates'
migration = module / '2026_10_21_00_portable_client_cache.sql'
sql = migration.read_text(encoding='utf-8')
historical = (module / '2026_10_11_00_historical_class_quests.sql').read_text(encoding='utf-8')
quest_update = re.search(r'UPDATE `quest_template`.*?WHERE `ID` = 5634.*?;', historical)[0]
assert '948081' in quest_update and '948090' in quest_update

# Contracts of the isolated adapters: native SQL row shape, SHA1, discovery,
# startup ordering and the configuration default must still match production.
assert 'SELECT `name`, `hash`, `state`, UNIX_TIMESTAMP(`timestamp`) FROM `updates` ORDER BY `name` ASC' in updater
assert 'using QueryResult = std::shared_ptr<ResultSet>;' in read('src/server/database/Database/DatabaseEnvFwd.h')
assert 'using SHA1 = Acore::Impl::GenericHash<EVP_sha1, Constants::SHA1_DIGEST_LENGTH_BYTES>;' in read('src/common/Cryptography/CryptoHash.h')
assert 'SHA1_DIGEST_LENGTH_BYTES = 20' in read('src/common/Cryptography/CryptoConstants.h')
assert '"%02X", bytes[i]' in read('src/common/Utilities/Util.cpp')
assert 'SetConfigValue<uint32>(CONFIG_CLIENTCACHE_VERSION, "ClientCacheVersion", 0);' in read('src/server/game/World/WorldConfig.cpp')
startup = function(read('src/server/apps/worldserver/Main.cpp'), 'bool StartDB()\n{')
assert startup.index('loader.Load()') < startup.index('sWorld->LoadDBVersion();')
initialize = function(session, 'void WorldSession::InitializeSession()')
assert 'uint32 cacheVersion = sWorld->getIntConfig(CONFIG_CLIENTCACHE_VERSION);' in initialize
assert 'SendClientCacheVersion(clientCacheVersion);' in function(session, 'void WorldSession::InitializeSessionCallback(')
assert 'class WorldPacket : public ByteBuffer' in read('src/server/game/Server/WorldPacket.h')
assert 'append<uint32>(value);' in function(read('src/server/shared/Packets/ByteBuffer.h'), 'ByteBuffer& operator<<(uint32 value)')
assert 'data << uint32(quest->GetRewSpell());' in read('src/server/game/Entities/Creature/GossipDef.cpp')
assert 'data << int32(quest->GetRewSpellCast());' in read('src/server/game/Entities/Creature/GossipDef.cpp')

fallback_start = world.index('    if (getIntConfig(CONFIG_CLIENTCACHE_VERSION) == 0)')
fallback = function(world[fallback_start:], '    if (getIntConfig(CONFIG_CLIENTCACHE_VERSION) == 0)')
native_updater = re.sub(r'^#include .*\n', '', updater, flags=re.MULTILINE)
native_header = re.sub(r'^#include .*\n', '', header, flags=re.MULTILINE)

support = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <map>
#include <memory>
#include <regex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>
using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;
using int32 = std::int32_t;
#define AC_DATABASE_API
#define LOG_TRACE(...) (void)0
#define LOG_DEBUG(...) (void)0
#define LOG_INFO(...) (void)0
#define LOG_WARN(...) (void)0
#define LOG_ERROR(...) (void)0
#define LOG_FATAL(...) (void)0
using UpdateException = std::runtime_error;
struct Field {
    std::string value;
    template<class T> T Get() const {
        if constexpr (std::is_same_v<T, std::string>) return value;
        else return static_cast<T>(std::stoull(value));
    }
};
struct ResultSet {
    std::vector<std::vector<Field>> rows;
    std::size_t index = 0;
    Field* Fetch() { return rows.at(index).data(); }
    bool NextRow() { return ++index < rows.size(); }
};
using QueryResult = std::shared_ptr<ResultSet>;
QueryResult Rows(std::vector<std::vector<Field>> rows) {
    if (rows.empty()) return nullptr;
    return std::make_shared<ResultSet>(ResultSet{rows, 0});
}
std::map<std::string, std::string> knownHashes;
namespace Acore {
std::vector<std::string> Tokenize(std::string_view value, char separator, bool) {
    std::vector<std::string> tokens;
    std::stringstream input{std::string(value)};
    for (std::string token; std::getline(input, token, separator);) tokens.push_back(token);
    return tokens;
}
namespace Crypto {
struct SHA1 {
    static std::array<uint8, 20> GetDigestOf(std::string const& value) {
        auto const& hex = knownHashes.at(value);
        std::array<uint8, 20> digest{};
        for (unsigned i = 0; i < 20; ++i) digest[i] = std::stoul(hex.substr(i * 2, 2), nullptr, 16);
        return digest;
    }
};
}}
std::string ByteArrayToHexStr(std::array<uint8, 20> const& bytes) {
    std::string hex;
    for (auto byte : bytes) { hex += "0123456789ABCDEF"[byte >> 4]; hex += "0123456789ABCDEF"[byte & 15]; }
    return hex;
}
'''

propagation = r'''
enum { CONFIG_CLIENTCACHE_VERSION, SMSG_CLIENTCACHE_VERSION };
struct Database {
    uint32 version = 0;
    QueryResult Query(std::string const& query) {
        assert(query == "SELECT db_version, cache_id FROM version LIMIT 1");
        return Rows({{{"fixture"}, {std::to_string(version)}}});
    }
} WorldDatabase;
struct World {
    uint32 configured = 0, _dbClientCacheVersion = 0;
    std::string _dbVersion;
    struct Config {
        World* world;
        template<class T> void OverwriteConfigValue(int, T value) { world->configured = value; }
    } _worldConfig{this};
    uint32 getIntConfig(int) { return configured; }
    void LoadDBVersion();
    void LoadConfigSettings() { FALLBACK }
};
struct WorldPacket {
    int opcode;
    std::vector<uint8> bytes;
    WorldPacket(int opcode_, unsigned) : opcode(opcode_) {}
    void operator<<(uint32 value) { for (unsigned shift = 0; shift < 32; shift += 8) bytes.push_back(value >> shift); }
};
struct WorldSession {
    std::vector<uint8> bytes;
    void SendPacket(WorldPacket const* packet) {
        assert(packet->opcode == SMSG_CLIENTCACHE_VERSION);
        bytes = packet->bytes;
    }
    void SendClientCacheVersion(uint32 version);
};
'''.replace('FALLBACK', fallback)
propagation += function(world, 'void World::LoadDBVersion()')
propagation += '\n' + function(auth, 'void WorldSession::SendClientCacheVersion(')

main = r'''
int main(int argc, char** argv) {
    if (argc == 3 && std::string(argv[1]) == "version") {
        WorldDatabase.version = std::stoul(argv[2]);
        for (uint32 overrideValue : {0u, 77u}) {
            World realm;
            realm.LoadDBVersion();
            for (unsigned repeat = 0; repeat < 3; ++repeat) {
                realm.configured = overrideValue;
                realm.LoadConfigSettings();
                uint32 expected = overrideValue ? overrideValue : WorldDatabase.version;
                assert(realm.configured == expected);
                WorldSession login;
                login.SendClientCacheVersion(realm.configured);
                assert(login.bytes.size() == 4);
                uint32 received = 0;
                for (unsigned i = 0; i < 4; ++i) received |= uint32(login.bytes[i]) << (i * 8);
                assert(received == expected);
            }
        }
        return 0;
    }
    assert(argc == 2);
    HASHES
    std::map<std::string, std::pair<std::string, std::string>> applied;
    unsigned round = 0;
    auto apply = [&](std::string const& query) {
        std::smatch found;
        std::regex entry(R"SQL(REPLACE INTO `updates` .*VALUES \("([^"]+)", "([^"]+)", '([^']+)', [0-9]+\))SQL");
        assert(std::regex_match(query, found, entry));
        applied[found[1]] = {found[2], found[3]};
    };
    auto retrieve = [&](std::string const& query) -> QueryResult {
        if (query == "SELECT `path`, `state` FROM `updates_include`") return Rows({{{"$/empty"}, {"RELEASED"}}});
        assert(query == "SELECT `name`, `hash`, `state`, UNIX_TIMESTAMP(`timestamp`) FROM `updates` ORDER BY `name` ASC");
        std::vector<std::vector<Field>> rows;
        for (auto const& [name, entry] : applied) rows.push_back({{name}, {entry.first}, {entry.second}, {"0"}});
        return Rows(rows);
    };
    auto applyFile = [&](std::filesystem::path const& path) {
        std::cout << round << ' ' << path.filename().string() << '\n';
    };
    for (round = 1; round <= 2; ++round) {
        UpdateFetcher restart(argv[1], apply, applyFile, retrieve, "world", std::string_view("mod-individual-progression"));
        auto result = restart.Update(true, true, false, 3);
        assert(result.updated == (round == 1 ? 2 : 0));
    }
    assert(applied.size() == 2);
}
'''


def database(initial):
    db = sqlite3.connect(':memory:')
    db.executescript('CREATE TABLE version (cache_id INTEGER); CREATE TABLE quest_template '
                     '(ID INTEGER, RewardDisplaySpell INTEGER, RewardSpell INTEGER); '
                     'INSERT INTO quest_template VALUES (5634,13908,19338);')
    db.execute('INSERT INTO version VALUES (?)', (initial,))
    return db


def verify_sql(text):
    for initial in (0, 17, None, 20261022):
        with database(initial) as db:
            db.executescript(quest_update + '\n' + text)
            assert db.execute('SELECT * FROM quest_template').fetchone() == (5634, 948081, 948090)
            expected = 20261022 if initial == 20261022 else 20261021
            assert db.execute('SELECT cache_id FROM version').fetchone() == (expected,)
            db.executescript(text)
            assert db.execute('SELECT cache_id FROM version').fetchone() == (expected,)


verify_sql(sql)
assert re.search(r'UPDATE\s+`version`.*?;', sql, re.DOTALL)
removed = re.sub(r'UPDATE\s+`version`.*?;', '', sql, flags=re.DOTALL)
try:
    verify_sql(removed)
except AssertionError:
    print('Client cache mutation rejected: missing SQL cache version update')
else:
    raise AssertionError('Missing SQL cache bump was accepted')

with tempfile.TemporaryDirectory(prefix='client-cache-fixture-') as temporary:
    work = Path(temporary)
    updates = work / 'modules/mod-individual-progression/data/sql/world/updates'
    updates.mkdir(parents=True)
    (work / 'empty').mkdir()
    files = {'2026_10_11_00_cached_quest.sql': quest_update, migration.name: sql}
    for name, text in files.items():
        (updates / name).write_text(text, encoding='utf-8')
    hashes = '\n'.join('knownHashes[' + json.dumps(text) + '] = "' + hashlib.sha1(text.encode()).hexdigest().upper() + '";'
                       for text in files.values())
    source = support + native_header + native_updater + propagation + main.replace('HASHES', hashes)
    cpp = work / 'fixture.cpp'
    executable = work / ('fixture.exe' if os.name == 'nt' else 'fixture')
    command = [cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror']
    if os.name != 'nt':
        command += [*SANITIZER_FLAGS, '-fno-pie', '-no-pie']

    def compile_run(text):
        cpp.write_text(text, encoding='utf-8')
        subprocess.run(command + [str(cpp), '-o', str(executable)], check=True)
        return subprocess.run([str(executable), str(work)], capture_output=True, text=True, timeout=TIMEOUT, check=False)

    result = compile_run(source)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ['1 ' + name for name in sorted(files)]
    with database(17) as db:
        for line in result.stdout.splitlines():
            db.executescript(files[line.split(' ', 1)[1]])
        version = db.execute('SELECT cache_id FROM version').fetchone()[0]
        assert version == 20261021
        subprocess.run([str(executable), 'version', str(version)], check=True, timeout=TIMEOUT)
    # Removing the native matching-hash early return must detect repeated imports.
    early_return = '                applied.erase(iter);\n                return;\n            }\n        }\n\n        uint32 speed = 0;'
    assert early_return in source
    mutant = source.replace(early_return, early_return.replace('                applied.erase(iter);\n                return;',
                                                              '                /* force reapplication */'), 1)
    result = compile_run(mutant)
    assert result.returncode != 0, 'Native updater accepted forced reapplication on restart'
    print('Client cache mutation rejected: forced SQL reapplication on restart')

print('Client cache: native update applied once; restart skipped; SQL, config override and login version verified')
