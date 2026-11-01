# NSAJ UI/UX audit and redesign proposal

**Date:** 23 October 2026  
**Status:** Approved by the project owner on 23 October 2026; implemented. See the [implementation record](ui-ux-implementation.md). The text below preserves the original audit and proposal context.  
**Scope:** All 18 frontend route patterns, shared public shell, private workspaces, account flows, and the content-management subsections.

## 1. Scope, evidence, and boundaries

This is a source-based product-design audit of the current repository. The review covers JSX structure, CSS including later overrides, component state, API interactions, decision records, and the existing Playwright specifications. Browser discovery returned no connected browsers; opening Chrome was unavailable. Consequently, no live screenshots, viewport measurements, screen-reader results, or completed-task timings are claimed. Findings about crowding and visual balance are design assessments of the implemented structure; they require rendered validation before implementation is signed off.

The 18 route patterns are `/`, `/issues`, `/articles/[slug]`, `/search`, `/calls-for-papers`, `/editorial-board`, `/templates`, `/presentations`, `/pages/[slug]`, `/sign-in`, `/recover`, `/accept-invitation`, `/author`, `/reviewer`, `/editorial`, `/editorial/checklist`, `/admin/content`, and `/admin/publication`. CMS pages share one template; published content for every possible slug has not been inspected. About, aims and scope, and author guidelines are explicitly covered below.

Preserve all existing data, endpoint contracts, authentication, permissions, scan requirements, approval gates, workflow transitions, and public/private boundaries. Keep reviewer recommendations distinct from editorial decisions. Site Admin access to confidential editorial material remains denied. Do not seed declarations, create policies, invent identifiers or credentials, or turn sample content into real journal content.

This proposal does not certify production readiness, security, or accessibility conformance. No backend migration or functional redesign is proposed. The minor interaction corrections in section 10 are explicitly identified for approval before implementation.

### What already works well

- Navy and blue already establish a restrained journal identity. Preserve the seal and journal name.
- Inter and Source Serif 4 are already bundled; introducing another font family is unnecessary.
- Native input labels, some fieldsets, focus outlines, status/error announcements, active public navigation, and a reduced-motion fallback already exist.
- Content administration already has a section rail, mobile section selector, overview, and one active editor. Refine this structure.
- Volume and issue grouping is meaningful. The select-and-Move alternative to dragging is valuable for keyboard and touch use.
- Permission explanations in the author workspace, explicit draft/submission distinction, approved checklist versions, receipts, confidentiality notices, and demo labels should remain visible.

### Severity definitions

| Severity | Meaning |
| --- | --- |
| Critical | Confirmed inability to complete an essential task or a demonstrated severe confidentiality/data-loss issue. None established by this audit. |
| High | Likely task error, incorrect context, misleading feedback, or substantial difficulty completing a main workflow. |
| Medium | Repeated friction, poor scanning, inconsistent hierarchy, or accessibility risk that needs correction. |
| Low | Cosmetic or maintenance inconsistency with limited immediate task impact. |

## 2. Prioritized findings

Repository paths below are relative to the repository root. Line numbers identify the reviewed source, not a rendered-browser reproduction.

