import { expect, test, type Page, type Route } from "@playwright/test";

const demoMode = process.env.NSAJ_E2E_DEMO_CONTENT === "true";

const issue = {
  id: "issue-1",
  number: "1",
  title: "Published issue fixture",
  description: "A description from the published issue endpoint.",
  published_at: "2026-06-15T00:00:00Z",
  volume: { number: 1, year: 2026 },
  articles: [{ slug: "fixture-article", title: "Published article fixture", url: "/articles/fixture-article" }],
};

const call = {
  id: "call-1",
  title: "Approved call fixture",
  description: "Approved call description.",
  scope: "Approved call scope.",
  manuscript_types: ["original research"],
  instructions: "Instructions from the published call.",
  opens_at: null,
  deadline_at: "2026-12-01T00:00:00Z",
  time_zone: "UTC",
  status: "open",
};

const article = {
  slug: "fixture-article",
  manuscript_reference: "NSH-000123",
  title: "Published article fixture",
  abstract: "Abstract from the published article endpoint.",
  keywords: ["journal", "research"],
  manuscript_type: "original research",
  authors: [{ full_name: "Approved Author", affiliation: "Approved affiliation", orcid: null }],
  published_at: "2026-06-15T00:00:00Z",
  volume: { number: 1, year: 2026, title: "Volume one" },
  issue: { number: "1", title: "Published issue fixture" },
  doi: null,
  license: null,
  citation: "Approved Author. Published article fixture.",
  publication_notice: null,
  file_url: null,
};

async function mockPublicApi(page: Page, empty = false) {
  const items = empty ? [] : undefined;
  await page.route("**/api/v1/public/**", async (route: Route) => {
    const url = new URL(route.request().url());
    if (
      empty &&
      (url.pathname === "/api/v1/public/articles/demo-article" ||
        url.pathname.startsWith("/api/v1/public/pages/"))
    ) {
      await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Not found" }) });
      return;
    }
    let payload: unknown;
    switch (url.pathname) {
      case "/api/v1/public/issues":
        payload = { items: items ?? [issue] };
        break;
      case "/api/v1/public/calls-for-papers":
        payload = { items: items ?? [call] };
        break;
      case "/api/v1/public/announcements":
        payload = { items: items ?? [{ id: "announcement-1", title: "Published announcement fixture", body: "Approved announcement text.", published_at: "2026-06-15T00:00:00Z" }] };
        break;
      case "/api/v1/public/editorial-board":
        payload = { items: items ?? [{ id: "board-1", full_name: "Approved Board Member", role: "editor", qualifications: "Approved qualifications", department: "Approved department", institution: "Approved institution", country: "Approved country", specializations: [], biography: "Approved biography", professional_url: null, orcid: null }] };
        break;
      case "/api/v1/public/presentations":
        payload = { items: items ?? [{ id: "resource-1", title: "Approved resource fixture", presenter: "Approved presenter", resource_type: "presentation", summary: "Approved resource summary.", occurred_at: null, external_url: null, file_url: null }] };
        break;
      case "/api/v1/public/templates":
        payload = { items: items ?? [{ id: "template-1", title: "Approved template fixture", category: "manuscript", description: "Approved template description.", language: "English", version: "1", effective_at: null, file_type: "application/pdf", download_url: "/fixture.pdf" }] };
        break;
      case "/api/v1/public/search":
        payload = { items: items ?? [{ ...article, authors: [{ full_name: "Approved Author" }] }] };
        break;
      default:
        if (url.pathname.startsWith("/api/v1/public/articles/")) payload = article;
        else if (url.pathname.startsWith("/api/v1/public/pages/")) payload = { slug: "aims-and-scope", title: "Approved aims and scope", body: "Approved journal page content.", published_at: null };
        else payload = { items: [] };
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) });
  });
}

