# Noble Scientific Advances Journal Platform

Full-stack scholarly publishing and editorial management platform for **Noble Scientific Advances Journal (NSAJ)**.

The platform is designed to support the complete scholarly publishing lifecycle—from public journal information and manuscript submission through editorial screening, peer review, revision, publication, article discovery, and journal administration.

> **Status:** Active development  
> **Architecture:** Modular monolith  
> **Backend:** FastAPI + PostgreSQL  
> **Frontend:** Next.js + TypeScript  
> **Local environment:** Docker Compose + WSL2

---

## Overview

The NSAJ Journal Platform is a full-stack academic publishing system intended to provide both:

1. a professional public-facing scholarly journal website, and
2. a secure editorial management environment for authors, reviewers, editors, and administrators.

The system is designed around explicit workflow states, role-based access control, secure handling of unpublished research, auditable editorial actions, and reliable publication records.

The platform is not intended to treat a manuscript submission as an automatically published article. Submission, review, editorial decisions, production, issue assignment, and publication are separate controlled stages.

---

## Core Objectives

The platform aims to:

- provide a maintainable scholarly publishing system for NSAJ;
- support manuscript submission and versioning;
- support editorial screening and assignment;
- manage reviewer invitations and peer-review workflows;
- record editorial decisions and revision cycles;
- organize articles into volumes and issues;
- publish verified article metadata and files;
- maintain Editorial Board information;
- manage Calls for Papers;
- manage author templates, journal policies, announcements, and public resources;
- protect confidential manuscripts, reviewer identities, and editorial records;
- maintain auditable workflow history;
- support DOI, ISSN, and other identifier records without making unverified public claims;
- provide a responsive and accessible public website;
- support backup, restore, migration, and operational continuity.

---

## Technology Stack

### Backend

- Python
- FastAPI
- PostgreSQL
- SQLAlchemy 2.x
- Alembic
- Pydantic
- pytest
- HTTPX

The backend is responsible for:

- authentication;
- authorization;
- workflow validation;
- manuscript management;
- reviewer assignments;
- editorial decisions;
- publication operations;
- file access control;
- audit logging;
- journal administration;
- notifications;
- metadata management;
- integrations.

### Frontend

- Next.js
- TypeScript
- React
- server-side or static rendering where appropriate

The frontend includes:

- public journal pages;
- article and issue pages;
- author workspace;
- reviewer workspace;
- editor and administrator interfaces;
- public search and archives;
- Editorial Board pages;
- Calls for Papers;
- Templates & Downloads;
- journal policies and resources.

Public-facing pages should be rendered in a way that supports discoverability and structured scholarly metadata.

### Database

PostgreSQL is the primary production database.

Database design should use:

- foreign keys;
- unique constraints;
- check constraints;
- transactions;
- explicit relationships;
- versioned records where appropriate;
- audit-safe historical records.

Important publication and editorial history must not be silently overwritten.

### Infrastructure

- Docker
- Docker Compose
- WSL2 / Ubuntu for local Linux development
- Git / GitHub
- VS Code
- Linux production hosting

---

## Architecture

The project follows a **modular monolith** architecture.

Domain boundaries should remain explicit, but the project should not introduce unnecessary microservices before scale, operational load, or isolation requirements justify them.

The application should favor:

- explicit business rules;
- testable workflows;
- clear service boundaries;
- centralized authorization;
- auditable state transitions;
- maintainable modules;
- minimal hidden automation.

### Repository Structure

```text
nsaj-journal-platform/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── repositories/
│   │   ├── services/
│   │   ├── workflows/
│   │   ├── tasks/
│   │   └── integrations/
│   ├── alembic/
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   ├── security/
│   │   └── fixtures/
│   ├── alembic.ini
│   └── pyproject.toml
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── features/
│   │   ├── lib/
│   │   └── types/
│   └── public/
│
├── infrastructure/
│   ├── docker/
│   └── deployment/
│
├── docs/
│   ├── requirements/
│   ├── architecture/
│   ├── decisions/
│   ├── security/
│   └── operations/
│
├── scripts/
├── .env.example
├── .gitignore
├── compose.yaml
└── README.md
```

