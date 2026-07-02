import { test, expect } from '@playwright/test';
import { execSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';

test.describe('Human-in-the-loop Tool Approval UI & Filter Tests', () => {

    test('Verify tools and scripts exist in codebase', async () => {
        const actionPath = path.join(__dirname, '../tools/action_approval_ui.py');
        const filterPath = path.join(__dirname, '../tools/filter_approval_handler.py');
        
        expect(fs.existsSync(actionPath)).toBeTruthy();
        expect(fs.existsSync(filterPath)).toBeTruthy();
        
        const actionContent = fs.readFileSync(actionPath, 'utf8');
        expect(actionContent).toContain('class Action');
        expect(actionContent).toContain('[PENDING_APPROVAL:');
        
        const filterContent = fs.readFileSync(filterPath, 'utf8');
        expect(filterContent).toContain('class Filter');
        expect(filterContent).toContain('inlet');
        expect(filterContent).toContain('/approve');
        expect(filterContent).toContain('/reject');
    });

    test('Run end-to-end integration test of Action and Filter inside openwebui-app container', async () => {
        const localAction = path.join(__dirname, '../tools/action_approval_ui.py');
        const localFilter = path.join(__dirname, '../tools/filter_approval_handler.py');
        const localTestScript = path.join(__dirname, 'test_filter_action.py');

        expect(fs.existsSync(localAction)).toBeTruthy();
        expect(fs.existsSync(localFilter)).toBeTruthy();
        expect(fs.existsSync(localTestScript)).toBeTruthy();

        console.log("Copying Action, Filter and test script to openwebui-app container...");
        execSync(`docker cp "${localAction}" openwebui-app:/tmp/action_approval_ui.py`);
        execSync(`docker cp "${localFilter}" openwebui-app:/tmp/filter_approval_handler.py`);
        execSync(`docker cp "${localTestScript}" openwebui-app:/tmp/test_filter_action.py`);

        console.log("Executing test_filter_action.py inside openwebui-app container...");
        try {
            const output = execSync('docker exec openwebui-app python /tmp/test_filter_action.py').toString();
            console.log(output);
            expect(output).toContain('All integration checks completed successfully!');
        } catch (error: any) {
            console.error(`Subprocess execution failed: ${error.message}`);
            console.error(`Stdout: ${error.stdout?.toString()}`);
            console.error(`Stderr: ${error.stderr?.toString()}`);
            throw error;
        } finally {
            // Cleanup inside container
            try {
                execSync('docker exec openwebui-app rm -f /tmp/action_approval_ui.py');
                execSync('docker exec openwebui-app rm -f /tmp/filter_approval_handler.py');
                execSync('docker exec openwebui-app rm -f /tmp/test_filter_action.py');
            } catch (e) {}
        }
    });
});