test("public routes share the journal shell and render published API content", async ({ page }) => {
  await mockPublicApi(page);
  const pages = [
    ["/", "Explore published research. Understand the publishing journey.", "Published issue fixture"],
    ["/issues", "Issues & archive", "Published issue fixture"],
    ["/editorial-board", "Journal editors", "Approved Board Member"],
    ["/calls-for-papers", "Calls for Papers", "Approved call fixture"],
    ["/presentations", "Journal resources", "Approved resource fixture"],
    ["/templates", "Templates and downloads", "Approved template fixture"],
    ["/articles/fixture-article", "Published article fixture", "Abstract from the published article endpoint."],
    ["/pages/aims-and-scope", "Approved aims and scope", "Approved journal page content."],
    ["/publishing-process", "The publishing process", "This preview outlines the planned manuscript journey."],
    ["/search?q=fixture", "Search articles", "Published article fixture"],
  ];

  for (const [path, heading, content] of pages) {
    await page.goto(path);
    await expect(page.locator('nav[aria-label="Public journal navigation"]')).toBeVisible();
    await expect(page.getByRole("heading", { name: heading, exact: true }).first()).toBeVisible();
    await expect(page.getByText(content, { exact: false }).first()).toBeVisible();
    await expect(page.locator(".demo-badge")).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Sign in", exact: true })).toBeVisible();
    await expect(page.getByRole("main")).toHaveAttribute("id", "main-content");
    await expect(page.locator("#main-content")).toHaveCount(1);
    await expect(page.getByText(/register/i)).toHaveCount(0);
    await expect(page.getByText(/submit manuscript/i)).toHaveCount(0);
    if (path === "/articles/fixture-article") {
      await expect(page.getByText("Paper ID: NSH-000123", { exact: true })).toBeVisible();
    }
  }

  await page.goto("/sign-in");
  await expect(page.locator('nav[aria-label="Public journal navigation"]')).toHaveCount(0);
});

test("homepage provides safe empty states for unpublished public data", async ({ page }) => {
  await mockPublicApi(page, true);
  await page.goto("/");
  if (demoMode) {
    await expect(page.getByText("Sample issue record — demo only")).toBeVisible();
    await expect(page.getByText("Sample Call for Papers — demo only")).toBeVisible();
    await expect(page.getByText("Sample journal announcement")).toBeVisible();
    await expect(page.getByText("No issue has been published yet.")).toHaveCount(0);
    await expect(page.getByText("ISSN: DEMO — NOT ISSUED")).toBeVisible();
  } else {
    await expect(page.getByText("No issue has been published yet.")).toBeVisible();
    await expect(page.getByText("No approved open calls are currently listed.")).toBeVisible();
    await expect(page.getByText("No announcements have been published.")).toBeVisible();
  }
  await expect(page.getByText(/peer reviewed|open access|global reach/i)).toHaveCount(0);
});

test("homepage offers reader and author paths, a process preview, and only published research links", async ({ page }) => {
  await mockPublicApi(page);
  await page.goto("/");

  await expect(page.getByRole("link", { name: "Explore published research" })).toHaveAttribute("href", "/issues");
  await expect(page.getByRole("link", { name: "For authors", exact: true })).toHaveAttribute("href", "/pages/author-guidelines");
  await expect(page.getByRole("heading", { name: "A manuscript’s path through the journal" })).toBeVisible();
  await expect(page.getByText("Submissions are not open through this site.", { exact: false })).toBeVisible();
  await expect(page.locator(".publication-journey--compact li")).toHaveCount(6);

  const articleLink = page.getByRole("link", { name: "Published article fixture", exact: true });
  await expect(articleLink).toHaveAttribute("href", "/articles/fixture-article");
  await expect(page.getByRole("link", { name: "Submit manuscript", exact: true })).toHaveCount(0);
});

test("publishing-process page explains preview status and editorial privacy", async ({ page }) => {
  await mockPublicApi(page);
  await page.goto("/publishing-process");

  await expect(page.getByRole("heading", { name: "The publishing process" })).toBeVisible();
  await expect(page.getByText(/Submissions are not open through this site/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "What is visible to the public?" })).toBeVisible();
  await expect(page.getByText(/reviewer reports, reviewer identities, and editorial records/)).toBeVisible();
  await expect(page.getByText(/Reviewer recommendations are kept separate from editorial decisions/)).toBeVisible();
});

test("public navigation groups content by visitor task", async ({ page }) => {
  await mockPublicApi(page);
  await page.goto("/");
  const navigation = page.locator(".public-navigation__links");

  await expect(navigation.getByText("Discover", { exact: true })).toBeVisible();
  await expect(navigation.getByText("For authors", { exact: true })).toBeVisible();
  await expect(navigation.getByText("Journal information", { exact: true })).toBeVisible();
  await navigation.locator(".public-navigation__group > summary").filter({ hasText: "For authors" }).click();
  await expect(navigation.getByRole("link", { name: "Publishing process" })).toHaveAttribute("href", "/publishing-process");
});

