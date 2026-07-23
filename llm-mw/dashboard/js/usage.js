// Usage tab logic - metrics, expanded tables, chart data, audit stream
import { mwFetch, updateStatus } from './utils.js';
import { buildRangeParams } from './filters.js';
import { addAuditEvent, clearAuditEvents } from './filters.js';
import { eventSource, setEventSource, setRetryCount, retryCount, MAX_RETRY_DELAY } from './auth.js';
import { renderDelta, formatValue } from './metrics_registry.js';
import { loadCompare, side } from './compare_data.js';

// Cache latest data for re-rendering on sort/top-N change
let _lastSummaryData = null;

// Accessor so other tabs (e.g. Overview) can reuse the global-range summary
// without issuing a duplicate /summary fetch.
export function getLastSummary() {
    return _lastSummaryData;
}

// Load summary data
export async function loadSummary() {
    try {
        updateStatus('ok', 'Loading data...');

        const params = buildRangeParams();

        const res = await mwFetch(`/v1/_mw/summary?${params}`);
        if (!res) return;
        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const data = await res.json();
        _lastSummaryData = data;

        // Notify dependent tabs (Overview) that fresh global-range summary is available
        try { document.dispatchEvent(new CustomEvent('summary:updated', { detail: data })); } catch (e) { /* noop */ }

        if (!data || !data.totals) {
            document.getElementById('topUsersTable').innerHTML = '<tr><td colspan="8" class="no-data">No data in selected time range.<br>Try "Last 7d" or "Last 30d"</td></tr>';
            document.getElementById('topModelsTable').innerHTML = '<tr><td colspan="8" class="no-data">No data in selected time range.<br>Try "Last 7d" or "Last 30d"</td></tr>';
            updateStatus('warning', 'No data in selected time range');
            return;
        }

        _renderMetrics(data.totals);
        _renderCompare(data.totals);   // fire-and-forget: badges must never gate the cards
        _renderTables(data);
        _updateInsights(data);

        // Update charts
        const { updateCharts } = await import('./charts.js');
        updateCharts(data);

        updateStatus('ok', 'Authenticated ✓');
    } catch (err) {
        console.error('Failed to load summary:', err);
        updateStatus('error', `Load error: ${err.message}`);
    }
}

// Re-render tables + insights + charts (on sort/top-N change)
export async function refreshTables() {
    if (_lastSummaryData) {
        _renderTables(_lastSummaryData);

        // Get current sort selections
        const sortByUser = document.getElementById('topUsersSortBy')?.value || 'cost';
        const sortByModel = document.getElementById('topModelsSortBy')?.value || 'cost';

        // Get sorted/sliced data
        const displayedUsers = _getSortedSlice(_lastSummaryData.breakdown_by_user || [], sortByUser, 'topUsersCount');
        const displayedModels = _getSortedSlice(_lastSummaryData.breakdown_by_model || [], sortByModel, 'topModelsCount');

        // Update insights with sorted data and sort criteria
        _updateInsights(_lastSummaryData, displayedUsers, sortByUser, displayedModels, sortByModel);

        // Sync doughnut charts with current Top-N/Sort selection
        const { updateUserCostChart, updateModelCostChart } = await import('./charts.js');
        updateUserCostChart(displayedUsers);
        updateModelCostChart(displayedModels);
    }
}

// ─── Metrics rendering ───────────────────────────────────────

