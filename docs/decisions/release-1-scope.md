# Release 1 scope and approved defaults

- **Status:** Working baseline; implementation decisions are still subject to
  requirements traceability
- **Decision date:** 22 October 2026

This record captures the project owner's approval to use the previously
proposed default release rules to unblock planning. It does not create journal
policies or claim that the rules are implemented. Where the source requirements
leave a policy open, that decision remains open.

## Confirmed architecture decision

Use the custom FastAPI/PostgreSQL/SQLAlchemy/Alembic backend and a custom
Next.js/TypeScript frontend as recorded in [ADR-010](ADR-010-custom-journal-platform.md).
Do not continue with OJS as the application platform.

## Approved working defaults

- Keep a public-facing site and private editorial operation within the custom
  modular monolith.
- Apply authorization on the server, deny by default, and scope access to the
  relevant user, role, action, and record.
- Authors access only their own submissions and permitted correspondence.
- Reviewers access only their assigned review work and permitted manuscript
  material.
- Editors act only on cases within their assignment and role; final decisions
  remain attributable to an authorized human editor.
- Public visitors see only intentionally published records and approved public
  resources. Acceptance alone does not publish an article.
- Editorial board appointment and public profile display do not grant
  application permissions. Public reviewer-board display stays off unless
  separately approved, verified, and consented.
- Staff and reviewer accounts are provisioned by invitation. Public author
  self-registration remains off until that account policy is approved.
- Keep manuscripts, reviews, reviewer identities, and editorial records
  private unless the requirements authorize a specific disclosure.

## Deferred decision

The access of Site Administrators to confidential editorial records (the
previously identified action 4) is explicitly deferred. Do not encode routine
access or a special exception for that role until the project owner decides.
Apply deny-by-default while the decision is pending.

## Requirements baseline and open policy decisions

The master requirements identify workflow labels including submitted,
technical check, editorial screening, reviewer invitation, under review,
revision requested, resubmitted, accepted, declined, production, scheduled,
published, and withdrawn. The final transition graph, review model, and
decision rules must be confirmed against the requirements before workflow
implementation.

Publication frequency, peer-review model, author eligibility, submission
requirements, licensing, charges, publisher identity, official contacts,
ISSN/DOI status, hosting, email, privacy retention, and external integrations
remain open as identified by the source documents. Do not publish unverified
claims or invent values for these items.

## Release boundary

The public preview milestone can contain approved informational pages and safe
empty states. It is not an operational editorial platform and must not accept
real submissions or imply that review, publication, email, or file workflows
are live. An operational release requires the complete, tested, secured, and
documented editorial and publication workflows plus operational readiness.

## Phase 1 boundary

Phase 1 establishes application configuration, the database/migration
integration, basic liveness/readiness checks, and the frontend shell. It does
not add accounts, roles, manuscripts, reviews, editorial decisions, file
uploads, public journal claims, or database schema changes.
