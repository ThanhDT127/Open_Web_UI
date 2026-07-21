// Access tab logic - HTTP access logs
import { mwFetch } from './utils.js';
import { buildRangeParams } from './filters.js';
import { accessEventSource, setAccessEventSource } from './auth.js';
import { escapeHtml } from './utils.js';

// Load access summary data
export async function loadAccessData() {
    try {
        const params = buildRangeParams();

        const res = await mwFetch(`/v1/_mw/access_summary?${params}`);
        if (!res || !res.ok) return;
        
        const data = await res.json();
        if (!data || !data.totals) return;

        const t = data.totals;
        document.getElementById('accessTotal').textContent = t.requests_total || 0;
        // Use error_count instead of error_rate_percent
        const errorRate = t.requests_total > 0 
            ? ((t.error_count || 0) / t.requests_total * 100) 
            : 0;
        document.getElementById('accessErrorRate').textContent = errorRate.toFixed(1) + '%';
        document.getElementById('accessLatency').textContent = t.avg_latency_ms ? t.avg_latency_ms.toFixed(0) + 'ms' : '-';

        // Update paths table
        const table = document.getElementById('accessPathsTable');
        if (data.breakdown_by_path && data.breakdown_by_path.length > 0) {
            table.innerHTML = data.breakdown_by_path.slice(0, 15).map(p => {
                // Calculate error rate if not provided
                const pathErrorRate = p.error_rate_percent !== undefined 
                    ? p.error_rate_percent 
                    : (p.count > 0 ? ((p.errors || 0) / p.count * 100) : 0);
                return `
                <tr>
                    <td>${escapeHtml(p.path)}</td>
                    <td>${p.count}</td>
                    <td>${p.errors || 0}</td>
                    <td>${pathErrorRate.toFixed(1)}%</td>
                </tr>
                `;
            }).join('');
        } else {
            table.innerHTML = '<tr><td colspan="4">No data</td></tr>';
        }
    } catch (err) {
        console.error('Failed to load access data:', err);
        document.getElementById('accessPathsTable').innerHTML = '<tr><td colspan="4" class="error-msg">Error loading data</td></tr>';
    }
}

// Connect to access event stream
export function connectAccessStream() {
    const eventsDiv = document.getElementById('accessEvents');
    
    // Close existing
    if (accessEventSource) {
        accessEventSource.close();
        setAccessEventSource(null);
    }
    
    eventsDiv.innerHTML = '<div class="loading">Connecting to access stream...</div>';

    try {
        const aes = new EventSource('/v1/_mw/access_stream');
        setAccessEventSource(aes);

        aes.addEventListener('access', (e) => {
            try {
                const data = JSON.parse(e.data);
                addAccessEvent(data);
            } catch (err) {
                console.error('Failed to parse access event:', err);
            }
        });

        aes.onerror = (e) => {
            console.error('Access stream error:', e);
            if (aes.readyState === EventSource.CLOSED) {
                eventsDiv.innerHTML = '<div class="error-msg">Access stream disconnected. Will retry...</div>';
                setTimeout(() => {
                    if (document.getElementById('accessTab').classList.contains('active')) {
                        connectAccessStream();
                    }
                }, 5000);
            }
        };
        
        aes.onopen = () => {
            eventsDiv.innerHTML = '';
        };
    } catch (err) {
        console.error('Failed to create access EventSource:', err);
        eventsDiv.innerHTML = '<div class="error-msg">Failed to connect access stream</div>';
    }
}

// Add access event to display
function addAccessEvent(data) {
    const eventsDiv = document.getElementById('accessEvents');
    if (eventsDiv.querySelector('.loading')) {
        eventsDiv.innerHTML = '';
    }

    const line = document.createElement('div');
    line.className = 'event-line';
    
    // BE sends: {ts, event, method, path, client, status, ms}
    const statusCode = data.status || 200;  // BE uses "status" not "status_code"
    const latency = data.ms || 0;           // BE uses "ms" not "latency_ms"
    
    line.innerHTML = `
        <span class="event-time">${escapeHtml(new Date(data.ts).toLocaleTimeString())}</span>
        <span class="event-status status-${statusCode < 400 ? 'ok' : 'error'}">${escapeHtml(data.method)} ${statusCode}</span>
        <span class="event-detail">${escapeHtml(data.path)} - ${latency}ms</span>
    `;
    eventsDiv.insertBefore(line, eventsDiv.firstChild);

    // Keep last 50 events
    while (eventsDiv.children.length > 50) {
        eventsDiv.removeChild(eventsDiv.lastChild);
    }
}