The repository structure should remain practical. Empty abstractions should not be created solely to match this diagram.

---

# Functional Scope

## Public Journal Website

The public website is expected to include:

- Home
- About the Journal
- Aims & Scope
- Editorial Board
- Call for Papers
- Author Guidelines
- Submit Manuscript
- Publication Ethics
- Peer Review Policy
- Current Issue
- Archives
- Publication Charges
- Templates & Downloads
- Presentations / Resources
- Announcements
- Contact Us

A public Reviewer Board may be introduced only if approved by journal policy.

---

## Homepage

The homepage should provide a clear scholarly journal identity without becoming overcrowded.

Expected content includes:

- journal introduction;
- journal scope;
- Submit Manuscript call-to-action;
- Current Issue;
- latest published articles;
- active Calls for Papers;
- approved announcements;
- Editorial Board link;
- Templates & Downloads;
- selected journal resources.

Only approved and genuinely public content should appear.

---

## Article Pages

Each published article should have a stable public landing page.

Typical metadata includes:

- title;
- authors;
- affiliations;
- abstract;
- keywords;
- article type;
- subject;
- volume;
- issue;
- publication date;
- article or page number;
- license information;
- DOI, if registered and verified;
- citation details;
- publication history;
- published article files;
- supplementary resources where applicable.

Draft, accepted-only, scheduled, or otherwise unpublished articles must not be publicly exposed.

---

## Current Issue and Archives

The platform should support:

- current published issue;
- historical archives;
- volume-based navigation;
- issue-based navigation;
- article listings;
- publication dates;
- metadata-driven archive generation.

Published archives must be generated from production records rather than hardcoded page content.

Draft and scheduled issues must remain private until publication.

---

# User Roles

The initial role model includes:

- Site Administrator
- Editor-in-Chief
- Managing Editor
- Associate Editor
- Reviewer
- Author
- Public / Anonymous Visitor

Roles do not automatically imply unrestricted access.

Permissions should be scoped to:

- resource;
- action;
- editorial responsibility;
- manuscript assignment;
- administrative authority.

An Editorial Board appointment must remain separate from application-level system permissions.

---

# Authentication and Authorization

Authorization must be enforced on the server.

Hiding a frontend button is not considered access control.

The system should follow a deny-by-default authorization model.

### Examples

Public visitors may access:

- approved journal pages;
- published articles;
- published issues;
- approved resources.

Authors may access:

- their own profile;
- their own submissions;
- permitted correspondence;
- permitted decision information;
- their own manuscript files.

Reviewers may access:

- assignments specifically assigned to them;
- permitted manuscript information;
- their own review forms;
- their own review history where allowed.

Editors may access:

- manuscripts within their editorial scope;
- reviewer assignment tools;
- decision workflows;
- relevant editorial records.

Site Administrators may manage:

- accounts;
- system configuration;
- integrations;
- platform administration.

Administrative privileges must not automatically replace or bypass editorial decision authority.

---

# Manuscript Workflow

The platform should distinguish clearly between manuscript states.

Possible states include:

```text
Submitted
↓
Technical Check
↓
Editorial Screening
↓
Reviewer Invitation
↓
Under Review
↓
Revision Requested
↓
Resubmitted
↓
Accepted
↓
Production
↓
Scheduled
↓
Published
```

Other valid outcomes may include:

- Declined
- Withdrawn

State transitions must validate:

- current workflow state;
- user permission;
- required metadata;
- required files;
- editorial prerequisites;
- publication requirements.

Invalid transitions should be rejected consistently.

---

# Manuscript Submission

Registered authors should be able to:

- create a submission;
- provide article metadata;
- identify co-authors;
- provide affiliations;
- submit abstracts;
- provide keywords;
- select manuscript type;
- complete required declarations;
- upload supported files;
- receive a submission reference;
- receive submission confirmation.

Submission must not be interpreted as acceptance.

---

# Manuscript Versioning

The system should distinguish between:

- initial submission;
- revised submission;
- accepted manuscript;
- production files;
- final published files.

Historical manuscript versions should be preserved where appropriate.

A revision should not silently overwrite previously submitted material when audit history is required.

---

# Peer Review

The peer-review system should support:

- reviewer directory;
- reviewer expertise;
- reviewer subject areas;
- invitation workflow;
- invitation acceptance;
- invitation decline;
- invitation expiry;
- reviewer deadlines;
- reminders;
- manuscript assignments;
- conflict-of-interest declaration;
- confidentiality acknowledgement;
- reviewer comments;
- comments to editors;
- author-facing comments where policy allows;
- recommendations;
- optional review attachments;
- completed review history;
- multiple review rounds.

Reviewer recommendations must remain distinct from editorial decisions.

---

## Reviewer Privacy

Reviewer records are private by default.

A reviewer must not be able to:

- browse unrelated manuscripts;
- access another reviewer's confidential report;
- access manuscripts not assigned to them.

A public Reviewer Board is a separate feature and must remain disabled unless explicitly approved.

---

# Editorial Decisions

Editorial decisions should be recorded independently from reviewer recommendations.

Decision records should identify:

- manuscript;
- authorized decision-maker;
- decision type;
- timestamp;
- decision letter or rationale;
- related workflow event;
- revision round where applicable.

Important decisions should be auditable.

Automated processes must not make substantive editorial decisions.

---

# Editorial Board Management

The platform should support Editorial Board records for roles such as:

- Editor-in-Chief;
- Associate Editor;
- Managing Editor;
- Editorial Board Member.

Possible profile fields include:

- name;
- photograph;
- role;
- qualifications;
- department;
- institution;
- country;
- specialization;
- keywords;
- biography;
- professional profile;
- ORCID where supplied;
- approved professional email;
- appointment dates;
- display order;
- active status.

---

## Verification and Consent

A profile should not become public merely because it has been entered into the system.

Publication may require:

- identity verification;
- qualification verification;
- affiliation verification;
- appointment confirmation;
- public-display consent;
- required profile fields;
- editorial approval.

Only approved and eligible profiles should appear publicly.

---

# Reviewer Directory

Private reviewer records may include:

- name;
- verified email;
- affiliation;
- expertise;
- subject areas;
- languages;
- ORCID;
- professional profile;
- invitation status;
- availability;
- conflicts;
- workload;
- active/deactivated state.

Reviewer management interfaces must remain protected.

---

# Volumes and Issues

The platform should support configurable volume and issue management.

## Volume Management

Authorized staff should be able to:

- create volumes;
- edit volumes;
- close volumes;
- archive volumes;
- browse related issues.

Possible fields include:

- number;
- year;
- title;
- status.

---

## Issue Management

Authorized staff should be able to:

- create issues;
- assign issues to volumes;
- edit issue metadata;
- upload covers where applicable;
- assign eligible articles;
- preview issues;
- schedule publication where supported;
- publish issues.

Possible issue states include:

- Draft
- Scheduled
- Published

Draft issues must not be publicly visible.

---

## Publication Readiness

Before publishing an issue, the system should validate required information.

Possible blockers include:

- missing article files;
- incomplete metadata;
- unresolved approvals;
- missing licensing details;
- incomplete copyright information;
- invalid article state;
- missing publication information.

Overrides should require explicit authorization and a recorded reason.

---

# Calls for Papers

Calls for Papers should be managed as structured records.

Possible fields include:

- title;
- description;
- scope;
- subject areas;
- manuscript types;
- opening date;
- closing date;
- time zone;
- related issue;
- contact;
- public status;
- display order;
- approval state.

Possible lifecycle states include:

```text
Draft
Scheduled
Open
Closed
Archived
```

Expired calls should be automatically closed where configured or clearly flagged for review.

Only approved Calls for Papers should appear publicly.

---

# Templates & Downloads

The platform should provide a public Templates & Downloads library.

Possible categories include:

- manuscript templates;
- author declaration forms;
- publication agreements;
- copyright forms;
- other approved journal resources.

Template records may contain:

- title;
- category;
- description;
- language;
- file type;
- version;
- effective date;
- updated date;
- status;
- display order;
- approval information;
- file reference;
- file history.

---

## Template Versioning

Staff should be able to:

- upload a template;
- replace a template;
- create new versions;
- approve versions;
- publish versions;
- deactivate older versions;
- reorder templates.

Only currently approved public files should be directly downloadable.

---

# Journal Content Management

Authorized users should be able to maintain:

- journal pages;
- policies;
- author guidance;
- reviewer guidance;
- announcements;
- homepage notices;
- publication charges;
- contact information;
- resources.

Unconfirmed values should remain internal rather than being presented publicly as fact.

---

# Scholarly Metadata

The platform should support structured article metadata including:

- title;
- authors;
- affiliations;
- abstract;
- keywords;
- publication date;
- issue information;
- references where supported;
- funding information;
- acknowledgements;
- license;
- identifiers.

Metadata quality should be validated before publication.

---

# DOI, ISSN, and Other Identifiers

Identifiers must have explicit statuses.

For example, DOI records may distinguish between:

```text
Planned
Assigned
Registered
Pending
Failed
```

ISSN records may include:

- print or online type;
- identifier;
- official title or authority information;
- verification evidence;
- status;
- verification date;
- change history.

The platform must never present an identifier as registered or verified unless that claim has actually been confirmed.

---

# Search and Discoverability

Public search should support relevant published metadata such as:

- article title;
- author;
- abstract;
- keyword;
- issue;
- volume.

Public search must never expose:

- private manuscripts;
- reviewer records;
- confidential reviews;
- draft articles;
- scheduled unpublished content.

---

# SEO

Public article and issue pages should support:

- stable URLs;
- descriptive page titles;
- meta descriptions;
- canonical URLs;
- sitemap generation;
- appropriate robots configuration;
- structured scholarly metadata;
- crawlable article content.

The software may support discoverability, but deployment alone does not guarantee indexing by Google Scholar, DOAJ, or any other external service.

---

# File Storage

Submitted manuscripts and confidential editorial files are private by default.

Private files should be stored outside unrestricted public web access where practical.

File access must go through authorization checks.

Uploads should validate:

- file size;
- supported extension;
- supported MIME/content type;
- safe filenames;
- content signatures where practical.

Malware scanning should be considered before uploaded files become available to journal staff.

Uploaded files must never be served as executable application content.

---

# Security

Security is a core product requirement.

The platform should include controls for:

- secure password hashing;
- account recovery;
- protected sessions;
- secure cookies;
- CSRF protection;
- resource-level authorization;
- rate limiting;
- privileged-account protection;
- session expiration;
- session revocation;
- secure file delivery;
- dependency updates;
- TLS in production;
- least-privilege database access;
- audit logging.

MFA should be enabled for privileged accounts where supported and practical.

---

## Security Principles

The platform must not assume that:

- successful login means access to every resource;
- successful upload means a file is safe;
- manuscript submission means manuscript acceptance;
- acceptance means article publication;
- frontend visibility controls equal authorization.

Authorization must be enforced at the backend.

---

# Audit Trail

Security-sensitive and editorially important actions should produce audit events.

Audit records may include:

- actor;
- action;
- resource;
- timestamp;
- result;
- reason;
- workflow transition.

Logs should not contain:

- passwords;
- authentication tokens;
- private manuscript content;
- confidential reviewer comments;
- unnecessary personal information.

---

# Notifications

The platform may support notifications for:

- account registration;
- reviewer invitations;
- review reminders;
- review deadlines;
- editorial decisions;
- revision requests;
- password recovery;
- publication events;
- administrative alerts.

Notification records should track:

- notification type;
- recipient;
- related resource;
- send status;
- timestamps;
- retry attempts;
- sanitized errors.

A failed email must not reverse a successful editorial action.

---

# Background Jobs

Background processing may be introduced for tasks such as:

- sending email;
- retrying notifications;
- deadline checks;
- closing expired Calls for Papers;
- reminders;
- scheduled publication;
- metadata synchronization.

