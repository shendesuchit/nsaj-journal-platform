import { expect, test } from "@playwright/test";

type IssueRecord = {
  id: string;
  number: string;
  title: string;
  status: "draft" | "scheduled" | "published" | "closed";
  scheduled_at: string | null;
  published_at: string | null;
};

type VolumeRecord = {
  id: string;
  number: number;
  year: number;
  title: string;
  status: "open" | "closed" | "archived";
  issues: IssueRecord[];
};

const demoMode = process.env.NSAJ_E2E_DEMO_CONTENT === "true";

test("volume workspace supports moving, saved reordering, keyboard controls, and mobile layout", async ({ page }, testInfo) => {
  const reorderRequests: { kind: string; ids: string[] }[] = [];
  let records: VolumeRecord[] = [
    {
      id: "00000000-0000-0000-0000-000000000101",
      number: 1,
      year: 2025,
      title: "Volume 1",
      status: "open",
      issues: [
        { id: "00000000-0000-0000-0000-000000000201", number: "3", title: "Draft Issue Three", status: "draft", scheduled_at: null, published_at: null },
        { id: "00000000-0000-0000-0000-000000000202", number: "4", title: "Draft Issue Four", status: "draft", scheduled_at: null, published_at: null },
      ],
    },
    {
      id: "00000000-0000-0000-0000-000000000102",
      number: 2,
      year: 2026,
      title: "Volume 2",
      status: "open",
      issues: [],
    },
  ];

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    let status = 200;
    let payload: unknown = { items: [] };
    if (url.pathname === "/api/v1/auth/me") {
      payload = { roles: ["site_admin"] };
    } else if (url.pathname === "/api/v1/admin/volumes" && request.method() === "GET") {
      payload = { items: records };
    } else if (url.pathname === "/api/v1/admin/volumes/order" && request.method() === "PUT") {
      const body = request.postDataJSON() as { volume_ids: string[] };
      reorderRequests.push({ kind: "volumes", ids: body.volume_ids });
      const byId = new Map(records.map((volume) => [volume.id, volume]));
      records = body.volume_ids.map((id) => byId.get(id)).filter((volume): volume is VolumeRecord => Boolean(volume));
      payload = { volume_ids: body.volume_ids };
    } else if (/^\/api\/v1\/admin\/volumes\/[^/]+\/issues\/order$/.test(url.pathname) && request.method() === "PUT") {
      const volumeId = url.pathname.split("/")[5];
      const body = request.postDataJSON() as { issue_ids: string[] };
      reorderRequests.push({ kind: "issues", ids: body.issue_ids });
      records = records.map((volume) => {
        if (volume.id !== volumeId) return volume;
        const drafts = new Map(volume.issues.filter((issue) => issue.status === "draft").map((issue) => [issue.id, issue]));
        let index = 0;
        return {
          ...volume,
          issues: volume.issues.map((issue) => issue.status === "draft" ? drafts.get(body.issue_ids[index++]) ?? issue : issue),
        };
      });
      payload = { issue_ids: body.issue_ids };
    } else if (/^\/api\/v1\/admin\/issues\/[^/]+\/volume$/.test(url.pathname) && request.method() === "PUT") {
      const issueId = url.pathname.split("/")[5];
      const body = request.postDataJSON() as { volume_id: string };
      let moving: IssueRecord | undefined;
      records = records.map((volume) => {
        const found = volume.issues.find((issue) => issue.id === issueId);
        if (found) moving = found;
        return { ...volume, issues: volume.issues.filter((issue) => issue.id !== issueId) };
      });
      records = records.map((volume) => volume.id === body.volume_id && moving
        ? { ...volume, issues: [...volume.issues, moving] }
        : volume);
      payload = { id: issueId, volume_id: body.volume_id, status: "draft", unchanged: false };
    } else if (request.method() !== "GET") {
      payload = { id: "saved-item", status: "draft" };
    }
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(payload) });
  });

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/admin/publication");
  await expect(page.getByRole("heading", { name: "Volumes and issues" }).first()).toBeVisible();
  const source = page.getByRole("region", { name: "Volume 1, 2025" });
  const destination = page.getByRole("region", { name: "Volume 2, 2026" });
  await page.screenshot({ path: testInfo.outputPath("publication-desktop.png"), fullPage: true });

  await source.getByLabel("Destination for Volume 1, Issue 3").selectOption(records[1].id);
  await source.getByRole("button", { name: "Move to volume" }).first().click();
  await expect(page.locator(".task-feedback").getByRole("status")).toContainText("Issue 3 moved to Volume 2");
  await expect(source.getByText("Draft Issue Three")).toHaveCount(0);
  await expect(destination.getByText("Draft Issue Three")).toBeVisible();

  await source.getByRole("button", { name: "Drag to reorder Issue 4" }).dragTo(destination);
  await expect(destination.getByText("Draft Issue Four")).toBeVisible();

  await destination.getByRole("button", { name: "Move Issue 4 up" }).click();
  await expect(destination.locator(".volume-issue__main strong")).toHaveText(["Draft Issue Four", "Draft Issue Three"]);
  expect(reorderRequests.find((request) => request.kind === "issues")?.ids).toEqual([
    "00000000-0000-0000-0000-000000000202",
    "00000000-0000-0000-0000-000000000201",
  ]);

  await page.getByRole("button", { name: "Move Volume 2 up" }).click();
  await expect(page.locator(".volume-card").first()).toHaveAttribute("aria-label", "Volume 2, 2026");
  expect(reorderRequests.find((request) => request.kind === "volumes")?.ids).toEqual([
    "00000000-0000-0000-0000-000000000102",
    "00000000-0000-0000-0000-000000000101",
  ]);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.getByLabel("Destination for Volume 2, Issue 3")).toBeVisible();
  await expect(page.locator(".volume-card").first()).toHaveAttribute("aria-label", "Volume 2, 2026");
  await expect(page.getByRole("region", { name: "Volume 2, 2026" }).locator(".volume-issue__main strong")).toHaveText(["Draft Issue Four", "Draft Issue Three"]);
  const dimensions = await page.evaluate(() => ({
    document: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport);
  await page.screenshot({ path: testInfo.outputPath("publication-mobile.png"), fullPage: true });
});

