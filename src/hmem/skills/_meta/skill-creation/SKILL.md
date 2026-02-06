---
name: skill-creation
description: Use when you've identified a recurring pattern worth abstracting into a skill
trigger_pattern: When 2+ similar processes exist or a recurring pattern is identified
tags:
  - meta
  - creation
  - induction
version: 1
is_protected: true
q_value: 0.5
q_update_count: 0
---

# Skill Creation

## Iron Law

**NO SKILL WITHOUT 2+ SIMILAR PROCESSES.**

A skill must be abstracted from concrete evidence, never from a single instance or pure speculation.

## When to Create a Skill

```
Decision Tree:
├── Found 2+ similar Processes in Neo4j?
│   └── YES → Candidate for skill creation
├── Same pattern applied successfully 2+ times?
│   └── YES → Candidate for skill creation
├── Only 1 instance of the pattern?
│   └── NO → Wait for more evidence
├── Pattern is project-specific?
│   └── NO → Only if generalizable beyond the project
└── Pattern is a one-time debugging step?
    └── NO → Debugging steps are NOT skills
```

## Creation Process

### Step 1: Gather Evidence

Use ProcessSearchTool to find similar processes:
```
processes = search_processes("trigger pattern description")
```

Require:
- At least 2 processes with similar triggers
- Processes should be generalizable (is_generalizable=true)
- Processes should have positive outcomes

### Step 2: Abstract the Pattern

From the concrete processes, extract:
1. **Generalized trigger**: What situation triggers this skill?
2. **Action template**: Step-by-step procedure (abstracted from specifics)
3. **Expected outcome**: What should happen when applied correctly?
4. **Boundary conditions**: When does this skill NOT apply?

### Step 3: Quality Checklist

Before creating, verify:
- [ ] Pattern is generalizable (works beyond original context)
- [ ] At least 2 source processes
- [ ] Clear trigger condition (not vague)
- [ ] Actionable steps (not just observations)
- [ ] Expected outcome defined
- [ ] No sensitive information (passwords, API keys)
- [ ] Name follows kebab-case convention
- [ ] Description starts with "Use when..."

### Step 4: Create

Use SkillCreateTool with:
- **name**: kebab-case, descriptive (e.g., "debug-memory-leak")
- **description**: "Use when [trigger condition]"
- **content**: Markdown with steps, examples, anti-patterns
- **tags**: 2-5 relevant tags
- **source_process_ids**: IDs of the source processes

## Naming Conventions

- Use kebab-case: `debug-memory-leak`, NOT `debugMemoryLeak`
- Start with action verb: `debug-`, `extract-`, `optimize-`, `handle-`
- Be specific: `debug-memory-leak`, NOT `debug-issue`
- Keep it short: 2-4 words

## Content Structure

```markdown
# Skill Name

## When to Use
[Clear trigger condition]

## Steps
1. [First step]
2. [Second step]
3. [...]

## Examples
[Concrete example of applying this skill]

## Anti-patterns
[What NOT to do]

## Boundary Conditions
[When this skill does NOT apply]
```

## Anti-patterns

- Creating skills from single instances
- Creating skills that are too vague ("be careful")
- Creating skills that are too specific ("fix line 234 in file X")
- Creating skills without source process provenance
- Creating duplicate skills (search first!)
