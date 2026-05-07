# Web UI Working Items Grouping Plan

This document records how OpenCode groups assistant working items and how to adapt the same interaction model to `pbi-agent` with the existing outer **Working** run retained.

Source inspected:

- Local OpenCode source: `/home/nasirus/opencode/packages/ui/src/components/message-part.tsx`, `/home/nasirus/opencode/packages/ui/src/components/basic-tool.tsx`, `/home/nasirus/opencode/packages/ui/src/components/tool-count-summary.tsx`
- Snapshot: `OpenCode.html`
- Current pbi-agent UI: `webapp/src/components/session/SessionTimeline.tsx`, `webapp/src/components/session/TimelineEntry.tsx`, `webapp/src/components/session/ToolResult.tsx`, `webapp/src/styles/session.css`

## Chosen direction

User-selected scope:

1. **Frontend + small backend/schema changes if useful.**
2. **Keep the current outer `Working` run**, but redesign the inner grouping.
3. **Inspired by OpenCode, adapted to pbi-agent shadcn/Tailwind tokens.**

Primary UX target has three disclosure levels. These levels are a strict nested hierarchy, not three independent display modes:

1. **Level 1, default collapsed state: one compact summary row with counts per tool category.** This is all the user sees inside the opened outer `Working` run until they expand the row.
2. **Level 2, first expansion: a list of every tool call, each rendered as a compact collapsed row.** Expanding level 1 reveals only these rows, not full outputs.
3. **Level 3, second expansion: one detailed card for a selected/expanded tool call.** A level-2 row must be explicitly expanded to reveal the existing full tool input/output card.

Implementation rule: opening a parent level must reveal exactly the next level down. The UI must not jump from level 1 directly to full detail cards. By default, every level-1 group is collapsed; when a level-1 group opens, every level-2 tool row remains collapsed unless the user opens an individual row.

## What OpenCode does

### Data model and grouping

OpenCode renders assistant output as a sequence of `Part` objects, not as one monolithic message. Important part types are:

- `text`: assistant visible message.
- `reasoning`: reasoning/thinking summary.
- `tool`: tool call with `tool`, `state.input`, `state.output`, `state.status`, `state.metadata`.
- `compaction`: divider/separator.

The key grouping function is `groupParts(parts)` in `message-part.tsx`.

OpenCode defines:

```ts
const CONTEXT_GROUP_TOOLS = new Set(["read", "glob", "grep", "list"])
const HIDDEN_TOOLS = new Set(["todowrite"])
```

Then it walks renderable parts in order:

- Consecutive context tools (`read`, `glob`, `grep`, `list`) are grouped into one `PartGroup` with `type: "context"`.
- Every non-context part is emitted as a standalone `PartGroup` with `type: "part"`.
- When a non-context part appears, the current context group is flushed first.
- At the end, any pending context group is flushed.

Pseudocode:

```ts
function groupParts(parts) {
  const groups = []
  let contextStart = -1

  for each part at index:
    if isContextTool(part):
      if contextStart < 0: contextStart = index
      continue

    flushContextGroup(index - 1)
    groups.push({ type: "part", ref: part })

  flushContextGroup(parts.length - 1)
  return groups
}
```

`renderable(part)` hides noise before grouping:

- `todowrite` hidden.
- Pending/running `question` hidden until it is answered/error/completed.
- Empty text/reasoning hidden.
- Unknown unsupported part types hidden.

### Context tool group row: level 1

The collapsed context group renders as one row:

```html
<div data-component="context-tool-group-trigger">
  <span data-slot="context-tool-group-title">
    <span data-slot="context-tool-group-label">
      <ToolStatusTitle active="..." activeText="Exploring" doneText="Explored" />
    </span>
    <span data-slot="context-tool-group-summary">
      <AnimatedCountList items=[read, search, list] />
    </span>
  </span>
  <Collapsible.Arrow />
</div>
```

Observed from `OpenCode.html`:

