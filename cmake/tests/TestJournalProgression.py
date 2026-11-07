"""Check the Journal's Progression tab against the pinned Individual Progression rules.

mod-forever-journal reports each character's stage from Individual Progression's
hidden stage quests, and JournalProgression names, for every stage, the boss kill
or quest that moves a character on and the stage it leads to. Individual
Progression alone decides those stages; a renumbered stage, another milestone
boss or a different stage-quest range would make the tab show the wrong goal
while the server still holds the gate. The Journal's stage reader and the
module's own reader are compiled from the production sources and compared for
every stage. Mutations change a tier's next stage, its milestone boss, a quest's
advance and the Journal's stage range, and each must be rejected.
"""

import argparse
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from FixtureSupport import (
    REPOSITORY,
    cxx,
    function,
    prepared_core,
    source_argument,
    sql_rows,
)


DUMP = r'''
dofile(arg[1])
for stage, t in pairs(JournalProgression.tiers) do
  print(table.concat({"tier", stage, t.stage, tostring(t.next)}, "\t"))
  for _, sec in ipairs(t.sections) do
    if sec.raid then print(table.concat({"raid", stage, sec.raid, sec.milestone or ""}, "\t")) end
    for _, s in ipairs(sec.steps or {}) do
      if s.advances then print(table.concat({"advance", stage, s.quest, s.advances}, "\t")) end
    end
  end
end
'''


def compile_and_run(source, directory, name):
    work = Path(directory)
    (work / f'{name}.cpp').write_text(source)
    executable = work / name
    build = subprocess.run([cxx(), '-std=c++20', '-Wall', '-Werror', '-o', str(executable), str(work / f'{name}.cpp')],
                           capture_output=True, text=True, check=False)
    if build.returncode:
        return None, build.stderr
    run = subprocess.run([str(executable)], capture_output=True, text=True, timeout=60, check=False)
    return run.returncode, run.stdout + run.stderr


def stage_rules(ip, directory):
    """NextStage and BossStage from the compiled strict-progression policy."""
    policy = (ip / 'src/StrictEarnedProgressionPolicy.h').read_text()
    bosses = [int(entry) for entry in re.findall(r'case (\d+):',
                                                function(policy, 'constexpr std::uint8_t BossStage('))]
    assert bosses, 'BossStage lists no boss'
    harness = (f'#include "{ip / "src/StrictEarnedProgressionPolicy.h"}"\n#include <cstdio>\n'
               'using namespace StrictEarnedProgressionPolicy;\nint main() {\n'
               '    for (unsigned stage = 0; stage <= LastStage; ++stage)\n'
               '        std::printf("next %u %u\\n", stage, unsigned(NextStage(std::uint8_t(stage))));\n'
               + ''.join(f'    std::printf("boss {entry} %u\\n", unsigned(BossStage({entry}u)));\n' for entry in bosses)
               + '    std::printf("last %u\\n", unsigned(LastStage));\n}\n')
    code, output = compile_and_run(harness, directory, 'policy')
    assert code == 0, output
    rows = [line.split() for line in output.splitlines()]
    following = {int(row[1]): int(row[2]) for row in rows if row[0] == 'next'}
    boss_stage = {int(row[1]): int(row[2]) for row in rows if row[0] == 'boss'}
    last = int(next(row[1] for row in rows if row[0] == 'last'))
    return following, boss_stage, last


def boss_names(core, ip, entries):
    """Names a milestone boss is known by: its creature template or its encounter credit."""
    names = {entry: set() for entry in entries}
    for row in sql_rows(core, 'creature_template', set(entries)):
        names[int(row['entry'])].add(row['name'])
    for path in sorted((ip / 'data/sql').rglob('*.sql')):
        text = path.read_text(encoding='utf-8', errors='replace')
        for statement in text.split(';'):
            body = statement.strip()
            if re.search(r'^(?:INSERT|REPLACE) INTO `creature_template` ', body, re.MULTILINE):
                for entry, _, name in re.findall(r'^\((\d+), (["\'])(.*?)\2,', body, re.MULTILINE):
                    if int(entry) in names:
                        names[int(entry)].add(name.replace("''", "'"))
            elif re.search(r'^INSERT INTO `instance_encounters` ', body, re.MULTILINE):
                for entry, name in re.findall(r'^\(\d+, \d+, (\d+), \d+, \'((?:[^\']|\'\')*)\'\)', body, re.MULTILINE):
                    if int(entry) in names:
                        names[int(entry)].add(name.replace("''", "'"))
    return names


