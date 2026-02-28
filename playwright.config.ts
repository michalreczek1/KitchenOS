import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL: 'http://127.0.0.1:3000',
    headless: true,
  },
  webServer: [
    {
      command: 'powershell -ExecutionPolicy Bypass -File .\\scripts\\start-e2e-backend.ps1',
      url: 'http://127.0.0.1:8000/health',
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: 'powershell -ExecutionPolicy Bypass -File .\\scripts\\start-e2e-frontend.ps1',
      url: 'http://127.0.0.1:3000',
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
})
