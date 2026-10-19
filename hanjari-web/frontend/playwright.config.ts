import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 20_000,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://localhost:5173",
    trace: "retain-on-failure",
  },
    projects: [
    { name: "mobile", use: { ...devices["Pixel 5"] } },      // Chromium 기반 (iPhone 은 WebKit 필요)
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: {
    command: "npm run dev",           // .env 의 VITE_MOCK=1 → 목업 모드
    url: "http://localhost:5173",
    reuseExistingServer: true,
  },
});