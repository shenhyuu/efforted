import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  workers: 1,
  use: { baseURL: 'http://127.0.0.1:4173', trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: 'python -m uvicorn main:app --host 127.0.0.1 --port 8011',
      cwd: '../backend', url: 'http://127.0.0.1:8011/health', reuseExistingServer: false,
      env: { ZHIHEN_DB_PATH: 'data/e2e.db' },
    },
    {
      command: 'pnpm dev --host 127.0.0.1 --port 4173',
      url: 'http://127.0.0.1:4173', reuseExistingServer: false,
      env: { VITE_API_PROXY: 'http://127.0.0.1:8011' },
    },
  ],
})