| ID / severity | Current issue and user impact | Recommendation | Source evidence |
| --- | --- | --- | --- |
| U01 — High | Editorial production forms use uncontrolled `defaultValue` inputs without resetting on case change; the created-article continuation state is not cleared in `openCase`. A newly selected case can retain another case's entered values or continuation link. | Bind/reset form and feedback state to the selected submission, preserve explicit unsaved-change handling, and always show the current manuscript identity beside an action. Treat as a correctness correction. | `frontend/src/app/editorial/page.tsx:81`, `:219`, `:228` |
| U02 — High | Public call deadlines use browser-local `toLocaleString()` followed by a separately supplied time-zone label. The displayed instant and label can disagree. | Format in the declared valid IANA zone, with a visible zone/offset; provide an explicit fallback for invalid zones. Keep the stored deadline unchanged. | `frontend/src/app/calls-for-papers/page.tsx:9`, `:37` |
| U03 — High | Content admin, publication, and reviewer loaders redirect to sign-in on broad request failures. An outage or forbidden request can appear to be an expired session. | Distinguish authentication, forbidden access, network/service failure, loading, and empty states. Offer retry for recoverable read failures. Preserve server authorization. | `frontend/src/app/admin/content/page.tsx:144`, `:190`; `admin/publication/page.tsx:61`; `reviewer/page.tsx:20` |
| U04 — High | Board verification controls are not initialized when the selected profile changes. Users can review a person while seeing values entered for another profile. | Selected-person heading plus record-bound identity, appointment, consent, and public-display fields. Review current evidence before the existing save/publish actions. | `frontend/src/app/admin/content/page.tsx:512`, `:518`, `:523` |
| U05 — High | Publication assembly depends on raw Article/Issue IDs and feedback far below the active task. Record identity and target issue are hard to verify. | Contextual issue work area; show known article and issue titles beside identifiers. Use existing record selections where data exists; retain ID entry where no current API supplies choices. Move feedback beside its action. | `frontend/src/app/admin/publication/page.tsx:287`, `:291`, `:307` |
| U06 — High | Reviewer acceptance refreshes the list but reuses the old assignment object; invited UI can coexist with the report. Completed assignments can reopen the same editable report form. | Synchronize selected assignment after refresh; show invitation, active review, awaiting-conflict-resolution, and completed views clearly. Keep the backend as the authority for access and status. | `frontend/src/app/reviewer/page.tsx:43`, `:48`, `:76`, `:83`, `:85` |
| U07 — High | The skip link targets a wrapper before public search/navigation. At mobile widths the eight-link related-navigation block precedes the actual content. Users must traverse repeated navigation to reach the task. | Skip to a focusable main-content landmark after navigation. Place optional related links after main content or in a collapsed mobile disclosure. | `frontend/src/app/layout.tsx:27`, `:59`; `components/public-site.tsx:146`, `:162`; `globals.css:1521` |
| U08 — Medium | Submission checkboxes inherit text-input width, height, and padding through `.draft-editor input`; their labels do not use the existing inline-form checkbox override. | Separate text-field and checkbox/radio styles; use an inline control with wrapped declaration text and a full clickable label. Verify native rendering in-browser. | `frontend/src/app/globals.css:272`, `:666`; `components/submission-intake.tsx:41` |
| U09 — High | Role changes, deactivation, publication, and final editorial actions have uneven visual emphasis and consequence review. Some actions execute immediately. | Clear primary/secondary/destructive variants and concise confirmation for consequential actions. State identity and consequence, and retain the original API action and guards. | `frontend/src/app/admin/content/page.tsx:363`, `:370`, `:395`; `admin/publication/page.tsx:302`; `editorial/page.tsx:201`, `:213` |
| U10 — Medium | Several mutations lack pending labels or duplicate-click protection; global notices are disconnected from the active form. Long forms mostly rely on a final generic alert. | Per-operation pending state, local persistent feedback, field-linked validation, and focusable error summaries for long forms. Never replace an error with a success toast. | `frontend/src/app/recover/page.tsx:24`, `:34`; `accept-invitation/page.tsx:31`; `admin/publication/page.tsx:72`; `reviewer/page.tsx:31` |
| U11 — Medium | Generic two-column grids give narrative text, identifiers, dates, and short inputs equal width. Editorial details, decisions, production, and audit information compete on long pages. | Use semantic sections and full-width narrative fields. Separate queue, selected record, and secondary/history areas. Choose disclosure by task frequency. | `frontend/src/app/globals.css:613`; `editorial/page.tsx:165`; `admin/content/page.tsx:414` |
| U12 — Medium | Style rules are repeated through base, compact overrides, admin, and publication layers. Status styles are duplicated, while some new controls have no shared button styling. | One semantic token system and reusable controls; migrate route groups incrementally and retire obsolete rules after parity checks. | `frontend/src/app/globals.css:1`, `:1679`, `:1896`, `:2218`, `:2437`; `editorial/checklist/page.tsx:32`; `components/submission-intake.tsx:43` |
| U13 — Medium | Primary text colors have good source contrast, but light input borders and focus outlines need attention. `#AEBDCB` against white is about 1.92:1, `#B5C3D1` 1.80:1, and `#78A9DC` 2.47:1. These may be insufficient where they provide essential control/state identification. | Darken essential boundaries and focus indicators. Validate each actual state and adjacent surface. These computed pairs are evidence of risk, not a complete conformance verdict. | `frontend/src/app/globals.css:279`, `:640`, `:715` |
| U14 — Medium | Operational metadata, role labels, attention text, and statuses can be very small; different workspaces inherit very large serif page titles. | Use a distinct application type scale; retain serif for journal reading, with Inter for operations. Increase essential metadata to 14px or more. | `frontend/src/app/globals.css:181`, `:2084`, `:2158`, `:2193`, `:2229`; `editorial/checklist/page.tsx:26` |
| U15 — Low | About/contact navigation has different anchor/page destinations, several screens lack workspace-level orientation, and author source strings contain actual mojibake. | Consistent destination labels, role-aware workspace navigation, current-location cues, and a UTF-8 text cleanup. | `frontend/src/components/public-site.tsx:7`, `:17`; `frontend/src/app/author/page.tsx:234`, `:238`, `:257` |
| U16 — Medium | Editorial, reviewer, and submitted-manuscript detail requests are not associated with a latest-selection sequence. Rapid record changes can allow an earlier request to finish last. | Ignore outdated responses or cancel read requests; identify detail by the latest selected record and show scoped loading. Verify with deliberately reordered responses. | `frontend/src/app/editorial/page.tsx:81`; `reviewer/page.tsx:47`; `components/submission-intake.tsx:31` |

