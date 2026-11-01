# Phases 4â€“6 implementation plan

- **Status:** Scoped application implementation complete; ready for the planned
  hands-on UI walkthrough
- **Basis:** Master requirements v2.0, prototype specification v1.0, ADR-010,
  and the approved release defaults

The repository did not contain a separate Phase 4â€“6 plan. This mapping groups
the remaining requirements into testable vertical increments. It does not turn
unverified journal information into public claims.

## Implemented application scope

- Phase 4 includes attributed workflow transitions, Editor-in-Chief case
  assignment, scoped review files, reviewer invitation and conflict handling,
  confidentiality acknowledgement, review reports, and a restricted recent
  activity view.
- Phase 5 includes editor decisions, author-visible decision letters, revision
  rounds, article production records, issue preparation, readiness blockers,
  explicit publication, citation output, and correction/retraction history.
- Phase 6 includes public article, issue, search, page, call, announcement,
  template, board, and resource views with approval and scan gates. Content
  managers can create and publish approved content from the frontend.
- The audit view is restricted to the Editor-in-Chief and omits event details.
  Site Admin remains denied access to confidential editorial records.
- The second Alembic migration has been applied after read-only inspection of
  the existing database. It adds workflow tables and expands the submission
  status check. Its downgrade is disabled to prevent deleting workflow data.

## Phase 4 â€” Editorial assignment and peer review

- Add submission workflow history and guarded state transitions.
- Add scoped editor assignment, private reviewer profiles, reviewer invitations,
  assignments, deadlines, conflict declarations, confidentiality acknowledgement,
  and confidential review reports.
- Keep reviewer recommendations separate from editor decisions.
- Scope editors to assigned cases and reviewers to their own accepted assignments.
- Use UTC for stored deadlines. The working review display default hides reviewer
  identity from authors; do not publish this as journal policy until approved.
- Keep Site Admin access to confidential editorial records denied.

## Phase 5 â€” Decisions, revisions, and publication

- Add attributable human editorial decisions, decision letters, revision rounds,
  and author resubmission records.
- Add data-driven volumes, issues, production articles, publication readiness
  checks, and explicit issue publication.
- Keep accepted and scheduled records private. Only intentionally published
  articles in published issues are public.
- Preserve publication history; corrections, expressions of concern, withdrawals,
  and retractions are recorded actions rather than silent deletion or overwrite.
- Show DOI only after a responsible editor records that registration was verified.

## Phase 6 â€” Public journal content and operational safeguards

- Add governed calls for papers, announcements, public pages/policies, and
  versioned public templates/resources with private storage and scan checks.
- Add public article/issue/archive/search endpoints that query published records
  only, with stable article URLs and citation metadata.
- Add an audit view and export/backup readiness documentation without exposing
  confidential records to Site Admin.
- Keep board/reviewer public display off until verification, consent, and a
  publication basis are recorded; keep unverified journal claims unpublished.

## Boundaries carried forward

- Implemented: the Editor-in-Chief creates and approves immutable declaration
  versions. Authors confirm the current approved version when submitting a complete
  draft with clean files. Exact wording remains a journal decision; none is seeded.
- The Site Admin confidential-record access decision remains deferred and denied
  by default.
- Peer-review visibility is a working configurable default, not an approved
  public policy statement.
- Publication frequency, license, charges, publisher/contact details, ISSN/DOI
  registration, privacy retention, production email/storage/scanning providers,
  hosting, and recovery objectives remain unconfirmed.
- Production deployment, mail, managed private storage and malware scanning,
  backups and restore rehearsal, monitoring, security review, and release
  operations remain follow-on work. This phase delivers application code and
  its local development workflow, not a production operating system.