test("demo preview fills empty public sections with labeled samples", async ({ page }) => {
  test.skip(!demoMode, "Build with NSAJ_E2E_DEMO_CONTENT=true to check preview samples.");
  await mockPublicApi(page, true);

  const samples: Array<[string, string]> = [
    ["/editorial-board", "Sample Editor 01"],
    ["/issues", "Sample issue record — demo only"],
    ["/calls-for-papers", "Sample Call for Papers — demo only"],
    ["/presentations", "Sample research presentation"],
    ["/templates", "Sample manuscript template"],
    ["/search?q=sample", "Sample article record — demo only"],
    ["/articles/demo-article", "Sample article record — demo only"],
    ["/pages/about", "About the journal — demo content"],
  ];

  for (const [path, sample] of samples) {
    await page.goto(path);
    await expect(page.getByText(sample, { exact: false }).first()).toBeVisible();
    await expect(page.locator(".demo-badge").first()).toBeVisible();
    await expect(page.getByText("ISSN: DEMO — NOT ISSUED")).toBeVisible();
    await expect(page.getByText(/DEMO PREVIEW — Sample journal content/)).toBeVisible();
  }
});

test("demo preview keeps API errors visible instead of substituting samples", async ({ page }) => {
  test.skip(!demoMode, "Build with NSAJ_E2E_DEMO_CONTENT=true to check preview errors.");
  await mockPublicApi(page, true);
  await page.route("**/api/v1/public/editorial-board", async (route) => {
    await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Unavailable" }) });
  });

  await page.goto("/editorial-board");
  await expect(page.locator(".error-message")).toContainText("The editorial board could not be loaded.");
  await expect(page.getByText("Sample Editor 01")).toHaveCount(0);
});

test("header search carries q to the search route and published search endpoint", async ({ page }) => {
  await mockPublicApi(page);
  let apiQuery = "";
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname === "/api/v1/public/search") apiQuery = url.searchParams.get("q") ?? "";
  });

  await page.goto("/");
  await page.getByLabel("Search published articles").fill("climate systems");
  await page.getByRole("button", { name: "Search", exact: true }).first().click();
  await expect(page).toHaveURL(/\/search\?q=climate(?:\+|%20)systems/);
  await expect(page.getByRole("heading", { name: "Published article fixture" })).toBeVisible();
  await expect.poll(() => apiQuery).toBe("climate systems");
});

test("public layout stays within desktop, tablet, and mobile widths with a keyboard menu", async ({ page }) => {
  await mockPublicApi(page, true);
  for (const width of [1440, 1280, 1024, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Explore published research. Understand the publishing journey." })).toBeVisible();
    const dimensions = await page.evaluate(() => ({
      document: document.documentElement.scrollWidth,
      viewport: document.documentElement.clientWidth,
    }));
    expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport);
    if (width <= 850) {
      const menu = page.locator(".public-navigation__mobile > summary");
      await menu.focus();
      await page.keyboard.press("Enter");
      const firstGroup = page.locator(".public-navigation__mobile-panel .public-navigation__group > summary").first();
      await expect(firstGroup).toBeVisible();
      await firstGroup.focus();
      await page.keyboard.press("Enter");
      const firstMenuLink = page.locator(".public-navigation__mobile-panel .public-navigation__group[open] .public-navigation__group-panel a").first();
      await expect(firstMenuLink).toBeVisible();
      await page.keyboard.press("Tab");
      await expect(firstMenuLink).toBeFocused();
    }
  }
});

test("public reading precedes the footer and the skip link focuses the main landmark", async ({ page }) => {
  await mockPublicApi(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/pages/aims-and-scope");
  await page.locator(".skip-link").focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("main")).toBeFocused();
  const order = await page.evaluate(() => {
    const main = document.querySelector("main");
    const footer = document.querySelector(".public-footer");
    return Boolean(main && footer && (main.compareDocumentPosition(footer) & Node.DOCUMENT_POSITION_FOLLOWING));
  });
  expect(order).toBe(true);
  await page.locator(".public-navigation__mobile > summary").click();
  await page.locator(".public-navigation__mobile-panel .public-navigation__group > summary").filter({ hasText: "For authors" }).click();
  const activeLink = page.locator('.public-navigation__mobile-panel a[aria-current="page"]');
  await expect(activeLink).toBeVisible();
  await expect(activeLink).toHaveText("Aims & scope");
});

