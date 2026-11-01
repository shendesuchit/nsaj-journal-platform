# NSAJ journal control update — 30 October 2026

## Install both archives together

These are source updates for your existing Next.js and FastAPI projects, not standalone projects.

1. Back up or commit your current code.
2. Extract FrontEnd.zip. Merge its `src` folder into the frontend project beside `package.json`.
3. Extract backendCode.zip. Merge its `app` folder into your FastAPI project beside `pyproject.toml`.
4. Preserve your existing `.env`, package files, `public` assets, storage, database, virtual environment and migration history. This update does not change the database schema.
5. Stop and restart the backend in PowerShell:
   `.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`
6. In the frontend project run `npm run build`, then `npm run start` (or restart `npm run dev` during development). Keep your existing API proxy configuration.
7. Sign out/in, then open **Admin → Journal control** (`/admin/overview`).

## Changes in this build

- Journal-wide paper tracker: search by title, author and reference; submitted/draft/active counts; ownership, status, pending role and next action. Managed content pages, announcements, calls and issue status remain available below the tracker.
- Open a manuscript for role-by-role responsibilities, recorded workflow checklist, clean manuscript downloads, reviewer reports and accountable activity history.
- Admin assistance: select a responsible user and a permitted action. Supports assignment and decision permission, checks, reviewer invitations/responses/reports, conflict resolution/cancellation, editorial decision, author-supplied revision, production, license/DOI verification, issue assignment, scheduling and publication.
- Existing handlers validate the represented user's permissions and workflow requirements. The admin remains logged in. Audit records identify the actual admin, represented person, reason and source reference. Decisions are attributed to the actual admin recorder; case ownership stays with the assigned editor.
- Reviewer/author-supplied content requires explicit source confirmation. The checklist reflects recorded events; checking a box cannot fabricate a review or bypass a step.
- Stale case snapshots are rejected. Refresh the case after a conflict before acting again.
- New submissions have distinct highlighting. Editorial filters include counts using the same search/owner scope. Author guidance follows current review progress, rather than only the stored manuscript status.
- Generic workflow changes cannot jump into review, decisions or publication. Dedicated actions drive those stages. Decisions that close outstanding reviews require explicit selection and a reason.
- Compact status panels and responsive forms; tracker scrolls within its own container on mobile. Combined date/time input uses the browser's local timezone and sends timezone-aware values.

## Important behavior

- A role alone does not confer case decision authority. First represent an eligible Editor-in-Chief to assign an editor/grant decision permission; then represent that assigned decision editor.
- Reviewer recommendations do not automatically accept a manuscript. The decision editor must record a decision and author letter.
- Issue scheduling/publication applies to all articles in the issue; the represented editor must have access to each affected case. Existing clean-file, metadata, license, DOI and publication-time checks remain enforced.
- Private report comments remain private. Authors see workflow outcomes and decision letters through the existing author workspace. Existing mail behavior is retained; this does not promise new email notifications for every action.
- Managed-page counts refer to content-managed informational pages, not every possible dynamic article URL.

## Verification performed

- Existing backend regression suite: 21 tests passed.
- Added integration coverage: complete assisted review-to-publication flow, permissions, stale state, author revision, attribution, reviewer conflict and cancellation.
- Next.js production build/type checking passed.
- Live local browser flow: admin assignment and case refresh passed.
- Admin overview/case checked at 1440px and 390px: no document overflow and no automated WCAG 2 A/AA violations in those checked states after contrast correction.

Validation used an isolated SQLite test database and captured mail. Production PostgreSQL concurrency, your SMTP provider, deployment proxy and every existing page still require your staging smoke test. No changes were deployed to your server.
