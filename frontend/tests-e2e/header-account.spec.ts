import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

for (const width of [1440, 320]) {
  test(`top-right logout revokes the session at ${width}px`, async ({ page, request }) => {
    const email = `logout-${randomUUID()}@example.test`;
    const password = "a secure logout test password 2026";
    const seed = await request.post("http://127.0.0.1:8123/__test__/seed-user", {
      data: { email, password, role: "author" },
    });
    expect(seed.ok()).toBeTruthy();
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/sign-in");
    await page.getByRole("textbox", { name: "Email", exact: true }).fill(email);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page).toHaveURL(/\/author$/);

    const header = page.locator(".brand-header");
    const logout = header.getByRole("button", { name: "Log out", exact: true });
    await expect(logout).toBeVisible();
    const position = await logout.boundingBox();
    expect(position).not.toBeNull();
    expect(position!.x + position!.width / 2).toBeGreaterThan(width / 2);
    expect(position!.y).toBeLessThan(100);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);

    const cookies = await page.context().cookies();
    const session = cookies.find(cookie => cookie.name === "nsaj_session");
    const csrf = cookies.find(cookie => cookie.name === "nsaj_csrf");
    expect(session).toBeDefined();
    expect(csrf).toBeDefined();
    // A forged logout cannot revoke the active session without its CSRF token.
    const forged = await page.context().request.post("/api/v1/auth/logout");
    expect(forged.status()).toBe(403);
    expect((await page.context().request.get("/api/v1/auth/me")).status()).toBe(200);

    // The account control is also available when an authenticated author visits
    // the public journal, rather than displaying a contradictory Sign in link.
    await header.getByRole("link", { name: "NSAJ journal home", exact: true }).click();
    await expect(page).toHaveURL("/");
    await expect(logout).toBeVisible();
    await expect(header.getByRole("link", { name: "Sign in", exact: true })).toHaveCount(0);
    const logoutRequest = page.waitForRequest(req => req.url().endsWith("/api/v1/auth/logout"));
    await logout.click();
    const sent = await logoutRequest;
    expect(sent.method()).toBe("POST");
    expect(sent.headers()["x-csrf-token"]).toBe(csrf!.value);
    await expect(page).toHaveURL(/\/sign-in$/);
    await expect(header.getByRole("link", { name: "Sign in", exact: true })).toBeVisible();
    await expect(logout).toHaveCount(0);
    expect((await page.context().cookies()).some(cookie => cookie.name === "nsaj_session")).toBe(false);
    expect((await page.context().request.get("/api/v1/author/submissions")).status()).toBe(401);
    // Replaying the old cookie proves server revocation, independently of the UI
    // removing its local cookie.
    const replay = await request.get("http://127.0.0.1:3123/api/v1/auth/me", {
      headers: { Cookie: `nsaj_session=${session!.value}` },
    });
    expect(replay.status()).toBe(401);
  });
}

test("logout prevents duplicate requests and reports a failed attempt", async ({ page }) => {
  let requests = 0;
  let finish: (() => void) | undefined;
  const gate = new Promise<void>(resolve => { finish = resolve; });
  await page.route("**/api/v1/auth/me", route => route.fulfill({ json: { id: "member", authenticated: true, roles: ["author"] } }));
  await page.route("**/api/v1/auth/logout", async route => {
    requests += 1;
    await gate;
    await route.fulfill({ status: 503, json: { detail: "Temporarily unavailable." } });
  });
  await page.setViewportSize({ width: 320, height: 1000 });
  await page.goto("/");
  const header = page.locator(".brand-header");
  await header.getByRole("button", { name: "Log out", exact: true }).click();
  await expect(header.getByRole("button", { name: "Logging out...", exact: true })).toBeDisabled();
  await expect.poll(() => requests).toBe(1);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  finish?.();
  await expect(header.getByRole("alert")).toHaveText("Could not log out. Please try again.");
  await expect(header.getByRole("button", { name: "Log out", exact: true })).toBeEnabled();
  await expect(page).toHaveURL("/");
});

test("logout lets an author keep unsaved draft changes", async ({ page }) => {
  let logoutRequests = 0;
  await page.route("**/api/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/auth/me") return route.fulfill({ json: { id: "author", display_name: "Student", roles: ["author"] } });
    if (path === "/api/v1/auth/logout") { logoutRequests += 1; return route.fulfill({ json: { ok: true } }); }
    if (path === "/api/v1/author/submission-checklist") return route.fulfill({ json: { checklist: null } });
    return route.fulfill({ json: { items: [] } });
  });
  await page.goto("/author");
  await page.getByRole("button", { name: "New draft", exact: true }).click();
  await page.getByLabel("Manuscript title").fill("Unsaved paper title");
  page.once("dialog", dialog => dialog.dismiss());
  await page.locator(".brand-header").getByRole("button", { name: "Log out", exact: true }).click();
  expect(logoutRequests).toBe(0);
  await expect(page.getByLabel("Manuscript title")).toHaveValue("Unsaved paper title");
  await expect(page).toHaveURL(/\/author$/);
  page.once("dialog", dialog => dialog.accept());
  await page.locator(".brand-header").getByRole("button", { name: "Log out", exact: true }).click();
  await expect(page).toHaveURL(/\/sign-in$/);
  expect(logoutRequests).toBe(1);
});