test("call deadlines use the configured zone on the call page and homepage", async ({ browser }) => {
  const context = await browser.newContext({ baseURL: test.info().project.use.baseURL, timezoneId: "America/Los_Angeles", locale: "en-GB" });
  const page = await context.newPage();
  await mockPublicApi(page);
  await page.route("**/api/v1/public/calls-for-papers", async (route) => {
    await route.fulfill({ json: { items: [{ ...call, time_zone: "Asia/Kolkata" }] } });
  });
  for (const path of ["/calls-for-papers", "/"]) {
    await page.goto(path);
    const deadline = page.locator('time[datetime="2026-12-01T00:00:00Z"]');
    await expect(deadline).toContainText("05:30");
    await expect(deadline).toContainText("Asia/Kolkata");
    await expect(deadline).toContainText("GMT+5:30");
  }
  await context.close();
});

test("invalid call zones fall back visibly to UTC without mislabeling local time", async ({ page }) => {
  await mockPublicApi(page);
  await page.route("**/api/v1/public/calls-for-papers", async (route) => {
    await route.fulfill({ json: { items: [{ ...call, time_zone: "Invalid/Time_Zone" }] } });
  });
  await page.goto("/calls-for-papers");
  await expect(page.locator(".public-call__deadline")).toContainText("UTC; configured time zone unavailable");
  await expect(page.locator(".public-call__deadline")).not.toContainText("Invalid/Time_Zone");
});

test("search shows one search form, the query, and the loaded result count", async ({ page }) => {
  await mockPublicApi(page);
  await page.goto("/search?q=fixture");
  await expect(page.getByRole("search")).toHaveCount(1);
  await expect(page.getByLabel("Title, author, abstract, or keyword")).toHaveValue("fixture");
  await expect(page.locator(".public-result-summary")).toHaveText('1 result shown for "fixture".');
  await page.goto("/search");
  await expect(page.getByText("Search published research by title, author, topic, or keyword.")).toBeVisible();
});

test("resources use document names and friendly formats, and public reads can retry", async ({ page }) => {
  await mockPublicApi(page);
  await page.goto("/templates");
  await expect(page.getByRole("link", { name: "Download Approved template fixture" })).toHaveAttribute("href", "/fixture.pdf");
  await expect(page.locator(".public-resource-row")).toContainText("PDF");
  let attempts = 0;
  await page.route("**/api/v1/public/editorial-board", async (route) => {
    attempts += 1;
    await route.fulfill(attempts === 1
      ? { status: 503, json: { detail: "Unavailable" } }
      : { json: { items: [{ id: "board-1", full_name: "Approved Board Member", role: "editor_in_chief" }] } });
  });
  await page.goto("/editorial-board");
  await expect(page.getByRole("main").getByRole("alert")).toContainText("The editorial board could not be loaded.");
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("heading", { name: "Approved Board Member" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Editor In Chief" })).toBeVisible();
});

test("all public page types reflow with long content at a narrow width", async ({ page }) => {
  await mockPublicApi(page);
  await page.route("**/api/v1/public/articles/fixture-article", async (route) => {
    await route.fulfill({ json: {
      ...article,
      title: "Long research title with detailed scientific context ".repeat(8),
      abstract: article.abstract.repeat(30),
      authors: [{ full_name: "Author".repeat(40), affiliation: "Institution".repeat(40), orcid: null }],
      citation: "Citation details ".repeat(100),
      doi: `10.0000/${"longidentifier".repeat(20)}`,
    } });
  });
  await page.setViewportSize({ width: 320, height: 900 });
  const paths = ["/issues", "/articles/fixture-article", "/search?q=fixture", "/calls-for-papers", "/editorial-board", "/templates", "/presentations", "/pages/aims-and-scope"];
  for (const path of paths) {
    await page.goto(path);
    await expect(page.getByRole("main")).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    const dimensions = await page.evaluate(() => ({ document: document.documentElement.scrollWidth, viewport: document.documentElement.clientWidth }));
    expect(dimensions.document, path).toBeLessThanOrEqual(dimensions.viewport);
  }
});