The existing main text pairs are worth retaining: ink `#1B2B3D` on white is approximately 14.39:1, navy `#112B49` 14.33:1, muted `#536578` 6.00:1, and blue `#2764A5` 6.08:1. These are calculations from solid CSS values; gradient, image, disabled, and layered states need separate review.

## 3. Design direction and page structure

Use the existing identity with simpler surfaces, stronger grouping, and a clear distinction between journal reading and operational work. Borders and whitespace should do most of the separation. Use a single subtle elevation only for temporary overlays or a focused floating surface. Avoid decorative rings, large gradients on routine inner pages, decorative icons, and dashboard metrics that have no task value.

### Public journal layout

```text
Journal brand + search + account access
Primary journal navigation, with active location
Compact breadcrumb + page title + short description
Main reading or collection content
Optional relevant links, subordinate to the content
Journal footer
```

Keep the homepage introductory treatment more prominent than an inner page. Article pages prioritize the article title and reading content; they do not need a second large decorative page banner. Retain all existing navigation destinations, with clearer labels where a destination contains more than the label implies.

### Private workspace layout

```text
Compact journal identity + available workspace links
Workspace navigation (desktop rail / mobile disclosure)
Breadcrumb + page title + relevant primary action
Queue or record list | Selected record and task
Contextual feedback, supporting history, and audit information
```

Use the authenticated role list only to present links to already available workspaces. It does not grant permissions, change role precedence, or override deny-by-default server checks. Do not add account controls without an existing supported action. Keep a visible return to the public journal.

### Layout dimensions

| Context | Proposed geometry |
| --- | --- |
| Public reading | Overall shell up to 1200px; prose approximately 65–75 characters per line; article actions adjacent on wide screens |
| Operations | Shell up to 1360px; 216–232px navigation rail where needed; content `minmax(0, 1fr)` |
| Queue/detail | Approximately 280–320px queue plus flexible detail; stack earlier than the current narrow-screen-only collapse |
| Authentication | 440–480px form surface, short context above, help below |
| Forms | Long prose spans the form; pair only related short fields; ordinary form area approximately 720–880px |
| Surfaces | One main work surface per task; 6px control corners and 8px meaningful panels; no nested rounded containers by default |

These are proposed defaults. Final widths should follow rendered content, not fixed device names.

## 4. Page-by-page redesign

Each row states the current problem, the UX reason, proposed layout, and expected improvement. All original actions and data remain available.

### Public pages

| Page / severity | Current problem → UX reasoning | Proposed layout → Expected improvement |
| --- | --- | --- |
| **Home `/` — Medium** | Large decorative hero, three highlight blocks, newest issue, calls, announcements, and six informational/resource cards create many similar focal points. → First-time visitors have several competing routes. | Compact introduction with Read latest issue and Submit manuscript entry; newest issue/article rows first; calls and announcements in a smaller adjacent section; About/scope/contact as simpler text sections and grouped links. Keep useful empty states and explicit demo labels. → A clearer route into reading or submission. |
| **Issues `/issues` — Medium** | Volume grouping is useful, but each issue contains nested headings and article lists inside repeated cards. “Current issue” links to an archive. → Harder to distinguish the latest issue from browsing history. | Page title “Issues & archive”; newest published issue emphasized in the same collection; volume headings with compact issue rows/disclosures and article lists below. Preserve chronological grouping and original links. → Faster archive scanning without changing publication rules. |
| **Article `/articles/[slug]` — Medium** | Article title, generic banner, related links, authors, abstract, metadata and citation compete for space. → Reading begins later than necessary. | Breadcrumb → full article title → authors/affiliations → verified publication metadata → abstract → file action and citation section → scholarly notices/history where present. Use a compact adjacent action area on desktop and inline actions on mobile. → Stronger reading hierarchy and clearly associated notices. |
| **Search `/search` — Medium** | Header search and page search duplicate controls; results can show 600-character abstracts without a result summary. → Excessive reading per result and weak orientation. | One dominant page search field with preserved query; result count for the loaded result set; simple title/author/excerpt rows; DOI secondary; distinct initial, searching, no-results, and unavailable states. Keep header search subordinate. → Easier result comparison. Do not imply global totals or add unsupported filters. |
| **Calls for Papers `/calls-for-papers` — High** | Deadline text can mismatch its zone; metadata appears before title, with long instructions inside repeated blocks. → Readers may misunderstand the deadline or scan past the subject. | Call title + textual state → correctly zoned deadline → short description/scope/types → clearly titled instructions section. Use a disclosure only for genuinely long supporting instructions. Demo samples remain explicitly non-actionable. → More reliable planning and faster relevance checks. |
| **Editorial board `/editorial-board` — Medium** | Profiles use repeated generic cards and can become long when credentials/affiliations expand. → Role and person identity are harder to compare. | Group by approved board role; name and appointment first, affiliation and approved public fields below, quieter links last. Prefer divided profile rows or a modest two-column directory. No invented people, portraits, credentials, or access rights. → A credible, legible directory. |
| **Templates `/templates` — Medium** | Generic download labels expose MIME-derived wording and mix descriptions, version, format and links. → Users must interpret technical strings to pick a document. | Resource rows: title, purpose, version, friendly file format and “Download [title]”. Display size only if the current API supplies it; no guessed values. → Predictable download choices. |
| **Presentations `/presentations` — Medium** | Generic cards give summary, author/date, video, external link and download similar emphasis. → Users must inspect each block for how to access it. | Title + credited presenter/date; concise summary; source-specific actions labeled Watch, Open resource, or Download. Keep external and private-file rules intact. → Faster source recognition and reduced repeated links. |
| **CMS page `/pages/[slug]` — Medium** | The shared template places related navigation before prose and presents the body as a preformatted text block. → Reading order and long-page scanning are weak. | Compact title and reading-width article, clear version/date if supplied, supporting navigation after content on mobile. Preserve literal policy wording and line breaks; do not silently parse plain text as rich HTML. An in-page contents list requires structured headings and is optional, not assumed. → Better reading without changing approved policy content. |

