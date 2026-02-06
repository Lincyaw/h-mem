# h-mem Web UI Comprehensive Redesign

**Date**: 2026-02-06
**Status**: Approved
**Style**: Minimal Dark
**Layout**: Collapsible 3-Panel

## Overview

Complete redesign of the h-mem web visualization interface to create an all-in-one dashboard for:
- Memory browsing (explore entities, facts, skills, processes)
- Knowledge graph visualization
- Debugging (inspect provenance, Q-values, lineage)
- Stats overview

## Critical Fixes Required

1. **Remove EVENT references** - EVENT/EventNode was removed from schema
2. **Add ENTITY and PROCESS types** - Missing from frontend GraphQL types
3. **Update stats display** - Remove "Total Events", add Entities/Processes

## Layout Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  [≡]  h-mem        🏷️42 📋128 ⚙️23 🎯8 💡5         [?] [⚙️] │
├────────┬─────────────────────────────────────────┬───────────┤
│        │                                         │           │
│  LEFT  │                                         │   RIGHT   │
│ PANEL  │            GRAPH CANVAS                 │   PANEL   │
│ (320px)│         (with floating controls)        │  (320px)  │
│        │                                         │           │
│ Search │                                         │  Details  │
│ Browse │                                         │  Actions  │
│ Filter │                                         │  Lineage  │
│        │                                         │           │
├────────┴─────────────────────────────────────────┴───────────┤
│              Legend: 🏷️Entity ◇  📋Fact ▢  ⚙️Process ☆ ...   │
└──────────────────────────────────────────────────────────────┘
```

### Panel Behaviors

- **Left panel**: Click `[≡]` to collapse to 48px icon strip
- **Right panel**: Auto-collapses when no node selected
- **Stats bar**: Compact metrics, clickable to jump to Browse
- **Legend**: Bottom bar, toggleable visibility

## Component Specifications

### 1. Header Bar

```
[≡] h-mem          🏷️ 42  📋 128  ⚙️ 23  🎯 8  💡 5    [?] [⚙️]
```

- Hamburger toggles left panel
- Stats with icons, clickable to browse that type
- Help button opens keyboard shortcuts modal
- Settings for future preferences

### 2. Left Panel - Search & Browse

**Tab-based with two modes:**

#### Search Mode
```
┌─────────────────────────┐
│  [🔍 Search] [📂 Browse] │
├─────────────────────────┤
│  ┌─────────────────┐    │
│  │ Search...    🔍 │    │
│  └─────────────────┘    │
│  Type: [All ▼]          │
│                         │
│  Results list...        │
│  - Entity badge + label │
│  - Truncated ID         │
└─────────────────────────┘
```

#### Browse Mode
```
┌─────────────────────────┐
│  Accordion by type:     │
│  ┌─────────────────────┐│
│  │ 🏷️ Entity      (42) ││
│  │ 📋 Fact        (128)││
│  │ ⚙️ Process     (23) ││
│  │ 🎯 Skill       (8)  ││
│  │ 💡 Principle   (5)  ││
│  │ 💬 Conversation(67) ││
│  └─────────────────────┘│
│                         │
│  Expanded items:        │
│  ├─ item-name           │
│  ├─ item-name           │
│  └─ item-name           │
└─────────────────────────┘
```

**Behaviors:**
- Click type → expand accordion, load items
- Items sorted by Q-value (desc) or recency
- Click item → add to graph + select + show details
- Double-click → expand its neighborhood

### 3. Right Panel - Details

**Three collapsible sections:**

#### Header
```
┌─────────────────────────┐
│  SKILL                  │ ← Type badge
│  skill-creation     [×] │ ← Title + close
│  ID: sk_abc...     [📋] │ ← Truncated + copy
└─────────────────────────┘
```

#### Properties Section (expanded by default)
```
┌─────────────────────────┐
│ ▼ Properties            │
├─────────────────────────┤
│  Description            │
│  "Guidelines for..."    │
│                         │
│  Trigger Pattern        │
│  `create.*skill`        │
│                         │
│  Q-Value     ████░ 0.82 │ ← Visual progress bar
│  Version     3          │
│  Created     2 days ago │ ← Human-readable (date-fns)
│  Deprecated  No         │
└─────────────────────────┘
```

#### Lineage Section (collapsed by default)
```
┌─────────────────────────┐
│ ▶ Lineage (3 nodes)     │
├─────────────────────────┤
│  💬 Conversation        │
│    ↓ GENERATES          │
│  ⚙️ Process             │
│    ↓ INDUCED            │
│  🎯 Skill (current)     │ ← Highlighted
└─────────────────────────┘
```

#### Actions Section
```
┌─────────────────────────┐
│ ▶ Actions               │
├─────────────────────────┤
│  [Expand ↔]  [Focus 🎯] │
│  [Deprecate] [Edit ✏️]  │
└─────────────────────────┘
```

**Action behaviors:**
- **Expand**: Load upstream/downstream into graph
- **Focus**: Center on node, dim unrelated nodes
- **Deprecate**: Modal with reason input
- **Edit**: Inline editing for Q-value, description

### 4. Graph Canvas

**Visual specifications:**
- Node size: 80px (up from 60px)
- Labels: Up to 40 chars, multi-line wrap
- Selected: White glow effect
- Deprecated: 50% opacity + dashed red border
- Hover: Tooltip with full label + type + Q-value

**Floating controls (top-left):**
```
┌──────┐
│ + −  │ ← Zoom in/out
│ ⊡    │ ← Fit to view
└──────┘
```

**Layout picker (top-right):**
```
┌──────────┐
│ cose ▼   │ → cose, circle, grid, dagre
└──────────┘
```

**Legend bar (bottom, toggleable):**
```
🏷️Entity ◇  📋Fact ▢  ⚙️Process ☆  🎯Skill ⬡  💡Principle ◆  💬Conv ▭
```

**Interactions:**
- Single click → select node
- Double click → expand neighborhood
- Right-click → context menu (expand, focus, deprecate, copy ID)
- Drag canvas → pan
- Scroll → zoom
- Drag node → reposition (sticky)

### 5. Node Type Styling

| Type         | Color   | Shape           | Icon |
|--------------|---------|-----------------|------|
| Entity       | #f97316 | octagon         | 🏷️   |
| Fact         | #eab308 | rectangle       | 📋   |
| Process      | #06b6d4 | star            | ⚙️   |
| Skill        | #22c55e | hexagon         | 🎯   |
| Principle    | #a855f7 | diamond         | 💡   |
| Conversation | #64748b | round-rectangle | 💬   |

### 6. Empty & Loading States

**Empty state (no nodes):**
```
        🧠

  Start exploring your memory

  • Search for concepts or entities
  • Browse by type in the left panel
  • Double-click nodes to expand

  Keyboard: ⌘K to search, ? for help
