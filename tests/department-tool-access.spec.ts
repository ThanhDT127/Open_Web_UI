/// <reference types="node" />
/**
 * Department Tool Access Tests (OpenSpec: department-plugin-access)
 *
 * Verifies group-based tool access control: a test user belonging only to the
 * `ke-toan-tai-chinh` group must see exactly the tools granted by the default
 * matrix in scripts/seed_department_access.py, and none of the restricted ones.
 *
 * Prerequisites: docker stack running + seed script already applied
 * (python scripts/seed_department_access.py).
 */
import { test, expect, request, APIRequestContext } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://localhost:3000';
const ADMIN_EMAIL = process.env.TEST_ADMIN_EMAIL;
const ADMIN_PASSWORD = process.env.TEST_ADMIN_PASSWORD;

// Test user provisioned by this suite (fixed credentials, idempotent)
const TEST_USER_EMAIL = 'test-ketoan@example.com';
const TEST_USER_PASSWORD = 'TestKeToan#2026';
const TEST_GROUP = 'ke-toan-tai-chinh';

// Default matrix expectations for a ke-toan-tai-chinh member
// (see WORKSPACE_TOOL_MATRIX / MCPO_SERVER_MATRIX in scripts/seed_department_access.py)
//
// Office365: mảng này do MCP server `server:office365` phụ trách. Tool Python
// `office365_tool` đã bị gỡ — nó nằm trong MUST_NOT_SEE để nếu ai seed lại bản Python
// thì test gãy ngay, thay vì để hai bản Office365 chạy song song.
const MUST_SEE = ['google_gmail_tool', 'server:office365'];
const MUST_NOT_SEE = ['office365_tool', 'code_interpreter', 'server:playwright', 'server:postgres'];

if (!ADMIN_EMAIL || !ADMIN_PASSWORD) {
    throw new Error('Missing TEST_ADMIN_EMAIL / TEST_ADMIN_PASSWORD environment variables');
}

async function signin(api: APIRequestContext, email: string, password: string): Promise<string> {
    const res = await api.post(`${BASE_URL}/api/v1/auths/signin`, {
        data: { email, password },
    });
    expect(res.status(), `signin as ${email}`).toBe(200);
    return (await res.json()).token;
}

test.describe('Department tool access control', () => {
    let adminApi: APIRequestContext;
    let adminToken: string;

    test.beforeAll(async () => {
        adminApi = await request.newContext({ ignoreHTTPSErrors: true });
        adminToken = await signin(adminApi, ADMIN_EMAIL!, ADMIN_PASSWORD!);

        const authHeaders = { Authorization: `Bearer ${adminToken}` };

        // 1. Ensure the test user exists
        const addRes = await adminApi.post(`${BASE_URL}/api/v1/auths/add`, {
            headers: authHeaders,
            data: {
                name: 'Test Ke Toan',
                email: TEST_USER_EMAIL,
                password: TEST_USER_PASSWORD,
                role: 'user',
            },
        });
        let userId: string;
        if (addRes.status() === 200) {
            userId = (await addRes.json()).id;
        } else {
            // Already exists — look up the id
            const usersRes = await adminApi.get(`${BASE_URL}/api/v1/users/all`, { headers: authHeaders });
            expect(usersRes.status()).toBe(200);
            const body = await usersRes.json();
            const users = Array.isArray(body) ? body : body.users;
            const found = users.find((u: any) => u.email === TEST_USER_EMAIL);
            expect(found, `user ${TEST_USER_EMAIL} should exist`).toBeTruthy();
            userId = found.id;
        }

        // 2. Ensure membership in the test group (and only add if missing)
        const groupsRes = await adminApi.get(`${BASE_URL}/api/v1/groups/`, { headers: authHeaders });
        expect(groupsRes.status()).toBe(200);
        const groups = await groupsRes.json();
        const group = groups.find((g: any) => g.name === TEST_GROUP);
        expect(group, `group ${TEST_GROUP} should exist (run seed script first)`).toBeTruthy();

        const exportRes = await adminApi.get(`${BASE_URL}/api/v1/groups/id/${group.id}/export`, {
            headers: authHeaders,
        });
        expect(exportRes.status()).toBe(200);
        const memberIds: string[] = (await exportRes.json()).user_ids || [];
        if (!memberIds.includes(userId)) {
            const addMemberRes = await adminApi.post(`${BASE_URL}/api/v1/groups/id/${group.id}/users/add`, {
                headers: authHeaders,
                data: { user_ids: [userId] },
            });
            expect(addMemberRes.status()).toBe(200);
        }
    });

    test.afterAll(async () => {
        await adminApi.dispose();
    });

    test('API: user in ke-toan-tai-chinh sees only tools from the matrix', async () => {
        const userApi = await request.newContext({ ignoreHTTPSErrors: true });
        const userToken = await signin(userApi, TEST_USER_EMAIL, TEST_USER_PASSWORD);

        const toolsRes = await userApi.get(`${BASE_URL}/api/v1/tools/`, {
            headers: { Authorization: `Bearer ${userToken}` },
        });
        expect(toolsRes.status()).toBe(200);
        const tools = await toolsRes.json();
        const toolIds = tools.map((t: any) => t.id);
        console.log('Tools visible to test user:', toolIds);

        for (const id of MUST_SEE) {
            expect(toolIds, `tool '${id}' must be visible to ${TEST_GROUP}`).toContain(id);
        }
        for (const id of MUST_NOT_SEE) {
            expect(toolIds, `tool '${id}' must NOT be visible to ${TEST_GROUP}`).not.toContain(id);
        }

        await userApi.dispose();
    });

    test('UI: chat interface does not expose restricted tools to test user', async ({ page }) => {
        // Login via UI
        await page.goto('/auth');
        await page.waitForLoadState('networkidle');
        const emailField = page.locator('input[type="email"], input[name="email"], input[autocomplete="email"]').first();
        await emailField.waitFor({ state: 'visible', timeout: 10000 });
        await emailField.fill(TEST_USER_EMAIL);
        await page.locator('input[type="password"]').first().fill(TEST_USER_PASSWORD);
        await page.locator('button[type="submit"]').first().click();
        await page.waitForTimeout(3000);
        expect(page.url()).not.toContain('/auth');

        // The chat UI renders its tool list from /api/v1/tools/ in the same
        // browser session — assert on that session's response (cookie-authed),
        // which is exactly the data source the tools menu displays.
        const toolsRes = await page.request.get(`${BASE_URL}/api/v1/tools/`);
        expect(toolsRes.status()).toBe(200);
        const toolIds = (await toolsRes.json()).map((t: any) => t.id);

        for (const id of MUST_NOT_SEE) {
            expect(toolIds, `restricted tool '${id}' leaked into UI session`).not.toContain(id);
        }

        // Best-effort UI probe: restricted tool names must not appear in the page
        const pageContent = await page.content();
        expect(pageContent).not.toContain('Code Interpreter (Secure Python Sandbox)');
    });
});