def quest_advances(ip):
    """Stage each quest reward moves a character to in Individual Progression."""
    header = (ip / 'src/IndividualProgression.h').read_text()
    constants = {name: int(value) for name, value in re.findall(r'\b([A-Z_][A-Z0-9_]*)\s*=\s*(\d+)', header)}
    switch = function((ip / 'src/IndividualProgressionPlayer.cpp').read_text(), 'switch (quest->GetQuestId())')
    advances, labels = {}, []
    for line in switch.splitlines():
        label = re.match(r'\s*case (\w+):', line)
        target = re.search(r'UpdateProgressionState\(player, (PROGRESSION_\w+)\)', line)
        if label:
            labels.append(constants.get(label.group(1)))
        elif target:
            advances.update((quest, constants[target.group(1)]) for quest in labels if quest)
        elif re.match(r'\s*break;', line):
            labels = []
    assert advances, 'no quest advances a stage'
    return advances


def read_tiers(lua, tiers, directory):
    script = Path(directory) / 'dump.lua'
    script.write_text(DUMP)
    result = subprocess.run([lua, str(script), str(tiers)], capture_output=True, text=True, timeout=60, check=False)
    if result.returncode:
        raise AssertionError(result.stderr)
    stages, raids, advances = {}, [], []
    for line in result.stdout.splitlines():
        kind, *fields = line.split('\t')
        if kind == 'tier':
            stages[int(fields[0])] = (int(fields[1]), None if fields[2] == 'nil' else int(fields[2]))
        elif kind == 'raid':
            raids.append((int(fields[0]), int(fields[1]), fields[2]))
        else:
            advances.append((int(fields[0]), int(fields[1]), int(fields[2])))
    return stages, raids, advances


def tier_problems(tiers, rules, names, quests):
    stages, raids, advances = tiers
    following, boss_stage, last = rules
    problems = []
    reachable = {following[stage] for stage in following if following[stage]} | {0}
    expected = {stage for stage in reachable if stage < last}
    if set(stages) != expected:
        problems.append(f'tiers {sorted(stages)} differ from the stages {sorted(expected)}')
    for stage, (declared, stage_next) in sorted(stages.items()):
        if declared != stage:
            problems.append(f'tier {stage} declares stage {declared}')
        if stage_next != following.get(stage):
            problems.append(f'tier {stage} leads to {stage_next}, Individual Progression to {following.get(stage)}')
    milestones = {stage: name for stage, _, name in raids if name}
    for stage, (_, stage_next) in sorted(stages.items()):
        entries = [entry for entry, reached in boss_stage.items() if reached == stage_next]
        quest_steps = [quest for tier, quest, reached in advances if tier == stage and reached == stage_next]
        if entries:
            if stage not in milestones:
                problems.append(f'tier {stage} names no milestone boss')
            elif not any(milestones[stage] in names[entry] for entry in entries):
                problems.append(f'tier {stage} milestone {milestones[stage]!r} is not the boss that reaches {stage_next}')
        elif not quest_steps:
            problems.append(f'tier {stage} names nothing that reaches {stage_next}')
    for tier, quest, reached in advances:
        if quests.get(quest) != reached:
            problems.append(f'quest {quest} in tier {tier} advances to {reached}, Individual Progression to {quests.get(quest)}')
    return problems


