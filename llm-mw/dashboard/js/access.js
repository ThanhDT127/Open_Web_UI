// Access tab logic - HTTP access logs
import { mwFetch } from './utils.js';
import { buildRangeParams } from './filters.js';
import { accessEventSource, setAccessEventSource } from './auth.js';
import { escapeHtml } from './utils.js';
import { formatValue, renderDelta, clearDelta } from './metrics_registry.js';
import { loadCompare, side } from './compare_data.js';

const _CARDS = ['accessTotal', 'accessFailureRate', 'accessDeniedRate', 'accessThrottledRate',
    'accessLatency', 'accessHttpP95', 'accessFailedLogins', 'accessHealthProbe'];
const _DETAILS = ['accessFailureDetail', 'accessDeniedDetail', 'accessThrottledDetail',
    'accessHttpP95Detail'];

function _set(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

// Clear every figure on the tab. An error notice sitting above a populated table still
// reads as though those numbers belong to the selected window — so the numbers go too.
function _clearAll() {
    _CARDS.forEach(id => _set(id, '—'));
    _DETAILS.forEach(id => _set(id, '—'));
    _CARDS.forEach(id => clearDelta(id));
    const table = document.getElementById('accessPathsTable');
    if (table) table.innerHTML = '<tr><td colspan="4">—</td></tr>';
}

function _showError(message) {
    _clearAll();
    const banner = document.getElementById('accessErrorBanner');
    if (banner) {
        banner.style.display = '';
        banner.textContent = `⚠️ Không tải được dữ liệu Access: ${message}. `
            + 'Các số đã được xoá — không hiển thị số của khoảng thời gian trước.';
    }
}

function _hideError() {
    const banner = document.getElementById('accessErrorBanner');
    if (banner) banner.style.display = 'none';
}

// Pull one metric out of a comparison side. Must return null (not 0) for an empty
// window: 0 makes the delta divide by zero and the badge then shows a fabricated
// increase on every load (the Phase 7b lesson).
const _pickAccess = (json) => {
    const t = json && json.totals;
    if (!t || !(t.requests_total > 0)) return null;
    return {
        requests_total: t.requests_total,
        failure_rate_percent: t.failure_rate_percent,
        denied_rate_percent: t.denied_rate_percent,
        throttled_rate_percent: t.throttled_rate_percent,
        http_p95_latency_ms: t.p95_latency_ms,
        failed_dashboard_logins: t.failed_dashboard_logins,
    };
};

async function _renderCompare(t) {
    try {
        const cmp = await loadCompare('/v1/_mw/access_summary', _pickAccess);
        const wire = (id, key, current) => renderDelta(id, key, {
            current, kt: side(cmp.kt, key), ck: side(cmp.ck, key),
        });
        wire('accessTotal', 'requests_total', t.requests_total);
        wire('accessFailureRate', 'failure_rate_percent', t.failure_rate_percent);
        wire('accessDeniedRate', 'denied_rate_percent', t.denied_rate_percent);
        wire('accessThrottledRate', 'throttled_rate_percent', t.throttled_rate_percent);
        wire('accessHttpP95', 'http_p95_latency_ms', t.p95_latency_ms);
        // Declared comparable in the registry since Phase 10 but never wired, which reads
        // as an oversight rather than a decision — the defect the registry exists to make
        // visible. The payload already carried the field.
        wire('accessFailedLogins', 'failed_dashboard_logins', t.failed_dashboard_logins);
    } catch (err) {
        console.error('Access compare failed:', err);
    }
}

// Load access summary data
export async function loadAccessData() {
    try {
        const params = buildRangeParams();

        const res = await mwFetch(`/v1/_mw/access_summary?${params}`);
        if (!res || !res.ok) throw new Error(`HTTP ${res ? res.status : 'null'}`);

        const data = await res.json();
        if (!data || !data.totals) throw new Error('payload thiếu totals');
        if (data.error) throw new Error(data.error);

        _hideError();
        const t = data.totals;
        const total = t.requests_total || 0;
        _set('accessTotal', formatValue('requests_total', total));

        // Three groups, three repair actions. The combined rate is deliberately absent.
        _set('accessFailureRate', formatValue('failure_rate_percent', t.failure_rate_percent));
        _set('accessFailureDetail', `${t.failures || 0} lượt · 5xx không tính healthcheck`);
        _set('accessDeniedRate', formatValue('denied_rate_percent', t.denied_rate_percent));
        _set('accessDeniedDetail', `${t.denied || 0} lượt · 401 · 403`);
        _set('accessThrottledRate', formatValue('throttled_rate_percent', t.throttled_rate_percent));
        _set('accessThrottledDetail', `${t.throttled || 0} lượt · 429`);

        _set('accessLatency', t.avg_latency_ms != null ? `${t.avg_latency_ms.toFixed(0)}ms` : '—');
        _set('accessHttpP95', formatValue('http_p95_latency_ms', t.p95_latency_ms));

        // Disclose the percentile's sample base whenever it covers less than every
        // request, rather than implying it was computed over all of them.
        const samples = t.latency_sample_count;
        _set('accessHttpP95Detail',
            samples == null ? '—'
                : samples >= total ? `${formatValue('requests_total', samples)} mẫu · phủ 100%`
                    : `${formatValue('requests_total', samples)} / ${formatValue('requests_total', total)} request có đo thời gian`);

        _set('accessFailedLogins', formatValue('failed_dashboard_logins', t.failed_dashboard_logins));
        _set('accessHealthProbe', formatValue('requests_total', t.health_probe_failures));

        // Update paths table — the payload now carries real per-path errors. The old
        // fallback (`p.errors || 0`) printed a constant 0 in two columns beside real
        // measurements, and readers concluded no path was failing.
        const table = document.getElementById('accessPathsTable');
        if (data.breakdown_by_path && data.breakdown_by_path.length > 0) {
            const rows = data.breakdown_by_path.slice(0, 15).map(p => `
                <tr>
                    <td>${escapeHtml(p.path)}</td>
                    <td>${p.count}</td>
                    <td>${p.errors}</td>
                    <td>${p.error_rate_percent.toFixed(1)}%</td>
                </tr>
            `).join('');
            // The table is cut to the busiest paths, so its error column cannot reconcile
            // with the total on its own. Say so rather than leave the gap unexplained.
            const outside = t.errors_outside_top_paths || 0;
            table.innerHTML = rows + (outside > 0
                ? `<tr><td colspan="2"><em>Các đường dẫn ngoài bảng</em></td><td>${outside}</td><td>—</td></tr>`
                : '');
        } else {
            table.innerHTML = '<tr><td colspan="4">No data</td></tr>';
        }

        // Fire-and-forget: a slow comparison must not hold up the current figures.
        _renderCompare(t);
    } catch (err) {
        console.error('Failed to load access data:', err);
        _showError(err.message || String(err));
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
