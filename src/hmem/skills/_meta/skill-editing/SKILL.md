---
name: skill-editing
description: Use when an existing skill needs updating based on new evidence
trigger_pattern: When a skill receives negative feedback or new evidence contradicts it
tags:
  - meta
  - editing
  - evolution
version: 1
is_protected: true
q_value: 0.5
q_update_count: 0
---

# Skill Editing

## Iron Law

**NO EDIT WITHOUT EVIDENCE.**

Every skill edit must be justified by concrete evidence: feedback signals, new processes, or observed failures.

## Decision Tree

```
Skill needs attention:
├── Q-value < 0.3 with 5+ uses?
│   ├── Fixable with content update?
│   │   └── YES → Edit content
│   └── Fundamentally wrong approach?
│       └── YES → Deprecate and create new
├── Q-value < 0.1 with 5+ uses?
│   └── Auto-suspended → Review for deprecation
├── New evidence contradicts skill?
│   ├── Minor correction needed?
│   │   └── Edit without version bump
│   └── Major change to approach?
│       └── Edit with version bump
├── Skill content is stale?
│   └── Update with version bump
└── Skill is protected?
    └── Requires force=True and clear justification
```

## Edit Types

### Minor Edit (no version bump)
- Fixing typos or clarifying language
- Adding small details that don't change the approach
- Updating examples

```
skill_edit(name, new_content, version_bump=False, reason="Clarified step 3")
```

### Major Edit (version bump)
- Changing the approach or methodology
- Adding/removing steps
- Updating based on new evidence
- Correcting wrong information

```
skill_edit(name, new_content, version_bump=True, reason="Added heap analysis step based on proc_xxx evidence")
```

### Deprecation (for broken skills)
- Skill is fundamentally wrong
- Skill is superseded by a better one
- Skill's domain is no longer relevant

Mark as suspended rather than deleting:
```
skill_edit(name, metadata_updates={"is_suspended": true}, reason="Superseded by skill-xyz")
```

## Editing Protected Skills

Meta-skills (skill-discovery, skill-creation, etc.) are protected:
- They require `force=True` to edit
- Edits MUST be justified with clear evidence
- The protection exists because meta-skills control the entire system

## Evidence Requirements

| Action | Minimum Evidence |
|--------|-----------------|
| Minor edit | 1 feedback signal or observation |
| Major edit | 2+ feedback signals or new process data |
| Deprecation | 3+ failure signals or clear supersession |
| Protected edit | Documented reasoning + 2+ evidence points |

## Anti-patterns

- Editing based on gut feeling without evidence
- Making a skill more generic instead of more precise
- Editing a skill that's working well (Q > 0.7)
- Deprecating instead of fixing
- Forgetting to provide a reason for the edit