function _renderMetrics(t) {
    document.getElementById('metricLLMCalls').textContent = (t.requests_total || 0).toLocaleString();
    document.getElementById('metricChat').textContent = t.chat_calls || 0;
    const embedEl = document.getElementById('metricEmbedding');
    if (embedEl) embedEl.textContent = t.embedding_calls || 0;
    document.getElementById('metricImage').textContent = t.image_calls || 0;
    document.getElementById('metricAudio').textContent = t.audio_calls || 0;

    const videoEl = document.getElementById('metricVideo');
    if (videoEl) videoEl.textContent = t.video_calls || 0;

    document.getElementById('metricCost').textContent = '$' + (t.cost_total_usd || 0).toFixed(4);
    document.getElementById('metricTokens').textContent = (t.tokens_total || 0).toLocaleString();
    document.getElementById('metricLatency').textContent = t.p95_latency_ms ? t.p95_latency_ms.toFixed(0) + 'ms' : '-';

    const errorRate = t.requests_total > 0 ? ((t.error_count || 0) / t.requests_total * 100) : 0;
    document.getElementById('metricErrorRate').textContent = errorRate.toFixed(1) + '%';
    const errCountEl = document.getElementById('metricErrorCount');
    if (errCountEl) errCountEl.textContent = `${t.error_count || 0} errors`;

    const billableElem = document.getElementById('metricBillableCalls');
    if (billableElem) billableElem.textContent = t.billable_calls || 0;

    const usageMissingElem = document.getElementById('metricUsageMissing');
    if (usageMissingElem) {
        const m = t.usage_missing_calls || 0;
        usageMissingElem.textContent = m;
        if (m > 0) usageMissingElem.parentElement.classList.add('warning');
        else usageMissingElem.parentElement.classList.remove('warning');
    }

    document.getElementById('metricPending').textContent = t.pending_open_count || 0;

    // ── Request lens (Phase 3) — values formatted from the registry ──
    const _set = (id, key) => {
        const el = document.getElementById(id);
        if (el) el.textContent = formatValue(key, t[key]);
    };
    _set('metricP50', 'p50_latency_ms');
    _set('metricP99', 'p99_latency_ms');
    _set('metricMaxLatency', 'max_latency_ms');
    _set('metricCostPerReq', 'cost_per_request');
    _set('metricCostPer1k', 'cost_per_1k_tokens');
    _set('metricAvgTokens', 'avg_tokens_per_request');
    _set('metricInOutRatio', 'tokens_in_out_ratio');
    _set('metricRpmAvg', 'rpm_avg');
    _set('metricRpmPeak', 'rpm_peak');
    _set('metricPendingAge', 'pending_oldest_age_sec');

    // Peak resolution: say which bucket the peak was measured over (per-minute exact
    // only when buckets are minutes; hourly/daily on longer ranges smooth it).
    const peakDetail = document.getElementById('metricRpmPeakDetail');
    if (peakDetail && t.rpm_peak_bucket) {
        const unit = { minute: 'phút', hour: 'giờ', day: 'ngày' }[t.rpm_peak_bucket] || t.rpm_peak_bucket;
        peakDetail.textContent = `Requests / phút · đỉnh đo theo ${unit}`;
    }
}

// A window with no requests at all is "no data", not "zero change" — returning null
// here is what makes the badge render an em dash instead of a fabricated 0%.
function _pickTotals(json) {
    const t = json && json.totals;
    return t && t.requests_total > 0 ? t : null;
}

// Card id -> metric key in the registry. `metricPending` is listed on purpose: the
// registry blocks it, so this proves the block rather than leaving it to chance.
const _COMPARE_CARDS = [
    ['metricLLMCalls', 'requests_total'],
    ['metricCost', 'cost_total_usd'],
    ['metricTokens', 'tokens_total'],
    ['metricLatency', 'p95_latency_ms'],
    ['metricErrorRate', 'error_rate_percent'],
    ['metricBillableCalls', 'billable_calls'],
    ['metricPending', 'pending_open_count'],
    // Request lens (Phase 3) — windowed metrics get a KT/CK badge automatically.
    ['metricP50', 'p50_latency_ms'],
    ['metricP99', 'p99_latency_ms'],
    ['metricMaxLatency', 'max_latency_ms'],
    ['metricCostPerReq', 'cost_per_request'],
    ['metricCostPer1k', 'cost_per_1k_tokens'],
    ['metricAvgTokens', 'avg_tokens_per_request'],
    ['metricInOutRatio', 'tokens_in_out_ratio'],
    ['metricRpmAvg', 'rpm_avg'],
    ['metricRpmPeak', 'rpm_peak'],
    // Listed on purpose though compare:false — proves the registry block is enforced,
    // not merely declared (no badge should appear).
    ['metricPendingAge', 'pending_oldest_age_sec'],
];

async function _renderCompare(t) {
    try {
        const cmp = await loadCompare('/v1/_mw/summary', _pickTotals);
        for (const [elementId, key] of _COMPARE_CARDS) {
            renderDelta(elementId, key, {
                current: t[key],
                kt: side(cmp.kt, key),
                ck: side(cmp.ck, key),
            });
        }
    } catch (err) {
        console.error('Compare badges failed:', err);
    }
}

// ─── Tables rendering ────────────────────────────────────────

function _renderTables(data) {
    _renderUsersTable(data.breakdown_by_user || []);
    _renderModelsTable(data.breakdown_by_model || []);
}

function _getSortedSlice(items, sortKey, countElId) {
    const count = parseInt(document.getElementById(countElId)?.value || '10');
    const sortBy = sortKey;

    const sortFns = {
        cost: (a, b) => (b.cost_usd || 0) - (a.cost_usd || 0),
        requests: (a, b) => (b.requests_total || 0) - (a.requests_total || 0),
        tokens: (a, b) => (b.tokens_total || 0) - (a.tokens_total || 0),
        latency: (a, b) => (b.p95_latency_ms || 0) - (a.p95_latency_ms || 0),
        errors: (a, b) => (b.error_rate_percent || 0) - (a.error_rate_percent || 0)
    };

    const sorted = [...items].sort(sortFns[sortBy] || sortFns.cost);
    return sorted.slice(0, count);
}

