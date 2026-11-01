import { expect, test, type Page } from "@playwright/test";
import type { WorkflowProgress } from "../src/lib/manuscript-progress";

type Assignment = { id: string; reference: string; title: string; status: string; due_at: null; round_number: number };
const assignment = (id: string, status = "accepted"): Assignment => ({
  id, reference: `NSAJ-${id.toUpperCase()}`, title: `Manuscript ${id}`, status, due_at: null, round_number: 1,
});
const manuscript = (item: Assignment) => ({
  ...item, abstract: `Abstract for ${item.title}`, authors: [],
  files: [{ id: `file-${item.id}`, name: `${item.id}.pdf`, url: `/private/${item.id}.pdf` }],
});
const editorialProgress = (status: string, round = 1): WorkflowProgress => ({
  current_round: round,
  bucket: ["production", "scheduled", "accepted"].includes(status) ? "production" : ["published", "declined", "withdrawn"].includes(status) ? "closed" : "needs_editor",
  waiting_on: "editor", next_action: status === "accepted" ? "prepare_production" : "review_case", due_at: null,
  review_counts: { invited: 0, accepted: 0, completed: 0, conflict_reported: 0, overdue: 0 },
});
const editorialCase = (id: string, status = "accepted", round = 1) => ({
  id, reference: `NSAJ-${id.toUpperCase()}`, title: `Manuscript ${id}`, status,
  abstract: `Abstract for Manuscript ${id}`, authors: [], reviews: [],
  assigned_editors: [{ id: "editor-1", display_name: "Assigned Editor" }], is_assigned_to_me: true,
  can_record_decision: true, progress: editorialProgress(status, round),
  reviewer_options: [],
  files: [{ id: `file-${id}`, name: `${id}.pdf`, scan_status: "clean" }],
});
const reviewerSelection = (page: Page) => page.getByRole("region", { name: "Selected review assignment", exact: true });
const editorialSelection = (page: Page) => page.getByRole("region", { name: "Selected editorial case", exact: true });
const settleRendering = (page: Page) => page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));

const adminProgress: WorkflowProgress = {
  current_round: 1,
  bucket: "needs_assignment",
  waiting_on: "editor_assignment",
  next_action: "assign_editor",
  due_at: null,
  review_counts: { invited: 0, accepted: 0, completed: 0, conflict_reported: 0, overdue: 0 },
};
const adminOverview = {
  observed_at: "2026-10-31T00:00:00Z",
  summary: { papers: 2, drafts: 0, active: 2, needs_assignment: 2 },
  pages: [], checks: [],
  content: { announcements: {}, calls: {}, issues: {} },
  manuscripts: {
    total: 2, offset: 0, limit: 50,
    items: [
      { id: "paper-alpha", status: "submitted", title: "Alpha study", authors: ["Author A"], editors: [], reference: "NSAJ-ALPHA", display_status: "Submitted", editor_assigned: false, progress: adminProgress },
      { id: "paper-beta", status: "submitted", title: "Beta study", authors: ["Author B"], editors: [], reference: "NSAJ-BETA", display_status: "Submitted", editor_assigned: false, progress: adminProgress },
    ],
  },
};
const adminCase = (id: string, reference: string, title: string) => ({
  id, reference, title, status: "submitted", display_status: "Submitted", snapshot: "a".repeat(64),
  progress: adminProgress, actors: [], roles: [], reviews: [], manual_transitions: [], schemas: {},
  editor_options: [], files: [], issues: [], history: [], steps: [{ label: "Submitted", recorded: true }],
});

