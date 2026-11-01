import { expect, test } from "@playwright/test";

test("password recovery guards pending completion and shows a terminal success", async ({ page }) => {
  let completeRequests = 0;
  let finish: (() => void) | undefined;
  const gate = new Promise<void>((resolve) => { finish = resolve; });
  await page.route("**/api/v1/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === "/api/v1/auth/recovery/complete") {
      completeRequests += 1;
      await gate;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(pathname.endsWith("/csrf") ? { csrf_token: "test" } : { ok: true }) });
  });
  await page.goto("/recover#token=recovery-token");
  await page.getByLabel("New password").fill("a new secure password 2026");
  await page.getByRole("button", { name: "Update password" }).click();
  await expect(page.getByRole("button", { name: "Updating password" })).toBeDisabled();
  await expect.poll(() => completeRequests).toBe(1);
  finish?.();
  await expect(page.getByRole("heading", { name: "Password updated" })).toBeVisible();
  await expect(page.getByLabel("New password")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Sign in with your new password" })).toBeVisible();
  await expect(page).toHaveURL(/\/recover$/);
});

test("recovery preserves failed entries and links validation to the field", async ({ page }) => {
  await page.route("**/api/v1/**", (route) => route.fulfill({
    status: route.request().url().includes("recovery/complete") ? 422 : 200,
    contentType: "application/json",
    body: JSON.stringify(route.request().url().includes("recovery/complete") ? { detail: [{ loc: ["body", "password"], msg: "Choose another password." }] } : { csrf_token: "test" }),
  }));
  await page.goto("/recover#token=recovery-token");
  await page.getByLabel("New password").fill("a new secure password 2026");
  await page.getByRole("button", { name: "Update password" }).click();
  await expect(page.getByLabel("New password")).toHaveValue("a new secure password 2026");
  await expect(page.getByLabel("New password")).toHaveAttribute("aria-invalid", "true");
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Choose another password.");
});

test("missing invitations explain the email link without development instructions", async ({ page }) => {
  await page.goto("/accept-invitation");
  await expect(page.getByRole("button", { name: "Create account" })).toBeDisabled();
  await expect(page.getByText("Open the invitation link sent to your email.", { exact: false })).toBeVisible();
  await expect(page.getByText("local development mail capture", { exact: false })).toHaveCount(0);
});