function _renderUsersTable(users) {
    const table = document.getElementById('topUsersTable');
    if (!users.length) {
        table.innerHTML = '<tr><td colspan="8" class="no-data">No user data</td></tr>';
        return;
    }

    const sortBy = document.getElementById('topUsersSortBy')?.value || 'cost';
    const displayed = _getSortedSlice(users, sortBy, 'topUsersCount');
    const totalCost = users.reduce((s, u) => s + (u.cost_usd || 0), 0);

    table.innerHTML = displayed.map((u, i) => {
        const share = totalCost > 0 ? ((u.cost_usd || 0) / totalCost * 100) : 0;
        const errClass = (u.error_rate_percent || 0) > 5 ? 'text-red' : '';
        return `<tr>
            <td class="rank">${i + 1}</td>
            <td class="user-id">${u.user_id}</td>
            <td>${(u.requests_total || 0).toLocaleString()}</td>
            <td>${(u.tokens_total || 0).toLocaleString()}</td>
            <td class="cost">$${(u.cost_usd || 0).toFixed(4)}</td>
            <td>${u.p95_latency_ms ? u.p95_latency_ms.toFixed(0) + 'ms' : '-'}</td>
            <td class="${errClass}">${(u.error_rate_percent || 0).toFixed(1)}%</td>
            <td>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: ${Math.min(share, 100)}%"></div>
                    <span class="progress-text">${share.toFixed(1)}%</span>
                </div>
            </td>
        </tr>`;
    }).join('');
}

function _renderModelsTable(models) {
    const table = document.getElementById('topModelsTable');
    if (!models.length) {
        table.innerHTML = '<tr><td colspan="8" class="no-data">No model data</td></tr>';
        return;
    }

    const sortBy = document.getElementById('topModelsSortBy')?.value || 'cost';
    const displayed = _getSortedSlice(models, sortBy, 'topModelsCount');

    table.innerHTML = displayed.map((m, i) => {
        const avgCost = (m.requests_total || 0) > 0 ? (m.cost_usd || 0) / m.requests_total : 0;
        const errClass = (m.error_rate_percent || 0) > 5 ? 'text-red' : '';
        const costTag = avgCost > 0.01 ? '<span class="tag tag-expensive">💲 expensive</span>' :
            avgCost > 0.001 ? '' :
                '<span class="tag tag-cheap">💚 cheap</span>';
        return `<tr>
            <td class="rank">${i + 1}</td>
            <td class="model-name">${m.model || 'unknown'} ${costTag}</td>
            <td>${(m.requests_total || 0).toLocaleString()}</td>
            <td>${(m.tokens_total || 0).toLocaleString()}</td>
            <td class="cost">$${(m.cost_usd || 0).toFixed(4)}</td>
            <td>$${avgCost.toFixed(4)}</td>
            <td>${m.p95_latency_ms ? m.p95_latency_ms.toFixed(0) + 'ms' : '-'}</td>
            <td class="${errClass}">${(m.error_rate_percent || 0).toFixed(1)}%</td>
        </tr>`;
    }).join('');
}

// ─── Insight text ────────────────────────────────────────────

