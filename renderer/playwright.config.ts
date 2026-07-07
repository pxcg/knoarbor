import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:8765",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "cd .. && uv run python -m uvicorn knoarbor.entrypoints.api:create_app --factory --host 127.0.0.1 --port 8765",
    url: "http://127.0.0.1:8765/health",
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