test("admin paper details open, reopen, and switch into view at desktop and mobile widths", async ({ page }) => {
  let holdBeta = false;
  let betaHeld = Promise.resolve();
  let signalBetaRequested = () => {};
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { authenticated: true, roles: ["site_admin"] } });
    if (path.endsWith("/admin/overview")) return route.fulfill({ json: adminOverview });
    if (path.endsWith("/admin/manuscripts/paper-alpha")) return route.fulfill({ json: adminCase("paper-alpha", "NSAJ-ALPHA", "Alpha study") });
    if (path.endsWith("/admin/manuscripts/paper-beta")) {
      if (holdBeta) { signalBetaRequested(); await betaHeld; }
      return route.fulfill({ json: adminCase("paper-beta", "NSAJ-BETA", "Beta study") });
    }
    return route.fulfill({ status: 404, json: { detail: "Unexpected test request" } });
  });

  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/admin/overview");
    await expect(page.getByRole("heading", { name: "Journal control", exact: true })).toBeVisible();

    const panel = page.getByRole("region", { name: "Opened paper details", exact: true });
    const alphaButton = page.getByRole("button", { name: "Open paper", exact: true }).first();
    await alphaButton.click();
    await expect(panel.getByRole("heading", { name: "NSAJ-ALPHA · Alpha study", exact: true })).toBeVisible();
    await expect(panel).toBeFocused();
    await expect(alphaButton).toHaveAttribute("aria-expanded", "true");
    await expect(panel).toBeInViewport();

    await page.evaluate(() => window.scrollTo(0, 0));
    const reopenButton = page.getByRole("button", { name: "View opened paper", exact: true });
    await reopenButton.focus();
    await page.keyboard.press("Enter");
    await expect(panel).toBeFocused();
    await expect(panel.getByRole("heading", { name: "NSAJ-ALPHA · Alpha study", exact: true })).toBeVisible();

    let releaseBeta!: () => void;
    let betaRequested!: () => void;
    betaHeld = new Promise<void>(resolve => { releaseBeta = resolve; });
    const betaRequest = new Promise<void>(resolve => { betaRequested = resolve; });
    signalBetaRequested = betaRequested;
    holdBeta = true;
    await page.getByRole("button", { name: "Open paper", exact: true }).click();
    await betaRequest;
    await expect(panel.getByRole("heading", { name: "Loading manuscript…", exact: true })).toBeVisible();
    await expect(panel.getByText("Alpha study", { exact: true })).toHaveCount(0);
    await expect(panel).toBeFocused();
    releaseBeta();
    holdBeta = false;
    await expect(panel.getByRole("heading", { name: "NSAJ-BETA · Beta study", exact: true })).toBeVisible();
    await expect(panel).toBeInViewport();

    const geometry = await page.evaluate(() => {
      const panelBox = document.querySelector("#selected-paper-panel")?.getBoundingClientRect();
      const mastheadBox = document.querySelector(".site-masthead")?.getBoundingClientRect();
      return { panelTop: panelBox?.top ?? -1, mastheadBottom: mastheadBox?.bottom ?? 0, documentWidth: document.documentElement.scrollWidth, viewportWidth: document.documentElement.clientWidth };
    });
    expect(geometry.panelTop).toBeGreaterThanOrEqual(geometry.mastheadBottom);
    expect(geometry.documentWidth).toBeLessThanOrEqual(geometry.viewportWidth);
  }
});

test("admin keeps a failed paper request visible in the focused details region", async ({ page }) => {
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { authenticated: true, roles: ["site_admin"] } });
    if (path.endsWith("/admin/overview")) return route.fulfill({ json: adminOverview });
    if (path.endsWith("/admin/manuscripts/paper-alpha")) return route.fulfill({ status: 503, json: { detail: "Case service unavailable" } });
    return route.fulfill({ status: 404, json: { detail: "Unexpected test request" } });
  });
  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto("/admin/overview");
  await page.getByRole("button", { name: "Open paper", exact: true }).first().click();
  const panel = page.getByRole("region", { name: "Opened paper details", exact: true });
  await expect(panel.getByRole("alert")).toBeVisible();
  await expect(panel).toBeFocused();
  await expect(panel).toBeInViewport();
});