Background jobs should be:

- durable;
- observable;
- safe to retry;
- idempotent where required.

Automated jobs must not make substantive editorial decisions.

---

# Accessibility

Key public and administrative journeys should target **WCAG 2.2 AA**.

Important requirements include:

- keyboard accessibility;
- visible focus states;
- semantic HTML;
- sufficient contrast;
- labelled forms;
- accessible error messages;
- responsive layouts;
- status text that does not depend only on color.

---

# Responsive Design

The application should support:

- desktop;
- tablet;
- mobile;
- narrow-screen layouts.

The visual direction should remain professional and academic.

The established design direction includes:

- navy and white;
- blue accents;
- clean spacing;
- readable typography;
- academic presentation;
- Georgia for journal branding and major headings where appropriate.

---

# Testing Strategy

A feature is not considered complete simply because the page renders.

Completion should include:

- expected behavior;
- permission checks;
- workflow rules;
- error cases;
- persistence;
- data integrity;
- tests;
- documentation;
- operational considerations.

---

## Unit Tests

Unit tests should cover:

- domain rules;
- validation;
- workflow transitions;
- permission helpers;
- metadata rules.

---

## Integration Tests

Integration tests should cover:

- PostgreSQL persistence;
- transactions;
- constraints;
- migrations;
- workflow state changes;
- data integrity.

---

## API Tests

API tests should include:

- successful requests;
- validation failures;
- unauthenticated requests;
- unauthorized requests;
- resource ownership;
- invalid transitions.

---

## Security Regression Tests

Important regression scenarios include:

- unauthenticated users cannot access private manuscripts;
- Author A cannot access Author B's submissions;
- Reviewer A cannot access manuscripts not assigned to them;
- revoked users lose access;
- role removal takes effect;
- draft articles remain private;
- accepted-but-unpublished articles remain private;
- invalid workflow transitions fail safely;
- unverified Editorial Board members do not appear as verified;
- unverified identifiers do not appear registered;
- notification retries do not create duplicate editorial actions;
- private information does not appear in logs.

---

## Browser / End-to-End Tests

Playwright may be used for critical journeys such as:

- registration;
- authentication;
- manuscript submission;
- reviewer assignment;
- review completion;
- editorial decision;
- article publication;
- public article access;
- authorization boundaries.

---

# Local Development

## Prerequisites

Recommended environment:

- Windows 11
- WSL2
- Ubuntu
- Docker Desktop
- Docker Compose
- Git
- VS Code
- VS Code Remote / WSL integration

The project should be stored inside the WSL2 Linux filesystem rather than `/mnt/c` where practical.

Example location:

```bash
~/projects/nsaj-journal-platform
```

---

## Clone the Repository

```bash
cd ~/projects
git clone <repository-url> nsaj-journal-platform
cd nsaj-journal-platform
```

---

## Environment Configuration

Create your local environment configuration from the example:

```bash
cp .env.example .env
```

Never commit `.env` or real credentials.

The `.env.example` file should document required variables without containing production secrets.

Possible categories include:

```text
DATABASE_URL
SECRET_KEY
SESSION_SETTINGS
EMAIL_PROVIDER
EMAIL_FROM_ADDRESS
PUBLIC_APP_URL
PRIVATE_FILE_STORAGE_PATH
PUBLIC_FILE_STORAGE_PATH
LOG_LEVEL
```

Exact variable names should follow the actual implementation.

---

# Docker Development

Build and start the development environment:

```bash
docker compose up --build
```

Run in detached mode:

```bash
docker compose up -d
```

Check services:

```bash
docker compose ps
```

View logs:

```bash
docker compose logs -f
```

Stop services:

```bash
docker compose down
```

Avoid destructive volume-pruning commands unless you explicitly understand which data will be removed.

---

# Backend Development

Example:

```bash
cd backend
```

Install dependencies using the dependency-management approach defined by the project.

Run the FastAPI development server:

```bash
uvicorn app.main:app --reload
```

Example API location:

```text
http://localhost:8000
```

Example API documentation:

```text
http://localhost:8000/docs
```

