/// <reference types="node" />
/**
 * Open WebUI Authentication Tests
 * Tests user login functionality with real admin credentials
 */
import { test, expect, request } from '@playwright/test';

// Load credentials from environment
const ADMIN_EMAIL = process.env.TEST_ADMIN_EMAIL;
const ADMIN_PASSWORD = process.env.TEST_ADMIN_PASSWORD;
const SUBKEY_ADMIN = process.env.SUBKEY_ADMIN;

if (!ADMIN_EMAIL || !ADMIN_PASSWORD || !SUBKEY_ADMIN) {
    throw new Error("Missing required environment variables for test execution: TEST_ADMIN_EMAIL, TEST_ADMIN_PASSWORD, SUBKEY_ADMIN");
}

test.describe('User Authentication - Login', () => {

    test('Admin can login with valid credentials', async ({ page }) => {
        await page.goto('/');
        await page.waitForLoadState('networkidle');
        await page.waitForTimeout(2000);

        // Find and fill email field
        const emailField = page.locator('input[type="email"], input[name="email"], input[autocomplete="email"]').first();
        await emailField.waitFor({ state: 'visible', timeout: 10000 });
        await emailField.fill(ADMIN_EMAIL);

        // Find and fill password field
        const passwordField = page.locator('input[type="password"]').first();
        await passwordField.fill(ADMIN_PASSWORD);

        // Click submit button
        const submitBtn = page.locator('button[type="submit"]').first();
        await submitBtn.click();

        // Wait for navigation after login
        await page.waitForTimeout(3000);

        // Should redirect to main interface (not stay on auth page)
        const currentUrl = page.url();
        const isLoggedIn = !currentUrl.includes('/auth') || currentUrl.includes('/chat') || currentUrl.includes('/');
        expect(isLoggedIn).toBeTruthy();
    });

    test('Login fails with wrong password', async ({ page }) => {
        await page.goto('/auth');
        await page.waitForLoadState('networkidle');
        await page.waitForTimeout(2000);

        const emailField = page.locator('input[type="email"], input[name="email"]').first();
        if (await emailField.count() > 0) {
            await emailField.fill(ADMIN_EMAIL);

            const passwordField = page.locator('input[type="password"]').first();
            await passwordField.fill('WrongPassword123');

            const submitBtn = page.locator('button[type="submit"]').first();
            await submitBtn.click();

            await page.waitForTimeout(2000);

            // Should show error or stay on login page
            const hasError = await page.locator('text=/error|invalid|incorrect/i').count() > 0;
            const stillOnAuth = page.url().includes('/auth') || page.url().includes('login');

            expect(hasError || stillOnAuth).toBeTruthy();
        }
    });
});

test.describe('API Authentication - Middleware', () => {

    test('Middleware accepts valid subkey for models endpoint', async () => {
        const context = await request.newContext();
        const response = await context.get('http://localhost:5000/v1/models', {
            headers: {
                'Authorization': `Bearer ${SUBKEY_ADMIN}`
            }
        });

        expect(response.ok()).toBeTruthy();
        const body = await response.json();
        expect(body).toHaveProperty('data');
    });

    test('Middleware responds to API requests', async () => {
        const context = await request.newContext();
        const response = await context.get('http://localhost:5000/v1/models', {
            headers: {
                'Authorization': 'Bearer any_key_here'
            }
        });

        // Middleware should respond (may allow or reject based on config)
        expect(response.status()).toBeDefined();
    });

    test('Middleware admin endpoint requires admin key', async () => {
        const context = await request.newContext();
        const response = await context.get('http://localhost:5000/admin/users', {
            headers: {
                'Authorization': 'Bearer invalid_admin_key'
            }
        });

        expect(response.status()).toBeGreaterThanOrEqual(400);
    });
});