test("reviewer acceptance opens the report and submission closes editing", async ({ page }, testInfo) => {
  let status = "invited";
  let reportPosts = 0;
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    const item = assignment("alpha", status);
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { authenticated: true, roles: ["reviewer"] } });
    if (path.endsWith("/reviewer/assignments")) return route.fulfill({ json: { items: [item] } });
    if (path.endsWith("/alpha/respond")) {
      expect(route.request().postDataJSON()).toMatchObject({ accept: true, confidentiality_accepted: true, has_conflict: false });
      status = "accepted";
      return route.fulfill({ json: { status } });
    }
    if (path.endsWith("/alpha/report")) {
      reportPosts += 1;
      expect(route.request().postDataJSON()).toMatchObject({ comments_to_editor: "Private report for alpha" });
      status = "completed";
      return route.fulfill({ json: { status } });
    }
    if (path.endsWith("/assignments/alpha")) return route.fulfill({ json: manuscript(item) });
    return route.fulfill({ status: 404, json: { detail: "Unexpected test request" } });
  });
  await page.goto("/reviewer");
  await page.getByRole("button", { name: /NSAJ-ALPHA/ }).click();
  const selected = reviewerSelection(page);
  await expect(selected.locator(".record-heading .eyebrow")).toContainText("Paper ID: NSAJ-ALPHA");
  await selected.getByLabel("Confidentiality acknowledgement").selectOption("yes");
  await selected.getByRole("button", { name: "Record response", exact: true }).click();
  await expect(selected.getByRole("heading", { name: "Confidential review report" })).toBeVisible();
  await expect(selected.getByRole("heading", { name: "Respond to this invitation" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /NSAJ-ALPHA/ })).toContainText("accepted");

  const comments = selected.getByLabel("Confidential comments to editor (required)");
  await comments.fill("Private report for alpha");
  await page.screenshot({path:testInfo.outputPath("reviewer-active.png"),fullPage:true});
  await selected.getByRole("button", { name: "Submit confidential review", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Submit confidential review?" });
  await expect(dialog).toContainText("NSAJ-ALPHA: Manuscript alpha");
  await expect(dialog.getByRole("button", { name: "Cancel", exact: true })).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(dialog.getByRole("button", {name:"Submit review",exact:true})).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(dialog.getByRole("button", {name:"Cancel",exact:true})).toBeFocused();
  expect(reportPosts).toBe(0);
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(comments).toHaveValue("Private report for alpha");
  await expect(selected.getByRole("button", {name:"Submit confidential review",exact:true})).toBeFocused();
  await selected.getByRole("button", { name: "Submit confidential review", exact: true }).click();
  await dialog.getByRole("button", { name: "Submit review", exact: true }).click();
  await expect(selected.getByRole("heading", { name: "Review submitted", exact: true })).toBeVisible();
  await expect(selected.getByRole("textbox")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /NSAJ-ALPHA/ })).toContainText("completed");
  expect(reportPosts).toBe(1);
});

test("completed review stays read only when the subsequent list refresh fails", async ({ page }) => {
  let submitted = false;
  const item = assignment("alpha");
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { authenticated: true, roles: ["reviewer"] } });
    if (path.endsWith("/reviewer/assignments")) return submitted
      ? route.fulfill({ status: 503, json: { detail: "Assignment refresh unavailable" } })
      : route.fulfill({ json: { items: [item] } });
    if (path.endsWith("/alpha/report")) { submitted = true; return route.fulfill({ json: { status: "completed" } }); }
    if (path.endsWith("/assignments/alpha")) return route.fulfill({ json: manuscript(item) });
    return route.fulfill({ status: 404, json: { detail: "Unexpected test request" } });
  });
  await page.goto("/reviewer");
  await page.getByRole("button", { name: /NSAJ-ALPHA/ }).click();
  const selected = reviewerSelection(page);
  await selected.getByRole("button", { name: "Open assigned manuscript" }).click();
  await selected.getByLabel("Confidential comments to editor (required)").fill("Private report");
  await selected.getByRole("button", { name: "Submit confidential review", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Submit review", exact: true }).click();
  await expect(selected.getByRole("heading", { name: "Review submitted", exact: true })).toBeVisible();
  await expect(selected.getByRole("alert")).toHaveText("Assignment refresh unavailable");
  await selected.getByRole("button", {name:"Open assigned manuscript"}).click();
  await expect(selected.getByRole("link", {name:"alpha.pdf"})).toHaveAttribute("href", "/private/alpha.pdf");
  await expect(selected.getByRole("textbox")).toHaveCount(0);
  await expect(page).toHaveURL(/\/reviewer$/);
});

