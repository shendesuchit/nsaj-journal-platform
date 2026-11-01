import { expect, test, type Page, type Route } from "@playwright/test";

type PageItem = {
  id: string;
  slug: string;
  title: string;
  status: string;
  version: number;
  updated_at: string;
};

async function mockContentAdmin(page: Page) {
  let pages: PageItem[] = [];
  let userRoles = ["editor_in_chief"];
  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    let payload: unknown = { items: [] };
    let status = 200;

    switch (url.pathname) {
      case "/api/v1/auth/me":
        payload = { id: "admin-1", roles: ["site_admin"] };
        break;
      case "/api/v1/admin/pages":
        if (request.method() === "POST") {
          const body = request.postDataJSON() as { slug: string; title: string };
          pages = [{
            id: "page-1",
            slug: body.slug,
            title: body.title,
            status: "draft",
            version: 1,
            updated_at: "2026-10-23T00:00:00Z",
          }];
          payload = { id: "page-1", slug: body.slug, status: "draft", version: 1 };
          status = 201;
        } else {
          payload = { items: pages };
        }
        break;
      case "/api/v1/admin/calls-for-papers":
        payload = { items: [{ id: "call-1", title: "Research call", status: "open", opens_at: null, deadline_at: null, time_zone: "UTC" }] };
        break;
      case "/api/v1/admin/announcements":
        payload = { items: [{ id: "announcement-1", title: "Journal notice", status: "published", publish_at: null, published_at: "2026-10-22T00:00:00Z" }] };
        break;
      case "/api/v1/admin/templates":
        payload = { items: [{ id: "template-1", title: "Author template", category: "manuscript", status: "draft", scan_status: "clean" }] };
        break;
      case "/api/v1/admin/board":
        payload = { items: [{ id: "board-1", full_name: "Board member", role: "board_member", is_active: true, identity_verified: false, qualification_verified: false, affiliation_verified: false, appointment_confirmed: false, consent_status: "pending", public_approved: false }] };
        break;
      case "/api/v1/admin/presentations":
        payload = { items: [{ id: "resource-1", title: "Research seminar", resource_type: "presentation", status: "draft", occurred_at: null, has_external_url: true, scan_status: null }] };
        break;
      case "/api/v1/admin/users":
        payload = { items: [{ id: "user-1", email: "editor@example.test", display_name: "Journal Editor", roles: userRoles, is_active: true }] };
        break;
      case "/api/v1/admin/users/user-1/roles":
        userRoles = (request.postDataJSON() as { roles: string[] }).roles;
        payload = { roles: userRoles };
        break;
      case "/api/v1/invitations":
        payload = { ok: true, message: "Invitation saved to the local development mail capture." };
        break;
      default:
        if (request.method() !== "GET") payload = { id: "saved-item", status: "draft" };
    }

    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(payload) });
  });
}

test("content overview shows persisted statuses and opens one editor at a time", async ({ page }) => {
  await mockContentAdmin(page);
  await page.goto("/admin/content");

  await expect(page.getByRole("heading", { name: "Content overview" })).toBeVisible();
  await expect(page.getByText("1 open · 0 scheduled · 0 drafts")).toBeVisible();
  await expect(page.locator(".admin-work-panel")).toHaveCount(0);

  await page.locator(".admin-rail__item").filter({ hasText: "Public pages" }).click();
  await expect(page.getByRole("heading", { name: "Public pages", exact: true })).toBeVisible();
  await expect(page.getByText("No public pages have been saved yet.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Calls for Papers", exact: true })).toHaveCount(0);

  await page.getByLabel("Stable URL slug").fill("about-journal");
  await page.getByLabel("Title", { exact: true }).fill("About the journal");
  await page.getByLabel("Approved page text").fill("Approved public information.");
  await page.getByRole("button", { name: "Save draft page" }).click();
  await expect(page.getByText("About the journal", { exact: true })).toBeVisible();
  await expect(page.getByText("draft", { exact: true })).toBeVisible();
});

