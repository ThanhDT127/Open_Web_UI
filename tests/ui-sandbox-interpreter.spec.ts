import { test, expect } from '@playwright/test';
import { execSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';

test.describe('Secure Code Sandbox (Jupyter Kernel Gateway) Tests', () => {

    test('Verify code_interpreter.py custom tool exists in codebase', async () => {
        const toolFilePath = path.join(__dirname, '../tools/code_interpreter.py');
        expect(fs.existsSync(toolFilePath)).toBeTruthy();
        
        const fileContent = fs.readFileSync(toolFilePath, 'utf8');
        expect(fileContent).toContain('class Tools');
        expect(fileContent).toContain('def run_python_code');
        expect(fileContent).toContain('SANDBOX_URL');
        expect(fileContent).toContain('OUTPUTS_DIR');
    });

    test('Verify code-sandbox service is running in Docker', async () => {
        const result = execSync('docker ps --filter "name=openwebui-sandbox" --format "{{.Status}}"').toString().strip();
        console.log(`Sandbox container status: ${result}`);
        expect(result).toContain('Up');
    });

    test('Run end-to-end sandbox execution and volume sharing check inside container', async () => {
        // Copy the test_sandbox.py file into the running openwebui-app container
        const localTestScript = path.join(__dirname, 'test_sandbox.py');
        expect(fs.existsSync(localTestScript)).toBeTruthy();
        
        console.log("Copying test_sandbox.py to openwebui-app container...");
        execSync(`docker cp "${localTestScript}" openwebui-app:/tmp/test_sandbox.py`);
        
        console.log("Executing test_sandbox.py inside openwebui-app container...");
        try {
            const output = execSync('docker exec openwebui-app python /tmp/test_sandbox.py').toString();
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
                execSync('docker exec openwebui-app rm -f /tmp/test_sandbox.py');
            } catch (e) {}
        }
    });
});

// Helper for cleaning strings
declare global {
    interface String {
        strip(): string;
    }
}
if (!String.prototype.strip) {
    String.prototype.strip = function() {
        return this.replace(/^\s+|\s+$/g, '');
    };
}