For individual CMS content: **About** should prioritize the approved journal description and supporting links; **Aims & scope** should make the existing scope text easy to scan without inventing disciplines; **Author guidelines** should place the existing submission instructions and related template links clearly. Other policy slugs use the same reading template and need a content-specific review when populated. No fees, licenses, peer-review claims, ISSN or indexing claims are to be inferred from a visual template.

### Account pages

| Page / severity | Current problem → UX reasoning | Proposed layout → Expected improvement |
| --- | --- | --- |
| **Sign in `/sign-in` — Medium** | Wide form, title stays “Sign in” during MFA, raw setup URI and recovery codes share the main flow. → Current step and next action are less clear. | Narrow account surface; current-step title; email/password, verification, or setup as the existing stage; helper/recovery links below; grouped setup key and recovery codes with optional copy controls. Preserve code formats, authentication and MFA rules. → Clearer continuation. |
| **Recovery `/recover` — High** | No pending protection; reset form stays actionable after success; end-user feedback refers to development mail capture. → Duplicate requests and consumed-token errors create doubt. | Request form → generic email-sent state; valid reset form → completed state with Sign in action. Explain existing password limits before entry, retain anti-enumeration wording and token behavior. Development details belong in developer documentation. → Clear completion and recovery. |
| **Accept invitation `/accept-invitation` — High** | Missing-link state contains a disabled form and local mail-capture instructions; account/MFA actions lack pending treatment. → Users cannot distinguish missing link, verification, setup, or completion. | Link state → existing account creation form → required MFA stage where applicable → completion. Distinct missing/expired/used-link feedback based on existing API responses; no fabricated identity confirmation. → More understandable onboarding. |

### Author, reviewer, and editorial pages

| Page / severity | Current problem → UX reasoning | Proposed layout → Expected improvement |
| --- | --- | --- |
| **Author `/author` — High** | Draft editor, file handling, final declarations, submitted list, receipt, decisions and revisions accumulate in one long surface. Global save/upload feedback can become distant. → Authors may lose the distinction between editing a draft and reviewing a submitted manuscript. | Manuscript list with Drafts and Submitted views; selected draft shows Details → Authors → Files → Review & submit as anchored sections with a compact completion summary. Keep explicit Save draft and separate Submit manuscript actions. Submitted detail shows status/timeline, current decision/revision task, correspondence, and expandable receipt. → Clear next action without imposing a new backend workflow or forced wizard. |
| **Reviewer `/reviewer` — High** | Invitations, conflicts, manuscript access and review forms are mixed; long confidential and author-facing comments sit in the same two-column grid. → Reviewers may misunderstand the current stage or audience. | Assignment list with status/round/deadline → current assignment header → invitation response or active review. Active review: manuscript/file context, Recommendation, Confidential comments to editor, Comments to author as vertically grouped fields. Completed state is distinct. Keep reviewer identity/privacy rules. → Clearer audience and status. |
| **Editorial `/editorial` — High** | Unassigned cases, my queue, metadata, transitions, invitations, conflicts, reports, decisions, production and journal audit compete. Raw states and technical IDs add cognitive load. → Harder to track case identity and the current task. | Queue/detail workspace; EIC can switch between existing unassigned and assigned collections. Selected case header carries reference/status; sections for Manuscript, Reviews, Decision, Production and History, using in-page navigation or accessible tabs after validation. Audit remains a separate supporting area. Keep every existing action reachable and preserve server transition validation. → Better case focus and safer context. |
| **Declarations `/editorial/checklist` — Medium** | Create form and full historical versions are stacked with native buttons, large inherited title and long UUIDs. → Active policy, draft wording, and historical evidence are difficult to distinguish. | Compact header → Current approved checklist with full exact text → Create new version action/form → selected unapproved version review and explicit approval action → collapsed immutable version history. UUID is secondary, wrap-safe and available for audit; no invented sequential version numbers. → Easier wording review and policy provenance. |

### Administration pages