test("switching reviewer assignments supports cancel and discards only after confirmation", async ({ page }) => {
  const items = [assignment("alpha"), assignment("beta")];
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { authenticated: true, roles: ["reviewer"] } });
    if (path.endsWith("/reviewer/assignments")) return route.fulfill({ json: { items } });
    const item = items.find(value => path.endsWith(`/assignments/${value.id}`));
    return item ? route.fulfill({ json: manuscript(item) }) : route.fulfill({ status: 404, json: { detail: "Unexpected test request" } });
  });
  await page.goto("/reviewer");
  await page.getByRole("button", { name: /NSAJ-ALPHA/ }).click();
  const selected = reviewerSelection(page);
  await selected.getByRole("button", { name: "Open assigned manuscript" }).click();
  await selected.getByLabel("Confidential comments to editor (required)").fill("Alpha draft report");
  await page.getByRole("button", { name: /NSAJ-BETA/ }).click();
  const dialog = page.getByRole("dialog", { name: "Discard unsaved review changes?" });
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(selected.getByRole("heading", { name: "Manuscript alpha", exact: true })).toBeVisible();
  await expect(selected.getByLabel("Confidential comments to editor (required)")).toHaveValue("Alpha draft report");
  await page.getByRole("button", { name: /NSAJ-BETA/ }).click();
  await dialog.getByRole("button", { name: "Discard changes", exact: true }).click();
  await expect(selected.getByRole("heading", { name: "Manuscript beta", exact: true })).toBeVisible();
  await expect(selected.getByRole("textbox")).toHaveCount(0);
  await selected.getByRole("button", { name: "Open assigned manuscript" }).click();
  await expect(selected.getByLabel("Confidential comments to editor (required)")).toHaveValue("");
  await expect(selected.getByText("Abstract for Manuscript alpha", { exact: true })).toHaveCount(0);
});

test("editorial production forms reset between cases and continuation belongs to the created record", async ({ page }, testInfo) => {
  const cases = [editorialCase("alpha"), editorialCase("beta")];
  let articlePosts = 0;
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { authenticated: true, roles: ["managing_editor"] } });
    if (path.endsWith("/editorial/worklist")) return route.fulfill({ json: { items: cases } });
    if (path.endsWith("/beta/article")) {
      articlePosts += 1;
      expect(route.request().postDataJSON()).toEqual({ slug: "nsaj-beta", title: "Manuscript beta", abstract: "Abstract for Manuscript beta", final_file_id: "file-beta", license: "Approved wording for beta", doi: null });
      cases[1].status = "production"; cases[1].progress = editorialProgress("production");
      return route.fulfill({ json: { id: "production-beta" } });
    }
    const item = cases.find(value => path.endsWith(`/submissions/${value.id}`));
    return item ? route.fulfill({ json: item }) : route.fulfill({ status: 404, json: { detail: "Unexpected test request" } });
  });
  await page.goto("/editorial");
  await page.getByRole("button", { name: /NSAJ-ALPHA/ }).click();
  const selected = editorialSelection(page);
  await selected.getByLabel("Published title").fill("Unsaved alpha title");
  await selected.getByLabel("Approved license text").fill("Alpha license");
  await selected.getByLabel("DOI, only if registered (optional)").fill("alpha-value");
  await page.getByRole("button", { name: /NSAJ-BETA/ }).click();
  const dialog = page.getByRole("dialog", { name: "Discard unsaved case changes?" });
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(selected.getByLabel("Published title")).toHaveValue("Unsaved alpha title");
  await page.getByRole("button", { name: /NSAJ-BETA/ }).click();
  await dialog.getByRole("button", { name: "Discard changes", exact: true }).click();
  await expect(selected.getByLabel("Published title")).toHaveValue("Manuscript beta");
  await expect(selected.getByLabel("Stable article URL slug")).toHaveValue("nsaj-beta");
  await expect(selected.getByRole("textbox", { name: "Abstract", exact: true })).toHaveValue("Abstract for Manuscript beta");
  await expect(selected.getByLabel("Approved license text")).toHaveValue("");
  await expect(selected.getByLabel("DOI, only if registered (optional)")).toHaveValue("");
  await page.screenshot({path:testInfo.outputPath("editorial-production.png"),fullPage:true});
  await selected.getByLabel("Final clean file").selectOption("file-beta");
  await selected.getByLabel("Approved license text").fill("Approved wording for beta");
  await selected.getByRole("button", { name: "Create production record", exact: true }).click();
  const continuation = selected.getByRole("link", { name: "Continue issue preparation" });
  await expect(continuation).toHaveAttribute("href", "/admin/publication?submissionReference=NSAJ-BETA");
  await expect(selected.getByText("production-beta", { exact: true })).toHaveCount(0);
  await expect(selected.getByRole("button", { name: "Create production record", exact: true })).toHaveCount(0);
  await expect(selected.getByRole("region", { name: "Manuscript progress", exact: true }).locator('[aria-current="step"]')).toContainText("Production");
  expect(articlePosts).toBe(1);
  await page.getByRole("button", { name: /NSAJ-ALPHA/ }).click();
  await expect(selected.getByLabel("Published title")).toHaveValue("Manuscript alpha");
  await expect(continuation).toHaveCount(0);
  await expect(selected.getByRole("button", { name: "Create production record", exact: true })).toBeEnabled();
});

