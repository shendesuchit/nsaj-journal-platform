import { expect, test, type Page } from "@playwright/test";

const paper = { id: "paper-1", reference: "NSAJ-76543210", title: "A selected paper with a long title for responsive workflow review", status: "resubmitted" };
const progress = { current_round: 2, bucket: "revisions_received", waiting_on: "editor", next_action: "review_revision", due_at: null, review_counts: { invited: 0, accepted: 0, completed: 0, conflict_reported: 0, overdue: 0 } };

async function fixture(page: Page, role: string) {
  await page.route("**/api/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    let json: unknown = { items: [] };
    if (path.endsWith("/auth/me")) json = { id: "member", display_name: "Journal member", authenticated: true, roles: [role] };
    else if (path.endsWith("/author/submission-checklist")) json = { checklist: null };
    else if (path.endsWith("/author/workspace")) json = { items: [paper] };
    else if (path.endsWith("/author/submissions/paper-1/editorial")) json = { ...paper, decisions: [], history: [{ status: "resubmitted", created_at: "2026-10-23T10:00:00Z" }] };
    else if (path.endsWith("/receipt")) return route.fulfill({ status: 404, json: { detail: "No legacy receipt" } });
    else if (path.endsWith("/reviewer/assignments")) json = { items: [{ ...paper, status: "invited", round_number: 2, due_at: "2026-11-12T12:00:00Z" }] };
    else if (path.endsWith("/editorial/worklist")) json = { items: [{ ...paper, assigned_editors: [{ id: "member", display_name: "Journal member" }], is_assigned_to_me: true, progress }] };
    else if (path.endsWith("/editorial/submissions/paper-1")) json = { ...paper, abstract: "Private fixture abstract", authors: [], files: [], reviews: [], reviewer_options: [], progress, can_record_decision: true, workflow: [] };
    else if (path.endsWith("/admin/production-articles")) json = { items: [{ ...paper, id: "article-1", status: "production", issue_id: "issue-1" }] };
    else if (path.endsWith("/admin/volumes")) json = { items: [{ id: "volume-1", number: 1, year: 2026, title: "Fixture volume", status: "open", issues: [{ id: "issue-1", number: "1", title: "Fixture issue", status: "draft" }] }] };
    return route.fulfill({ json });
  });
}

for (const width of [1440, 768, 390, 320]) {
  test(`selected manuscript workflows reflow and identify the paper at ${width}px`, async ({ page }, testInfo) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width, height: 1000 });
    for (const [path, role, phase] of [["/author", "author", "Editorial checks"], ["/reviewer", "reviewer", "Peer review"], ["/editorial", "editor_in_chief", "Editorial checks"], ["/admin/publication?submissionReference=NSAJ-76543210", "editor_in_chief", "Production"]]) {
      await page.unroute("**/api/v1/**");
      await fixture(page, role);
      await page.goto(path);
      if (path === "/reviewer" || path === "/editorial") await page.getByRole("button", { name: /NSAJ-76543210/ }).first().click();
      const tracker = page.getByRole("region", { name: "Manuscript progress", exact: true });
      await expect(tracker).toContainText("NSAJ-76543210");
      await expect(tracker.locator('.manuscript-progress__phases [aria-current="step"]')).toHaveCount(1);
      await expect(tracker.locator('.manuscript-progress__phases [aria-current="step"]')).toContainText(phase);
      await expect(tracker.getByRole("status")).toContainText(path === "/reviewer" ? "Your task phase" : "Current phase");
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
      if (path === "/reviewer") {
        await page.getByLabel("Confidentiality acknowledgement").focus();
        await expect(page.getByLabel("Confidentiality acknowledgement")).toBeFocused();
      }
      await page.screenshot({ path: testInfo.outputPath(`${role}-${path.split("/")[1]}-${width}.png`), fullPage: true });
    }
  });
}

test("reviewer completion describes only their task and never requests later manuscript decisions", async ({ page }) => {
  const requested: string[] = [];
  await page.route("**/api/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    requested.push(path);
    return route.fulfill({ json: path.endsWith("/auth/me") ? { id: "reviewer", authenticated: true, roles: ["reviewer"] } : { items: [{ ...paper, status: "completed", due_at: null, round_number: 2 }] } });
  });
  await page.goto("/reviewer");
  await page.getByRole("button", { name: /NSAJ-76543210/ }).click();
  const tracker = page.getByRole("region", { name: "Manuscript progress", exact: true });
  await expect(tracker.getByRole("status")).toContainText("Your review submitted");
  await expect(tracker).toContainText("Later editorial decisions and other reviewers' work remain private");
  await expect(tracker.locator('.manuscript-progress__phases [aria-current="step"]')).toContainText("Peer review");
  expect(requested.every(path => path.endsWith("/auth/me") || path.endsWith("/reviewer/assignments"))).toBe(true);
});

test("an unknown manuscript status has no invented highlight or next action", async ({ page }) => {
  await fixture(page, "editor_in_chief");
  await page.route("**/api/v1/editorial/worklist", route => route.fulfill({ json: { items: [{ ...paper, status: "external_hold", assigned_editors: [], is_assigned_to_me: false, progress: { ...progress, bucket: "needs_editor", next_action: "review_case" } }] } }));
  await page.goto("/editorial");
  await page.getByRole("button", { name: /NSAJ-76543210/ }).first().click();
  const tracker = page.getByRole("region", { name: "Manuscript progress", exact: true });
  await expect(tracker).toContainText("External hold");
  await expect(tracker.locator('.manuscript-progress__phases [aria-current="step"]')).toHaveCount(0);
  await expect(tracker.getByRole("status")).not.toContainText("Review this case");
});