| Page / severity | Current problem → UX reasoning | Proposed layout → Expected improvement |
| --- | --- | --- |
| **Content admin `/admin/content` — High** | Existing overview/rail is sound, but record lists, creation fields, editing, approval and publication share one dense work area. Section choice and unsaved inputs are transient. → Repeated scanning and possible loss of context. | Keep overview and rail; section title + primary Create action → compact record list → selected record/detail form. Preserve mobile selector. Propose URL-backed section selection and dirty-form protection as explicit interaction changes. → Predictable navigation and fewer simultaneous fields. |
| **Publication `/admin/publication` — High** | Volume board, creation, article verification, issue assembly, readiness and publish tasks are separated by broad disclosures and ID fields. → Publication target is difficult to verify. | Keep volume groups and accessible Move control; issue rows → selected issue assembly → article verification → readiness summary → explicit publication review. Keep uncommon volume configuration disclosed. Use existing loaded records; show full identifiers only as supporting details or necessary input fallback. → A clearer publication sequence with existing guards. |

### Content administration: each work area

| Area | Specific redesign and rationale |
| --- | --- |
| Overview | Show the existing persisted counts/statuses and direct next actions. Keep informational summaries concise; avoid extra decorative KPI cards. |
| Accounts | Identity/roles/status rows → Manage access detail. Show session-revocation consequences before role save, and confirm deactivation with the account identity. Retain all current role constraints and legacy-role handling. |
| Public pages | List title/slug/version/status → selected wording review → existing publish action. If a required preview field is unavailable from current responses, keep the limitation explicit; do not fabricate a preview. |
| Calls for Papers | Group Call details, Submission information, and Schedule; full-width description/scope/instructions; show an explicit time-zone conversion summary for the current datetime entry. Differentiate immediate approval from approval for scheduled display. |
| Announcements | Full-width body, separate schedule metadata and status; explain why a scheduled publish action is disabled and when it becomes available. |
| Templates | Metadata → upload/file summary → scan state → existing publication action. Explain a blocked scan or unavailable file adjacent to the action. |
| Editorial board | Selected person header → identity/appointment verification → consent → approved public fields → review → existing save/publish actions. Initialize controls from that selected record, with clear missing-evidence states. |
| Resources | Resource details → date → URL/file source information → scan state → save. Keep existing source combinations rather than inventing a new exclusive choice. |

## 5. Proposed design system

### Color palette

Keep the established navy and blue. Use semantic aliases, so a warning or error does not depend on a screen-specific hard-coded color.

| Token / purpose | Proposed value | Usage |
| --- | --- | --- |
| Primary brand | `#112B49` | Main action, navigation emphasis |
| Primary hover/active | `#0B1E34` | Hover and pressed actions |
| Secondary accent | `#2764A5` | Links, selected navigation, secondary emphasis |
| Page background | `#F5F7FA` | Application canvas |
| Surface | `#FFFFFF` | Reading and work surfaces |
| Subtle surface | `#EEF3F8` | Secondary grouping and table header |
| Decorative divider | `#D7E0E9` | Nonessential separators, not sole input boundaries |
| Essential control border | `#74869A` | Active text fields against white; approximately 3.74:1 |
| Primary text | `#1B2B3D` | Body and control text |
| Muted text | `#536578` | Secondary content; retain readable contrast |
| Focus | `#1D4ED8` | 2–3px outline with offset; test on every surface |
| Success | `#166534` on `#F0FDF4` | Explicit completed/clean state |
| Warning | `#B45309` on `#FFFBEB` | Pending verification, blocking issue with remedy |
| Error | `#B91C1C` on `#FEF2F2` | Validation or failed request |
| Information | `#1E40AF` on `#EFF6FF` | Neutral guidance |

Colors are proposed tokens, not permission or workflow rules. Status labels always appear in text. Use warning styling for a condition that needs attention; do not automatically make every draft or every scheduled item an alarm.

### Typography

| Role | Proposed size / weight / line height |
| --- | --- |
| Application page title | Inter, 28–32px, 600, 1.2 |
| Public page/article title | Source Serif 4, 32–40px, 500–600, 1.2; allow long titles to wrap |
| Home introduction title | Source Serif 4, at most 44–48px desktop, 30–34px mobile |
| Section heading | Inter 20–22px/600/1.35 in operations; serif counterpart on reading pages |
| Subheading | Inter 16–18px/600/1.4 |
| Body | Inter 16px/400/1.6; public long-form prose 17–18px/1.7 |
| Label | Inter 14px/600/1.4 |
| Helper text/table content | Inter 14px/400/1.5 |
| Button | Inter 14–15px/600/1.3 |
| Nonessential caption | Inter 12–13px/400/1.4; never the sole location of an instruction |

Use relative units in implementation. Avoid all-uppercase running labels and raw underscored state names. Preserve the exact wording of approved declarations and policies.

### Spacing and density