test("switching editorial tasks retains cancelled edits and clears confirmed discarded entries", async ({ page }) => {
  const item = editorialCase("alpha", "under_review");
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { authenticated: true, roles: ["associate_editor"] } });
    if (path.endsWith("/editorial/worklist")) return route.fulfill({ json: { items: [item] } });
    if (path.endsWith("/submissions/alpha")) return route.fulfill({ json: item });
    return route.fulfill({ status: 404, json: { detail: "Unexpected test request" } });
  });
  await page.goto("/editorial");
  await page.getByRole("button", { name: /NSAJ-ALPHA/ }).click();
  const selected = editorialSelection(page);
  await selected.getByLabel("Letter to author (required)").fill("Draft author letter");
  await selected.getByRole("navigation", { name: "Editorial case tasks" }).getByRole("button", { name: "Assign reviewer", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Discard unsaved form changes?" });
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(selected.getByLabel("Letter to author (required)")).toHaveValue("Draft author letter");
  await selected.getByRole("navigation", { name: "Editorial case tasks" }).getByRole("button", { name: "Assign reviewer", exact: true }).click();
  await dialog.getByRole("button", { name: "Discard changes", exact: true }).click();
  await selected.getByLabel("Reviewer").selectOption("new");
  await expect(selected.getByLabel("Reviewer email")).toHaveValue("");
  await selected.getByRole("button", { name: "Editor decision", exact: true }).click();
  await dialog.getByRole("button", { name: "Discard changes", exact: true }).click();
  await expect(selected.getByLabel("Letter to author (required)")).toHaveValue("");
});

test("editor assigns an existing reviewer from the case list without re-entering contact details", async ({ page }) => {
  const item = {
    ...editorialCase("gamma", "under_review", 2),
    reviewer_options: [{
      id: "reviewer-profile-1",
      full_name: "Dr. Existing Reviewer",
      email: "reviewer@example.test",
      affiliation: "Research Institute",
      expertise: ["biology"],
      languages: ["English"],
    }],
  };
  const assignmentBodies: Record<string, unknown>[] = [];
  await page.route("**/api/v1/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { authenticated: true, roles: ["associate_editor"] } });
    if (path.endsWith("/editorial/worklist")) return route.fulfill({ json: { items: [item] } });
    if (path.endsWith("/submissions/gamma/reviewers")) {
      assignmentBodies.push(request.postDataJSON() as Record<string, unknown>);
      return route.fulfill({ status: 201, json: { ok: true, status: "invited" } });
    }
    if (path.endsWith("/submissions/gamma")) return route.fulfill({ json: item });
    return route.fulfill({ status: 404, json: { detail: "Unexpected test request" } });
  });

  await page.goto("/editorial");
  await page.getByRole("button", { name: /NSAJ-GAMMA/ }).click();
  const selected = editorialSelection(page);
  await selected.getByRole("navigation", { name: "Editorial case tasks" }).getByRole("button", { name: "Assign reviewer", exact: true }).click();
  await selected.getByLabel("Reviewer").selectOption("reviewer-profile-1");
  await selected.getByLabel("Due date and time (local)").fill("2030-05-01T12:00");
  await expect(selected.getByLabel("Reviewer email")).toHaveCount(0);
  await selected.getByRole("button", { name: "Assign selected reviewer", exact: true }).click();

  expect(assignmentBodies[0]).toMatchObject({
    email: "reviewer@example.test",
    full_name: "Dr. Existing Reviewer",
    affiliation: "Research Institute",
    expertise: ["biology"],
    languages: ["English"],
    round_number: 2,
  });
  expect(assignmentBodies[0]?.due_at).toEqual(expect.stringMatching(/Z$/));
  await expect(page.getByText("Existing reviewer assigned to this case.", { exact: true })).toBeVisible();
});