- Completed label: **Explored**.
- Running label: **Exploring**.
- Summary: `1 read`, `2 searches`, `1 list` etc.
- `glob` and `grep` are counted together as **search/searches**.
- Zero-count categories are omitted.
- The row is compact, text-first, and uses a ghost collapsible style.
- The status label can shimmer while active, then swap to done text.
- The count list animates numbers, but the essential behavior is the count summary, not the animation.

### Context group list: level 2

When the context group opens, OpenCode renders a vertical list:

```html
<div data-component="context-tool-group-list">
  <div data-slot="context-tool-group-item">
    <div data-component="tool-trigger">
      <span data-slot="basic-tool-tool-title">Read</span>
      <span data-slot="basic-tool-tool-subtitle">file.tsx</span>
      <span data-slot="basic-tool-tool-arg">offset=...</span>
    </div>
  </div>
</div>
```

Important behavior:

- The level-2 list items are **not full result cards**.
- They show only a concise tool title, subtitle, and a few arguments.
- They reuse the same `tool-trigger` visual grammar as ordinary tool cards.
- Running items shimmer their title and hide subtitle/args until no longer pending.
- Context group items in OpenCode do not appear to open a full detail card from this grouped list; for `pbi-agent`, we should add level 3 because that is the desired target.

### Standalone tool cards

Non-context tools (`bash`, `edit`, `write`, `apply_patch`, `webfetch`, `websearch`, `task`, etc.) render through `BasicTool` or a custom registered tool component.

`BasicTool` provides:

- One compact trigger row.
- Optional detail content below it.
- Pending/running tools cannot be toggled closed/opened by user while pending.
- `hideDetails` suppresses the detail section entirely.
- `defaultOpen` can be set per tool type:
  - shell default open controlled by a flag.
  - edit/write/apply_patch default open controlled by a flag.
- `forceOpen` and `locked` exist for special cases.

OpenCode `task`/sub-agent tools are special:

- They render as a compact card with agent title + task description.
- If there is a child session id, the trigger becomes a link to the child session.
- The snapshot shows `task-tool-card`, `task-tool-title`, and an external-link action.
- The task is not folded into context counts.

### Reasoning/thinking blocks

OpenCode `reasoning` parts are rendered as their own block if `showReasoningSummaries` is enabled and text is non-empty. They are not merged into the context tool count row. They use markdown and paced/streaming rendering. Visually they are lower chrome than assistant text and tool cards.

For pbi-agent, thinking should remain inside the outer `Working` run but should be grouped separately from tool-count rows, e.g. as a compact **Thinking** row with optional details.

## Current pbi-agent behavior

Current frontend grouping is in `SessionTimeline.tsx`:

- `buildRenderUnits()` groups consecutive `thinking` and `tool_group` timeline items into a single outer `work_run` unit.
- The outer `WorkRun` defaults closed.
- When opened, all inner items are rendered with `TimelineEntry bare`.

Current inner rendering:

- `thinking` bare renders title + full markdown body immediately.
- `tool_group` bare renders every `ToolResult` full card immediately.
- `ToolResult` cards are detailed and heavy: card header, status badge, tool name badge, full stdout/stderr/content sections.

This means pbi-agent currently has only two levels:

1. Outer `Working` row.
2. Full detail cards for every thinking/tool item.

It lacks the desired middle summary/list layer and therefore becomes visually dense when a run performs many tool calls.

## Proposed pbi-agent target model

Keep this top-level shape:

```text
User message
Assistant text fragments, if any
Working                     <- existing outer work-run row, default closed
  Exploring · 3 reads, 2 searches, 1 shell, 1 edit   <- new level 1 inside work-run
    Read TODO.md                                      <- level 2 row
      full detail card                                <- level 3, if opened
    Read MEMORY.md
    Search "timeline-entry"
    Shell bun run typecheck
  Thinking
    markdown detail, if opened
Assistant final message
```

### Level 0: existing outer Working run

Keep the existing `WorkRun` component and semantics:

- It still coalesces consecutive work items between messages.
- It still appears as `Working` with phase/running state.
- It still defaults closed and closes after final assistant message using `closeSignal`.
- It still shows sub-agent summary when relevant.

