Decisions are locked. Here is the plan.

---

# Plan — Normalize Dialog, AlertDialog, Validation Buttons, DropdownMenu, and Badge in `webapp/`

## Summary

Audit and normalize the five surfaces (`Dialog`, `AlertDialog`, dialog-footer validation buttons, `DropdownMenu`, `Badge`) so every call site uses a single canonical shadcn primitive. Two thin composite primitives (`FormDialog`, `ConfirmDialog`) absorb the repeated dialog boilerplate, the `Badge` primitive grows semantic variants that replace ~6 BEM stylesheets, and bespoke per-component CSS overrides for these primitives are removed from `modal.css`, `utilities.css`, `session.css`, and `settings.css`.

Deliverable for this phase: implementation of Section "Implementation Changes".

## Implementation Checklist

- [X] Add `FormDialog` and `ConfirmDialog` composite primitives.
- [X] Extend `Badge` with `success`, `warning`, `info`, `running`, `completed`, and `failed`; status variants render a built-in leading dot.
- [X] Migrate listed form/wide dialog consumers to `FormDialog`: `ProviderModal`, `ModelProfileModal`, `TaskModal`, `BoardStageEditorModal`, `OnboardingModal`, `ProviderAuthFlowModal`, `RunDetailModal`, `SettingsPreviewDialog`, `ProviderUsageLimitsDialog`.
- [X] Migrate listed confirmation consumers to `ConfirmDialog`: `DeleteSessionModal`, `DeleteConfirmModal`.
- [X] Migrate Badge call sites for status pills, settings tags, command/skill aliases, run/event/tool badges, `WorkspaceBadge`, `ProviderAuthFlowModal`, and session sub-agent status to semantic variants.
- [X] Migrate dropdown sizing for `SessionSidebar` and `SessionPage` profile selector to shadcn defaults / Tailwind width utility.
- [X] Remove targeted dead CSS for dialog action button overrides, delete-confirm overrides, status-pill styles, badge-only styles, dropdown sizing, wide modal/preview shell remnants, and workspace-badge BEM styling.
- [X] Add/update frontend tests for `FormDialog`, `ConfirmDialog`, Badge variants, and migrated modal/status call sites.

## Validation Notes

- [X] `bun run typecheck` — passed.
- [X] Focused Vitest for new primitives and migrated modal/status call sites — passed (`26` tests).
- [X] `bun run lint` — passed.
- [X] `bun run test:web` — passed (`42` files, `494` tests). Existing React `act(...)` warnings from Composer/TimelineEntry remain warnings only.
- [X] `bun run web:build` — passed; static app assets regenerated under `src/pbi_agent/web/static/app`.
- [X] Review fix validation: `bun run test:web -- webapp/src/components/ui/form-dialog.test.tsx` and `bun run typecheck` — passed.
- [X] Review fix validation: `bun run test:web -- webapp/src/components/shared/StatusPill.test.tsx`, `bun run typecheck`, and `bun run lint` — passed.
- [X] Review fix validation: `bun run test:web -- webapp/src/components/ui/badge.test.tsx`, `bun run typecheck`, and `bun run lint` — passed.
- [X] Confidence-gate hardening: `git diff --check` — passed after removing extra blank line at EOF in `webapp/src/styles/session.css`.
- [X] Final frontend gate: `git diff --check`, `bun run lint`, `bun run typecheck`, `bun run test:web` (43 files, 505 tests; existing `act(...)` warnings only), and `bun run web:build` — passed.
- [ ] Manual visual smoke not run in this delegated pass.

## Follow-up Notes

- `app-action-row`, `app-close-icon-button`, and `modal-icon-shell` intentionally remain because they are still used outside this normalization surface.
- The add/install dialogs in `CommandsSettingsSection`, `SkillsSettingsSection`, and `AgentsSettingsSection` still use the broader task-form body/input/list layout classes; they were outside the listed dialog call-site migration and remain covered by existing settings tests.

## Test Plan

- **Unit (Vitest)**: `FormDialog` renders title/description/icon, submits on Enter, disables primary while `isPending`, shows error alert, hides footer when `primaryAction` omitted; `ConfirmDialog` calls `onConfirm`, blocks dismissal while `isPending`, renders error alert.
- **Badge variants**: DOM assertion that each new variant emits expected `data-variant` and renders the leading dot for `running|completed|failed`.
- **Call-site regressions**: run `bun run test:web` and confirm migrated modals pass without their old className-based selectors; update tests to use roles/names and `data-variant` where relevant.
- **Build & lint**: `bun run typecheck`, `bun run lint`, `bun run web:build` after migration; `uv run pytest -q --tb=short -x` is not required (no Python source changes).
- **Visual smoke**: manual pass through Sessions tab (delete session, profile selector dropdown, run history menu, run detail modal), Board tab (task modal, stage editor modal), Settings tab (provider modal, model profile modal, provider auth flow, usage limits dialog, command preview, delete confirms, skill cards), Dashboard tab (runs count badge), and Onboarding modal.

## Assumptions

- The migration accepts minor visual diffs where current CSS deviated from shadcn defaults (e.g. action-button min-width disappears, `status-pill::before` becomes an inline `<span>` dot inside the badge). Visual parity is not a constraint — convergence on shadcn tokens is.
- `ProviderAuthFlowModal` is treated as a form-style dialog even though its internal actions remain step-specific. Multi-step state stays inside the component.
- `RunDetailModal`'s `size="wide"` exists in `FormDialog` and maps to `sm:max-w-4xl`.
- `WorkspaceBadge`, `StatusPill`, and dashboard count badges stay as wrapper components where they own behavior/layout; they no longer hand-style the inner Badge with BEM badge classes.
- No backward-compatibility shims were added.
