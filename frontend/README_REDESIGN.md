# NSAJ frontend — complete redesigned source

This archive contains the complete Next.js frontend, including the earlier visual redesign and the functional changes requested on 25 October 2026. Use it with the matching backend update.

## Run

Use Node.js 20.9 or newer:

```sh
npm ci
npm run typecheck
npm run build
npm start
```

Proxy `/api/v1/*` to the FastAPI backend on the same public origin. API calls retain the existing cookie/CSRF flow. No credentials belong in frontend environment variables. Keep demo content disabled in production; the existing `NEXT_PUBLIC_NSAJ_DEMO_CONTENT` flag remains a design-preview setting. Search now shows actual API results, including honest empty states, rather than injecting sample results.

## Implemented changes

- Neutral ivory and cool teal theme with warm amber accents; consistent controls, typography, compact cards, accessible focus states and responsive layouts.
- Calls and announcements immediately below the home hero. One consolidated research-area section with ten areas: the nine requested categories plus the existing Technology category. Category links filter published articles by area.
- Impact-factor placeholder explicitly shows that a verified value is unavailable. The contact address comes from backend configuration.
- A direct Submit a manuscript route presents online and email options. Email remains unavailable until the backend is configured; no fake email address is displayed.
- The publishing journey uses six numbered icon cards that stack on mobile. Its copy describes the real workflow, including possible revision and publication only after acceptance.
- Presentations & resources is removed from Explore research navigation. Its existing route and footer link remain available.
- Author drafts include Area of research and conditional Other Area details. Saved data, completion indicators and final-submission readiness agree with backend validation. Incomplete drafts can still be saved.
- Search supports author/title text and an area selector, with proper loading, error and empty states.
- Admin calls/announcements include full draft editing, local date/time scheduling, approval, rescheduling, cancellation, deletion of unpublished records, and archiving. Edits require reapproval. Existing unsaved-change prompts and confirmations are preserved; stale versions return an actionable error.
- Email claim links survive sign-in within the current tab. New-author invitations lead to the same draft-confirmation screen. An imported draft opens directly in the author workspace, preserving the normal declarations and editorial handoff.

## Latest interface refinements

- Normal-height, full-width keywords input with help below it; Add author alongside email on wide screens.
- Separate amber drafts and teal submitted-manuscript panels, with compact cards, counts and status labels.
- Before you submit is in the left sidebar, using the same completion rules as the submission gate. It starts collapsed on small screens, with progress visible.
- Bell and megaphone panels for announcements and calls; slimmer home publishing stages and horizontal template downloads. Detailed publishing guidance remains available.
- A shared keyboard-accessible calendar across announcements, calls, reviewer deadlines, board appointments and presentation dates. DD/MM/YYYY and 24-hour HH:mm are displayed; the existing local ISO values and UTC conversions remain intact. Clear, reset, date validation and unsaved-change tracking are preserved.
- Assigned editors can download scanned private manuscripts, with failures reported in the existing error area.

Use both updated packages for editor downloads. This round adds no migration beyond the previous update. Preserve your existing `.env`, database and private storage, rebuild the frontend and restart both services.

### Quick acceptance checks

1. Create/save/reopen a draft; enter keywords; add/remove authors; upload a file; confirm declarations; submit and inspect the receipt. Incomplete drafts must still save; incomplete final submissions must stay blocked.
2. Download an assigned manuscript and open it. Unassigned/revoked editors, administrators, anonymous users and unclean files must not gain download access.
3. Select/type dates; test invalid dates, leap days, keyboard arrows and Escape; save/approve/edit/reschedule/cancel/delete. Reopening must show the same local time. Test Clear and form reset.
4. Verify board appointment dates and presentation date/time values in their existing workflows.
5. Check mobile layout, keyboard navigation, announcements/calls with and without content, all template downloads, search and email claim.

## Design decisions

Consolidated navigation and content reduce repetition. Calls and news are visible before the archive; research areas use compact, consistent tiles. The journey communicates stages visually without implying automatic acceptance. Forms expose required fields before submission and preserve draft saving. Scheduled-content actions live alongside each record, while the editor displays the user's local time zone explicitly.

## Backend rollout required

Run `alembic upgrade head` using the accompanying backend. Configure the dedicated IMAP inbox, SMTP delivery and private malware scanner before enabling email intake. The backend README explains credentials, migration, retry commands and operational limitations. Existing roles, private files, declaration approvals and publication permissions remain in force.

## Validation

Production build and TypeScript checks were run. Browser checks use the real FastAPI API for author draft/file/declaration submission and scheduled-content administration. Desktop/mobile layout checks and axe accessibility checks cover the modified flows. Backend regression tests are included in the backend package. No live deployment or external email delivery is included.
