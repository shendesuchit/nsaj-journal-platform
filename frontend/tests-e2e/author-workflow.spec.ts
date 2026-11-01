import { createHmac, randomUUID } from "node:crypto";
import { mkdir, open, readFile, readdir, rm } from "node:fs/promises";
import path from "node:path";

import { expect, test } from "@playwright/test";

const password = "test author password 2026";
const updatedPassword = "new author password 2026";
const runId = process.env.NSAJ_E2E_RUN_ID ?? "missing-run-id";
const repoRoot = path.resolve(process.cwd(), "..");
const mailDirectory = path.join(repoRoot, ".local", `e2e-${runId}`, "mail");
const testDataDirectory = path.resolve(repoRoot, ".local", `e2e-${runId}`);
const localDataRoot = path.resolve(repoRoot, ".local");

test.afterAll(async () => {
  if (
    path.dirname(testDataDirectory) === localDataRoot &&
    /^e2e-[0-9a-f-]{36}$/i.test(path.basename(testDataDirectory))
  ) {
    await rm(testDataDirectory, { recursive: true, force: true });
  }
});

function decodeBase32(value: string): Buffer {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const character of value.replace(/=+$/, "").toUpperCase()) {
    const index = alphabet.indexOf(character);
    if (index < 0) throw new Error("Invalid test MFA secret.");
    bits += index.toString(2).padStart(5, "0");
  }
  const bytes: number[] = [];
  for (let offset = 0; offset + 8 <= bits.length; offset += 8) {
    bytes.push(Number.parseInt(bits.slice(offset, offset + 8), 2));
  }
  return Buffer.from(bytes);
}

function authenticatorCode(secret: string): string {
  const counter = BigInt(Math.floor(Date.now() / 30_000));
  const message = Buffer.alloc(8);
  message.writeBigUInt64BE(counter);
  const digest = createHmac("sha1", decodeBase32(secret)).update(message).digest();
  const offset = digest[digest.length - 1] & 0x0f;
  const number = (digest.readUInt32BE(offset) & 0x7fffffff) % 1_000_000;
  return number.toString().padStart(6, "0");
}

async function capturedMessage(recipient: string, subject: string) {
  const names = await readdir(mailDirectory);
  for (const name of names) {
    const value = JSON.parse(
      await readFile(path.join(mailDirectory, name), "utf8"),
    ) as { to: string; subject: string; link: string };
    if (value.to === recipient && value.subject === subject) return value;
  }
  throw new Error("Expected message was not found in the local mail capture.");
}

test("author workspace explains when an account lacks the Author role", async ({ page }) => {
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ authenticated: true, display_name: "Reviewer", roles: ["reviewer"] }),
  }));

  await page.goto("/author");

  await expect(page.getByRole("heading", { name: "Author access required" })).toBeVisible();
  await expect(page.locator(".error-message")).toContainText("Ask a Site Admin to assign it");
  await expect(page.getByRole("button", { name: "Save draft" })).toHaveCount(0);
  await expect(page).toHaveURL(/\/author$/);
});

test("author workspace closes when the server revokes Author access", async ({ page }) => {
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ authenticated: true, display_name: "Test Author", roles: ["author"] }),
  }));
  await page.route("**/api/v1/author/submissions", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [] }),
      });
    }
    return route.fulfill({
      status: 403,
      contentType: "application/json",
      body: JSON.stringify({ detail: "An Author role is required." }),
    });
  });

  await page.goto("/author");
  await expect(page.getByRole("heading", { name: "Welcome, Test Author" })).toBeVisible();
  await page.getByLabel("Manuscript title").fill("A draft after access changed");
  await page.getByRole("button", { name: "Save draft" }).click();

  await expect(page.getByRole("heading", { name: "Author access required" })).toBeVisible();
  await expect(page.locator(".error-message")).toContainText("Ask a Site Admin to assign it");
  await expect(page.getByRole("button", { name: "Save draft" })).toHaveCount(0);
});