Use a 4px base with named steps: **4, 8, 12, 16, 24, 32, 48, 64px**. Default form-field gap 16–24px; related label/helper gaps 4–8px; section gaps 32px; desktop surface padding 24px, mobile 16px. Use a consistent 44px comfortable control height. Data rows should accommodate wrapped titles and secondary text, typically at least 48–56px; avoid a forced fixed row height. Do not compact a long form by shrinking its text.

### Reusable components

| Component family | Contract and usage |
| --- | --- |
| `PublicShell`, `WorkspaceShell`, `AccountShell` | Shared identity, landmarks, navigation and widths. Route content supplies the current location. |
| `PageHeader`, `SectionHeader`, `Breadcrumbs` | Page purpose and one task-level primary action; supporting metadata stays quieter. |
| `Button`, `ActionGroup` | Primary, secondary, text and danger variants; pending label, disabled semantics and focus treatment. Preserve native link/button distinction. |
| `FormField`, `FormSection`, `FormActions` | Label, required/optional indicator, helper, error and stable IDs; semantic fieldset/legend where appropriate. |
| `CheckboxField`, `RadioGroup`, `SelectField` | Native controls first, full clickable labels and correct input-specific styles. Use a custom combobox only if the existing record set warrants it. |
| `FileUploadField` | Existing file types/size guidance, selected-file summary, pending/scan state and recovery guidance. No unsupported drag/drop upload feature. |
| `StatusBadge`, `InlineNotice`, `FieldError`, `FormErrorSummary` | One semantic mapping, text plus tone, appropriate live regions, actionable errors. |
| `RecordList`, `DataTable`, `RecordDetail` | Compact comparison for collections; details on selection. Use tables for real columns, lists for narrative entries. |
| `Tabs`, `Disclosure` | Tabs only for sibling views with correct keyboard behavior; native details for supporting history/infrequent options. Keep drafts mounted or protected when switching. |
| `LoadingState`, `EmptyState`, `AccessState`, `ErrorState` | Distinguish loading, no records, no match, forbidden, signed out, and unavailable. Show a supported next action. |
| `ConfirmationDialog` | Current record identity, consequence, clear action/cancel, keyboard trap/escape and focus return. Only for consequential actions. |
| `MfaSetup`, `RecoveryCodes` | Consistent setup instructions, wrap-safe secrets and optional deliberate copy; never log or auto-export credentials. |

Do not add modals, tooltips, switches, custom date pickers or pagination just to complete a component catalogue. Use native date controls with visible timezone context. Tooltips must never be the only label/help. Model dates and booleans retain their existing API meaning.

## 6. Forms and content-block strategy

1. Start each task with a short purpose and the record identity. Show visible required markers and define them; indicate optional fields where helpful. Draft metadata can remain incomplete when the backend allows saving it; distinguish final-submission requirements from draft-saving requirements.
2. Arrange fields in reading order. Single-column for passwords, evidence, comments, abstracts and policy text. Pair only naturally related short fields such as date/time or name/type.
3. Group authors, manuscript details, files, editorial correspondence, verification evidence and scheduling under semantic section headings. Keep persistent actions tied to their form.
4. Display format and length rules before an error. Map structured API validation to existing fields when possible; retain generic server errors when precise mapping is unavailable. Never guess that authorization errors are validation errors.
5. On failure preserve entries, summarize the problem, and focus an error summary or the affected field appropriately. On success use a short local status message and retain the changed record context.
6. Explain unavailable actions nearby: unsaved draft, missing acknowledgements, pending scan, no approved checklist, or scheduled publication. Preserve the server's final validation even if the UI presents a readiness summary.
7. Keep manual Save actions; do not introduce autosave or move submission into Save. Avoid mandatory wizards for existing single-page tasks. An author completion overview can use anchors within the same form.

**Card rule:** a container should correspond to a distinct object or task, not every heading. Volumes, a selected manuscript, an authentication task, and a separately actionable call are meaningful groups. A title, metadata, abstract, file list and button within one manuscript do not each need another card. Use rows, definition lists, headings, and separators within the main surface.

## 7. Navigation and data-heavy screens

- Preserve route structure. Add workspace location cues and role-appropriate links; keep Admin content's working rail and mobile selector. Normalize wording such as Issues & archive and About the journal so label and destination agree.
- Show full title/reference in the selected work area; list rows can truncate only when the full value is available on selection or accessible expansion. Identifiers should wrap or be deliberately copied; they must not push the layout wider.
- Tables use a caption, scoped column headers, left-aligned text, right-aligned numeric values, readable dates, quiet separators and meaningful empty states. Do not turn long prose into a table.
- Use statuses to aid comparison, not color every row. Label row actions with the record context for assistive technology.
- Preserve existing collection data. Client-side search/sort may be added only for the already loaded records and must say so; global sorting, filters, result totals and pagination require explicit API support and are outside this visual scope if absent. Never paginate a partial dataset as if it were complete.
- On mobile, convert suitable operational records into named stacked rows; genuinely comparative wide tables can use a labeled local horizontal-scroll region. Avoid whole-page horizontal scrolling.
- Retain keyboard/select alternatives for volume moves. Do not make dragging the only way to operate an issue.

