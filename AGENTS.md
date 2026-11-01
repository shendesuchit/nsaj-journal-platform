# NSAJ — Repository Instructions

## 1. Project purpose

Build the Noble Scientific Advances Journal (NSAJ) platform according to the approved master requirements, prototype specification, and architecture guidance.

Treat requirements documents as the baseline. Do not assume that a requirement is already implemented.

## 2. Approved technical direction

- Backend: Python and FastAPI.
- Database: PostgreSQL.
- ORM: SQLAlchemy 2.x.
- Schema migrations: Alembic.
- Validation and settings: Pydantic and Pydantic Settings.
- Testing: pytest and HTTPX; use PostgreSQL integration tests when required.
- Linting and formatting: Ruff.
- Initial architecture: modular monolith, not microservices.
- Frontend: Next.js and TypeScript, subject to the approved frontend plan.

Develop natively on Windows using VS Code and PowerShell. Do not require WSL2, Ubuntu, or Docker Desktop for the development workflow.

## 3. Protected resources

- Work only in the current NSAJ FastAPI repository unless explicitly authorised otherwise.
- The new repository is expected at `F:\Projects\NSAJ-FastAPI`.
- Never modify, delete, migrate, reset, or repurpose the existing `nsaj` project or its Docker volumes.
- Never run destructive Git, database, filesystem, or container commands without explaining their scope and obtaining approval where appropriate.
- Inspect existing files before modifying them. Preserve unrelated user changes.

## 4. Engineering workflow

- Work in small, reviewable increments.
- Before substantial changes, explain the intended changes and relevant files.
- Inspect the current repository, Git status, and existing tests before editing.
- Prefer explicit types, clear module boundaries, and maintainable code.
- Keep configuration separate from application logic.
- Store local secrets in environment variables or an untracked local environment file. Never commit secrets.
- Do not silently overwrite existing files or configuration.
- Do not claim a command, test, migration, or feature succeeded without verifying its result.
- Explain PowerShell commands and identify the directory from which they should run.

## 5. Security and editorial integrity

- Enforce authentication and authorisation on the server.
- Use deny-by-default, resource-scoped permissions.
- Protect private manuscripts, reviewer identities, confidential reviews, and editorial records.
- Keep manuscript and review files private unless publication is explicitly authorised.
- Validate editorial workflow transitions and record important actions in an audit trail.
- Keep reviewer recommendations distinct from editorial decisions.
- Apply secure session management, CSRF protection where applicable, expiry, and revocation.
- Do not expose passwords, tokens, private manuscript contents, or unnecessary personal data in logs.
- Display ISSN, DOI, indexing, accreditation, publisher, policy, and editorial claims only when verified and approved.

## 6. Testing and quality

- Add or update tests for every meaningful behaviour change.
- Test successful requests, validation failures, unauthenticated access, and unauthorised access.
- Test cross-user and cross-role access to sensitive records.
- Test database constraints, transactions, and migrations against PostgreSQL.
- Run relevant tests and Ruff checks before declaring work complete.
- Report failures honestly; do not weaken tests merely to obtain a passing result.

## 7. Requirements and decisions

Distinguish between:
- Confirmed requirements
- Approved architecture decisions
- Proposed defaults
- Open business or product decisions
- Implemented and verified behaviour

Do not invent journal policies, fees, people, credentials, registrations, identifiers, or external approvals.

If a requirement is ambiguous or conflicting, explain the options and ask for a decision before making an irreversible or consequential choice.

## 8. Definition of done

A change is complete only when:
1. Its intended behaviour is implemented.
2. Relevant tests pass, or remaining failures are documented.
3. Security and permission implications are addressed.
4. Configuration and documentation are updated where needed.
5. The resulting changes are summarised for review.