test("demo volume moves are labeled and remain local to the current preview", async ({ page }) => {
  test.skip(!demoMode, "Build with NSAJ_E2E_DEMO_CONTENT=true to check preview-only volume moves.");
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    let payload: unknown = { items: [] };
    if (url.pathname === "/api/v1/auth/me") payload = { roles: ["site_admin"] };
    if (url.pathname === "/api/v1/admin/volumes") payload = { items: [] };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) });
  });
  await page.goto("/admin/publication");
  const source = page.getByRole("region", { name: "Volume 8, 2026" });
  const destination = page.getByRole("region", { name: "Volume 7, 2025" });
  await expect(page.getByText("These fictional volumes and issues are preview records.")).toBeVisible();
  await expect(page.getByText("Demo only").first()).toBeVisible();
  const conflictingIssue = source.getByRole("listitem").filter({ hasText: "Sample research issue" });
  await conflictingIssue.getByLabel("Destination for Volume 8, Issue 1").selectOption("demo-volume-7-2025");
  await conflictingIssue.getByRole("button", { name: "Move to volume" }).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Issue 1 already exists in Volume 7 (2025).");
  await expect(conflictingIssue).toBeVisible();
  await expect(destination.getByText("Sample research issue — Demo only")).toHaveCount(1);

  const movableIssue = source.getByRole("listitem").filter({ hasText: "Issue 3" });
  await movableIssue.getByLabel("Destination for Volume 8, Issue 3").selectOption("demo-volume-7-2025");
  await movableIssue.getByRole("button", { name: "Move to volume" }).click();
  await expect(page.locator(".task-feedback").getByRole("status")).toContainText("The change is not saved");
  await expect(source.getByText("Sample special issue — Demo only")).toHaveCount(0);
  await expect(destination.getByText("Sample special issue — Demo only")).toBeVisible();
  await page.reload();
  await expect(page.getByRole("region", { name: "Volume 8, 2026" }).getByText("Sample special issue — Demo only")).toBeVisible();
});