function _updateInsights(data, displayedUsers, userSortBy, displayedModels, modelSortBy) {
    const t = data.totals || {};
    const allUsers = data.breakdown_by_user || [];
    const allModels = data.breakdown_by_model || [];
    const tr = data.time_range || {};

    // Use displayed data if provided, otherwise fall back to all data
    const users = displayedUsers || allUsers;
    const models = displayedModels || allModels;
    const uSort = userSortBy || 'cost';
    const mSort = modelSortBy || 'cost';

    // Time label
    let timeLabel = '';
    if (tr.start && tr.end) {
        const s = new Date(tr.start);
        const e = new Date(tr.end);
        const fmtOpts = { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' };
        timeLabel = `(${s.toLocaleString('vi-VN', fmtOpts)} → ${e.toLocaleString('vi-VN', fmtOpts)})`;
    }

    // Overview insight (always shows totals, independent of sort)
    const overviewEl = document.getElementById('insightOverview');
    if (overviewEl) {
        if (t.requests_total > 0) {
            const costPerReq = t.cost_total_usd / t.requests_total;
            overviewEl.textContent = `${timeLabel} ${t.requests_total} requests | $${t.cost_total_usd.toFixed(4)} total | ~$${costPerReq.toFixed(4)}/req | ${(t.tokens_total || 0).toLocaleString()} tokens`;
        } else {
            overviewEl.textContent = `${timeLabel} Không có dữ liệu trong khoảng thời gian này. Thử chọn khoảng rộng hơn.`;
        }
    }

    // Sort-aware metric formatters
    const sortLabels = {
        cost: { icon: '💰', label: 'chi phí', fmt: u => `$${(u.cost_usd || 0).toFixed(4)}` },
        requests: { icon: '📊', label: 'requests', fmt: u => `${(u.requests_total || 0).toLocaleString()} requests` },
        tokens: { icon: '🔤', label: 'tokens', fmt: u => `${(u.tokens_total || 0).toLocaleString()} tokens` },
        latency: { icon: '⏱', label: 'latency', fmt: u => `${(u.p95_latency_ms || 0).toFixed(0)}ms` },
        errors: { icon: '⚠️', label: 'error rate', fmt: u => `${(u.error_rate_percent || 0).toFixed(1)}%` }
    };

    // Users insight — reflects current sort
    const usersEl = document.getElementById('insightUsers');
    if (usersEl) {
        if (users.length > 0) {
            const top = users[0];
            const totalCost = allUsers.reduce((s, u) => s + (u.cost_usd || 0), 0);
            const share = totalCost > 0 ? (top.cost_usd / totalCost * 100).toFixed(0) : 0;
            const sm = sortLabels[uSort] || sortLabels.cost;
            usersEl.textContent = `${timeLabel} 🏆 ${top.user_id} dẫn đầu ${sm.label} (${sm.fmt(top)}, chiếm ${share}% cost) | ${allUsers.length} users active.`;
        } else {
            usersEl.textContent = `${timeLabel} Chưa có dữ liệu user.`;
        }
    }

    // Models insight — reflects current sort
    const modelsEl = document.getElementById('insightModels');
    if (modelsEl) {
        if (models.length > 0) {
            const topModel = models[0];
            const sm = sortLabels[mSort] || sortLabels.cost;
            // Also find most popular by requests (if not already sorting by requests)
            let popularText = '';
            if (mSort !== 'requests') {
                const byReq = [...allModels].sort((a, b) => (b.requests_total || 0) - (a.requests_total || 0));
                if (byReq.length > 0) {
                    popularText = ` | 🔥 ${byReq[0].model} phổ biến nhất (${byReq[0].requests_total} requests)`;
                }
            }
            modelsEl.textContent = `${timeLabel} ${sm.icon} ${topModel.model} dẫn đầu ${sm.label} (${sm.fmt(topModel)})${popularText} | ${allModels.length} models.`;
        } else {
            modelsEl.textContent = `${timeLabel} Chưa có dữ liệu model.`;
        }
    }
}

// ─── Event stream ────────────────────────────────────────────

export function connectEventStream() {
    const eventsDiv = document.getElementById('events');

    if (eventSource) {
        eventSource.close();
        setEventSource(null);
    }

    eventsDiv.innerHTML = '<div class="loading">Connecting to event stream...</div>';

    try {
        const es = new EventSource('/v1/_mw/stream');
        setEventSource(es);

        es.addEventListener('audit', (e) => {
            try {
                const data = JSON.parse(e.data);
                addAuditEvent(data);
                setRetryCount(0);
            } catch (err) {
                console.error('Failed to parse event:', err);
            }
        });

        es.onerror = async (e) => {
            console.error('EventSource error:', e);
            if (es.readyState === EventSource.CLOSED) {
                try {
                    const testRes = await fetch('/v1/_mw/summary?minutes=1', { credentials: 'include' });
                    if (testRes.status === 403) {
                        eventsDiv.innerHTML = '<div class="error-msg">Authentication required.</div>';
                        const { stopDashboard } = await import('./main.js');
                        stopDashboard();
                        const { showLoginUI } = await import('./auth.js');
                        showLoginUI('Session expired. Please login again.');
                        return;
                    }
                } catch (testErr) { /* ignore */ }

                const newRetryCount = retryCount + 1;
                setRetryCount(newRetryCount);
                const delays = [1000, 2000, 5000, 10000, MAX_RETRY_DELAY];
                const delay = delays[Math.min(newRetryCount - 1, delays.length - 1)];

                eventsDiv.innerHTML = `<div class="error-msg">Stream disconnected. Retrying in ${delay / 1000}s... (attempt ${newRetryCount})</div>`;
                updateStatus('warning', `Stream disconnected, retry ${newRetryCount}`);

                setTimeout(() => {
                    if (document.getElementById('dashboard').classList.contains('hidden')) return;
                    connectEventStream();
                }, delay);
            } else {
                eventsDiv.innerHTML = '<div class="loading">Stream connection error, retrying...</div>';
            }
        };

        es.onopen = () => {
            clearAuditEvents();
            eventsDiv.innerHTML = '';
            setRetryCount(0);
            updateStatus('ok', 'Authenticated ✓ (Stream connected)');
        };
    } catch (err) {
        console.error('Failed to create EventSource:', err);
        eventsDiv.innerHTML = '<div class="error-msg">Failed to connect stream.</div>';
        updateStatus('error', 'Stream connection failed');
    }
}
