# NSAJ UI/UX implementation record

Date: 23 October 2026. Implements the approved [audit and redesign proposal](ui-ux-audit-and-redesign-proposal.md).

## Delivered scope

### Phase 1: shared foundations

- Consolidated the old global CSS layers into semantic colors, typography, spacing, input-specific controls, feedback, badges, focus, and responsive operational layouts.
- Added shared buttons, form fields/sections, notices, status/loading/empty components, and a native modal confirmation dialog with cancel-first focus and trigger-focus restoration.
- Added role-aware links to existing workspaces. Links are presentation only; all backend permissions remain authoritative. Site Admin keeps volume/content administration and is not offered confidential editorial access.
- Moved the skip destination to each real, focusable main landmark. Public content precedes related navigation on narrow screens.
- Made structured API validation readable and available as field errors without changing endpoint contracts.

### Phase 2: pages and interactions

All 18 route patterns were updated: home, issues/archive, article, search, calls, board, templates, presentations, CMS page template, sign-in/MFA, recovery, invitation, author, reviewer, editorial, declarations, content admin, and publication.

- Public pages use quieter headers, compact collections, reading-width articles, grouped board entries, contextual downloads, friendly file formats, retry states, and a single dominant search form. Call deadlines use the configured time zone with an explicit UTC fallback for invalid zone values.
- Author forms have named details/authors/files/submission sections, local feedback, separate save/submit actions, declaration context, submitted-manuscript details, correspondence, revisions and expandable receipts/history.
- Reviewer invitation/active/completed states are distinct. Completion closes editing even if a following refresh fails. Existing completed-assignment manuscript downloads remain available when the server permits them.
- Editorial case actions are grouped by task. Selected-record requests ignore stale responses; forms reset by manuscript/task; production continuation links are cleared on selection changes.
- Declaration management clearly distinguishes current, draft and prior wording. Approval and author submission receive consequence review; no wording is seeded or automatically approved.
- Content admin preserves the working rail/mobile selector, adds URL-backed section location, selected-profile verification context, deliberate publication/access confirmations, and expandable account access controls.
- Publication preserves volume grouping and both drag and keyboard/select moves. Known issues can be selected by identity; article identifiers remain necessary because the existing API has no article lookup collection. Readiness, verification, and publication feedback stay with the task.
- Account screens share a narrow layout, field-linked validation, pending states, MFA-stage focus, and a terminal password-recovery success view. End-user instructions no longer depend on development mail-capture paths.
- Unsaved changes are guarded on record/task switches, links, full unload and browser history. The history guard uses a temporary current-route entry while dirty; it does not persist private form values. Separate dirty forms share a single navigation prompt.

### Phase 3: responsive, accessibility and regression review

- Added automated route-wide checks for a single focusable main and absence of horizontal page overflow at 1440, 768, 390 and 320 CSS pixels. Public layout checks also cover laptop widths and long content.
- Added regressions for deadline zones, error retry, field errors, pending/terminal recovery, selected board context, confirmation cancel/accept, readiness, reviewer completion, production context, stale responses, and unsaved browser Back behavior.
- Keyboard checks cover public menus, skip-link focus, modal initial focus, modal Tab/Shift+Tab containment and focus restoration.
- Inspected browser-test screenshots of public reading, home, account and operational layouts at desktop/mobile widths, including populated review/production forms. Screenshots use isolated test records.
- Kept the existing invitation, MFA, recovery, upload and cross-author isolation integration path.
- Changed only the browser-test harness to use a per-run SQLite file. This prevents concurrent browser requests from sharing a single in-memory SQLite connection. The production PostgreSQL configuration and application backend were not changed.

## Verification

Final command results are recorded below after execution. Earlier failing runs were used to correct selectors, test database concurrency, and history navigation; they are not reported as passing runs.

- Backend regression suite: **22 passed** using the existing Windows mail-capture ACL requirements outside the sandbox.
- Ruff: **passed** for `app`, `tests`, and `alembic`.
- Next.js production build and TypeScript compilation: **passed**.
- Full browser suite with preview coverage enabled: **45 passed, none skipped** (1.4 minutes). Includes all 18 route patterns at 1440, 768, 390 and 320px.
- Demo-disabled workflow checks also passed. The long layout sweep passed when isolated and was split into separate viewport contexts for deterministic execution.
- Final local build: **passed** with backend port 8000 and demo content disabled. Generated route rewrites were checked to confirm the test backend (8123) is absent.

## Practical limits

- The redesign preserves APIs, data, workflow rules, approvals, scanning, private files, and server authorization. No migrations or journal-policy changes were made for this redesign.
- Article lookup and saved board evidence/public-field values are not supplied by existing management list APIs. The UI states these limits and requires complete evidence re-entry when replacing verification; it does not invent missing data or widen access.
- Rich-text CMS conversion, server-wide search/filter/pagination, autosave, and new workflow policies remain outside the approved visual scope.
- Browser semantics/keyboard/reflow checks and source contrast calculations were performed. A human assistive-technology audit and formal WCAG conformance certification were not performed. Production operations/security readiness remain separate from UI completion.

## Developer workflow

From `F:\Projects\NSAJ-FastAPI` in PowerShell:

```powershell
.venv\Scripts\pytest.exe -q
.venv\Scripts\ruff.exe check app tests alembic
npm --prefix frontend run typecheck
```

From `F:\Projects\NSAJ-FastAPI\frontend`:

```powershell
npm run test:e2e
```

That script builds with public demo content disabled, starts isolated test servers on 8123/3123, and removes its exact per-run test database after completion. The existing local development server is not stopped or repurposed. Demo-specific tests require a build with `NSAJ_E2E_DEMO_CONTENT=true`; demo records remain fictional and preview-only.
