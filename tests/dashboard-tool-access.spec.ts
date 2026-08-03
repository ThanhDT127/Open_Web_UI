/**
 * Bật/tắt tool ngay tại Edit Group và Edit User của dashboard.
 *
 * Open WebUI 0.9.6 chỉ cho biên tập quyền tool từ phía *tool* (Workspace → Tools →
 * Access Control) và không có UI phân quyền theo user. Dashboard lật lại trục đó.
 * Test lái UI thật rồi đối chiếu xuống `access_grant` — nơi Open WebUI thực sự chốt quyền.
 */
import { test, expect, Page } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://localhost:3000';
const ADMIN_KEY = process.env.ADMIN_KEY;

const GROUP = 'ke-toan-tai-chinh';
// Ngoài chính sách phòng ban của ke-toan (WORKSPACE_TOOL_MATRIX: it, ky-thuat-rd)
const TOGGLE_TOOL = 'code_interpreter';

test.beforeAll(() => {
    if (!ADMIN_KEY) throw new Error('Missing ADMIN_KEY — chạy: set -a && . ./.env && set +a');
});

async function login(page: Page) {
    await page.goto(`${BASE_URL}/dashboard`);
    // index.html cài sẵn window.dashboardAPI toàn stub "Dashboard still loading...";
    // bấm trước khi module thay nó vào thì nút login không làm gì cả.
    await page.waitForFunction(
        () => !String((window as any).dashboardAPI?.authenticate).includes('still loading'),
    );
    await page.fill('#adminKeyInput', ADMIN_KEY!);
    await page.click('button:has-text("Access Dashboard")');
    await expect(page.locator('#dashboard')).not.toHaveClass(/hidden/, { timeout: 15000 });
}

/** Quyền như Open WebUI nhìn thấy — đọc qua API, không đọc lại state của dashboard. */
async function groupToolIds(page: Page, groupName: string): Promise<string[]> {
    const res = await page.request.get(`${BASE_URL}/v1/_mw/admin/tool-access/groups`, {
        headers: { 'X-Admin-Key': ADMIN_KEY! },
    });
    expect(res.ok()).toBeTruthy();
    const { groups } = await res.json();
    const group = groups.find((g: any) => g.name === groupName);
    expect(group, `group ${groupName} không tồn tại`).toBeTruthy();
    return group.tool_ids;
}

async function openGroupsTab(page: Page) {
    await page.click('.tab:has-text("Groups")');
    await expect(page.locator('#groupToolAccessTable tr').first()).toBeVisible();
}

test.describe('Dashboard — bật/tắt tool tại Edit Group', () => {
    test.afterEach(async ({ page }) => {
        // Trả về ma trận gốc: ke-toan không có code_interpreter.
        const current = await groupToolIds(page, GROUP);
        if (current.includes(TOGGLE_TOOL)) {
            const res = await page.request.get(`${BASE_URL}/v1/_mw/admin/tool-access/groups`, {
                headers: { 'X-Admin-Key': ADMIN_KEY! },
            });
            const { groups } = await res.json();
            const group = groups.find((g: any) => g.name === GROUP);
            await page.request.put(
                `${BASE_URL}/v1/_mw/admin/tool-access/groups/${group.id}`,
                {
                    headers: { 'X-Admin-Key': ADMIN_KEY!, 'Content-Type': 'application/json' },
                    data: { tool_ids: current.filter((t: string) => t !== TOGGLE_TOOL) },
                },
            );
        }
    });

    test('Tab Groups liệt kê tool đang cấp cho từng phòng ban', async ({ page }) => {
        await login(page);
        await openGroupsTab(page);

        const row = page.locator('#groupToolAccessTable tr', { hasText: GROUP });
        await expect(row).toBeVisible();
        // Đúng ma trận: ke-toan có gmail/drive/office365, KHÔNG có code_interpreter
        await expect(row.locator('.tool-chip', { hasText: 'google_gmail_tool' })).toBeVisible();
        await expect(row.locator('.tool-chip', { hasText: TOGGLE_TOOL })).toHaveCount(0);
    });

    test('Bật tool trong Edit Group ghi thật vào access_grant', async ({ page }) => {
        await login(page);
        await openGroupsTab(page);

        await page.locator('#groupToolAccessTable tr', { hasText: GROUP })
            .locator('button.btn-edit').click();

        const modal = page.locator('#groupToolModal');
        await expect(modal).toBeVisible();
        await expect(modal.locator('#groupToolModalTitle')).toContainText(GROUP);

        const box = modal.locator(`input[type="checkbox"][value="${TOGGLE_TOOL}"]`);
        await expect(box).not.toBeChecked();      // chưa cấp theo ma trận
        await box.check();
        await modal.locator('#groupToolSaveBtn').click();
        await expect(modal).toBeHidden();

        // Quyền có thật ở access_grant, không chỉ đổi màu trên UI
        expect(await groupToolIds(page, GROUP)).toContain(TOGGLE_TOOL);
        await expect(
            page.locator('#groupToolAccessTable tr', { hasText: GROUP })
                .locator('.tool-chip', { hasText: TOGGLE_TOOL }),
        ).toBeVisible();
    });

    test('Tắt tool trong Edit Group thu hồi quyền', async ({ page }) => {
        await login(page);
        await openGroupsTab(page);

        const row = page.locator('#groupToolAccessTable tr', { hasText: GROUP });

        // Bật trước để có cái mà tắt
        await row.locator('button.btn-edit').click();
        await page.locator(`#groupToolModal input[value="${TOGGLE_TOOL}"]`).check();
        await page.locator('#groupToolSaveBtn').click();
        await expect(page.locator('#groupToolModal')).toBeHidden();
        expect(await groupToolIds(page, GROUP)).toContain(TOGGLE_TOOL);

        // Rồi tắt
        await row.locator('button.btn-edit').click();
        const box = page.locator(`#groupToolModal input[value="${TOGGLE_TOOL}"]`);
        await expect(box).toBeChecked();
        await box.uncheck();
        await page.locator('#groupToolSaveBtn').click();
        await expect(page.locator('#groupToolModal')).toBeHidden();

        expect(await groupToolIds(page, GROUP)).not.toContain(TOGGLE_TOOL);
        // Các tool khác của group không bị cuốn theo
        expect(await groupToolIds(page, GROUP)).toContain('google_gmail_tool');
    });
});

