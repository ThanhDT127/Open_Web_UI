// Authentication and session management
import { mwFetch, updateStatus, set403Handler } from './utils.js';

// Global state
export let eventSource = null;
export let accessEventSource = null;
export let summaryInterval = null;
export let retryCount = 0;
export const MAX_RETRY_DELAY = 15000; // 15s max

export function setEventSource(es) {
    eventSource = es;
}

export function setAccessEventSource(aes) {
    accessEventSource = aes;
}

export function setSummaryInterval(si) {
    summaryInterval = si;
}

export function setRetryCount(rc) {
    retryCount = rc;
}

// Stop all dashboard loops and streams
export function stopDashboardLoops() {
    if (summaryInterval) {
        clearInterval(summaryInterval);
        summaryInterval = null;
    }
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    if (accessEventSource) {
        accessEventSource.close();
        accessEventSource = null;
    }
    retryCount = 0;
}

// Show login UI with message
export function showLoginUI(message) {
    document.getElementById('authPrompt').classList.remove('hidden');
    document.getElementById('dashboard').classList.add('hidden');

    if (message) {
        showError(message);
    }
}

// Show error message
function showError(msg) {
    const errorDiv = document.getElementById('authError');
    errorDiv.textContent = msg;
    errorDiv.classList.remove('hidden');
}

// Authenticate and start dashboard
export async function authenticate() {
    const input = document.getElementById('adminKeyInput');
    const key = input.value.trim();

    if (!key) {
        showError('Please enter admin key');
        return;
    }

    try {
        const res = await fetch('/v1/_mw/dashboard/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ admin_key: key })
        });

        if (res.status === 403) {
            throw new Error('Invalid admin key');
        }
        if (!res.ok) {
            throw new Error('Login failed');
        }

        await res.json();
        input.value = '';

        // Success - hide auth prompt and show dashboard. The server sets an
        // HttpOnly cookie; do not store the raw admin key in browser storage.
        document.getElementById('authPrompt').classList.add('hidden');
        document.getElementById('dashboard').classList.remove('hidden');

        // Verify cookie works
        await checkAuthStatus();

        // Start dashboard
        const { startDashboard } = await import('./main.js');
        startDashboard();
    } catch (err) {
        showError(err.message || 'Authentication failed');
    }
}

// Check auth status and cookie presence
async function checkAuthStatus() {
    try {
        const res = await mwFetch('/v1/_mw/auth_check');
        if (!res || !res.ok) {
            updateStatus('warning', 'Auth check failed - cookie may not work across different hosts');
            return false;
        }
        const data = await res.json();
        if (data.ok) {
            updateStatus('ok', 'Authenticated ✓');
            return true;
        }
        updateStatus('warning', 'Cookie not present - use same host (localhost OR 127.0.0.1, not mixed)');
        return false;
    } catch (err) {
        updateStatus('warning', 'Auth check failed');
        return false;
    }
}

// Setup Enter key for login
export function initAuth() {
    // Set 403 handler in utils to avoid circular dependency
    set403Handler(async (message) => {
        // Import stopDashboard dynamically to avoid circular dependency
        const { stopDashboard } = await import('./main.js');
        stopDashboard();
        showLoginUI(message || 'Session expired. Please login again.');
    });

    const input = document.getElementById('adminKeyInput');
    input.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            authenticate();
        }
    });

    // Check cookie-backed session on page load. Do not require sessionStorage;
    // a valid HttpOnly cookie should be enough to restore the dashboard.
    document.addEventListener('DOMContentLoaded', async () => {
        try {
            const authenticated = await checkAuthStatus();
            if (authenticated) {
                document.getElementById('authPrompt').classList.add('hidden');
                document.getElementById('dashboard').classList.remove('hidden');
                const { startDashboard } = await import('./main.js');
                startDashboard();
            }
        } catch (err) {
            // Not logged in, stay on login screen
            console.log('Not logged in:', err);
        }
    });
}