```

**Loading states:**
- Lists: Skeleton loaders (pulsing bars)
- Graph: Subtle pulse on loading nodes
- Stats: Shimmer effect

### 7. Keyboard Shortcuts

| Key       | Action                    |
|-----------|---------------------------|
| ⌘/Ctrl+K  | Focus search              |
| ?         | Show help modal           |
| Escape    | Deselect / close panel    |
| Delete    | Remove selected from graph|
| F         | Fit graph to view         |
| E         | Expand selected node      |
| 1-6       | Filter by type in browse  |

## File Changes Required

### New Files
- `src/components/layout/Header.tsx` - Stats header bar
- `src/components/browse/TypeBrowser.tsx` - Accordion browser
- `src/components/browse/TypeList.tsx` - Items within type
- `src/components/detail/LineageTree.tsx` - Provenance display
- `src/components/detail/ActionButtons.tsx` - Node actions
- `src/components/graph/GraphLegend.tsx` - Legend bar
- `src/components/graph/FloatingControls.tsx` - Zoom/layout
- `src/components/shared/Skeleton.tsx` - Loading skeletons
- `src/components/modals/HelpModal.tsx` - Keyboard shortcuts
- `src/hooks/useKeyboardShortcuts.ts` - Global shortcuts

### Modified Files
- `src/lib/graphql-client.ts` - Add Entity/Process types, remove Event
- `src/store/graph-store.ts` - Add browse state, lineage loading
- `src/components/layout/MainLayout.tsx` - New structure
- `src/components/search/SearchBar.tsx` - Tabs, type filter
- `src/components/detail/NodeDetailPanel.tsx` - Sections, lineage
- `src/components/graph/GraphCanvas.tsx` - Larger nodes, tooltips
- `src/components/graph/GraphControls.tsx` - Move to floating
- `src/lib/cytoscape-config.ts` - Updated styles
- `src/index.css` - Additional styles

### Deleted Code
- All EventNode references
- EVENT type from NodeType enum

## Dependencies

No new dependencies required. Current stack:
- React 18
- Zustand (state)
- Cytoscape.js (graph)
- Tailwind CSS (styling)
- graphql-request (API)

Optional addition for better dates:
- `date-fns` for human-readable timestamps ("2 days ago")

## Implementation Order

1. **Phase 1: Data Model Fix** (Breaking)
   - Update graphql-client.ts types
   - Remove Event, add Entity/Process
   - Fix stats display

2. **Phase 2: Layout Restructure**
   - Collapsible panels
   - New header bar
   - Floating graph controls

3. **Phase 3: Browse Mode**
   - Type accordion
   - Item lists with pagination
   - Click-to-graph behavior

4. **Phase 4: Detail Panel Enhancement**
   - Collapsible sections
   - Lineage tree view
   - Action buttons

5. **Phase 5: Graph Improvements**
   - Larger nodes, better labels
   - Legend bar
   - Layout picker
   - Context menu

6. **Phase 6: Polish**
   - Keyboard shortcuts
   - Help modal
   - Loading skeletons
   - Empty states