Actual ports may differ depending on Docker and project configuration.

---

# Database Migrations

Create a migration:

```bash
alembic revision --autogenerate -m "description"
```

Apply migrations:

```bash
alembic upgrade head
```

Inspect migration status:

```bash
alembic current
```

Database schema changes should be made through migrations rather than manual production modifications.

---

# Backend Tests

Run the complete backend test suite:

```bash
pytest
```

Run a specific group:

```bash
pytest tests/unit
```

```bash
pytest tests/integration
```

```bash
pytest tests/security
```

---

# Frontend Development

Example:

```bash
cd frontend
npm install
npm run dev
```

Example frontend location:

```text
http://localhost:3000
```

Actual scripts should follow `package.json`.

---

# Frontend Tests

Depending on project configuration:

```bash
npm run test
```

Run browser tests:

```bash
npx playwright test
```

Run linting:

```bash
npm run lint
```

---

# API Design Principles

Protected endpoints should:

1. authenticate the requester;
2. identify the actor;
3. load the requested resource;
4. validate resource-level permission;
5. validate workflow state;
6. validate business prerequisites;
7. execute the operation in a safe transaction;
8. create required audit events;
9. return an appropriate response.

The frontend must not be relied upon to enforce protected workflow rules.

---

# Error Handling

Errors should be:

- safe;
- structured;
- useful;
- non-sensitive.

The API must avoid leaking:

- stack traces in production;
- database credentials;
- access tokens;
- internal storage paths;
- manuscript content;
- reviewer identity;
- confidential review information.

---

# Logging

Logs should support debugging and operations without exposing confidential information.

Recommended logging fields include:

- request ID;
- user ID where appropriate;
- action;
- resource type;
- outcome;
- duration;
- error category.

Do not log sensitive request payloads indiscriminately.

---

# Health Monitoring

The platform should expose health information sufficient for operational monitoring.

Health checks may include:

- application availability;
- database connectivity;
- background worker status;
- notification subsystem status;
- storage availability.

Health endpoints must not reveal sensitive configuration.

---

# Backup and Recovery

Production operations should include backups of:

- PostgreSQL data;
- uploaded files;
- published assets;
- custom application code;
- configuration documentation;
- plugin/integration information where relevant;
- deployment documentation.

Database-only backups are insufficient.

---

## Off-Site Backups

Backups should include at least one copy outside the primary application host.

Initial planning may use:

- daily backup;
- encrypted off-server storage;
- approximately 30-day rolling retention.

Actual retention must be confirmed against operational and privacy requirements.

---

## Restore Testing

Restore procedures should be tested periodically.

Tests should verify:

- database restoration;
- file restoration;
- application startup;
- account integrity;
- article records;
- publication files;
- configuration;
- required integrations.

Restore tests should be documented.

---

# Portability

The journal should retain operational control over:

- source code;
- domain registration;
- hosting;
- database credentials;
- storage;
- backups;
- email configuration;
- DOI/identifier service credentials where applicable.

The system should maintain documented procedures for:

- data export;
- file export;
- migration;
- server restoration;
- platform transition if necessary.

---

# Privacy

The platform will handle sensitive information including:

- unpublished manuscripts;
- reviewer identities;
- private editorial correspondence;
- personal information;
- conflicts of interest;
- editorial decisions.

Before production launch, the project should define:

- privacy notice;
- retention schedule;
- deletion policy;
- anonymization rules;
- access rules;
- incident-response procedures;
- account closure behavior.

---

# Research Integrity

The journal platform should support operational handling of:

- authorship;
- conflicts of interest;
- originality;
- plagiarism checks;
- ethical approval information where relevant;
- complaints;
- appeals;
- corrections;
- expressions of concern;
- withdrawals;
- retractions.

Automated systems may assist checks, but editorial decisions remain under authorized human control.

---

# Publication Integrity

Published scholarly records should not be silently deleted or overwritten.

Corrections, retractions, and major publication changes should use governed procedures that preserve publication history where appropriate.

---

# Development Roadmap

The development plan is organized into vertical, testable increments.