test("editorial details ignore a slow response for a previously selected case", async ({ page }) => {
  const cases = [editorialCase("alpha"), editorialCase("beta")];
  let releaseAlpha!: () => void;
  let alphaRequested!: () => void;
  let alphaFulfilled!: () => void;
  const held = new Promise<void>(resolve => { releaseAlpha = resolve; });
  const requested = new Promise<void>(resolve => { alphaRequested = resolve; });
  const fulfilled = new Promise<void>(resolve => { alphaFulfilled = resolve; });
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { authenticated: true, roles: ["managing_editor"] } });
    if (path.endsWith("/editorial/worklist")) return route.fulfill({ json: { items: cases } });
    if (path.endsWith("/submissions/alpha")) {
      alphaRequested(); await held; await route.fulfill({ json: cases[0] }); alphaFulfilled(); return;
    }
    if (path.endsWith("/submissions/beta")) return route.fulfill({ json: cases[1] });
    return route.fulfill({ status: 404, json: { detail: "Unexpected test request" } });
  });
  await page.goto("/editorial");
  await page.getByRole("button", { name: /NSAJ-ALPHA/ }).click();
  await requested;
  await page.getByRole("button", { name: /NSAJ-BETA/ }).click();
  const selected = editorialSelection(page);
  await expect(selected.getByLabel("Published title")).toHaveValue("Manuscript beta");
  const alphaResponse = page.waitForResponse(response => response.url().endsWith("/editorial/submissions/alpha"));
  releaseAlpha(); await fulfilled; await (await alphaResponse).finished();
  await settleRendering(page);
  await expect(selected.getByRole("heading", { name: "Manuscript beta", exact: true })).toBeVisible();
  await expect(selected.getByLabel("Published title")).toHaveValue("Manuscript beta");
  await expect(page.getByRole("button", { name: /NSAJ-BETA/ })).toHaveAttribute("aria-current", "true");
});