test("invitation, MFA, recovery, draft upload, and author isolation", async ({
  page,
  browser,
  request,
}) => {
  test.setTimeout(180_000);
  const adminEmail = `admin-${randomUUID()}@example.test`;
  const authorEmail = `author-${randomUUID()}@example.test`;
  const otherEmail = `other-${randomUUID()}@example.test`;

  const adminSeed = await request.post("http://127.0.0.1:8123/__test__/seed-user", {
    data: { email: adminEmail, password, role: "site_admin" },
  });
  expect(adminSeed.ok()).toBeTruthy();
  const admin = (await adminSeed.json()) as { mfa_secret: string };
  const csrfProbe = await request.get("http://127.0.0.1:3123/api/v1/auth/csrf");
  expect(csrfProbe.status()).toBe(200);

  page.on("requestfailed", (failed) => {
    console.error("Browser request failed", failed.url(), failed.failure()?.errorText);
  });
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill(adminEmail);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Verify your identity" })).toBeVisible();
  await page.getByLabel("Authenticator or recovery code").fill(authenticatorCode(admin.mfa_secret));
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page).toHaveURL(/\/admin\/content$/);

  const csrfCookie = (await page.context().cookies()).find((cookie) => cookie.name === "nsaj_csrf");
  expect(csrfCookie).toBeDefined();
  const invitation = await page.context().request.post("http://127.0.0.1:3123/api/v1/invitations", {
    headers: { "X-CSRF-Token": csrfCookie?.value ?? "" },
    data: { email: authorEmail, display_name: "Invited Author", role: "author" },
  });
  expect(invitation.ok()).toBeTruthy();

  const inviteMessage = await capturedMessage(authorEmail, "NSAJ account invitation");
  await page.goto(inviteMessage.link);
  await page.getByLabel("Create password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: /Welcome/ })).toBeVisible();
  await expect(page.getByText(/does not submit a manuscript for editorial review/i)).toBeVisible();
  await page.getByRole("button", { name: "New draft" }).click();
  await page.getByLabel("Manuscript title").fill("A private draft for testing");
  await page.getByLabel("Manuscript type").selectOption("original research");
  await page.getByLabel("Abstract").fill("Draft abstract content.");
  await page.getByLabel("Keywords, separated by commas").fill("science, testing");
  await page.getByLabel("Author 1 name").fill("Invited Author");
  await page.getByLabel("Affiliation", { exact: true }).fill("Research Institute");
  const draftCreated = page.waitForResponse((response) => response.url().endsWith("/api/v1/author/submissions") && response.request().method() === "POST");
  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(page.getByRole("status")).toContainText("not been submitted for editorial review");
  const createdDraft = await (await draftCreated).json() as { reference: string };
  expect(createdDraft.reference).toMatch(/^NSH-\d{6,}$/);
  await expect(page.locator(".draft-editor").first().locator(".work-meta")).toHaveText(`Paper ID: ${createdDraft.reference} / Draft`);

  const pdf = Buffer.from("%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n");
  await page.locator('input[type="file"]').setInputFiles({
    name: "private-paper.pdf",
    mimeType: "application/pdf",
    buffer: pdf,
  });
  await expect(page.getByRole("status")).toContainText("passed malware scanning");
  await expect(page.getByText(/private-paper\.pdf.*clean/i)).toBeVisible();

  await page.locator('input[type="file"]').setInputFiles({
    name: "not-a-manuscript.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("not a manuscript"),
  });
  await expect(page.locator(".error-message")).toContainText(
    "Only PDF and DOCX files are accepted",
  );

  await mkdir(testDataDirectory, { recursive: true });
  const oversizedPath = path.join(testDataDirectory, "oversized.pdf");
  const oversizedFile = await open(oversizedPath, "w");
  await oversizedFile.truncate(50 * 1024 * 1024 + 1);
  await oversizedFile.close();
  await page.locator('input[type="file"]').setInputFiles(oversizedPath);
  await expect(page.locator(".error-message")).toContainText(
    "File exceeds the 50 MB limit",
    { timeout: 120_000 },
  );

  const draft = await page.context().request.get("http://127.0.0.1:3123/api/v1/author/submissions");
  expect(draft.ok()).toBeTruthy();
  const items = (await draft.json()) as { items: Array<{ id: string; reference: string; files: Array<{ id: string }> }> };
  const savedDraft = items.items[0];
  expect(savedDraft).toBeDefined();
  expect(savedDraft.reference).toBe(createdDraft.reference);
  expect(savedDraft.files.length).toBe(1);

  const otherSeed = await request.post("http://127.0.0.1:8123/__test__/seed-user", {
    data: { email: otherEmail, password, role: "author" },
  });
  expect(otherSeed.ok()).toBeTruthy();
  const otherContext = await browser.newContext({ baseURL: "http://127.0.0.1:3123" });
  const otherPage = await otherContext.newPage();
  await otherPage.goto("/sign-in");
  await otherPage.getByLabel("Email").fill(otherEmail);
  await otherPage.getByLabel("Password").fill(password);
  await otherPage.getByRole("button", { name: "Sign in" }).click();
  await expect(otherPage.getByRole("heading", { name: /Welcome/ })).toBeVisible();
  await expect(otherPage.getByText("A private draft for testing")).toHaveCount(0);
  const crossView = await otherContext.request.get(
    `http://127.0.0.1:3123/api/v1/author/submissions/${savedDraft.id}`,
  );
  const crossDownload = await otherContext.request.get(
    `http://127.0.0.1:3123/api/v1/author/submissions/${savedDraft.id}/files/${savedDraft.files[0].id}`,
  );
  expect(crossView.status()).toBe(404);
  expect(crossDownload.status()).toBe(404);
  await otherContext.close();

  await page.goto("/recover");
  await page.getByLabel("Email").fill(authorEmail);
  await page.getByRole("button", { name: "Send recovery instructions" }).click();
  await expect(page.getByRole("status")).toContainText("recovery instructions");
  const recoveryMessage = await capturedMessage(authorEmail, "NSAJ password recovery");
  await page.goto(recoveryMessage.link);
  await page.getByLabel("New password").fill(updatedPassword);
  await page.getByRole("button", { name: "Update password" }).click();
  await expect(page.getByRole("status")).toContainText("Password updated");

  await page.goto("/sign-in");
  await page.getByLabel("Email").fill(authorEmail);
  await page.getByLabel("Password").fill(updatedPassword);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: /Welcome/ })).toBeVisible();
  await expect(page.getByRole("button", { name: new RegExp(createdDraft.reference) })).toBeVisible();
});
