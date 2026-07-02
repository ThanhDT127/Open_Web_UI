import { defineConfig, devices } from '@playwright/test';
import * as dotenv from 'dotenv';
import * as path from 'path';

/**
 * Read environment variables from file.
 * https://github.com/motdotla/dotenv
 */
dotenv.config({ path: path.resolve(__dirname, '../.env') });

export default defineConfig({
    testDir: '.',
    timeout: 180000,
    expect: {
        timeout: 5000
    },
    fullyParallel: false,
    forbidOnly: !!process.env.CI,
    retries: process.env.CI ? 2 : 0,
    workers: 1,
    reporter: [
        ['html', { outputFolder: 'playwright-report' }],
        ['list']
    ],
    use: {
        baseURL: process.env.BASE_URL || 'https://localhost:3000',
        ignoreHTTPSErrors: true,
        actionTimeout: 5000,
        navigationTimeout: 15000,
        trace: 'on-first-retry',
        screenshot: 'only-on-failure',
        video: 'retain-on-failure',
        ignoreHTTPSErrors: true,
    },

    projects: [
        {
            name: 'chromium',
            use: { ...devices['Desktop Chrome'] },
        },
    ],

    webServer: {
        command: 'echo "Docker stack should already be running"',
        url: 'http://localhost:3000',
        reuseExistingServer: true,
        timeout: 5000,
    },
});