test("Chief worklist filters team summaries without requesting confidential case details", async ({ page }) => {
  const assigned = { ...editorialCase("alpha", "under_review"), assigned_editors: [{ id: "editor-a", display_name: "Editor A" }, { id: "editor-b", display_name: "Editor B" }], is_assigned_to_me: false };
  assigned.progress = { ...assigned.progress, bucket: "waiting_review", waiting_on: "reviewer", next_action: "await_review", review_counts: { invited: 0, accepted: 2, completed: 1, conflict_reported: 0, overdue: 0 } };
  const unassigned = { ...editorialCase("beta", "submitted"), assigned_editors: [] as { id: string; display_name: string }[], is_assigned_to_me: false };
  unassigned.progress = { ...unassigned.progress, bucket: "needs_assignment", waiting_on: "editor_assignment", next_action: "assign_editor" };
  const closed = { ...editorialCase("closed", "declined"), is_assigned_to_me: false };
  let detailReads = 0;
  let auditReads = 0;
  let assignmentBody: Record<string, unknown> | null = null;
  await page.route("**/api/v1/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { authenticated: true, roles: ["editor_in_chief"] } });
    if (path.endsWith("/editorial/worklist")) return route.fulfill({ json: { items: [assigned, unassigned, closed].map(({ id, reference, title, status, assigned_editors, is_assigned_to_me, progress }) => ({ id, reference, title, status, assigned_editors, is_assigned_to_me, progress })) } });
    if (path.endsWith("/editorial/editors")) return route.fulfill({ json: { items: [{ id: "editor-a", display_name: "Editor A", email: "a@example.test", roles: ["associate_editor"] }] } });
    if (path.endsWith("/editorial/submission-checklists")) return route.fulfill({ json: { items: [{ approved_at: "2030-01-01T00:00:00Z" }] } });
    if (path.endsWith("/editorial/audit")) { auditReads += 1; return route.fulfill({ json: { items: [] } }); }
    if (path.endsWith("/submissions/beta/editors")) {
      assignmentBody = request.postDataJSON();
      unassigned.assigned_editors = [{ id: "editor-a", display_name: "Editor A" }];
      unassigned.progress = { ...unassigned.progress, bucket: "needs_editor", waiting_on: "editor", next_action: "start_technical_check" };
      return route.fulfill({ json: { ok: true } });
    }
    if (path.includes("/editorial/submissions/")) { detailReads += 1; return route.fulfill({ status: 403, json: { detail: "Full case access requires assignment" } }); }
    return route.fulfill({ status: 404, json: { detail: "Unexpected test request" } });
  });
  await page.goto("/editorial");
  await expect(page.getByRole("heading", { name: "Editorial worklist", exact: true })).toBeVisible();
  expect(auditReads).toBe(0);
  await page.getByRole("button", { name: /NSAJ-ALPHA/ }).click();
  const selected = editorialSelection(page);
  await expect(selected.getByText("Editor A, Editor B", { exact: true })).toBeVisible();
  await expect(selected.getByText("This is a team summary.", { exact: false })).toBeVisible();
  await expect(selected.getByRole("button", { name: "Retry selected case" })).toHaveCount(0);
  await expect(selected.getByText("Manuscript details and files", { exact: true })).toHaveCount(0);
  await expect(selected.getByRole("region", { name: "Manuscript progress", exact: true }).locator('[aria-current="step"]')).toContainText("Peer review");
  expect(detailReads).toBe(0);
  await page.getByLabel("Assigned editor", { exact: true }).selectOption("editor-b");
  await expect(page.getByRole("button", { name: /NSAJ-ALPHA/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /NSAJ-BETA/ })).toHaveCount(0);
  await page.getByLabel("Assigned editor", { exact: true }).selectOption("");
  await page.getByRole("button", { name: "Needs assignment", exact: true }).click();
  await page.getByRole("button", { name: /NSAJ-BETA/ }).click();
  await selected.getByLabel("Assign NSAJ-BETA to").selectOption("editor-a");
  await selected.getByLabel("May record decisions for this case").check();
  await selected.getByRole("button", { name: "Assign case", exact: true }).click();
  await expect(selected.getByText("Case NSAJ-BETA assigned.", { exact: true })).toBeVisible();
  expect(assignmentBody).toEqual({ editor_id: "editor-a", can_make_decisions: true });
  expect(detailReads).toBe(0);
  await page.getByRole("button", { name: "Closed", exact: true }).click();
  await expect(page.getByRole("button", { name: /NSAJ-CLOSED/ })).toBeVisible();
  await page.getByLabel("Find a manuscript").fill("missing title");
  await expect(page.getByText("No manuscripts match this view.", { exact: true })).toBeVisible();
  await page.getByText("Recent journal activity", { exact: true }).click();
  await expect(page.getByText("No journal activity has been recorded.", { exact: true })).toBeVisible();
  expect(auditReads).toBe(1);
});