test("public archive follows the API's saved volume and issue display order", async ({ page }) => {
  await page.route("**/api/v1/public/issues", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [
        { id: "issue-1a", number: "1", title: "Issue One", description: "", published_at: "2026-01-01T00:00:00Z", volume: { number: 2, year: 2026 }, articles: [] },
        { id: "issue-2", number: "2", title: "Issue Two", description: "", published_at: "2026-06-01T00:00:00Z", volume: { number: 2, year: 2026 }, articles: [] },
        { id: "issue-1b", number: "2", title: "Older Issue Two", description: "", published_at: "2025-06-01T00:00:00Z", volume: { number: 1, year: 2025 }, articles: [] },
      ] }),
    });
  });
  await page.goto("/issues");
  const volumeHeadings = page.locator(".public-volume-group__header h2");
  await expect(volumeHeadings).toHaveText(["Volume 2 · 2026", "Volume 1 · 2025"]);
  const newestVolume = page.locator(".public-volume-group").first();
  await expect(newestVolume.locator(".public-issue-row h3")).toHaveText(["Issue One", "Issue Two"]);
});

test("Editor-in-Chief can sign in through MFA and reach the editorial workspace", async ({ page, request }) => {
  const { createHmac, randomUUID } = await import("node:crypto");
  const email = `editor-in-chief-${randomUUID()}@example.test`;
  const password = "test editorial password 2026";
  const response = await request.post("http://127.0.0.1:8123/__test__/seed-user", {
    data: { email, password, role: "editor_in_chief" },
  });
  expect(response.ok()).toBeTruthy();
  const seeded = await response.json() as { mfa_secret: string };
  expect(seeded.mfa_secret).toBeTruthy();

  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const character of seeded.mfa_secret) {
    bits += alphabet.indexOf(character).toString(2).padStart(5, "0");
  }
  const secret: number[] = [];
  for (let offset = 0; offset + 8 <= bits.length; offset += 8) {
    secret.push(Number.parseInt(bits.slice(offset, offset + 8), 2));
  }
  const counter = BigInt(Math.floor(Date.now() / 30_000));
  const counterBytes = Buffer.alloc(8);
  counterBytes.writeBigUInt64BE(counter);
  const digest = createHmac("sha1", Buffer.from(secret)).update(counterBytes).digest();
  const truncationOffset = digest[digest.length - 1] & 0x0f;
  const code = ((digest.readUInt32BE(truncationOffset) & 0x7fffffff) % 1_000_000)
    .toString().padStart(6, "0");

  await page.goto("/sign-in");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Verify your identity" })).toBeVisible();
  await page.getByLabel("Authenticator or recovery code").fill(code);
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page).toHaveURL(/\/editorial$/);
  await expect(page.getByRole("heading", { name: "Assigned cases" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "My queue" })).toBeVisible();
});


test("publication failure offers retry without signing out the user", async ({ page }) => {
  let unavailable = true;
  await page.route("**/api/v1/**", (route) => {
    const pathname = new URL(route.request().url()).pathname;
    const failed = pathname === "/api/v1/admin/volumes" && unavailable;
    return route.fulfill({ status: failed ? 503 : 200, contentType: "application/json", body: JSON.stringify(failed ? { detail: "Unavailable" } : pathname === "/api/v1/auth/me" ? { roles: ["site_admin"] } : { items: [] }) });
  });
  await page.goto("/admin/publication");
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Publication records could not be loaded");
  await expect(page).toHaveURL(/\/admin\/publication$/);
  unavailable = false;
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("heading", { name: "Volumes and issues" }).first()).toBeVisible();
  await expect(page.getByText("Assigned editors handle confidential article assembly", { exact: false })).toBeVisible();
  await expect(page.getByText("Assemble and publish an issue", { exact: true })).toHaveCount(0);
});

