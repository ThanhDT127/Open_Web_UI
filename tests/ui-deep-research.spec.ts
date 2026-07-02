import { test, expect } from '@playwright/test';
import { execSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';

test.describe('Deep Research Agentic Pipe UI & Integration Tests', () => {

    test('Verify tools and scripts exist in codebase', async () => {
        const pipePath = path.join(__dirname, '../tools/deep_research_pipe.py');
        expect(fs.existsSync(pipePath)).toBeTruthy();
        
        const pipeContent = fs.readFileSync(pipePath, 'utf8');
        expect(pipeContent).toContain('class Pipe');
        expect(pipeContent).toContain('pipe(');
        expect(pipeContent).toContain('<thinking>');
        expect(pipeContent).toContain('</thinking>');
    });

    test('Run end-to-end integration test of Deep Research Pipe inside openwebui-app container', async () => {
        const localPipe = path.join(__dirname, '../tools/deep_research_pipe.py');
        const localTestScript = path.join(__dirname, 'test_deep_research_integration.py');

        expect(fs.existsSync(localPipe)).toBeTruthy();
        expect(fs.existsSync(localTestScript)).toBeTruthy();

        console.log("Copying Pipe and test script to openwebui-app container...");
        execSync(`docker cp "${localPipe}" openwebui-app:/tmp/deep_research_pipe.py`);
        execSync(`docker cp "${localTestScript}" openwebui-app:/tmp/test_deep_research_integration.py`);

        console.log("Executing test_deep_research_integration.py inside openwebui-app container...");
        try {
            const output = execSync('docker exec openwebui-app python /tmp/test_deep_research_integration.py').toString();
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
                execSync('docker exec openwebui-app rm -f /tmp/deep_research_pipe.py');
                execSync('docker exec openwebui-app rm -f /tmp/test_deep_research_integration.py');
            } catch (e) {}
        }
    });
});
