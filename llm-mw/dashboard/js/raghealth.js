// RAG Health tab — ingestion, retrieval and storage health.
// Data comes from /v1/_mw/rag-health/{ingestion,retrieval,storage}.
import { mwFetch, escapeHtml } from './utils.js';
import { currentTimeRange } from './filters.js';

let ingestChart = null;
let modelChart = null;
let loading = false;

// Use the dashboard-wide shared time range (same as the other tabs), then layer
// on the tab-specific model/user filters passed in `extra`.
function buildParams(extra = {}) {
    const params = new URLSearchParams();
    if (currentTimeRange?.minutes) {
        params.append('start', new Date(Date.now() - currentTimeRange.minutes * 60000).toISOString().replace('Z', '+00:00'));
        params.append('end', new Date().toISOString().replace('Z', '+00:00'));
    } else if (currentTimeRange?.start && currentTimeRange?.end) {
        params.append('start', currentTimeRange.start);
        params.append('end', currentTimeRange.end);
    }
    for (const [k, v] of Object.entries(extra)) {
        if (v) params.append(k, v);
    }
    return params;
}

function fmtPct(v) {
    return (v === null || v === undefined) ? '-' : Number(v).toFixed(1) + '%';
}

function fmtTs(ts) {
    return ts ? new Date(ts).toLocaleString() : '-';
}

// ── Charts (lazy init; Chart.js may not be ready on first paint) ──
function ensureCharts() {
    if (typeof Chart === 'undefined') return false;
    if (!ingestChart) {
        const el = document.getElementById('ragIngestChart');
        if (el) {
            ingestChart = new Chart(el.getContext('2d'), {
                type: 'line',
                data: { labels: [], datasets: [{
                    label: 'Failure Rate (%)', data: [], borderColor: '#ef4444',
                    backgroundColor: '#ef444422', tension: 0.3, fill: true, borderWidth: 2, pointRadius: 2
                }] },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { ticks: { color: '#64748b', font: { size: 11 } }, grid: { color: '#1e293b' } },
                        y: { beginAtZero: true, max: 100, ticks: { color: '#64748b', font: { size: 11 } }, grid: { color: '#1e293b' } }
                    }
                }
            });
        }
    }
    if (!modelChart) {
        const el = document.getElementById('ragRetrModelChart');
        if (el) {
            modelChart = new Chart(el.getContext('2d'), {
                type: 'bar',
                data: { labels: [], datasets: [{
                    label: 'Hit-Rate (%)', data: [], backgroundColor: '#3b82f6'
                }] },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { ticks: { color: '#64748b', font: { size: 11 } }, grid: { color: '#1e293b' } },
                        y: { beginAtZero: true, max: 100, ticks: { color: '#64748b', font: { size: 11 } }, grid: { color: '#1e293b' } }
                    }
                }
            });
        }
    }
    return true;
}

// Keep the model/user dropdowns populated from observed data (preserve selection).
function mergeOptions(selectId, values, allLabel) {
    const sel = document.getElementById(selectId);
    if (!sel) return;
    const current = sel.value;
    const existing = new Set(Array.from(sel.options).map(o => o.value).filter(Boolean));
    for (const v of values) {
        if (v && !existing.has(v)) {
            const opt = document.createElement('option');
            opt.value = v;
            opt.textContent = v;
            sel.appendChild(opt);
            existing.add(v);
        }
    }
    sel.value = current;
}

// ── Ingestion ──
async function loadIngestion() {
    const res = await mwFetch(`/v1/_mw/rag-health/ingestion?${buildParams()}`);
    if (!res || !res.ok) return;
    const data = await res.json();
    const s = data.summary || {};

    document.getElementById('ragIngestCalls').textContent = s.total_calls ?? 0;
    document.getElementById('ragIngestFailRate').textContent = fmtPct(s.failure_rate);
    document.getElementById('ragIngestFailCount').textContent = `${s.failures ?? 0} failures`;
    document.getElementById('ragIngestLatency').textContent =
        s.avg_latency_ms != null ? `${s.avg_latency_ms.toFixed(0)}ms` : '-';

    if (ensureCharts() && ingestChart) {
        const ts = s.timeseries || [];
        ingestChart.data.labels = ts.map(b => new Date(b.ts).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }));
        ingestChart.data.datasets[0].data = ts.map(b => b.failure_rate || 0);
        ingestChart.update();
    }

    const tbody = document.getElementById('ragIngestFailures');
    const failures = data.recent_failures || [];
    tbody.innerHTML = failures.length ? failures.map(f => `
        <tr>
            <td>${escapeHtml(fmtTs(f.ts))}</td>
            <td>${escapeHtml(f.user_id || '-')}</td>
            <td>${escapeHtml(f.error_type || '-')}</td>
            <td>${escapeHtml(f.error_message || '-')}</td>
        </tr>`).join('') : '<tr><td colspan="4" class="loading">No failures in range</td></tr>';
}