Change only its expanded body:

- Instead of rendering all `TimelineEntry bare` items directly, render a new `WorkingItemsPanel`.
- `WorkingItemsPanel` builds OpenCode-style groups from the work-run `items`.

### Level 1: group summary rows

Level 1 is the default inner state of an opened outer `Working` run. It is the collapsed parent layer for all tool work. Inside an opened `Working` run, show one compact summary row per contiguous group and do **not** show individual tool rows or result cards until the user expands the summary row.

Required behavior:

- Default state: all level-1 rows are closed.
- Closed level-1 row content is only label + aggregate counts + status/chevron.
- Opening a level-1 row reveals level 2 only: the compact list of individual tool calls.
- Opening a level-1 row must not automatically open any level-2 tool row.
- Closing a level-1 row hides the entire level-2/level-3 subtree but should preserve individual level-2 open state in memory if reasonable, so reopening can restore the user's inspection context.

Group kinds:

1. `context_tools`: consecutive low-noise context tools.
2. `action_tools`: consecutive non-context tool calls. This may be one row or split by action type/status; see grouping rules below.
3. `thinking`: one or more thinking items.
4. `sub_agent`: sub-agent tool call represented by a dedicated navigation card, not by inline level-3 details.

Recommended first implementation:

- Group **all consecutive non-sub-agent tool calls** into one `tool_summary` group, but category-count them by type.
- Keep thinking as separate rows when it appears before/between/after tools.
- Split `sub_agent` calls out of normal tool details and render them as special high-level cards if `tool_name === "sub_agent"` or `subAgentId` is present.

Why: pbi-agent timeline currently receives `tool_group` items, and each `tool_group.items` may already contain several tool entries. Flattening them into individual `WorkingToolCall` records before grouping gives the cleanest UI.

Level-1 row contents:

- Left: chevron.
- Label:
  - Running: **Working**, **Exploring**, or **Running tools** depending on phase/category.
  - Done: **Worked**, **Explored**, or **Tools**.
- Summary counts:
  - `read_file` / `read_image` / `read_web_url` -> `read` / `reads` or split web as `fetch` if clearer.
  - `shell` -> `shell`.
  - `apply_patch` and edit-like metadata -> `edit` / `edits`.
  - `web_search` -> `search` / `searches`.
  - `sub_agent` -> `agent` / `agents` only for summary counts; sub-agent calls still render as dedicated navigation cards rather than expandable detail rows.
  - everything else -> `tool` / `tools`.
- Right: running spinner/dot if any child is running; chevron.

Example labels:

- `Explored · 3 reads, 2 searches`
- `Ran tools · 1 shell, 1 edit`
- `Delegated · 1 agent`
- `Thinking · 2 notes`

### Level 2: collapsed list of individual tool calls

Level 2 is visible only inside an expanded level-1 summary row. It is still a collapsed browsing layer, not the detail layer. When a level-1 tool summary row opens, render a compact list of every flattened tool call.

Required behavior:

- Every level-2 row defaults collapsed.
- A level-2 row is a compact trigger, not a result card.
- Opening a level-2 row reveals level 3 for that tool only.
- Multiple level-2 rows may be open at once unless a later product decision asks for accordion behavior.
- Running rows may show live status, but they should still preserve the hierarchy. If details are unavailable while running, the row can be disabled/locked; it should not force the whole group into full-detail mode.

Each row should show:

- Tool icon using `lucide-react`.
- Human title: `Read`, `Shell`, `Patch`, `Web fetch`, etc. (`Sub-agent` is a special navigation card, not a normal expandable tool row.)
- Subtitle: the most useful input/output identifier.
- Optional args: max 2 short key/value chips or plain muted spans.
- Status on the right: running dot/spinner, done check, failed icon or text.
- Chevron only when details are available.

Rows default collapsed. Clicking a row opens level 3.

Suggested detail extraction:

| Tool | Title | Subtitle | Args |
| --- | --- | --- | --- |
| `shell` | Shell | command, truncated | cwd, timeout |
| `read_file` | Read | path | line range, shape/windowed |
| `read_image` | Image | path | mime/size |
| `read_web_url` | Fetch | URL hostname/path | markdown/truncated |
| `web_search` | Search | query | source count |
| `apply_patch` | Edit/Patch | path or `N files` | operation |
| `sub_agent` | Dedicated sub-agent card | task title | agent type/status; navigates to read-only child session instead of opening inline detail |
| unknown | tool name | best string arg | up to 2 args |

### Level 3: detail card for one tool

Level 3 is the only place where full tool input/output details appear. When a level-2 row opens, render the existing detailed result card below that specific row.

Required behavior:

- Level-3 detail cards are never rendered directly under level 1.
- Level-3 detail cards are never visible in the default state.
- Level-3 content is scoped to one selected/expanded tool call.
- If a tool has no meaningful details, the level-2 row can omit its chevron or show a small disabled state, but it should still participate in the level-2 list.

Implementation should reuse current detail renderers instead of duplicating output logic:

- Keep `ToolResult` as the level-3 detail renderer.
- Extract current card body helpers only if needed.
- `GitDiffResult` remains the rich detail for `apply_patch`/file-edit results.

Changes to `ToolResult`:

- It should become usable in two modes:
  - `variant="detail"` or current default: full card.
  - Optional future `variant="compact"` if needed, but prefer a new `ToolCallRow` for level 2.
- Remove or reduce redundant badges in the detail card only after the grouped header carries the same status/tool name. Avoid double status noise.

## Backend/schema changes recommended

A frontend-only implementation is possible because `TimelineToolGroupItem.items[].metadata` already contains `tool_name`, `arguments`, `result`, `status`, `success`, `call_id`, etc. However, small backend/schema improvements will make grouping reliable.

Recommended direct changes, no migration/backcompat:

### 1. Add stable ids to tool group entries

Current type:

```ts
export type TimelineToolGroupEntry = {
  text: string;
  classes?: string;
  metadata?: ToolCallMetadata;
};
```

Target:

```ts
export type TimelineToolGroupEntry = {
  id: string;
  text: string;
  classes?: string;
  metadata?: ToolCallMetadata;
};
```

Backend should set `id` to:

- tool call id/call_id when available;
- otherwise deterministic item id + index.

Rationale: level-2 open state must be stable across live updates. Using array index will flicker when a running tool updates or a parallel tool result arrives.

### 2. Add normalized display fields where backend already knows them

Optional but helpful:

```ts
metadata: {
  tool_name: string;
  status: "running" | "completed" | "failed";
  call_id?: string;
  display_title?: string;
  display_subtitle?: string;
  display_args?: string[];
  category?: "read" | "search" | "shell" | "edit" | "agent" | "web" | "other";
  ...existing
}
```

Frontend can still infer these, but normalized fields keep labels consistent between SSE live events and saved snapshots.

### 3. Preserve running placeholder entries

`tool_execution_start()` already inserts running items before results arrive. Ensure each pending entry has:

- stable id/call id,
- `metadata.tool_name`,
- `metadata.arguments`,
- `metadata.status = "running"`.

Then result updates should upsert the same entry id, not add a new detail row.

## Frontend implementation sketch

### New types

Create a frontend-only normalized type in `SessionTimeline.tsx` or a new module `workingItems.ts`:

```ts
type WorkingToolCall = {
  id: string;
  parentItemId: string;
  text: string;
  metadata?: ToolCallMetadata;
  status: "running" | "completed" | "failed";
  toolName: string;
  category: "read" | "search" | "shell" | "edit" | "agent" | "web" | "other";
};

type WorkingGroup =
  | { kind: "tools"; key: string; calls: WorkingToolCall[]; running: boolean }
  | { kind: "thinking"; key: string; items: TimelineThinkingItem[]; running: boolean }
  | {
      kind: "sub_agent";
      key: string;
      call: WorkingToolCall;
      subAgentId?: string;
      childSessionId?: string;
      parentSessionId?: string;
      running: boolean;
    };
```

