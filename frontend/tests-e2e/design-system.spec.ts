import { expect, test } from "@playwright/test";

test("server field validation remains understandable in the redesigned sign-in form", async ({ page }) => {
  await page.route("**/api/v1/auth/csrf", route => route.fulfill({ json: { csrf_token: "test-token" } }));
  await page.route("**/api/v1/auth/login", route => route.fulfill({ status: 422, json: { detail: [{ loc: ["body", "email"], msg: "Enter a valid email address" }] } }));
  await page.goto("/sign-in");
  await page.getByRole("textbox", { name: "Email", exact: true }).fill("author@example.test");
  await page.locator('input[autocomplete="current-password"]').fill("example password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Enter a valid email address");
  await expect(page.getByText("[object Object]", { exact: false })).toHaveCount(0);
});

test("workspace navigation presents existing role access without granting editorial access to Site Admin", async ({ page }) => {
  await page.route("**/api/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    return route.fulfill({ json: path.endsWith("/auth/me") ? { id: "test-admin", authenticated: true, display_name: "Administrator", roles: ["site_admin", "author", "editor_in_chief"] } : { items: [] } });
  });
  await page.goto("/admin/content");
  const nav = page.getByRole("navigation", { name: "Your workspaces" });
  await expect(nav.getByRole("link", { name: "My manuscripts" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Publication", exact: true })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Editorial cases" })).toHaveCount(0);
  await expect(nav.getByRole("link", { name: "Journal administration" })).toHaveAttribute("aria-current", "page");
});

test("unsaved manuscript edits survive cancelled links and browser Back navigation", async ({ page }) => {
  await page.route("**/api/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    return route.fulfill({ json: path.endsWith("/auth/me") ? { id: "member", authenticated: true, display_name: "Member", roles: ["site_admin", "author"] } : path.endsWith("/author/submission-checklist") ? { checklist: null } : { items: [] } });
  });
  await page.goto("/admin/content");
  await page.getByRole("navigation", { name: "Your workspaces" }).getByRole("link", { name: "My manuscripts" }).click();
  await page.getByLabel("Manuscript title").fill("Unsaved research title");
  page.once("dialog", dialog => dialog.dismiss());
  await page.locator(".brand-header").getByRole("link", { name: "View public site" }).click();
  await expect(page).toHaveURL(/\/author$/);
  page.once("dialog", dialog => dialog.dismiss());
  await page.evaluate(() => window.history.back());
  await expect(page.getByLabel("Manuscript title")).toHaveValue("Unsaved research title");
  await expect(page).toHaveURL(/\/author$/);
  page.once("dialog", dialog => dialog.accept());
  await page.evaluate(() => window.history.back());
  await expect(page).toHaveURL(/\/admin\/content$/);
});

for (const width of [1440, 768, 390, 320]) {
test(`every route has one focusable main and reflows at ${width}px`, async ({ page }, testInfo) => {
  test.setTimeout(90_000);
  let roles = ["author"];
  const article = { slug: "design-fixture", title: "A research title that remains readable across desktop and mobile layouts", abstract: "A published abstract used for interface review. This is isolated browser test data.", keywords: ["research"], manuscript_type: "original research", authors: [{ full_name: "Test Author", affiliation: "Test Institute", orcid: null }], published_at: "2026-06-15T00:00:00Z", volume: { number: 1, year: 2026, title: "Volume one" }, issue: { number: "1", title: "Research issue" }, citation: "Test Author. Research title.", doi: null, license: null, publication_notice: null, file_url: null };
  const issue = { id: "issue-1", number: "1", title: "Research issue", description: "Published browser fixture", published_at: "2026-06-15T00:00:00Z", volume: { number: 1, year: 2026 }, articles: [{ slug: article.slug, title: article.title, url: `/articles/${article.slug}` }] };
  await page.route("**/api/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    let json: unknown = { items: [] };
    if (path.endsWith("/auth/me")) json = { id: "test-user", display_name: "Journal member", authenticated: true, roles };
    else if (path.includes("/public/articles/")) json = article;
    else if (path.includes("/public/pages/")) json = { slug: "author-guidelines", title: "Author guidelines", body: "Approved guidance appears here.\n\nThis is isolated browser test data.", published_at: null };
    else if (path === "/api/v1/public/issues") json = { items: [issue] };
    else if (path === "/api/v1/public/search") json = { items: [article] };
    else if (path.endsWith("/author/submission-checklist")) json = { checklist: null };
    return route.fulfill({ json });
  });
  const routes = ["/", "/issues", "/articles/design-fixture", "/search?q=research", "/calls-for-papers", "/editorial-board", "/templates", "/presentations", "/pages/author-guidelines", "/publishing-process", "/sign-in", "/recover", "/accept-invitation", "/author", "/reviewer", "/editorial", "/editorial/checklist", "/admin/content", "/admin/publication"];
    await page.setViewportSize({ width, height: 1000 });
    for (const path of routes) {
      roles = path.startsWith("/admin/content") ? ["site_admin"] : path.startsWith("/editorial") || path.startsWith("/admin/publication") ? ["editor_in_chief"] : path === "/reviewer" ? ["reviewer"] : ["author"];
      console.info(`Layout review ${width}px: ${path}`);
      await page.goto(path, {timeout:15_000});
      const main = page.locator("main#main-content");
      await expect(main).toHaveCount(1);
      await expect(main).toHaveAttribute("tabindex", "-1");
      await expect(main.getByRole("heading", { level: 1 })).toBeVisible();
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), { message: `${path} overflows at ${width}px` }).toBe(true);
      if ([1440, 390].includes(width) && ["/", "/articles/design-fixture", "/author", "/reviewer", "/editorial", "/sign-in", "/admin/content", "/admin/publication"].includes(path)) {
        await page.screenshot({ path: testInfo.outputPath(`${path.replace(/\W+/g, "-") || "home"}-${width}.png`), fullPage: true });
      }
    }
});
}