## Phase 1 — Requirements and Architecture

- confirm product requirements;
- define user journeys;
- define workflow states;
- define permissions;
- define acceptance criteria;
- identify project risks.

## Phase 2 — Development Environment

- configure WSL2;
- configure Docker Desktop;
- configure VS Code;
- validate Git workflow;
- validate project paths.

## Phase 3 — Application Foundation

- create FastAPI application;
- configure PostgreSQL;
- configure application settings;
- add health endpoint;
- configure Alembic;
- establish repository structure.

## Phase 4 — Engineering Workflow

- linting;
- formatting;
- tests;
- logging;
- error handling;
- CI;
- developer documentation.

## Phase 5 — Authentication and Authorization

- accounts;
- authentication;
- sessions;
- account recovery;
- roles;
- permissions;
- revocation;
- authorization tests.

## Phase 6 — Public Journal Shell

- public navigation;
- approved journal pages;
- branding;
- journal configuration;
- identifier display controls.

## Phase 7 — Editorial Board

- member profiles;
- verification;
- consent;
- public visibility;
- audit history.

## Phase 8 — Manuscript Submission

- manuscript forms;
- authors;
- declarations;
- file upload;
- ownership;
- manuscript versions.

## Phase 9 — Peer Review

- reviewer profiles;
- invitations;
- assignments;
- deadlines;
- review forms;
- confidentiality controls.

## Phase 10 — Editorial Decisions

- explicit workflow transitions;
- decision records;
- revision requests;
- resubmissions;
- decision history.

## Phase 11 — Calls for Papers

- create Calls for Papers;
- approve Calls for Papers;
- open/close dates;
- deadlines;
- public status;
- archive.

## Phase 12 — Publication

- volumes;
- issues;
- article assignment;
- readiness validation;
- final publication;
- public article pages.

## Phase 13 — Metadata and Resources

- Templates & Downloads;
- policies;
- scholarly metadata;
- metadata exports;
- notifications;
- approved integrations.

## Phase 14 — Hardening

- security testing;
- accessibility review;
- SEO;
- performance;
- privacy controls;
- regression testing.

## Phase 15 — Operations and Release

- production deployment;
- backups;
- restore testing;
- monitoring;
- incident procedures;
- staff documentation;
- handover.

---

# Open Decisions

Several project decisions must be confirmed before production launch.

These include:

- publication frequency;
- volume and issue policy;
- editorial calendar;
- peer-review model;
- reviewer anonymity model;
- author eligibility;
- submission types;
- maximum upload sizes;
- required declarations;
- editorial authority rules;
- conflict-of-interest policy;
- licensing;
- copyright;
- publication charges / APCs;
- ISSN status;
- DOI provider;
- publisher identity;
- official contact details;
- Editorial Board public-display rules;
- privacy and retention policy;
- hosting;
- domain;
- email provider;
- backup strategy;
- recovery objectives;
- external indexing targets;
- supported integrations;
- accessibility ownership;
- operational support responsibilities.

Until these are confirmed, implementation should remain configurable and public pages should avoid unsupported claims.

---

# Definition of Done

A feature is considered complete only when appropriate areas are covered.

Depending on the feature, this includes:

- data model;
- migrations;
- validation;
- API behavior;
- authorization;
- UI;
- workflow behavior;
- error handling;
- audit logging;
- unit tests;
- integration tests;
- authorization tests;
- browser tests;
- documentation;
- operational considerations.

A page rendering successfully is not sufficient evidence that a feature is production-ready.

---

# Security Reporting

Security issues should not be disclosed publicly before a responsible reporting process is established.

Before public release, the project should provide a documented vulnerability reporting channel.

---

# Contributing

Development contributions should follow the project's architecture, security, workflow, and testing standards.

Before submitting changes:

1. create a focused branch;
2. keep changes scoped;
3. add or update tests;
4. run the relevant test suite;
5. run linting and formatting;
6. confirm migrations where applicable;
7. document important architectural changes;
8. ensure secrets are not committed;
9. verify authorization boundaries;
10. submit a pull request for review.

---