### Flattening

```ts
function flattenToolGroup(item: TimelineToolGroupItem): WorkingToolCall[] {
  return item.items.map((entry, index) => {
    const metadata = entry.metadata;
    const toolName = metadata?.tool_name ?? "tool";
    return {
      id: stableToolEntryId(item, entry, index),
      parentItemId: item.itemId,
      text: entry.text,
      metadata,
      status: inferToolStatus(entry),
      toolName,
      category: categorizeTool(toolName, metadata),
    };
  });
}
```

`stableToolEntryId()` should prefer `entry.id` after schema change, then `metadata.call_id`, then `${item.itemId}:${index}` as a temporary fallback.

### Grouping

Start with simple contiguous grouping:

```ts
function buildWorkingGroups(items: WorkItem[]): WorkingGroup[] {
  const groups = []
  let toolBuffer = []
  let thinkingBuffer = []

  for each item:
    if thinking:
      flushTools()
      thinkingBuffer.push(item)
      continue

    if tool_group:
      flushThinking()
      for each flattened call:
        if call.category === "agent": flushTools(); pushSubAgentCardGroup(call)
        else toolBuffer.push(call)

  flushThinking()
  flushTools()
  return groups
}
```

Future refinement can split context-style read/search/list tools from shell/edit/action tools, but the count row should already count by category.

### Components

Recommended component split:

```text
SessionTimeline.tsx
  WorkRun
    WorkingItemsPanel
      WorkingGroupSummaryRow
      WorkingToolCallList
        WorkingToolCallRow
          ToolResult (detail)
      WorkingSubAgentCard
      WorkingThinkingGroup
```

Or create:

- `webapp/src/components/session/WorkingItemsPanel.tsx`
- `webapp/src/components/session/workingItems.ts`
- `webapp/src/components/session/ToolCallRow.tsx`

Keep `SessionTimeline.tsx` focused on timeline/scroll behavior.

### Open/close behavior

Treat the three levels as a hierarchy of nested collapsibles:

```text
Working run opened by user
  [closed] Level 1 summary row: Tools · 3 reads, 1 shell
    [hidden until level 1 opens] Level 2 compact tool row: Read TODO.md
      [hidden until this level 2 row opens] Level 3 detail card
    [hidden until level 1 opens] Level 2 compact tool row: Shell bun run lint
      [hidden until this level 2 row opens] Level 3 detail card
```

Sub-agent card exception:

```text
Working run opened by user
  Sub-agent card: Researcher · running
    click -> /sessions/:parentSessionId/sub-agents/:childSessionId read-only page
```

Rules:

- Outer `Working` remains default closed.
- When the outer `Working` is opened, all level-1 groups are still closed by default. The opened outer run should show only one or more summary/count rows plus any special sub-agent cards at the appropriate chronological position.
- Level-1 groups default closed even while tools are running. Running state is communicated in the summary row via spinner/shimmer/status text, not by auto-expanding details.
- Level-2 tool rows default closed when their parent level-1 group opens.
- Opening level 1 reveals only level 2 rows; it must not render level 3 cards.
- Opening level 2 reveals the level 3 card for that tool only.
- Opening a level-2 row should not close siblings initially; multiple open is useful for comparing outputs.
- On `closeSignal` from final assistant message:
  - close outer `Working` if user has not explicitly opened historical detail;
  - close level-1 and level-2 details for the active run.
- Preserve open states by stable group key/tool id across live updates, but never use live updates to auto-promote a closed level into an open one.

### Autoscroll

Current `handleUserOpenCollapsible()` only handles the outer active `WorkRun`. Extend the same principle:

- If user opens level 1 or level 2 in the active running work run, align bottom of newly revealed content into view.
- Historical opens must not reset auto-follow or clear `New messages below`.
- New live tool updates should scroll to the latest row, not to the outer WorkRun wrapper.

## Styling guidance