## 8. Interaction-state specification

| State | Required behavior |
| --- | --- |
| Hover/pressed | Restrained color/border change without shifting content; no hidden-only-on-hover essential action |
| Focus | Strong visible outline, logical reading order; focus is not obscured by sticky navigation or action bars |
| Selected/active | Visible text/location context plus border or marker; expose state through appropriate semantics |
| Disabled | Native disabled where appropriate plus adjacent reason; no tooltip-only explanation |
| Pending | Per-operation label such as Saving or Publishing, `aria-busy` on the relevant area, prevent duplicate mutation; preserve text entry |
| Success | Short local `role=status` confirmation tied to the changed record; persistent receipt/history remains available |
| Warning | Describe blocker/consequence and a supported remedy; no color-only meaning |
| Error | Specific recoverable guidance, retained entries, appropriate `role=alert`; distinguish forbidden and unavailable |
| Empty/no results | Distinct wording and appropriate existing action, such as Create draft or adjust search |
| Loading | Reserve sensible space; label the loading area rather than briefly displaying an empty state |

Use subtle 120–160ms transitions where helpful; respect reduced motion. Do not announce an entire editable manuscript panel on every change; scope live regions to succinct status updates.

## 9. Responsive design and accessibility

### Responsive behavior

- **Wide desktop:** stable navigation rail, queue/detail work areas, reading line-length limits; expand usable content width without stretching every form.
- **Laptop/tablet:** collapse the queue/detail layout when the detail area is cramped, approximately 960–1024px as a starting point; navigation can become a disclosure or existing selector. Avoid keeping a two-column form merely because it fits mathematically.
- **Mobile:** compact header, accessible menu, page purpose and current task first, one-column forms and actions that wrap; related public links after content. Show the selected record with an obvious return to its list.
- Test at 1440, 1280, 1024, 768, 390 and 320 CSS-pixel widths, 200% text enlargement and 400% zoom equivalents, with long titles, many authors, long URLs, full declaration text, and error messages. These are planned checks, not completed results.
- A sticky action bar is optional; use it only where it avoids long travel and does not hide fields, keyboard focus, or mobile screen space.

### Accessibility acceptance targets