## Branch Naming

Suggested conventions:

```text
feature/manuscript-submission
feature/reviewer-assignment
fix/article-publication-state
security/private-file-access
docs/deployment-guide
refactor/workflow-service
```

---

## Commit Messages

Prefer clear, focused commit messages.

Examples:

```text
feat: add manuscript submission endpoint
feat: add reviewer invitation workflow
fix: prevent draft articles from public access
security: enforce manuscript ownership checks
docs: document local Docker setup
test: add reviewer authorization regression tests
```

---

# Pull Request Checklist

Before opening a pull request, verify:

- [ ] code follows project architecture;
- [ ] tests have been added or updated;
- [ ] test suite passes;
- [ ] authorization has been considered;
- [ ] sensitive data is not logged;
- [ ] migrations are included when needed;
- [ ] API changes are documented;
- [ ] UI changes are accessible;
- [ ] public claims are verified;
- [ ] private records remain private;
- [ ] workflow transitions are validated;
- [ ] documentation is updated.

---

# Environment Safety

The NSAJ Journal Platform should remain isolated from unrelated repositories, databases, Docker volumes, and application environments.

Do not run destructive global cleanup commands as a troubleshooting shortcut.

Examples requiring particular caution include:

```bash
docker system prune
docker volume prune
docker compose down -v
```

These commands can remove data outside the immediate development task depending on the environment.

Always verify scope before executing destructive operations.

---

# Documentation

Project documentation should be maintained under:

```text
docs/
├── requirements/
├── architecture/
├── decisions/
├── security/
└── operations/
```

Important architecture decisions should be recorded as ADRs or equivalent decision records.

---

# Architecture Decisions

Current architectural direction includes:

- **ADR-001:** Python + FastAPI + PostgreSQL backend.
- **ADR-002:** Modular monolith before microservices.
- **ADR-003:** Next.js + TypeScript public frontend.
- **ADR-004:** Server-side, deny-by-default authorization.
- **ADR-005:** Secure server-managed sessions.
- **ADR-006:** Manuscripts and reviews are private by default.
- **ADR-007:** Editorial decisions remain human-controlled and auditable.
- **ADR-008:** DOI and ISSN claims are shown only when verified.
- **ADR-009:** Backup and recovery are release requirements.

Material architectural changes should document:

- reason;
- alternatives;
- security impact;
- requirements impact;
- operational impact;
- migration implications;
- approval status.

---

# Important Project Principles

1. **Private means private.**  
   Manuscripts, reviews, reviewer identities, and confidential editorial data must not become public accidentally.

2. **Frontend controls are not authorization.**  
   Access control must be enforced by the backend.

3. **Accepted is not published.**  
   Article publication requires an explicit publication process.

4. **Reviewer recommendation is not an editorial decision.**

5. **Identifiers must be verified.**  
   Do not invent DOI, ISSN, indexing, accreditation, or registration claims.

6. **Editorial decisions require an authorized human actor.**

7. **Important state transitions must be auditable.**

8. **Published scholarly records should not be silently overwritten.**

9. **Backups are incomplete until they can be restored.**

10. **A feature is not finished just because its UI exists.**

---

# Project Status

The project is under active development.

Requirements, policy decisions, integrations, workflow behavior, and operational details may evolve as implementation and testing continue.

Items that have not been formally approved should remain configurable or marked as TBD rather than being presented publicly as confirmed journal policy.

---

# License

Project licensing is currently **TBD**.

Do not assume an open-source license until the repository owner approves and adds the appropriate license file.

---

# Project

**Noble Scientific Advances Journal Platform**

Full-stack scholarly publishing and editorial management system for the Noble Scientific Advances Journal.

---

## Suggested GitHub Repository Description

> Full-stack scholarly publishing and editorial management platform for Noble Scientific Advances Journal, built with Next.js, FastAPI, and PostgreSQL.

## Suggested GitHub Topics

```text
scholarly-publishing
academic-publishing
journal-management
peer-review
editorial-workflow
fastapi
nextjs
postgresql
typescript
docker
research
publication-platform
```
