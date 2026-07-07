// Real-time Active Users SSE stream logic

let _eventSource = null;

export function connectActiveUsersStream() {
    if (_eventSource) {
        _eventSource.close();
    }

    const streamUrl = '/v1/_mw/admin/active-users/stream';
    _eventSource = new EventSource(streamUrl);

    _eventSource.addEventListener('live_metrics', (e) => {
        try {
            const data = JSON.parse(e.data);
            
            // Update active users
            const activeCount = data.active_users !== undefined ? data.active_users : 0;
            const activeEl = document.getElementById('metricActiveUsers');
            if (activeEl) {
                activeEl.textContent = activeCount;
            }
            
            // Update pending count (real-time)
            const pendingCount = data.pending_count !== undefined ? data.pending_count : 0;
            const pendingEl = document.getElementById('metricPending');
            if (pendingEl) {
                pendingEl.textContent = pendingCount;
            }
        } catch (err) {
            console.error('Failed to parse live metrics event:', err);
        }
    });

    _eventSource.addEventListener('error', (e) => {
        console.error('SSE Active Users connection error:', e);
        const el = document.getElementById('metricActiveUsers');
        if (el) {
            el.textContent = '?';
        }
        // EventSource will automatically retry connecting
    });
}

export function disconnectActiveUsersStream() {
    if (_eventSource) {
        _eventSource.close();
        _eventSource = null;
    }
}
