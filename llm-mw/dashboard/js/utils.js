// Dashboard utilities and helpers
export function escapeHtml(value) {
    return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

export function formatTimestamp(ts, bucket) {
    const d = new Date(ts);
    if (bucket === 'minute') {
        return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    } else if (bucket === 'hour') {
        return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit' });
    } else {
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    }
}

// Update status bar
export function updateStatus(type, message) {
    const dot = document.getElementById('statusDot');
    const msg = document.getElementById('statusMessage');

    if (!dot || !msg) return;

    dot.className = 'status-dot';
    msg.className = 'status-message';

    if (type === 'error') {
        dot.classList.add('error');
        msg.classList.add('error');
    } else if (type === 'warning') {
        dot.classList.add('warning');
    }

    msg.textContent = message;
}

// Centralized fetch with cookie credentials and 403 handling.
// Admin auth is carried by the HttpOnly mw_admin_session cookie set at login.
// Note: 403 handler will be set by auth module to avoid circular dependency.
let handle403 = null;

export function set403Handler(handler) {
    handle403 = handler;
}

export async function mwFetch(path, opts = {}) {
    const defaultHeaders = {
        'Content-Type': 'application/json',
        ...(opts.headers || {})
    };

    const mergedOpts = {
        ...opts,
        credentials: 'include',
        headers: defaultHeaders
    };

    try {
        const res = await fetch(path, mergedOpts);

        // Handle 403 - session expired or unauthorized
        if (res.status === 403) {
            console.warn('403 Forbidden - auth required');
            if (handle403) {
                handle403('Session expired or unauthorized. Please login again.');
            } else {
                console.error('403 handler not initialized');
                updateStatus('error', 'Authentication required');
            }
            return null;
        }

        return res;
    } catch (err) {
        console.error(`mwFetch error for ${path}:`, err);
        updateStatus('error', `Network error: ${err.message}`);
        throw err;
    }
}
