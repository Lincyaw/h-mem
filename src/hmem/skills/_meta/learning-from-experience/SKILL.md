---
name: learning-from-experience
description: Use after completing any task to extract reusable patterns
trigger_pattern: After completing a task, resolving a bug, or discovering a new approach
tags:
  - meta
  - learning
  - reflection
version: 1
is_protected: true
q_value: 0.5
q_update_count: 0
---

# Learning from Experience

## Iron Law

**EVERY TASK IS A LEARNING OPPORTUNITY.**

After completing any non-trivial task, evaluate what was learned and whether it should become a reusable skill.

## Post-Task Reflection Process

### Step 1: Assess the Task Outcome

After completing a task, ask:
1. Was the task successful? → Provide "success" feedback to any skills used
2. Did any skills fail? → Provide "failure" feedback
3. Was a new approach discovered? → Candidate for process recording

### Step 2: Provide Feedback on Used Skills

For EVERY skill that was loaded during the task:
```
skill_feedback("skill-name", "success")  # or "failure" or "partial"
```

This is critical for Q-value learning. Without feedback, skills cannot improve.

### Step 3: Identify New Patterns

Check if the task revealed a reusable pattern:

```
Pattern Recognition Checklist:
├── Did I solve a problem in a new way?
│   └── Record as a Process
├── Did I apply the same approach I've used before?
│   └── Search for similar processes, consider skill creation
├── Did I learn something about a tool or system?
│   └── Record as a Fact/Attribute
├── Did I discover a general principle?
│   └── Record as a Principle
└── Did nothing new happen?
    └── That's fine, not every task produces learning
```

### Step 4: Evaluate for Skill Induction

If you've identified a pattern:

1. **Search for similar processes**:
   ```
   processes = search_processes("trigger description")
   ```

2. **Count similar processes**:
   - 0-1 similar: Too early. Record and wait.
   - 2+: Consider skill creation
   - 3+: Strong candidate for skill creation

3. **Assess generalizability**:
   - Can this pattern apply beyond the current project?
   - Would another agent benefit from knowing this?
   - Is it specific enough to be actionable?

### Step 5: Create or Update Skills

Based on the evidence:
- **New pattern with 2+ examples**: Create a new skill
- **Existing skill helped**: Provide success feedback
- **Existing skill was wrong**: Provide failure feedback + edit if needed
- **Existing skill was incomplete**: Edit to add missing steps

## Feedback Loop

The learning cycle is:
```
Task → Skills Used → Outcome → Feedback → Q-value Update → Better Skills
  │                                                              │
  └──────── New Patterns → Process Recording → Skill Induction ──┘
```

This creates a virtuous cycle where:
1. Skills improve through feedback
2. New skills emerge from accumulated processes
3. Bad skills get suspended through low Q-values
4. Good skills rise to the top through high Q-values

## Quality Signals

### Signs the system is learning well:
- Q-values of good skills trending upward
- New skills being created from process clusters
- Low-quality skills being auto-suspended
- Agents finding relevant skills before tasks

### Signs the system needs attention:
- No new skills being created despite many tasks
- All skills having similar Q-values (~0.5)
- No feedback being provided (Q-values frozen)
- Skills being created without source processes

## Anti-patterns

- Skipping feedback after tasks ("I'll do it later")
- Only providing positive feedback (negativity bias avoidance)
- Creating skills from a single impressive instance
- Not searching for existing skills before creating new ones
- Ignoring auto-suspended skills (they need review, not abandonment)
