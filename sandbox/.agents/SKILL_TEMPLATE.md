---
name: example-skill
description: Use this skill for one clear sandbox task family. Keep this sentence short, specific, and action-oriented.
---

# Example Skill

Describe the task scope, when to use the skill, and any authorization boundary that matters.

## Help First

Use this section for direct CLI skills whose installed help output should be the source of truth.

```sh
tool --help
```

## Resource Paths

Use this section when the skill ships files under its skill root. `load_skill` lists shipped resource files automatically; reference files with `.agents/skills/<skill-name>/...` paths when commands need them.

- Wrapper script: `.agents/skills/example-skill/scripts/example-skill.sh`
- Supporting files: `.agents/skills/example-skill/scripts/support`

## Usage

Use this section when the skill ships a wrapper script, reference file, template, dataset, or other resource. Read, inspect, or execute shipped resources with sandbox commands.

```sh
.agents/skills/example-skill/scripts/example-skill.sh [options] <input>
```

## Common Commands

Provide bounded examples that match the sandbox command model.

```sh
tool --help
.agents/skills/example-skill/scripts/example-skill.sh --help
```

## Output

Describe what to report: command used, scope, relevant findings, output paths, and failures that affect completion.
