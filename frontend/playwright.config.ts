import { randomUUID } from "node:crypto";
import { defineConfig, devices } from "@playwright/test";

const runId = process.env.NSAJ_E2E_RUN_ID ?? randomUUID();
process.env.NSAJ_E2E_RUN_ID = runId;

export default defineConfig({
  testDir: "./tests-e2e",
  fullyParallel: false,
  // One shared local test API and database; keep browser workloads deterministic
  // on the native Windows development machine.
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: "list",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: "http://127.0.0.1:3123",
    trace: "off",
    ...devices["Desktop Chrome"],
  },
  webServer: [
    {
      command: "powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start-e2e-backend.ps1",
      url: "http://127.0.0.1:8123/health",
      name: "NSAJ test API",
      timeout: 120_000,
      reuseExistingServer: false,
      env: { NSAJ_E2E_RUN_ID: runId },
    },
    {
      command: "powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start-e2e-frontend.ps1",
      url: "http://127.0.0.1:3123",
      name: "NSAJ test frontend",
      timeout: 120_000,
      reuseExistingServer: false,
      env: { NSAJ_E2E_RUN_ID: runId },
    },
  ],
});
