# NSAJ UI density optimization

## What changed
- Reduced public utility bar and masthead height while preserving navigation and account actions.
- Replaced the generic header book mark with the supplied scientific open-book artwork, cropped to the symbol only.
- Kept the official journal name as live text: **Noble Scientific Advances Journal**.
- Reduced homepage hero height, artwork scale, heading spacing, and supporting-copy spacing.
- Reduced discipline-strip height.
- Reduced repeated vertical padding across homepage sections.
- Tightened the scope list, author CTA band, template cards, publishing journey, news/CFP area, trust area, follow band, and footer.
- Added responsive density adjustments for 1450+, 1120, 960, 760, and 600px breakpoints.

## Logo decision
The first supplied concept has the stronger visual direction for the website because the open-book/science symbol works with the journal's Science / Engineering / Technology scope. The supplied full wordmarks were not embedded because their text does not exactly match the approved journal name. The implementation therefore uses only the symbol and renders the correct journal name in HTML.

## Files changed
- `src/components/journal-header.tsx`
- `src/app/journal-theme.css`
- `public/nsaj-navbar-mark.png` (new)

## Validation note
CSS brace balance and changed-file references were checked. A full Next.js build/typecheck could not be completed in this environment because package installation required network dependencies that were unavailable/timed out.
