# NSAJ UX Compactness Review

## Changes implemented in this package

- Home navigation now shows **ISSN: 2456-9976** immediately before the public navigation on desktop. It is intentionally labelled only as “ISSN” because the supplied template does not identify it as print or electronic ISSN.
- The three supplied author files are available as local public downloads:
  - `NSAJ_TEMPLATE.docx`
  - `Copyright_Agreement.doc`
  - `Registration_Form.doc`
- Downloads are surfaced on Home, Templates & Downloads, Author Guidelines, Publishing Process, and the Author workspace.
- Public-page headers, sidebars, cards, archive groups, editorial profiles, search results, footer spacing, and repeated section gaps have been reduced.
- The repetitive author-resource sidebar is hidden on small screens because the same destinations already exist in the mobile navigation.
- Account, author/editor/reviewer workspace, and admin panel padding has been reduced modestly without reducing form control/tap target sizes.

## Page-by-page UX observations and recommendations

### Home
Implemented: compact masthead/hero/sections, visible ISSN, real download cards, tighter footer.
Next: once real article content grows, keep only 3–4 recent article links on Home and move the rest to Current Issue/Search.

### About / Aims & Scope / Policy pages
Implemented: smaller title block and tighter sidebar/layout.
Next: split long policy text with an in-page contents list only when a page exceeds roughly 5–6 major sections. Avoid cardifying every paragraph.

### Author Guidelines
Implemented: direct preparation-file downloads beneath the approved page content.
Next: structure final approved guidance into “Before you write / Format / Files / Ethics / Submit” sections so authors can scan rather than read one long block.

### Templates & Downloads
Implemented: the supplied files are first-class downloads; backend-managed resources remain available below them.
Next: when versioning is operational, show version/effective date beside every official file and hide superseded versions from normal public view.

### Publishing Process
Implemented: compact journey and direct author downloads.
Next: keep detailed policy explanations collapsed behind optional “Learn more” disclosures; the default view should remain a short six-step journey.

### Editorial Board
Implemented: tighter profile cards and group spacing.
Next: if the board exceeds ~20–25 people, add role filters and institution/country search rather than making cards smaller.

### Calls for Papers
Implemented: tighter cards and long instructions already collapse into a disclosure.
Next: move deadline/status into a compact top metadata row and avoid repeating generic submission instructions in every call when a shared Author Guidelines link is sufficient.

### Issues & Archive
Implemented: denser volume/issue containers.
Next: when the archive becomes large, add a compact year/volume jump control. Do not render every historical volume fully expanded by default.

### Article pages
Implemented: reduced surrounding layout gaps while preserving reading width.
Next: keep abstract and article body readable; compact metadata/actions, not scholarly text. On mobile, place PDF/citation actions directly after the article metadata.

### Search
Implemented: smaller result cards and spacing.
Next: once enough content exists, add lightweight filters for year, subject, manuscript type, and author. Avoid a large filter sidebar until there is enough data to justify it.

### Presentations / Resources
Implemented: tighter resource rows.
Next: use one-line metadata (type · contributor · date) and show only a short summary in list view.

### Sign in / Recovery / Invitation
Implemented: reduced desktop account panel height/margins.
Next: keep one primary action per screen and move explanatory security/help copy below the form or into a compact note.

### Author workspace
Implemented: tighter shell/panels and preparation downloads.
Next: make the “Jump to” strip sticky within the draft editor on long forms; collapse completed preparation sections only after the user has saved them successfully.

### Reviewer workspace
Implemented through shared workspace compactness rules.
Next: prioritize the assigned manuscript, deadline, conflict declaration, and submit-review action above history/details. Keep confidential guidance concise and persistent.

### Editorial / Admin workspaces
Implemented: reduced panel/header spacing without shrinking controls.
Next: show summary counts and exceptions first; use expandable detail panels for secondary metadata. Keep action buttons close to the record they affect and avoid repeated explanatory copy in every panel.

## Content verification note

The supplied Registration Form currently contains a website URL, a fee schedule, and an email address line that should be verified before treating the document as final public policy. The file itself has not been edited in this package.