- Target WCAG 2.2 AA; measure rendered foreground/background combinations. Ordinary text needs at least 4.5:1, large text 3:1, subject to the standard's exceptions. See [W3C contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).
- Essential control/state cues need suitable non-text contrast, generally 3:1 against adjacent colors; subtle decorative separators have a different role. See [W3C non-text contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html).
- Reflow ordinary content at 320 CSS pixels without two-dimensional page scrolling, with applicable exceptions for genuinely two-dimensional content. See [W3C reflow guidance](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html).
- Aim for 44px comfortable controls. The AA minimum target-size criterion is 24×24 CSS pixels with specified exceptions including spacing and inline links; 44px is the proposed product default. See [W3C target-size guidance](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html).
- One clear main landmark per view; skip links land after repeated chrome. Logical heading hierarchy and meaningful navigation labels. Preserve semantic labels and fieldsets, add `aria-describedby`/`aria-invalid` for help and validation. See [W3C form instructions](https://www.w3.org/WAI/tutorials/forms/instructions/).
- Verify keyboard-only navigation, visible focus, tab/disclosure behavior, confirmation focus containment/return, and focus after MFA stages, selected-record changes, validation, and successful completion. Provide non-drag alternatives.
- Review with a screen reader: names, roles, states, selected records, labels, errors, deadlines, scan results, and completion announcements. Keep confidential and author-visible review fields unambiguously labeled.

## 10. Minor interaction corrections proposed for approval

These go beyond styling. They are recommended because the audit found concrete context or feedback problems. They must be reviewed explicitly before implementation; none has been applied by this audit.

| Proposed correction | Preserved behavior / boundary |
| --- | --- |
| Reset/bind manuscript and board forms when the selected record changes; clear record-specific continuation links and notices; protect unsaved edits | Same API payloads, scope and final actions; no silent cross-record reuse or automatic saving |
| Associate detail responses with the latest selected record; distinguish a receipt read failure from a legitimately absent legacy receipt | Same read endpoints and scopes; stale or failed reads must not be represented as current, successful data |
| Synchronize reviewer selection after response; distinguish completed review UI | Same invitation/conflict/review endpoints and confidentiality rules; no new review-edit permission |
| Correct displayed deadline zone and clarify local datetime conversion | Same stored timestamps and scheduling endpoints |
| Separate sign-out, forbidden and unavailable states; provide read retry; show terminal recovery success | Same authentication, anti-enumeration and token rules |
| Add pending/duplicate-click protection and local feedback | Same mutations and server idempotency/validation behavior; UI protection is not a substitute for server checks |
| Add consequence review for final submit/decision, checklist approval, publishing, role changes and deactivation | Same accountable action, exact declaration wording and approvals; never pre-check declarations or bypass readiness |
| Keep section location in the URL; protect dirty forms during navigation | Existing routes and information architecture; no additional backend storage |
| Add deliberate copy controls for identifiers/MFA setup when useful | User-triggered copy only; no new persistence, export or logging of secrets |

Do not bundle workflow-policy changes, new dashboards, autosave, permissions, rich-text conversion, unsupported data filtering, or new publication rules into this redesign.

## 11. Prioritized delivery plan

### Phase 1 — High-impact foundational changes

**Priority:** establish consistency and correct misleading context before page-by-page polish.

1. Confirm the direction and interaction corrections in this proposal. Capture rendered baseline screens and state coverage when browser access is available.
2. Introduce semantic color/type/spacing/control tokens and shared Button, FormField, CheckboxField, Notice, StatusBadge and state components. Keep page behavior stable while migrating.
3. Establish public/workspace/account shells, correct skip target, responsive content order and active-location cues. Use the current content-admin rail as a foundation.
4. Address U01–U06 as isolated, reviewable correctness changes with focused tests. Keep API and policy behavior unchanged.
5. Validate a representative public page, an account flow, and author draft/submission on desktop/mobile before extending the system.

**Likely files:** `frontend/src/app/globals.css`, `layout.tsx`, `components/public-site.tsx`, new reusable components under `frontend/src/components`, and narrowly scoped affected route components. Read local Next.js documentation before implementation, per `frontend/AGENTS.md`.

**Exit criteria:** consistent tokens and controls; selected-record context protected; deadline labels truthful; distinct access/error states; no regressions in existing routes or API payloads.

### Phase 2 — Page and component redesign

1. Author workspace and submission/receipt/revision detail; then reviewer and editorial queue/detail views, including EIC declarations.
2. Publication assembly/readiness and content-administration subareas, preserving volume moves, account constraints and publication gates.
3. Public home, archive, article, search, calls, board, resources and CMS template.
4. Account sign-in/MFA, invitation and recovery stages using the shared account components.
5. Retire superseded CSS only after the relevant route group is migrated; avoid accumulating another override layer.

**Exit criteria:** every route follows its specified hierarchy; one clear task-level primary action; long forms grouped semantically; feedback beside its task; no redundant nested card structures. All original operations remain available.

### Phase 3 — UX polish, responsiveness, accessibility and consistency

1. Full route/state walkthrough with keyboard, screen reader, zoom and narrow viewports; contrast checks of each interactive state.
2. Long-data, empty/error/loading, expired-link, forbidden, pending-scan, stale-checklist, completed-review and publication-blocker cases.
3. Validate confirmation focus, scroll/focus after selection, pending states, selected-record integrity and dirty-form behavior.
4. Extend the existing Playwright specifications and run regression checks. Recheck backend permission and workflow tests where an interaction correction could affect requests.
5. Final designer review across all 18 route patterns, remove obsolete styles, and document the component/state contracts.

**Exit criteria:** the acceptance matrix below is satisfied with recorded results. Visual polish alone is not a production-readiness claim.

## 12. Verification plan and approval

The existing tests were read, not executed for this documentation-only audit. There are Playwright specifications for public content and responsive navigation, admin sections/roles, publication volume moves, MFA, author invitation/recovery/upload/isolation, and checklist submission. Preserve them and extend coverage for the proposed interactions.

| Area | Acceptance evidence required after implementation |
| --- | --- |
| Workflow parity | Same Save draft, upload/scan, declaration confirmation, submit/receipt, review, decision, revision, production and publication paths |
| Permissions | Server enforces existing scopes; unauthorized views do not expose record contents; no Site Admin confidential-record access introduced |
| Record context | Switching manuscripts, articles, issues or board profiles never reuses another record's inputs/action target |
| Forms | Labels/rules visible, errors linked, values retained, pending actions clear, keyboard paths complete |
| Collections | Long labels wrap, meaningful status text, empty/loading/error separated; sorting/filtering claims match loaded data |
| Publication | Accepted/private content stays private; readiness and explicit publish gates retained; keyboard issue moves retained |
| Accessibility | Measured contrast/reflow, keyboard and screen-reader results, focus visibility/return, touch-target review |
| Responsiveness | Recorded desktop/laptop/tablet/mobile screenshots and no unintended document-level horizontal overflow |
| Engineering | TypeScript and relevant Playwright checks; relevant backend tests for request behavior; Ruff if Python changes are needed |
| Design consistency | All 18 route patterns reviewed against one component/token system and this proposal |

### Approval requested

Approve the restrained navy/blue direction, typography and layout system, page-by-page structures, and the explicitly listed interaction corrections. Approval authorizes implementation in the three phases above while preserving APIs, data, permissions and journal policies. If desired, approval can exclude individual interaction corrections; those should remain separate from styling work.

**Audit result:** a coherent foundation exists, but operational hierarchy, selected-record context, feedback and shared controls need substantial refinement. No Critical issue is asserted, no UI redesign has been applied, and rendered-browser validation remains outstanding.