def reader_problems(journal, ip, directory, name='readers'):
    """Compile the Journal's and the module's stage readers and compare them for every stage."""
    source = (journal / 'src/Journal.cpp').read_text()
    constants = ''.join(re.findall(r'^\s*(constexpr uint(?:8|32) IP_(?:PROGRESSION_QUEST_BASE|STATE_MAX) = \d+;)\n',
                                   source, re.MULTILINE))
    journal_reader = function(source, 'uint8 ProgressionState(Player* player)')
    header = (ip / 'src/IndividualProgression.h').read_text()
    states = function(header, 'enum ProgressionState') + ';'
    ip_reader = function((ip / 'src/IndividualProgression.cpp').read_text(),
                         'uint8 IndividualProgression::GetPlayerProgressionFromQuests(')
    harness = f'''#include <cstdint>
#include <cstdio>
#include <set>
using uint8 = std::uint8_t; using uint32 = std::uint32_t;
enum QuestStatus {{ QUEST_STATUS_NONE = 0, QUEST_STATUS_REWARDED = 6 }};
{states}
struct Player {{
    std::set<uint32> rewarded;
    bool IsInWorld() const {{ return true; }}
    bool IsGameMaster() const {{ return false; }}
    QuestStatus GetQuestStatus(uint32 quest) const {{ return rewarded.count(quest) ? QUEST_STATUS_REWARDED : QUEST_STATUS_NONE; }}
}};
struct {{ bool progressionEnabled = true, eraLocks = true; }} sConfig;
{constants}
{journal_reader}
struct IndividualProgression {{ uint8 GetPlayerProgressionFromQuests(Player* player) const; }};
{ip_reader}
int main() {{
    IndividualProgression module;
    int failures = 0;
    // Every stage reached in order, a lone later stage quest, and quests on either side of the range.
    for (uint32 stage = 0; stage <= 20; ++stage) {{
        Player inOrder, alone;
        for (uint32 i = 1; i <= stage; ++i) inOrder.rewarded.insert(66000 + i);
        alone.rewarded.insert(66000 + stage);
        for (Player* player : {{&inOrder, &alone}}) {{
            unsigned journal = ProgressionState(player), ip = module.GetPlayerProgressionFromQuests(player);
            if (journal != ip) {{ std::printf("stage quests up to %u: Journal %u, Individual Progression %u\\n", stage, journal, ip); ++failures; }}
        }}
    }}
    return failures != 0;
}}
'''
    code, output = compile_and_run(harness, directory, name)
    if code is None:
        return [f'stage readers do not compile: {output}']
    return [output.strip()] if code else []


def check(args, tiers_file, journal, directory):
    rules = stage_rules(args.ip, directory)
    names = boss_names(args.core, args.ip, list(rules[1]))
    problems = tier_problems(read_tiers(args.lua, tiers_file, directory), rules, names, quest_advances(args.ip))
    return problems + reader_problems(journal, args.ip, directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source_argument(parser, 'core', default=prepared_core(), help='prepared core source directory')
    source_argument(parser, 'ip', default=prepared_core() / 'modules/mod-individual-progression')
    source_argument(parser, 'journal', default=prepared_core() / 'modules/mod-forever-journal')
    source_argument(parser, 'addon', default=REPOSITORY / '.module-cache/prepared-source-addons/JournalProgression')
    parser.add_argument('--lua', default=shutil.which('lua5.1') or shutil.which('lua'), help='Lua 5.1 executable')
    args = parser.parse_args()
    if not args.lua:
        parser.error('Lua 5.1 is required')

    with tempfile.TemporaryDirectory(prefix='journal-progression-') as directory:
        problems = check(args, args.addon / 'Tiers.lua', args.journal, directory)
        assert not problems, '\n'.join(problems)
        print('Journal stages, milestones and quest advances match Individual Progression', flush=True)

        tiers = (args.addon / 'Tiers.lua').read_text()
        reader = (args.journal / 'src/Journal.cpp').read_text()
        mutations = (
            ('a tier leads to the skipped stage 11', 'tiers', 'Black Temple.", next = 12', 'Black Temple.", next = 11'),
            ('another milestone boss', 'tiers', 'milestone = "Kil\'jaeden"', 'milestone = "Kalecgos"'),
            ('Into the Breach advances past TBC', 'tiers', 'name = "Into the Breach", advances = 8',
             'name = "Into the Breach", advances = 9'),
            ('the Journal stops before the last stage', 'journal', 'constexpr uint8 IP_STATE_MAX = 18;',
             'constexpr uint8 IP_STATE_MAX = 17;'),
            ('the Journal reads another quest range', 'journal', 'IP_PROGRESSION_QUEST_BASE + i)',
             'IP_PROGRESSION_QUEST_BASE + i + 1)'),
        )
        for index, (label, target, old, new) in enumerate(mutations):
            work = Path(directory) / f'mutant-{index}'
            (work / 'src').mkdir(parents=True)
            original = tiers if target == 'tiers' else reader
            assert original.count(old) == 1, f'{label} mutation was not applied'
            mutated = original.replace(old, new)
            (work / 'Tiers.lua').write_text(mutated if target == 'tiers' else tiers)
            (work / 'src/Journal.cpp').write_text(mutated if target == 'journal' else reader)
            if not check(args, work / 'Tiers.lua', work, directory):
                raise AssertionError(f'Journal progression fixture did not reject {label}')
            print(f'Journal progression mutation rejected: {label}', flush=True)


if __name__ == '__main__':
    main()
