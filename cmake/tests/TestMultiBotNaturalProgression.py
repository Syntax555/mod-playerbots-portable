"""Check that MultiBot's remote talent, gearing and bank commands keep the natural progression refusals.

A natural bot learns its own talents, gears itself through play and banks at a
banker it can reach. The bridge refuses remote talent builds and spec switches,
SelfBot AutoGear and maintenance, and only banks through the native banker
handler with a banker in interaction range. The pinned upstream bridge, which
has none of these refusals, must fail every check.
"""

import argparse
import re

from FixtureSupport import function, pinned_source, prepared_core, source_argument


# Comments and string or character literal contents, blanked so that braces and
# semicolons inside them do not end a statement.
LITERALS = re.compile(r'//[^\n]*|/\*.*?\*/|R"\((?:.|\n)*?\)"|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'', re.DOTALL)


def code(text):
    return LITERALS.sub(lambda match: re.sub(r'[^\n]', ' ', match.group(0)), text)


def earlier_branch(body, branch, effect):
    """Whether branch is an earlier arm of the if/else chain that holds every effect.

    From the end of branch to each effect, every statement that ends at the
    chain's own level must be followed by `else`, so no effect runs once branch
    has been taken.
    """
    start = body.find(branch)
    if start < 0 or body.count(branch) != 1:
        return False
    plain = code(body)
    targets = [match.start() for match in re.finditer(re.escape(effect), body)]
    if not targets or targets[0] < start:
        return False
    depth, needs_else = 0, True
    for cursor in range(start + len(branch), targets[-1]):
        character = plain[cursor]
        if character.isspace():
            continue
        if needs_else and depth == 0:
            if not plain.startswith('else', cursor):
                return False
            needs_else = False
        if character in '({':
            depth += 1
        elif character in ')}':
            depth -= 1
            if depth < 0:
                return False
            needs_else = character == '}' and depth == 0
        elif character == ';' and depth == 0:
            needs_else = True
    return True


def talent_build(bridge):
    body = function(bridge, 'void RunTalentApplyCommand(\n')
    return earlier_branch(body, 'else if (sPlayerbotAIConfig.naturalProgression)\n        reason = "NATURAL_PROGRESSION";',
                          'PlayerbotFactory::InitTalentsByParsedSpecLink(')


def talent_spec(bridge):
    body = function(bridge, 'void RunTalentSpecApplyCommand(\n')
    branch = 'else if (sPlayerbotAIConfig.naturalProgression)\n        reason = "NATURAL_PROGRESSION";'
    return all(earlier_branch(body, branch, effect) for effect in ('bot->CastSpell(', 'bot->ActivateSpec('))


def self_bot_upkeep(bridge):
    body = function(bridge, 'void RunSelfActionCommand(')
    branch = ('else if (sPlayerbotAIConfig.naturalProgression && (action == "AUTOGEAR" || action == "MAINTENANCE"))\n'
              '        reason = "NATURAL_PROGRESSION";')
    return all(earlier_branch(body, branch, effect) for effect in ('PlayerbotFactory::AutoGear(', 'PlayerbotFactory factory('))


def reachable_banker(bridge):
    body = function(bridge, 'Creature* FindNearbyNpcWithFlag(')
    refusal = body.find('if (requireInteraction && !bot->GetNPCIfCanInteractWith(guid, npcFlag))\n            continue;')
    return 0 <= refusal < body.find('return creature;')


def native_bank_move(bridge):
    body = function(bridge, 'uint32 MoveNaturalBankItem(')
    interaction = 'bot->GetNPCIfCanInteractWith(banker->GetGUID(), UNIT_NPC_FLAG_BANKER) != banker)\n        return 0;'
    session = body.find('bot->GetSession()->GetPlayer() != bot')
    first = body.find(interaction)
    activate = body.find('bot->GetSession()->HandleBankerActivateOpcode(activatePacket);')
    again = body.find(interaction, first + 1)
    moves = [body.find(call) for call in ('bot->BankItem(', 'bot->StoreItem(', 'bot->RemoveItem(')]
    return 0 <= session < first < activate < again < min(moves)


def bank_lookup(body):
    lookup = 'Creature* const banker = FindNearbyNpcWithFlag(bot, UNIT_NPC_FLAG_BANKER, sPlayerbotAIConfig.naturalProgression);'
    refusal = 'if (!banker)\n    {\n        reason = sPlayerbotAIConfig.naturalProgression ? "NATURAL_PROGRESSION" : "BANKER_NOT_FOUND";\n        return 0;\n    }'
    return 0 <= body.find(lookup) < body.find(refusal)


def natural_loop(body, move, direct):
    branch = 'if (sPlayerbotAIConfig.naturalProgression)\n        {\n            moved += ' + move
    start = body.find(branch)
    if start < 0:
        return False
    block = function(body[start:], 'if (sPlayerbotAIConfig.naturalProgression)')
    return block.rstrip('} \n').endswith('continue;') and start + len(block) < body.find(direct)


def bank_deposit(bridge):
    body = function(bridge, 'uint32 MoveMatchingBagItemsToBank(')
    return bank_lookup(body) and natural_loop(body, 'MoveNaturalBankItem(bot, banker, item, true, reason);', 'bot->BankItem(')


def bank_withdraw(bridge):
    body = function(bridge, 'uint32 MoveMatchingBankItemsToBags(')
    return bank_lookup(body) and natural_loop(body, 'MoveNaturalBankItem(bot, banker, item, false, reason);', 'bot->StoreItem(')


def exact_deposit(bridge):
    body = function(bridge, 'void RunInventoryItemDepositExactCommand(\n')
    lookup = 'FindNearbyNpcWithFlag(bot, UNIT_NPC_FLAG_BANKER, sPlayerbotAIConfig.naturalProgression);'
    branch = 'else if (sPlayerbotAIConfig.naturalProgression)\n                        moved = MoveNaturalBankItem(bot, banker, sourceItem, true, reason);'
    return 0 <= body.find(lookup) < body.find(branch) and earlier_branch(body, branch, 'bot->BankItem(')


GATES = {
    'remote talent build': talent_build,
    'remote spec switch and dual-spec grant': talent_spec,
    'SelfBot AutoGear and maintenance': self_bot_upkeep,
    'banker in interaction range': reachable_banker,
    'native banker handler': native_bank_move,
    'bank deposit by item': bank_deposit,
    'bank withdrawal by item': bank_withdraw,
    'exact bank deposit': exact_deposit,
}
# Each mutation removes or bypasses one refusal; the named gate must reject it.
MUTATIONS = (
    ('remote talent build',
     ('    else if (sPlayerbotAIConfig.naturalProgression)\n        reason = "NATURAL_PROGRESSION";\n'
      '    else if (!ConsumeTalentApplyRateLimit(requester))'),
     '    else if (!ConsumeTalentApplyRateLimit(requester))'),
    ('remote talent build',
     ('else if (sPlayerbotAIConfig.naturalProgression)\n        reason = "NATURAL_PROGRESSION";\n'
      '    else if (!ConsumeTalentApplyRateLimit(requester))'),
     ('else if (sPlayerbotAIConfig.naturalProgression)\n        reason = "NATURAL_PROGRESSION";\n'
      '    if (!ConsumeTalentApplyRateLimit(requester))')),
    ('remote spec switch and dual-spec grant',
     ('    else if (sPlayerbotAIConfig.naturalProgression)\n        reason = "NATURAL_PROGRESSION";\n'
      '    else if (!ConsumeTalentSpecApplyRateLimit(requester))'),
     '    else if (!ConsumeTalentSpecApplyRateLimit(requester))'),
    ('SelfBot AutoGear and maintenance',
     'sPlayerbotAIConfig.naturalProgression && (action == "AUTOGEAR" || action == "MAINTENANCE")',
     'false && (action == "AUTOGEAR" || action == "MAINTENANCE")'),
    ('banker in interaction range', 'if (requireInteraction && !bot->GetNPCIfCanInteractWith(guid, npcFlag))',
     'if (requireInteraction && !bot)'),
    ('native banker handler',
     ("    // Require the actual banker; do not allow the core's self-bank command exemption.\n"
      '    if (bot->GetNPCIfCanInteractWith(banker->GetGUID(), UNIT_NPC_FLAG_BANKER) != banker)\n        return 0;\n'),
     ''),
    ('native banker handler', 'bot->GetSession()->GetPlayer() != bot || ', ''),
    ('bank deposit by item',
     ('moved += MoveNaturalBankItem(bot, banker, item, true, reason);\n            if (!reason.empty())\n'
      '                return moved;\n            if (requestedCount > 0 && moved >= requestedCount)\n                break;\n'
      '            continue;'),
     ('moved += MoveNaturalBankItem(bot, banker, item, true, reason);\n            if (!reason.empty())\n'
      '                return moved;\n            if (requestedCount > 0 && moved >= requestedCount)\n                break;')),
    ('bank withdrawal by item',
     ('Creature* const banker = FindNearbyNpcWithFlag(bot, UNIT_NPC_FLAG_BANKER, sPlayerbotAIConfig.naturalProgression);\n'
      '    if (!banker)\n    {\n        reason = sPlayerbotAIConfig.naturalProgression ? "NATURAL_PROGRESSION" : "BANKER_NOT_FOUND";\n'
      '        return 0;\n    }\n\n    uint32 moved = 0;\n    while (Item* const item = FindBankItemByEntry(bot, itemId))'),
     ('Creature* const banker = FindNearbyNpcWithFlag(bot, UNIT_NPC_FLAG_BANKER);\n'
      '    if (!banker)\n    {\n        reason = sPlayerbotAIConfig.naturalProgression ? "NATURAL_PROGRESSION" : "BANKER_NOT_FOUND";\n'
      '        return 0;\n    }\n\n    uint32 moved = 0;\n    while (Item* const item = FindBankItemByEntry(bot, itemId))')),
    ('exact bank deposit',
     ('                    else if (sPlayerbotAIConfig.naturalProgression)\n'
      '                        moved = MoveNaturalBankItem(bot, banker, sourceItem, true, reason);\n                    else\n'),
     ('                    else if (sPlayerbotAIConfig.naturalProgression)\n'
      '                        moved = MoveNaturalBankItem(bot, banker, sourceItem, true, reason);\n                    if (true)\n')),
)


def failing(bridge):
    failed = []
    for name, check in GATES.items():
        try:
            passed = check(bridge)
        except ValueError:
            passed = False
        if not passed:
            failed.append(name)
    return failed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source_argument(parser, help='MultiBotBridge.cpp to check instead of the prepared one')
    args = parser.parse_args()
    path = args.source or prepared_core() / 'modules/mod-multibot-bridge/src/MultiBotBridge.cpp'
    if not path.is_file():
        raise SystemExit('PrepareModules.cmake must prepare mod-multibot-bridge first')
    bridge = path.read_text()
    failed = failing(bridge)
    if failed:
        raise SystemExit('MultiBot bridge no longer refuses under natural progression: ' + ', '.join(failed))
    for name, old, new in MUTATIONS:
        if bridge.count(old) != 1:
            raise SystemExit(f'{name} mutation was not applied')
        if name not in failing(bridge.replace(old, new)):
            raise SystemExit(f'Natural progression check did not reject a mutation of the {name} gate')
    missed = set(GATES) - set(failing(pinned_source('mod-multibot-bridge', 'src/MultiBotBridge.cpp')))
    if missed:
        raise SystemExit('The upstream bridge passes natural progression checks: ' + ', '.join(sorted(missed)))
    print('MultiBot natural progression: remote talents, spec switches, SelfBot AutoGear/maintenance and banking '
          'without a reachable banker refused; every gate mutation and the upstream bridge rejected')


if __name__ == '__main__':
    main()
