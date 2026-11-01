# NSAJ frontend theme update

This project applies the navy, white and muted teal journal theme to your existing Next.js frontend. It continues to use your current backend, authentication and editorial workflows through the existing `/api/v1` integration.

## What changed

- Refined journal masthead with accessible desktop and mobile navigation, search and account access.
- Redesigned homepage with the scientific journal cover, discipline links, live issue content, approved templates, publishing process and announcements.
- Shared typography, spacing, compact controls, subtle borders and consistent status styling across public and private pages.
- Focused sign-in, invitation and password recovery layouts. Password visibility is optional; passwords remain controlled by the existing account flow.
- Consistent required-field indicators. Author draft fields still permit incomplete drafts; final submission rules remain in the existing workflow.
- Role-aware workspace navigation after sign-in and authenticator setup. Role assignments and backend authorization are preserved.
- Simpler volume and issue management: suggested next numbering, the current publication year, direct “Add an issue to this volume” actions and a three-step explanation. Optional descriptions and archive rearranging controls are kept out of the main path.
- Fixed a pre-existing unsaved-changes crash on local HTTP pages by using the existing browser cryptography API when `randomUUID` is unavailable. This affects a local history marker only.

## Connect to your existing backend

Use the same environment and backend URL as your current project. `src/lib/api.ts`, the `/api/v1` rewrite, dependency versions and lockfile are unchanged.

```powershell
npm ci
npm run dev
```

If your backend runs somewhere other than the existing default `http://127.0.0.1:8000`, set `API_BACKEND_URL` in your usual environment before starting or building the frontend. Keep using your existing invited accounts, CSRF/session cookies and MFA configuration.

For a production build:

```powershell
npm run typecheck
npm run build
npm run start
```

## Branding review

The supplied images fit the navy-and-teal science direction, but their wordmarks use “Nobel Scientific Advance Journal,” whereas this project uses “Noble Scientific Advances Journal.” The detailed illustration and tiny numerical labels also lose clarity at navbar size. The screenshot version contains cropped text and screen artefacts.

The implementation therefore uses a clean vector book/science mark with the existing journal name. Your original `public/nsaj-seal.png` is retained. Correct the supplied wordmark spelling and obtain a clean vector or high-resolution brand export before using it as the official logo.

## Verification

- `npm run typecheck` passed.
- `npm run build` passed for all existing routes.
- Compatibility checks found all 83 original API calls preserved across 33 original TypeScript source files.
- Nine workspace-routing cases passed, including mixed-role priority and accounts without workspace permissions.
- The homepage, sign-in layout, required markers and mobile menu were inspected in a browser.
- Mobile homepage and sign-in layouts, plus the tablet homepage, fit their viewports without horizontal overflow.
- Volume creation, target-volume selection, draft issue creation and the optional archive controls were exercised with isolated local API fixtures.

The uploaded archive contains the frontend only. Full login, email delivery, file scanning and publishing tests against the real backend are still required in your environment. The original Windows E2E scripts are retained; their backend and `tests-e2e` folder were not included in the upload.

No test accounts, API fixtures, preview server overrides, generated build folders or credentials are included in this deliverable.