test("site admin can assign a role to an existing account", async ({ page }) => {
  await mockContentAdmin(page);
  await page.goto("/admin/content");
  await page.locator(".admin-rail__item").filter({ hasText: "Accounts" }).click();

  const account = page.locator(".admin-record").filter({ hasText: "editor@example.test" });
  await account.locator("summary").click();
  await account.getByRole("checkbox", { name: "Author" }).check();
  await account.getByRole("button", { name: "Save role changes" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Save role changes" }).click();

  await expect(page.locator(".task-feedback").getByRole("status")).toContainText("Roles updated for editor@example.test");
  await expect(account.locator(".admin-record__main")).toContainText("editor_in_chief, author");
});

test("author invitation displays the actual delivery status", async ({ page }) => {
  await mockContentAdmin(page);
  await page.goto("/admin/content?section=accounts");
  await page.getByLabel("Email", { exact: true }).fill("student@example.test");
  await page.getByLabel("Display name", { exact: true }).fill("Student Author");
  await page.getByLabel("Role", { exact: true }).selectOption("author");
  const created = page.waitForRequest(request => request.url().endsWith("/api/v1/invitations") && request.method() === "POST");
  await page.getByRole("button", { name: "Send invitation", exact: true }).click();
  expect((await created).postDataJSON()).toEqual({ email: "student@example.test", display_name: "Student Author", role: "author" });
  await expect(page.locator(".task-feedback").getByRole("status")).toHaveText("Invitation saved to the local development mail capture.");
  await expect(page.getByText("Invitation sent.", { exact: false })).toHaveCount(0);
});

test("content navigation fits desktop, tablet, and mobile widths", async ({ page }) => {
  await mockContentAdmin(page);
  for (const width of [1440, 768, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/admin/content");
    await expect(page.getByRole("heading", { name: "Content overview" })).toBeVisible();
    const dimensions = await page.evaluate(() => ({
      document: document.documentElement.scrollWidth,
      viewport: document.documentElement.clientWidth,
    }));
    expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport);
    if (width <= 850) {
      await expect(page.locator(".admin-rail")).toBeHidden();
      const sectionMenu = page.getByLabel("Content section");
      await expect(sectionMenu).toBeVisible();
      await sectionMenu.selectOption("calls");
      await expect(page.getByRole("heading", { name: "Calls for Papers", exact: true })).toBeVisible();
    } else {
      await expect(page.locator(".admin-rail")).toBeVisible();
    }
  }
});


test("content service errors remain in the workspace and allow retry", async ({ page }) => {
  let failed = true;
  await mockContentAdmin(page);
  await page.route("**/api/v1/admin/pages", (route) => route.fulfill({
    status: failed ? 503 : 200, contentType: "application/json", body: JSON.stringify(failed ? { detail: "Service unavailable" } : { items: [] }),
  }));
  await page.goto("/admin/content");
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Content status could not be loaded");
  await expect(page).toHaveURL(/\/admin\/content$/);
  failed = false;
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("heading", { name: "Content overview" })).toBeVisible();
});

test("board verification uses the selected person and protects unsaved entries", async ({ page }) => {
  await mockContentAdmin(page);
  await page.route("**/api/v1/admin/board", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [
    { id: "person-a", full_name: "Person Alpha", role: "board_member", is_active: true, identity_verified: true, qualification_verified: false, affiliation_verified: true, appointment_confirmed: true, consent_status: "granted", public_approved: false },
    { id: "person-b", full_name: "Person Beta", role: "board_member", is_active: true, identity_verified: false, qualification_verified: true, affiliation_verified: false, appointment_confirmed: false, consent_status: "pending", public_approved: false },
  ] }) }));
  await page.goto("/admin/content?section=board");
  await page.getByRole("combobox", { name: "Profile", exact: true }).selectOption("person-a");
  await expect(page.getByRole("heading", { name: "Person Alpha", exact: true })).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Identity checked" })).toBeChecked();
  await page.getByLabel("Consent evidence reference").fill("alpha-evidence");
  await page.getByRole("combobox", { name: "Profile", exact: true }).selectOption("person-b");
  await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByRole("combobox", { name: "Profile", exact: true })).toHaveValue("person-a");
  await expect(page.getByLabel("Consent evidence reference")).toHaveValue("alpha-evidence");
  await page.getByRole("combobox", { name: "Profile", exact: true }).selectOption("person-b");
  await page.getByRole("dialog").getByRole("button", { name: "Discard changes" }).click();
  await expect(page.getByRole("heading", { name: "Person Beta", exact: true })).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Identity checked" })).not.toBeChecked();
  await expect(page.getByRole("checkbox", { name: "Qualifications checked" })).toBeChecked();
  await expect(page.getByRole("combobox", { name: "Consent status", exact: true })).toHaveValue("pending");
  await expect(page.getByLabel("Consent evidence reference")).toHaveValue("");
  await page.locator(".admin-rail__item").filter({ hasText: "Public pages" }).click();
  await expect(page).toHaveURL(/section=pages/);
});