test("decision authority is case scoped and second-round decisions use the current round", async ({ page }) => {
  const delegated = editorialCase("delegated", "under_review", 2);
  const coordinator = { ...editorialCase("coordinator", "under_review", 2), can_record_decision: false };
  let decisionBody: Record<string, unknown> | null = null;
  await page.route("**/api/v1/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { authenticated: true, roles: ["associate_editor"] } });
    if (path.endsWith("/editorial/worklist")) return route.fulfill({ json: { items: [coordinator, delegated] } });
    if (path.endsWith("/submissions/delegated/decision")) {
      decisionBody = request.postDataJSON(); delegated.status = "revision_requested"; delegated.progress = { ...delegated.progress, bucket: "awaiting_author", waiting_on: "author", next_action: "upload_revision" };
      return route.fulfill({ json: { status: "revision_requested" } });
    }
    const item = [coordinator, delegated].find(value => path.endsWith(`/submissions/${value.id}`));
    return item ? route.fulfill({ json: item }) : route.fulfill({ status: 404, json: { detail: "Unexpected test request" } });
  });
  await page.goto("/editorial");
  await page.getByRole("button", { name: /NSAJ-COORDINATOR/ }).click();
  const selected = editorialSelection(page);
  await expect(selected.getByRole("button", { name: "Editor decision", exact: true })).toHaveCount(0);
  await expect(selected.getByText("You may coordinate the case; decision authority has not been granted.", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: /NSAJ-DELEGATED/ }).click();
  await selected.getByLabel("Letter to author (required)").fill("Please revise the second-round manuscript.");
  await selected.getByRole("button", { name: "Record decision", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Confirm decision", exact: true }).click();
  await expect(selected.getByText("Editorial decision recorded and attributed to your account.", { exact: true })).toBeVisible();
  expect(decisionBody).toMatchObject({ round_number: 2, decision: "revision_requested" });
  await expect(selected.getByRole("region", { name: "Manuscript progress", exact: true }).locator('[aria-current="step"]')).toContainText("Decision and revision");
});

test("mixed Site Admin and editorial accounts cannot load the confidential worklist", async ({ page }) => {
  let worklistReads = 0;
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { authenticated: true, roles: ["site_admin", "editor_in_chief"] } });
    worklistReads += 1;
    return route.fulfill({ status: 403, json: { detail: "Forbidden" } });
  });
  await page.goto("/editorial");
  await expect(page.getByRole("heading", { name: "Editorial access required", exact: true })).toBeVisible();
  expect(worklistReads).toBe(0);
});

test("reviewer manuscript details ignore a slow response after changing assignments", async ({ page }) => {
  const items = [assignment("alpha"), assignment("beta")];
  let releaseAlpha!: () => void;
  let alphaRequested!: () => void;
  const held = new Promise<void>(resolve => { releaseAlpha = resolve; });
  const requested = new Promise<void>(resolve => { alphaRequested = resolve; });
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/me")) return route.fulfill({ json: { authenticated: true, roles: ["reviewer"] } });
    if (path.endsWith("/reviewer/assignments")) return route.fulfill({ json: { items } });
    if (path.endsWith("/assignments/alpha")) { alphaRequested(); await held; return route.fulfill({ json: manuscript(items[0]) }); }
    if (path.endsWith("/assignments/beta")) return route.fulfill({ json: manuscript(items[1]) });
    return route.fulfill({ status: 404, json: { detail: "Unexpected test request" } });
  });
  await page.goto("/reviewer");
  await page.getByRole("button", { name: /NSAJ-ALPHA/ }).click();
  const selected = reviewerSelection(page);
  await selected.getByRole("button", { name: "Open assigned manuscript" }).click();
  await requested;
  await page.getByRole("button", { name: /NSAJ-BETA/ }).click();
  await selected.getByRole("button", { name: "Open assigned manuscript" }).click();
  await expect(selected.getByText("Abstract for Manuscript beta", { exact: true })).toBeVisible();
  const alphaResponse = page.waitForResponse(response => response.url().endsWith("/reviewer/assignments/alpha"));
  releaseAlpha(); await (await alphaResponse).finished();
  await settleRendering(page);
  await expect(selected.getByText("Abstract for Manuscript beta", { exact: true })).toBeVisible();
  await expect(selected.getByText("Abstract for Manuscript alpha", { exact: true })).toHaveCount(0);
  await expect(selected.getByRole("link", { name: "beta.pdf", exact: true })).toBeVisible();
});
