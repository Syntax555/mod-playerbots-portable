# Shared agent skills

These project-local skills travel with the repository, including fresh clones
and worktrees. Codex discovers them under `.agents/skills/`; agents that read
`AGENTS.md` can load the same files directly. Open a new chat after updating an
existing checkout so its skill catalog includes them.

## Sources

| Collection | Pinned source | Included files | License |
| --- | --- | --- | --- |
| Ponytail | [DietrichGebert/ponytail at `09c434ab73ca43761c5d8b0c5d341926c2fba710`](https://github.com/DietrichGebert/ponytail/tree/09c434ab73ca43761c5d8b0c5d341926c2fba710) | All six directories under upstream `skills/` | [MIT](licenses/ponytail.txt) |
| Matt Pocock Skills | [mattpocock/skills at `5beb35b040e3de97e54fa9e386d7e42d15c295c2`](https://github.com/mattpocock/skills/tree/5beb35b040e3de97e54fa9e386d7e42d15c295c2) | The 27 stable skills listed in upstream `.claude-plugin/plugin.json` | [MIT](licenses/mattpocock-skills.txt) |

Each skill directory is an unchanged upstream copy, including its references,
templates, credits and `agents/openai.yaml` where present. Experimental skills
outside the Matt Pocock plugin manifest are excluded.

## Use

Ponytail's `full` coding guidance is enabled by the root `AGENTS.md`. Choose
other skills when their descriptions match the task. Examples in Codex:
`$ponytail`, `$ponytail-review`, `$diagnosing-bugs`, `$tdd`, and `$code-review`.
These local names have no plugin namespace.

Matt Pocock's original invocation policies are preserved: eleven skills allow
automatic selection; sixteen require the user to name them. The latter include
interviews, issue publishing, implementation orchestration and handoffs.
`$setup-matt-pocock-skills` is available to configure issue-tracker, triage-label
and domain-document conventions when those workflows are wanted.

This is the editable-file installation supported by both upstream projects.
Plugin lifecycle hooks, status displays and automatic plugin updates are not
part of this installation. Ponytail modes are instructions within each chat.

## Update

Review upstream changes and choose an exact commit for each collection. Copy
each complete Ponytail skill directory and each Matt Pocock skill directory
listed in that commit's plugin manifest into this directory. Preserve their
licenses, resources and invocation metadata, and update the source revisions
above in the same change. Remove a skill only after checking references from
the remaining skills and repository guidance.

Verify that every directory has a readable `SKILL.md`, its `name` matches the
directory, and all bundled resources match the selected upstream revision.
Run `git diff --check` before sharing the update.