Use pbi-agent tokens/shadcn components, not OpenCode CSS variables directly.

### Visual language

- Compact rows, not full cards, for levels 1 and 2.
- Use `Button variant="ghost" size="sm"` or `CollapsibleTrigger asChild` with semantic row classes.
- Use `Badge` sparingly for counts/status only when text alone is insufficient.
- Prefer muted inline text: `Tools · 3 reads, 1 shell` instead of many badges.
- Use `Separator` or existing subtle borders instead of ad-hoc heavy dividers.
- Use lucide icons with `data-icon="inline-start"` inside buttons when applicable.

### CSS class proposal

Add near existing work-run styles in `session.css`:

```css
.working-items-panel { ... }
.working-group { ... }
.working-group__trigger { ... }
.working-group__summary { ... }
.working-group__count-list { ... }
.working-tool-list { ... }
.working-tool-row { ... }
.working-tool-row__main { ... }
.working-tool-row__title { ... }
.working-tool-row__subtitle { ... }
.working-tool-row__args { ... }
.working-tool-row__status { ... }
.working-tool-row__detail { ... }
.working-thinking-row { ... }
```

### Suggested dimensions

- Level-1 row: `min-height: 2rem`, padding `var(--sp-2) var(--sp-3)`, font `var(--text-xs)` or `var(--text-sm)`.
- Level-2 row: `min-height: 2.25rem`, padding `var(--sp-2)`, smaller icon container than current `ToolResult` card.
- Detail cards: keep current card size, but nest with left padding/border to communicate hierarchy.
- Group list gap: `var(--sp-1)` or `var(--sp-2)`; avoid `var(--sp-3)` between every compact row.

### Accessibility

- Every collapsible trigger needs a meaningful accessible name, e.g. `aria-label="Tools: 3 reads, 1 shell"`.
- Count text must be real text, not only animation/visual spans.
- Running indicators need `aria-label="running"` or hidden decorative plus text status.
- Sub-agent cards should remain keyboard reachable and navigate to the read-only child session; do not expose an inline expand control for them.

## Tool categorization rules

Initial mapping for pbi-agent:

```ts
const TOOL_CATEGORY_BY_NAME = {
  read_file: "read",
  read_image: "read",
  read_web_url: "web",
  web_search: "search",
  shell: "shell",
  apply_patch: "edit",
  sub_agent: "agent",
};
```

Additional heuristics:

- If `isApplyPatchToolMetadata(metadata)` -> `edit` regardless of tool name.
- If `tool_name` contains `grep`, `glob`, or `search` -> `search`.
- If `tool_name` contains `read` or `list` -> `read`.
- Otherwise -> `other`.

Count labels:

| Category | Singular | Plural |
| --- | --- | --- |
| read | read | reads |
| search | search | searches |
| shell | shell | shells |
| edit | edit | edits |
| web | fetch | fetches |
| agent | agent | agents |
| other | tool | tools |

## Sub-agent management

Current pbi-agent already carries `subAgentId` on timeline items and a `subAgents` map in snapshots. The refactor should turn that into a dedicated read-only drill-down experience instead of exposing sub-agent internals inline in the main timeline.

### Main-session sub-agent card

Target behavior in the main session:

- Outer Working row may keep showing aggregate sub-agent summary (`agentSummary`).
- Inside `WorkingItemsPanel`, a `sub_agent` tool call must render as **one dedicated sub-agent card**.
- The sub-agent card is a special row/card, not a normal level-2 tool with level-3 details.
- The card must show only high-level state:
  - agent name/type if known;
  - task title or shortened task instruction;
  - status: queued/running/completed/failed/interrupted/stale as applicable;
  - compact elapsed time or token/cost summary only if already available and not noisy.
- The card must not show raw tool input, raw output, child messages, child tool calls, or `SubAgentToolResult` detail inline.
- While the child agent is running, the card should display an ongoing state using the same subtle running treatment as tool summary rows.
- Completion should update the card status in place without expanding or replacing it with a detail card.

Interaction:

- Clicking/activating the sub-agent card opens the child sub-agent session page.
- The whole card can be the navigation target, or the card can have a clearly labeled primary action such as **Open agent session**.
- Do not combine expand and navigate on the same chevron. For sub-agent cards there is no level-3 inline expansion; the drill-down page is the detail.
- The card must remain keyboard reachable with a clear accessible name, for example `Open sub-agent session: Researcher, running`.

### Hidden read-only sub-agent session page

Clicking a sub-agent card opens a new session-like page containing the full conversation history for that sub-agent run.

Required behavior for the sub-agent page:

- It should reuse the existing session timeline UI as much as possible so child messages, thinking, and tool work are readable with the same working-items grouping behavior.
- It is **read-only**.
- Chat input/composer is disabled and should be replaced by a clear footer/link back to the parent session, e.g. **Back to main session**.
- The interrupt/Stop button must not be visible.
- Follow-up message actions must not be available.
- `ask_user` / pending question UI must not be interactive; child sessions should not request user input from this read-only surface. If an old/persisted pending question somehow exists, render it as inert historical content or a non-actionable notice.
- Runtime controls that mutate execution state, provider/model, attached files, images, or shell-command submission must be hidden or disabled.
- The page should show read-only context in the header, for example `Researcher agent · read-only` and a link back to the parent session.

Visibility and routing constraints:

- This special sub-agent session must be reachable **only** from its parent sub-agent card.
- It must not appear in the normal saved-session sidebar, normal conversation history list, recents, session search, kanban task session links, or notifications as an independent conversation.
- Prefer a nested route that encodes the parent relationship, for example:
  - `/sessions/:parentSessionId/sub-agents/:subAgentSessionId`, or
  - `/sessions/:parentSessionId/agents/:subAgentId` if the backend exposes sub-agent ids rather than child session ids.
- The route loader/API must verify the child belongs to the parent session. A direct URL is acceptable only when the parent/child ids match; otherwise return not found.
- Browser back should return naturally to the parent session when navigated from the card; the explicit footer/header link must also route back to `/sessions/:parentSessionId`.

### Backend/session model requirements

To support the drill-down page, backend events/snapshots should expose stable child-session metadata for every sub-agent card:

```ts
type SubAgentSummary = {
  sub_agent_id: string;
  parent_session_id: string;
  child_session_id: string;
  title: string;
  agent_name?: string;
  task_instruction?: string;
  status: "queued" | "running" | "completed" | "failed" | "interrupted" | "stale";
  started_at?: string;
  ended_at?: string;
};
```

Recommended direct implementation, no migration/backcompat:

- Persist each sub-agent run as a child session/projection with `parent_session_id` and `sub_agent_id`.
- Mark child sessions as hidden/internal so normal session listing excludes them by default.
- Persist or reconstruct the child timeline from sub-agent-scoped events (`sub_agent_id`) so the child page can show the full child conversation history after refresh/restart.
- Include `child_session_id` or a resolvable child route target in the main-session sub-agent card metadata before rendering the card as clickable.
- Keep parent timeline events compact: parent sees only the sub-agent summary card and final status, not all child internals duplicated inline.
- Child-session APIs should be read-only endpoints or existing session detail endpoints with a read-only flag. Mutating endpoints (`messages`, `runs`, `interrupt`, `question-response`, uploads, shell-command) must reject child/read-only sessions if called directly.

### Frontend implementation notes

- Add a `SubAgentCard` or `WorkingSubAgentCard` component used by `WorkingItemsPanel` for `category === "agent"` calls.
- Do not pass sub-agent calls to `ToolResult`; remove the planned inline `SubAgentToolResult` detail from this flow.
- Add a read-only mode to `SessionPage`/timeline composition, driven by route/API payload rather than only frontend route convention.
- In read-only mode:
  - hide interrupt controls;
  - hide/disable composer and replace it with the back link;
  - suppress follow-up affordances and pending-question submission actions;
  - keep timeline scroll, markdown rendering, working-item grouping, copy buttons, and non-mutating inspection controls.
