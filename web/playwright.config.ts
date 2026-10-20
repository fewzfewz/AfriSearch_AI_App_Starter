import { defineConfig } from "@playwright/test";

// Browser tests against the real API with fake models (tests/e2e/server.py).
// Build first: npm run build. Locally, PW_CHANNEL=chrome uses an installed Chrome.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: "http://127.0.0.1:8799",
    channel: process.env.PW_CHANNEL || undefined,
    trace: "retain-on-failure",
  },
  webServer: {
    command: `${process.env.E2E_PYTHON ?? "python"} ../tests/e2e/server.py 8799`,
    url: "http://127.0.0.1:8799/api/health",
    timeout: 120_000,
    reuseExistingServer: false,
  },
});