// ── Retrieval ──
async function loadRetrieval() {
    const extra = {
        model: document.getElementById('ragModel')?.value,
        user_id: document.getElementById('ragUser')?.value,
    };
    const res = await mwFetch(`/v1/_mw/rag-health/retrieval?${buildParams(extra)}`);
    if (!res || !res.ok) return;
    const data = await res.json();

    document.getElementById('ragRetrAttached').textContent = data.kb_attached ?? 0;
    document.getElementById('ragRetrCited').textContent = data.cited ?? 0;
    document.getElementById('ragRetrHitRate').textContent = fmtPct(data.hit_rate);

    const byModel = data.by_model || [];
    mergeOptions('ragModel', byModel.map(m => m.model), 'All Models');
    if (ensureCharts() && modelChart) {
        modelChart.data.labels = byModel.map(m => m.model);
        modelChart.data.datasets[0].data = byModel.map(m => m.hit_rate || 0);
        modelChart.update();
    }

    const srcBody = document.getElementById('ragRetrBySource');
    const bySource = data.by_source || [];
    srcBody.innerHTML = bySource.length ? bySource.map(s => `
        <tr>
            <td>${escapeHtml(s.source)}</td>
            <td>${s.attached}</td>
            <td>${s.cited}</td>
            <td>${escapeHtml(fmtPct(s.hit_rate))}</td>
        </tr>`).join('') : '<tr><td colspan="4" class="loading">No KB-attached messages in range</td></tr>';

    const zeroBody = document.getElementById('ragRetrZeroCite');
    const zero = data.zero_citation_messages || [];
    mergeOptions('ragUser', zero.map(z => z.user_id), 'All Users');
    zeroBody.innerHTML = zero.length ? zero.map(z => `
        <tr>
            <td>${escapeHtml(fmtTs(z.ts))}</td>
            <td>${escapeHtml(z.user_id || '-')}</td>
            <td>${escapeHtml(z.model || '-')}</td>
            <td>${escapeHtml(z.question_preview || '-')}</td>
        </tr>`).join('') : '<tr><td colspan="4" class="loading">No zero-citation messages 🎉</td></tr>';
}

// ── Storage ──
async function loadStorage() {
    const res = await mwFetch('/v1/_mw/rag-health/storage');
    if (!res || !res.ok) return;
    const data = await res.json();

    const errEl = document.getElementById('ragStorError');
    if (data.error) {
        errEl.textContent = `Storage query unavailable: ${data.error}`;
        errEl.classList.remove('hidden');
    } else {
        errEl.classList.add('hidden');
    }

    const zeroKB = data.zero_chunk_kbs || [];
    const orphan = data.orphaned_chunks || [];
    const outlier = data.chunk_count_outliers || [];

    document.getElementById('ragStorZeroKB').textContent = zeroKB.length;
    document.getElementById('ragStorOrphan').textContent = orphan.length;
    document.getElementById('ragStorOutlier').textContent = outlier.length;

    document.getElementById('ragStorZeroKBTable').innerHTML = zeroKB.length ? zeroKB.map(k => `
        <tr>
            <td>${escapeHtml(k.name || '-')}</td>
            <td>${escapeHtml(k.owner || '-')}</td>
            <td>${escapeHtml(fmtTs(k.created_at))}</td>
            <td>${k.file_count}</td>
        </tr>`).join('') : '<tr><td colspan="4" class="loading">None 🎉</td></tr>';

    document.getElementById('ragStorOrphanTable').innerHTML = orphan.length ? orphan.map(o => `
        <tr>
            <td>${escapeHtml(o.collection_name || '-')}</td>
            <td>${o.chunk_count}</td>
        </tr>`).join('') : '<tr><td colspan="2" class="loading">None 🎉</td></tr>';

    document.getElementById('ragStorOutlierTable').innerHTML = outlier.length ? outlier.map(o => `
        <tr>
            <td>${escapeHtml(o.filename || '-')}</td>
            <td>${escapeHtml(o.owner || '-')}</td>
            <td>${o.size_bytes ?? '-'}</td>
            <td>${o.chunk_count}</td>
            <td>${o.expected_count}</td>
        </tr>`).join('') : '<tr><td colspan="5" class="loading">None 🎉</td></tr>';
}

export async function loadRagHealth() {
    if (loading) return;
    loading = true;
    try {
        await Promise.all([loadIngestion(), loadRetrieval(), loadStorage()]);
    } catch (err) {
        console.error('Failed to load RAG health:', err);
    } finally {
        loading = false;
    }
}

export function applyRagFilters() {
    loadRagHealth();
}

export function resetRagFilters() {
    // Time range is the shared dashboard control; only the tab-local filters reset here.
    ['ragModel', 'ragUser'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
    loadRagHealth();
}