- Make cached query keys distinguish parent sessions from hidden child sessions so opening a child page does not pollute normal saved-session lists.

### Open questions before implementation

- Whether the child page should use `child_session_id` as a true hidden saved-session id or derive entirely from `(parent_session_id, sub_agent_id)` event replay.
- Whether running child pages should stream live child events directly or rely on parent session events filtered by `sub_agent_id`. Prefer direct child session SSE if child sessions are persisted; otherwise filter the parent stream carefully.
- Whether failed sub-agent cards should navigate to the child page even if no child messages were captured. Preferred behavior: navigate when a child timeline exists; otherwise keep the card inert and show the failure summary.

## Testing plan

Frontend unit tests:

- `buildWorkingGroups()` groups consecutive tool calls and splits thinking.
- Tool counts omit zero categories and pluralize correctly.
- Stable keys survive result updates when `call_id` stays the same.
- Running status propagates to group row.
- `ToolCallRow` opens detail card on click.
- `closeSignal` closes level-1 and level-2 details.
- Sub-agent calls render as one high-level card with no inline detail, and clicking it navigates to a read-only child session when metadata provides a child route.

Component tests:

- `SessionTimeline` renders only one inner tool summary row by default after opening `Working`.
- Opening summary reveals compact tool rows, not full detail cards.
- Opening one tool row reveals `ToolResult` detail.
- Existing `apply_patch` default-open behavior is preserved at level 3 if desired, or explicitly changed and tested.
- Sub-agent card shows only high-level state and no inline raw input/output detail.
- Clicking a sub-agent card navigates to the read-only child-session route when metadata includes a child target.
- Read-only child-session page renders history but hides interrupt controls, replaces composer with a back-to-main-session link, and disables follow-up/question submission affordances.

Backend tests if adding entry ids/display fields:

- Running tool start publishes entries with stable ids and `status: running`.
- Tool result upserts same entry id.
- Saved snapshot/replay preserves entry ids/display fields.
- API type generation updated and checked.
- Hidden child sub-agent sessions are excluded from normal saved-session list/search/sidebar payloads.
- Parent/child route or API rejects unrelated ids.
- Mutating endpoints reject child/read-only sessions.
- Child timeline reload/replay preserves sub-agent conversation history after refresh.

Validation by touched surface:

- Frontend-only: `bun run test:web`, `bun run lint`, `bun run typecheck`, `bun run web:build`.
- Backend/schema: add `bun run web:api-types`, relevant `uv run pytest -q --tb=short -x tests/test_web_serve.py tests/test_session.py`, plus Ruff checks.

## Implementation sequence

1. Add backend `TimelineToolGroupEntry.id` and optional normalized display/category fields; regenerate API types.
2. Add backend child sub-agent session/projection metadata (`parent_session_id`, `sub_agent_id`, `child_session_id`, hidden/read-only flags) and read-only detail route/API support.
3. Add `workingItems.ts` with flattening, categorization, count summary, and grouping helpers.
4. Add focused tests for `workingItems.ts`.
5. Add `WorkingItemsPanel`, compact row components, and the special `SubAgentCard` with navigation instead of inline detail.
6. Replace `WorkRun` expanded body from direct `TimelineEntry bare` rendering to `WorkingItemsPanel`.
7. Reuse `ToolResult` for non-sub-agent level-3 detail and adjust detail-card styling only where nested layout needs it.
8. Add read-only child-session page mode: no composer, no interrupt, no follow-up/question submission, and a back-to-main-session link.
9. Update `SessionTimeline`/`SessionPage` tests for the three disclosure levels plus sub-agent drill-down behavior.
10. Run frontend/backend validations and rebuild static app assets.

## Non-goals for the first pass

- Do not replace pbi-agent timeline with OpenCode's full message/part model.
- Do not copy OpenCode styles or CSS variables directly.
- Do not add migrations/backcompat shims.
- Do not animate odometer counts unless the static count summary already works well.
- Do not hide all tool details permanently; level 3 must preserve current debuggability.
