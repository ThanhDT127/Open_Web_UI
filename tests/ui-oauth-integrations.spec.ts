import { test, expect, request } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

// Load variables
const ADMIN_EMAIL = process.env.TEST_ADMIN_EMAIL || 'admin@example.com';
const SUBKEY_ADMIN = process.env.SUBKEY_ADMIN || 'YOUR_SUBKEY_ADMIN';
const ADMIN_KEY = process.env.ADMIN_KEY || 'YOUR_ADMIN_KEY';

test.describe('OAuth 2.0 Click-to-Connect API & Integration Tests', () => {

    test('Verify google_gmail_tool.py exists and matches structure', async () => {
        const toolFilePath = path.join(__dirname, '../tools/google_gmail_tool.py');
        expect(fs.existsSync(toolFilePath)).toBeTruthy();
        
        const fileContent = fs.readFileSync(toolFilePath, 'utf8');
        expect(fileContent).toContain('class Tools');
        expect(fileContent).toContain('def send_gmail');
        expect(fileContent).toContain('google_gmail');
        expect(fileContent).toContain('/_mw/integrations/get_token');
    });

    test('Middleware OAuth flow API end-to-end verification', async () => {
        const apiContext = await request.newContext();

        // 1. Fetch reconciliation report to find the OpenWebUI ID of our admin user
        const reconRes = await apiContext.get('http://localhost:5000/v1/_mw/admin/users/reconciliation', {
            headers: {
                'X-Admin-Key': ADMIN_KEY
            }
        });
        expect(reconRes.ok()).toBeTruthy();
        const reconData = await reconRes.json();
        
        let openwebui_user_id = '';
        for (const item of reconData.matched || []) {
            if (item.openwebui && item.openwebui.email === ADMIN_EMAIL) {
                openwebui_user_id = item.openwebui.id;
                break;
            }
        }
        if (!openwebui_user_id) {
            for (const item of reconData.unmatched_openwebui || []) {
                if (item.email === ADMIN_EMAIL) {
                    openwebui_user_id = item.id;
                    break;
                }
            }
        }
        
        expect(openwebui_user_id).not.toBe('');
        console.log(`Found mapped OpenWebUI ID for ${ADMIN_EMAIL}: ${openwebui_user_id}`);

        // 2. Map openwebui_user_id to adminrd user
        const mapRes = await apiContext.put('http://localhost:5000/v1/_mw/admin/users/adminrd/openwebui-mapping', {
            headers: {
                'X-Admin-Key': ADMIN_KEY,
                'Content-Type': 'application/json'
            },
            data: {
                openwebui_user_id: openwebui_user_id
            }
        });
        if (!mapRes.ok()) {
            console.error(`Mapping failed with status ${mapRes.status()}: ${await mapRes.text()}`);
        }
        expect(mapRes.ok()).toBeTruthy();
        const mapData = await mapRes.json();
        expect(mapData.user.openwebui_user_id).toBe(openwebui_user_id);

        // 3. Request redirect URL generation for google_gmail
        const connectRes = await apiContext.get(`http://localhost:5000/v1/_mw/oauth/connect?provider=google_gmail&openwebui_user_id=${openwebui_user_id}`, {
            maxRedirects: 0
        });
        if (connectRes.status() !== 302 && connectRes.status() !== 307) {
            console.error(`Connect failed with status ${connectRes.status()}: ${await connectRes.text()}`);
        }
        expect([302, 307]).toContain(connectRes.status());
        const location = connectRes.headers()['location'];
        expect(location).toBeDefined();
        expect(location).toContain('accounts.google.com');
        expect(location).toContain('scope=');
        expect(location).toContain('state=');
        
        const urlParams = new URLSearchParams(location.split('?')[1]);
        const stateParam = urlParams.get('state');
        expect(stateParam).toBeDefined();
        const decodedState = decodeURIComponent(stateParam!);
        expect(decodedState).toBe(`google_gmail:ow_user_id:${openwebui_user_id}`);

        // 4. Mock provider callback with code
        const callbackUrl = `http://localhost:5000/v1/_mw/oauth/callback?code=mock-code-1234&state=${stateParam}`;
        const callbackRes = await apiContext.get(callbackUrl);
        expect(callbackRes.ok()).toBeTruthy();
        
        const callbackHtml = await callbackRes.text();
        expect(callbackHtml).toContain('Kết Nối Thành Công!');

        // 5. Retrieve decrypted token via integrations endpoint
        const gettokenRes = await apiContext.get(`http://localhost:5000/v1/_mw/integrations/get_token?provider=google_gmail&openwebui_user_id=${openwebui_user_id}`, {
            headers: {
                'Authorization': `Bearer ${SUBKEY_ADMIN}`
            }
        });
        expect(gettokenRes.ok()).toBeTruthy();
        
        const tokenData = await gettokenRes.json();
        expect(tokenData).toHaveProperty('access_token');
        expect(tokenData.access_token).toContain('mock-access-token-google_gmail');

        // 6. Test invalid request cases
        // 6a. Unsupported provider
        const badProviderRes = await apiContext.get(`http://localhost:5000/v1/_mw/oauth/connect?provider=unknown_prov&openwebui_user_id=${openwebui_user_id}`);
        expect(badProviderRes.status()).toBe(400);

        // 6b. Request token for non-existent integration
        const missingIntegrationRes = await apiContext.get(`http://localhost:5000/v1/_mw/integrations/get_token?provider=google_drive&openwebui_user_id=${openwebui_user_id}`, {
            headers: {
                'Authorization': `Bearer ${SUBKEY_ADMIN}`
            }
        });
        expect(missingIntegrationRes.status()).toBe(404);
    });
});
