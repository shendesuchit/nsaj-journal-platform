# Focused acceptance checks

Use staging/test papers and test accounts. Apply frontend and backend together.

1. Submit as author. Admin tracker shows title, author, reference and a highlighted submitted status. Search each field. An unassigned paper is counted under needs assignment.
2. Admin → Open paper → Act on behalf of Chief → Assign editor. Confirm decision permission is optional. Check history names the admin and represented Chief; ownership names the assigned editor.
3. Complete technical checks. Confirm the normal editor dropdown cannot jump straight to under review or published.
4. Invite two reviewers. Record each real supplied response with its source reference. Confidentiality and conflict checks must still apply.
5. Submit only one report: author sees review in progress. Submit the second: author and editor see reviews received / awaiting editorial decision.
6. An editor without decision permission cannot decide, including through admin assistance. Grant permission using Chief assistance and retry.
7. With an outstanding review, attempt decision without closing it: blocked. Either await its report or explicitly close it with a reason. Completed reports remain retained.
8. Record revision requested and an author letter. Author sees the letter. Submit a real revised file through admin assistance with author source confirmation. Review round increments and author ownership is retained.
9. Record acceptance. Prepare a production article with a clean final file. Verify license and DOI where applicable. An unready issue must not publish; a future scheduled issue must not publish early.
10. Confirm conflict resolution and cancellation are limited to a current assignment on the selected paper. A cancelled reviewer cannot submit a late report.
11. Open the same case twice. Save an action in one view, then attempt an old action in the other: stale snapshot rejected. Refresh before retrying.
12. Author/reviewer accounts must receive access denied for admin endpoints. Admin must still be denied normal editorial/reviewer endpoints; assistance uses its dedicated routes.
13. Download a clean file through admin case details. Confirm history records the download; quarantined files are blocked.
14. Check 390px mobile and desktop layouts; table scroll remains inside the tracker. Check counted editorial filters after search/owner filters.
15. Refresh author and editor views after admin actions and confirm current status, next step and correspondence agree.

Optional automated checks: copy the included `verification_tests` directory into the backend root and run `.\.venv\Scripts\python.exe -m pytest verification_tests -q`. These tests use an isolated in-memory SQLite database. Install pytest in your test environment if needed. The legacy migration regression expects your existing `alembic` directory.
