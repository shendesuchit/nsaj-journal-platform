# Volume lifecycle

Publication managers can change a volume's status from the Publication workspace.

- **Open:** accepts new issues and incoming draft issues.
- **Closed:** stops accepting new issues; existing issues can finish publication.
- **Archived:** removes a completed volume from the default management view.
  All issues must be published before archiving. Published articles and issues
  remain accessible through the public archive.

Use **Show archived volumes** to find archived records. **Restore volume** returns
an archived volume to Closed; **Reopen** then allows new issues again. These actions
do not delete volumes, issues, articles, or manuscript files.

Each status change requires authentication, a publication management role and CSRF
protection. The API checks the expected previous status, locks the volume during
the change, and records the operator and status transition in the audit trail.
No database migration is required: the existing volume status field is used.
