// SPDX-License-Identifier: AGPL-3.0-only
// End-to-end tests (F1): the built web app served by the real backend, with the fake AI
// provider and the fixture place index, so runs are deterministic, free and offline.
import { defineConfig, devices } from "@playwright/test";

const PORT = 8010;
const chromePath = process.env.PW_CHROMIUM_PATH; // a system Chrome where browsers can't be downloaded

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
    ...(chromePath ? { launchOptions: { executablePath: chromePath } } : {}),
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
  webServer: {
    command: `bash e2e/serve.sh ${PORT}`,
    url: `http://127.0.0.1:${PORT}/readyz`,
    timeout: 120_000,
    reuseExistingServer: !process.env.CI,
  },
});