test.describe('Dashboard — bật/tắt tool tại Edit User', () => {
    test('Modal Edit User hiện tool kế thừa từ group và cho cấp riêng', async ({ page }) => {
        await login(page);

        // Cần một middleware user đã map sang Open WebUI thì phần tool mới hiện — VÀ user đó
        // phải còn ít nhất một tool chưa kế thừa từ group, nếu không chẳng có gì để cấp riêng.
        // Hỏi API thay vì đoán: group của user đầu danh sách có thể đã được cấp hết tool.
        const res = await page.request.get(`${BASE_URL}/v1/_mw/admin/users`, {
            headers: { 'X-Admin-Key': ADMIN_KEY! },
        });
        const { users } = await res.json();

        let mapped: any = null;
        for (const u of users.filter((x: any) => x.openwebui_user_id && x.user_id !== 'admin')) {
            const r = await page.request.get(
                `${BASE_URL}/v1/_mw/admin/tool-access/users/${u.openwebui_user_id}`,
                { headers: { 'X-Admin-Key': ADMIN_KEY! } },
            );
            if (!r.ok()) continue;
            const { tools } = await r.json();
            if (tools.some((t: any) => !t.inherited_from.length && !t.public && !t.direct)) {
                mapped = u;
                break;
            }
        }
        test.skip(!mapped, 'Không có user nào vừa map sang Open WebUI vừa còn tool trống để cấp riêng');

        await page.click('.tab:has-text("Users")');
        await page.locator('#usersTable tr', { hasText: mapped.user_id })
            .locator('button.btn-edit').click();

        const section = page.locator('#modalToolsSection');
        await expect(section).toBeVisible();
        await expect(section.locator('.tool-row').first()).toBeVisible();

        // Tool kế thừa từ group: hiện là đã bật nhưng khóa — thu hồi phải sửa ở Edit Group,
        // bỏ tick ở đây không có tác dụng nên không được cho bấm.
        const locked = section.locator('.tool-row-locked');
        if (await locked.count() > 0) {
            await expect(locked.first().locator('input[type="checkbox"]')).toBeChecked();
            await expect(locked.first().locator('input[type="checkbox"]')).toBeDisabled();
        }

        // Grant riêng: bật một tool nằm ngoài chính sách phòng ban rồi lưu
        const free = section.locator('.tool-row:not(.tool-row-locked) input[type="checkbox"]').first();
        const toolId = await free.getAttribute('value');
        await free.check();
        await page.click('#modalSaveBtn');
        await expect(page.locator('#userModal')).toBeHidden();

        const after = await page.request.get(
            `${BASE_URL}/v1/_mw/admin/tool-access/users/${mapped.openwebui_user_id}`,
            { headers: { 'X-Admin-Key': ADMIN_KEY! } },
        );
        const detail = await after.json();
        const tool = detail.tools.find((t: any) => t.id === toolId);
        expect(tool.direct, `${toolId} phải thành grant riêng của user`).toBe(true);
        expect(tool.effective).toBe(true);

        // Dọn: trả user về không có grant riêng
        await page.request.put(
            `${BASE_URL}/v1/_mw/admin/tool-access/users/${mapped.openwebui_user_id}`,
            {
                headers: { 'X-Admin-Key': ADMIN_KEY!, 'Content-Type': 'application/json' },
                data: { tool_ids: [] },
            },
        );
    });
});
