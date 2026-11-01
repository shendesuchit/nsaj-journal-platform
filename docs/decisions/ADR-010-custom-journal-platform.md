# ADR-010: Build the NSAJ journal platform in-house

- **Status:** Approved by the project owner
- **Decision date:** 22 October 2026
- **Scope:** Platform architecture for this repository

## Context

The master requirements and architecture guidance describe OJS as the preferred
publishing engine, subject to a feasibility proof of concept. The project owner
has decided not to proceed with OJS because its configuration and implementation
complexity, and the resulting dependency on that platform, are not feasible for
this project at present.

## Decision

Build NSAJ as a custom modular monolith with a FastAPI backend, PostgreSQL,
SQLAlchemy 2.x, Alembic, Pydantic Settings, and a custom Next.js/TypeScript
frontend. Develop and run the local workflow natively on Windows with PowerShell;
WSL2 and Docker Desktop are not required.

The functional, security, privacy, editorial-integrity, public-content, and
operational requirements in the source documents remain the baseline. This
decision changes the implementation platform, not those product requirements.

## Consequences

- NSAJ owns and must implement the submission, review, editorial decision,
  revision, publication, access-control, audit, and operational workflows.
- Domain boundaries stay within one application until evidence justifies
  separating services.
- Do not create a second platform or database for the same publishing records.
- No production workflow or policy is considered implemented by this decision.
- Reassess selected integrations and infrastructure as feasibility questions;
  do not make them prerequisites without an approved need.

## Open decisions

- The approved default release rules are recorded in
  [Release 1 scope and defaults](release-1-scope.md).
- The Site Admin's access to confidential editorial records remains undecided.
  Phase 1 grants no such access because Phase 1 implements no editorial
  authorization behavior.
- Peer-review model, publication policy, licensing, charges, official publisher
  details, identifiers, hosting, email, and retention remain subject to the
  source documents' open decisions.

## Superseded guidance

This decision supersedes the OJS preference and the WSL2/Docker Desktop local
workflow in the reference architecture guidance for this project. The source
documents remain the requirements baseline for functionality and safeguards.
