---
name: knowledge-extraction
description: Use when processing conversations to extract reusable knowledge (entities, facts, processes)
trigger_pattern: When ingesting a conversation, processing user input, or consolidating memories
tags:
  - meta
  - extraction
  - entity
  - fact
  - process
version: 1
is_protected: true
q_value: 0.5
q_update_count: 0
---

# Knowledge Extraction

## Iron Law

**EXTRACT ONLY WHAT'S WORTH REMEMBERING FOR FUTURE CONVERSATIONS.**

Not everything in a conversation is knowledge. Filter aggressively.

## When to Extract

```
Trigger Conditions:
├── New conversation received for memory storage
├── User explicitly shares a preference or fact
├── A successful procedure/workflow is completed
├── User corrects previous understanding
└── Pattern emerges across multiple interactions
```

## What to Extract

### 1. Entities

Real-world things that have attributes worth tracking.

**Types**:
- `PERSON`: Users, team members, contacts
- `PROJECT`: Codebases, products, initiatives
- `ORGANIZATION`: Companies, teams, departments
- `TOOL`: Software, libraries, frameworks
- `CONCEPT`: Domain concepts, technical terms

**Extract When**:
- Entity has attributes mentioned in conversation
- Entity is referenced multiple times
- Entity relationships are established

**DON'T Extract**:
- Random variable names from code
- Temporary values or config entries
- Error message fragments
- Generic terms without context

### 2. Facts (Attributes)

Properties of entities with scope and cardinality.

**Structure**:
```
Entity -[HAS_ATTRIBUTE]-> Fact
  - slot: "preference.theme" | "tech.database" | "role.title"
  - value: "dark" | "PostgreSQL" | "Tech Lead"
  - cardinality: "single" | "multi"
  - scope: "universal" | "project" | "task" | "session"
```

**Cardinality Rules**:
| Cardinality | Meaning | Conflict Handling | Examples |
|-------------|---------|-------------------|----------|
| `single` | Only one value valid | New value supersedes old | job title, preferred theme |
| `multi` | Multiple values coexist | Deduplicate only | hobbies, skills, languages |

**Scope Rules**:
| Scope | Meaning | Persistence | Examples |
|-------|---------|-------------|----------|
| `universal` | Always true | Permanent | "I prefer dark mode" |
| `project` | True within project | Project lifetime | "This project uses PostgreSQL" |
| `task` | True for current task | Task lifetime | "Currently debugging OOM" |
| `session` | Temporary choice | **DON'T PERSIST** | "Let's try this approach first" |

**Extract When**:
- User EXPLICITLY states preference: "I like...", "I prefer...", "I always..."
- User CONFIRMS a fact: "Yes, we use X", "That's correct"
- Learned configuration that user confirmed works

**DON'T Extract**:
- Assistant suggestions not confirmed by user
- Implementation details (passwords, ports, config values)
- Debugging artifacts (error messages, stack traces)
- Session-scoped temporary decisions

### 3. Processes

Trigger → Action → Outcome patterns that may become skills.

**Structure**:
```
Process {
  trigger: "When/If [condition]"
  action: "Do [steps]"
  outcome: "Result [expected state]"
  is_generalizable: bool
}
```

**Generalizability Test**:

```
Is this process GENERALIZABLE?
├── Can it apply to different projects?
│   └── YES → is_generalizable = true
├── Can it apply to different contexts?
│   └── YES → is_generalizable = true
├── Would another agent benefit from knowing this?
│   └── YES → is_generalizable = true
├── Is it a one-time specific fix?
│   └── NO → is_generalizable = false
└── Is it tied to specific values/passwords?
    └── NO → is_generalizable = false
```

**Generalizable Examples** ✓:
- "When OOM occurs → Capture heap dump → Identify leak source"
- "Before deployment → Run full test suite → Ensure stability"
- "When designing API → Define interfaces first → Consistent contracts"

**NOT Generalizable** ✗:
- "Set password to testpassword123" (specific value)
- "Restart the Neo4j container" (specific debugging step)
- "Change line 234 in auth.py" (too specific)
- "Run `npm install`" (trivial command)

## Extraction Quality Checklist

Before storing extracted knowledge:

- [ ] **Uniqueness**: Is this information already stored?
- [ ] **Relevance**: Will this help in future conversations?
- [ ] **Accuracy**: Did the user confirm this, or is it assumed?
- [ ] **Scope**: Is the scope correctly classified?
- [ ] **Cardinality**: Single or multi? Will conflict detection work?
- [ ] **Generalizability**: For processes, can it transfer to new contexts?
- [ ] **No Secrets**: No passwords, API keys, or sensitive data?

## Anti-patterns

| Anti-pattern | Why It's Wrong | Correct Approach |
|--------------|----------------|------------------|
| Extract everything | Pollutes memory with noise | Filter aggressively |
| Assume user intent | Creates false knowledge | Only extract explicit statements |
| Store session decisions | Clutters with temporary info | Mark as session scope, don't persist |
| Store debugging steps | Not reusable | Only store generalizable processes |
| Duplicate information | Wastes space, causes conflicts | Deduplicate by (entity, slot, value) |
| Store assistant suggestions | User didn't confirm | Wait for user confirmation |

## Extraction Pipeline

```
Conversation Received
    │
    ▼
┌─────────────────────────────────────────┐
│ 1. Read ENTIRE conversation first       │
│    (Don't extract per-message)          │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ 2. Identify Entities with attributes    │
│    - Skip entities without facts        │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ 3. Extract Facts with scope + cardinality│
│    - Skip session-scoped (don't persist)│
│    - Deduplicate by (entity, slot, value)│
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ 4. Identify Processes                   │
│    - Check generalizability             │
│    - Skip non-generalizable             │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ 5. Store in Neo4j with provenance       │
│    Conversation -[:GENERATES]-> Fact    │
│    Conversation -[:GENERATES]-> Process │
│    Entity -[:HAS_ATTRIBUTE]-> Fact      │
└─────────────────────────────────────────┘
```

## Conflict Resolution

When a new fact conflicts with existing knowledge:

| Scenario | Resolution |
|----------|------------|
| Same entity, same slot, different value, cardinality=single | New supersedes old (mark old as superseded) |
| Same entity, same slot, same value | Deduplicate (don't create new) |
| Same entity, same slot, different value, cardinality=multi | Add new value (coexist) |
| Different scope | Both can coexist (universal ≠ project-specific) |

## Examples

### Good Extraction

**Conversation**:
```
User: I always use dark mode, it's easier on my eyes.
Assistant: I'll remember that preference.
User: Also, for this h-mem project, we're using Neo4j as the database.
```

**Extracted**:
```yaml
entities:
  - name: "User"
    type: "PERSON"
  - name: "h-mem"
    type: "PROJECT"

facts:
  - entity: "User"
    slot: "preference.theme"
    value: "dark"
    cardinality: "single"
    scope: "universal"  # "always" = universal

  - entity: "h-mem"
    slot: "tech.database"
    value: "Neo4j"
    cardinality: "single"
    scope: "project"  # specific to h-mem

processes: []  # No generalizable procedures here
```

### Bad Extraction (Don't Do This)

**Same Conversation, Wrong Extraction**:
```yaml
# WRONG - extracted too much
entities:
  - name: "dark mode"      # ✗ Not an entity, it's a value
  - name: "eyes"           # ✗ Irrelevant
  - name: "Neo4j"          # ✗ Should be a value, not entity

facts:
  - entity: "User"
    slot: "reason"
    value: "easier on eyes"  # ✗ Explanation, not a fact
    scope: "session"         # ✗ Wrong scope
```
