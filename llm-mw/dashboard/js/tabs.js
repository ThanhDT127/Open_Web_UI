// Tab switching logic
import { loadAccessData, connectAccessStream } from './access.js';
import { loadUsers } from './users.js';
import { loadLogs } from './logs.js';
import { loadSettings } from './settings.js';
import { loadRagHealth } from './raghealth.js';
import { loadKnowledge } from './knowledge.js';
import { accessEventSource } from './auth.js';

// FIX: Pass event explicitly
export function switchTab(e, tabName) {
    // Update tab buttons
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    e.target.classList.add('active');

    // Update tab content
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.getElementById(tabName + 'Tab').classList.add('active');

    // Load tab-specific data
    if (tabName === 'access') {
        loadAccessData();
        if (!accessEventSource) connectAccessStream();
    } else if (tabName === 'users') {
        loadUsers();
    } else if (tabName === 'logs') {
        // Auto-load to populate dropdowns
        loadLogs();
    } else if (tabName === 'settings') {
        loadSettings();
    } else if (tabName === 'raghealth') {
        loadRagHealth();
    } else if (tabName === 'knowledge') {
        loadKnowledge();
    }
}