test("article loading failure keeps volume management usable and supports retry", async ({ page }) => {
  let unavailable = true;
  await page.route("**/api/v1/**", route => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === "/api/v1/auth/me") return route.fulfill({ json: { roles: ["editor_in_chief"] } });
    if (pathname === "/api/v1/admin/volumes") return route.fulfill({ json: { items: [{ id: "volume-1", number: 1, year: 2026, title: "Current volume", status: "open", issues: [] }] } });
    if (pathname === "/api/v1/admin/production-articles") return unavailable
      ? route.fulfill({ status: 503, json: { detail: "Unavailable" } })
      : route.fulfill({ json: { items: [{ id: "article-1", reference: "NSAJ-12345678", title: "Available article", status: "production", issue_id: null }] } });
    return route.fulfill({ json: {} });
  });
  await page.goto("/admin/publication");
  await expect(page.getByRole("region", { name: "Volume 1, 2026" })).toBeVisible();
  await page.getByText("Manage volumes and issues", { exact: true }).click();
  await expect(page.getByRole("heading", { name: "Create a volume", exact: true })).toBeVisible();
  await page.getByText("Assemble and publish an issue", { exact: true }).first().click();
  await expect(page.getByRole("alert")).toContainText("Production articles could not be loaded");
  unavailable = false;
  await page.getByRole("button", { name: "Retry articles", exact: true }).click();
  await expect(page.getByLabel("Production article")).toBeEnabled();
  await expect(page.getByLabel("Production article")).toContainText("NSAJ-12345678");
});

test("publication retains issue identity through readiness and confirmation", async ({ page }, testInfo) => {
  const actions: string[] = [];
  await page.route("**/api/v1/**", (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (route.request().method() === "POST") actions.push(pathname);
    const payload = pathname === "/api/v1/auth/me" ? { roles: ["editor_in_chief"] }
      : pathname === "/api/v1/admin/volumes" ? { items: [{ id: "volume-1", number: 1, year: 2026, title: "Volume one", status: "open", issues: [{ id: "issue-1", number: "2", title: "Confirmed research issue", status: "draft" }] }] }
      : pathname === "/api/v1/admin/production-articles" ? { items: [{ id: "article-1", reference: "NSAJ-TEST-ARTICLE", title: "Confirmed article", status: "production", issue_id: null }] }
      : pathname.endsWith("/readiness") ? { ready: true, blockers: [] } : { ok: true };
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) });
  });
  await page.goto("/admin/publication?submissionReference=NSAJ-TEST-ARTICLE");
  await page.getByText("Assemble and publish an issue", { exact: true }).first().click();
  await expect(page.getByLabel("Production article")).toHaveValue("article-1");
  await page.getByRole("combobox", { name: "Issue", exact: true }).selectOption("issue-1");
  await expect(page.locator(".record-context")).toContainText("Confirmed research issue");
  await expect(page.locator(".record-context")).toContainText("Confirmed article");
  await expect(page.locator(".record-context")).not.toContainText("article-1");
  await page.screenshot({ path: testInfo.outputPath("publication-article-picker.png"), fullPage: true });
  await expect(page.getByRole("button", { name: "Publish issue", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Check readiness" }).click();
  await expect(page.getByRole("heading", { name: "Ready to publish" })).toBeVisible();
  await page.getByRole("button", { name: "Publish issue", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("Confirmed research issue");
  await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();
  expect(actions).toHaveLength(0);
  await page.getByRole("button", { name: "Publish issue", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Publish issue" }).click();
  await expect(page.locator(".task-feedback").getByRole("status")).toContainText("Confirmed research issue published");
  expect(actions).toEqual(["/api/v1/editorial/issues/issue-1/publish"]);
});
