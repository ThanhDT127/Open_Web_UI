// RAG Health tab — ingestion, retrieval and storage health.
// Data comes from /v1/_mw/rag-health/{ingestion,retrieval,storage}.
import { mwFetch, escapeHtml } from './utils.js';
import { buildRangeParams } from './filters.js';
import { formatValue, classify, minSample, renderDelta, clearDelta } from './metrics_registry.js';
import { loadCompare, side } from './compare_data.js';

let ingestChart = null;
let modelChart = null;
let loading = false;

// Use the dashboard-wide shared time range (same as the other tabs), then layer
// on the tab-specific model/user filters passed in `extra`.
function buildParams(extra = {}) {
    return buildRangeParams(extra);
}

function fmtPct(v) {
    return (v === null || v === undefined) ? '-' : Number(v).toFixed(1) + '%';
}

// A hit-rate of null means no answer was recorded to judge, which is not 0%.
// Rounding goes through the registry so this card, the Knowledge matrix and any
// future export cannot round differently.
function fmtHitRate(v) {
    return v == null ? '—' : formatValue('citation_hit_rate', v);
}

// ok/warn/danger accent on a metric card; null clears it (sample too small to judge).
function setCardState(cardId, state) {
    const el = document.getElementById(cardId);
    if (!el) return;
    el.classList.remove('ok', 'warn', 'danger');
    if (state) el.classList.add(state);
}

// Each section reads its own endpoint, so each owns a banner — mirroring ragStorError.
// They used to `return` silently on a failed fetch; the range resolver now answers 400 on
// malformed input instead of quietly substituting a default window, so that silence had
// become reachable and would have left the previous range's figures on screen unmarked.
//
// Three groups, all wiped together: values, tables, and the caption lines. The captions
// carry counts of their own ("36/359 lượt hỏi", "42 lượt không đọc được"), so a caption
// surviving under a dashed value states a figure for a window that was never read — the
// failure Phase 8 fixed on the Overview CSAT card.
const INGEST_SLOTS = [
    ['ragIngestCalls', 'ragIngestFailRate', 'ragIngestLatency'],
    [['ragIngestFailures', 4]],
    ['ragIngestFailCount'],
];
const RETRIEVAL_SLOTS = [
    ['ragRetrAttached', 'ragRetrCited', 'ragRetrHitRate', 'ragCoverage'],
    [['ragRetrBySource', 5], ['ragRetrZeroCite', 4]],
    ['ragRetrCitedDetail', 'ragRetrHitRateDetail', 'ragCoverageDetail',
     'ragRetrUnpairedNote', 'ragRetrModelNote'],
];

function setSectionError(bannerId, message, valueIds = [], tableIds = [], textIds = []) {
    const el = document.getElementById(bannerId);
    if (el) {
        el.textContent = message ? `Không đọc được dữ liệu: ${message}` : '';
        el.classList.toggle('hidden', !message);
    }
    if (!message) return;
    for (const id of valueIds) {
        const v = document.getElementById(id);
        if (v) v.textContent = '—';
        // A comparison badge outlives its card's numbers otherwise, and a delta against
        // a value no longer on screen is worse than none.
        clearDelta(id);
    }
    for (const [id, cols] of tableIds) {
        const t = document.getElementById(id);
        if (t) t.innerHTML = `<tr><td colspan="${cols}" class="loading">Không đọc được dữ liệu</td></tr>`;
    }
    for (const id of textIds) {
        const t = document.getElementById(id);
        if (t) t.textContent = '';
    }
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
                    label: 'Tỷ lệ nạp thất bại (%)', data: [], borderColor: '#ef4444',
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
                    label: 'Tỷ lệ trích được nguồn (%)', data: [], backgroundColor: '#3b82f6'
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
    if (!res || !res.ok) {
        setSectionError('ragIngestError', `HTTP ${res ? res.status : 'không kết nối được'}`, ...INGEST_SLOTS);
        return;
    }
    setSectionError('ragIngestError', '');
    const data = await res.json();
    const s = data.summary || {};

    document.getElementById('ragIngestCalls').textContent = s.total_calls ?? 0;
    document.getElementById('ragIngestFailRate').textContent = fmtPct(s.failure_rate);
    document.getElementById('ragIngestFailCount').textContent = `${(s.failures ?? 0).toLocaleString()} lượt lỗi`;
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
        </tr>`).join('') : '<tr><td colspan="4" class="loading">Không có lượt nạp nào thất bại trong khoảng này</td></tr>';

    // Fire-and-forget, and only when there is a current figure to compare against.
    if (s.total_calls != null) renderIngestionCompare(s.total_calls);
}

// ── Period comparison (Phase 9c) ────────────────────────────────
// A window with no embedding calls / no questions at all has nothing to compare against:
// its zeros mean "nothing happened", not "the value was zero". Returning null is what
// makes the badge print "—" instead of inventing a −100%.
const _pickIngestion = (json) => {
    const s = json && json.summary;
    return s && s.total_calls > 0 ? { embedding_calls: s.total_calls } : null;
};
// The minimum-sample rule itself now lives in renderDelta, so this function no longer
// applies it — it only has to CARRY the two denominators so renderDelta can.
//
// The two must stay separate. They are two points on one funnel: every question asked,
// then those with a document attached, then those whose answer was actually recorded.
// `evaluated` is therefore always the smaller of the two, in every environment, and the
// two shrink for unrelated reasons — attachment moves with how people work, pairing with
// the infrastructure (a request answered after the window closes is never paired, by
// design: the response CTE carries the same bounds). Collapsing them into one denominator
// would either publish a hit-rate measured off a handful of answers or suppress a coverage
// figure resting on thousands of questions.
const _pickRetrieval = (json) => {
    const c = json && json.coverage;
    if (!c || !c.total_requests) return null;
    return {
        citation_hit_rate: json.hit_rate,
        kb_coverage_percent: c.coverage_percent,
        evaluated: json.evaluated || 0,
        total_requests: c.total_requests,
    };
};

// Both of these still clear the old badge FIRST, and the reason narrowed rather than went
// away. renderDelta now clears the card itself before any of its own early returns, so the
// two paths that used to need this guard no longer do — a sample below the minimum and an
// empty comparison window both reach renderDelta and are handled inside it. What renderDelta
// cannot cover is the path where it is never called at all: if loadCompare rejects, control
// jumps straight to the catch, and without the clear below the previous range's delta would
// sit under the new range's number precisely when the data failed to load.
async function renderIngestionCompare(current) {
    clearDelta('ragIngestCalls');
    try {
        const cmp = await loadCompare('/v1/_mw/rag-health/ingestion', _pickIngestion);
        renderDelta('ragIngestCalls', 'embedding_calls', {
            current,
            kt: side(cmp.kt, 'embedding_calls'),
            ck: side(cmp.ck, 'embedding_calls'),
        });
    } catch (err) {
        console.error('RAG ingestion compare failed:', err);
    }
}

async function renderRetrievalCompare(data, evaluated, extra) {
    clearDelta('ragRetrHitRate');
    clearDelta('ragCoverage');

    const cov = data.coverage || {};
    try {
        // The tab-local model/user filters travel with the comparison windows too.
        // Without them the badge would measure a filtered present against an unfiltered
        // past and call the difference a trend.
        const cmp = await loadCompare('/v1/_mw/rag-health/retrieval', _pickRetrieval, { extra });
        // Each metric names its own denominator. `evaluated` counts answers we could read;
        // `total_requests` counts questions asked. See _pickRetrieval for why one shared
        // count cannot serve both.
        renderDelta('ragRetrHitRate', 'citation_hit_rate', {
            current: data.hit_rate,
            currentSample: evaluated,
            kt: side(cmp.kt, 'citation_hit_rate', 'evaluated'),
            ck: side(cmp.ck, 'citation_hit_rate', 'evaluated'),
        });
        renderDelta('ragCoverage', 'kb_coverage_percent', {
            current: cov.coverage_percent,
            currentSample: cov.total_requests || 0,
            kt: side(cmp.kt, 'kb_coverage_percent', 'total_requests'),
            ck: side(cmp.ck, 'kb_coverage_percent', 'total_requests'),
        });
    } catch (err) {
        console.error('RAG retrieval compare failed:', err);
    }
}

// ── Retrieval ──
async function loadRetrieval() {
    const extra = {
        model: document.getElementById('ragModel')?.value,
        user_id: document.getElementById('ragUser')?.value,
    };
    const res = await mwFetch(`/v1/_mw/rag-health/retrieval?${buildParams(extra)}`);
    if (!res || !res.ok) {
        setSectionError('ragRetrError', `HTTP ${res ? res.status : 'không kết nối được'}`, ...RETRIEVAL_SLOTS);
        return;
    }
    setSectionError('ragRetrError', '');
    const data = await res.json();

    const attached = data.kb_attached ?? 0;
    const evaluated = data.evaluated ?? 0;
    const unpaired = data.unpaired ?? 0;
    const floor = minSample('citation_hit_rate');

    document.getElementById('ragRetrAttached').textContent = attached.toLocaleString();
    document.getElementById('ragRetrCited').textContent = (data.cited ?? 0).toLocaleString();
    document.getElementById('ragRetrCitedDetail').textContent = evaluated > 0
        ? `Trên ${evaluated.toLocaleString()} câu trả lời đọc được`
        : 'Chưa đọc được câu trả lời nào để đếm';
    document.getElementById('ragRetrHitRate').textContent = fmtHitRate(data.hit_rate);
    // Keep the ⓘ: the element's title attribute (2000-char response truncation) is still
    // the only warning about late citation markers, and a tooltip nobody knows to hover
    // is not a warning.
    document.getElementById('ragRetrHitRateDetail').textContent =
        evaluated > 0 && evaluated < floor
            ? `Mẫu ${evaluated}/${floor} — chưa đủ để kết luận ⓘ`
            : 'Trên số câu trả lời đọc được ⓘ';
    // A colour is a verdict. Below the minimum the number stays, the verdict does not.
    setCardState('ragCardHitRate', classify('citation_hit_rate', data.hit_rate, evaluated));

    // ── Coverage (Phase 9b) ──
    // The detail line prints the numerator and denominator because neither is the
    // KB-Attached card next to it: that one counts every <source> tag, this one only the
    // shared knowledge bases. Ad-hoc uploads are named rather than folded in — people
    // reaching for their own file is a signal the shared corpus is missing something.
    const cov = data.coverage || {};
    const covTotal = cov.total_requests ?? 0;
    const covFloor = minSample('kb_coverage_percent');
    document.getElementById('ragCoverage').textContent =
        cov.coverage_percent == null ? '—' : formatValue('kb_coverage_percent', cov.coverage_percent);
    const covParts = [`${(cov.kb_requests ?? 0).toLocaleString()}/${covTotal.toLocaleString()} lượt hỏi`];
    if (cov.adhoc_requests) covParts.push(`${cov.adhoc_requests.toLocaleString()} lượt kéo file riêng`);
    if (covTotal > 0 && covTotal < covFloor) covParts.push(`mẫu ${covTotal}/${covFloor}`);
    if (covTotal === 0) covParts.length = 0;
    document.getElementById('ragCoverageDetail').textContent =
        covParts.length ? `${covParts.join(' · ')} ⓘ` : 'Chưa có lượt hỏi nào trong khoảng này ⓘ';

    // Silent when every answer was recorded; loud when they were not.
    const noteEl = document.getElementById('ragRetrUnpairedNote');
    if (noteEl) {
        noteEl.innerHTML = unpaired > 0
            ? `<span title="Không tìm thấy sự kiện chat.response cho các request này — câu trả lời có thể đã trích dẫn tốt, mình chỉ không ghi lại. Câu trả lời dạng streaming chỉ bắt đầu được ghi từ 01/07/2026.">⚠️ ${unpaired.toLocaleString()}/${attached.toLocaleString()} lượt không đọc được câu trả lời — không tính vào tỷ lệ trích dẫn</span>`
            : '';
    }

    const byModel = data.by_model || [];
    mergeOptions('ragModel', byModel.map(m => m.model), 'All Models');
    // Models with nothing evaluated are dropped rather than plotted as a 0% bar — a bar
    // at zero reads as a measured result. Dropping them silently swaps one wrong reading
    // for another, so the count of what was dropped is stated above the chart.
    const plotted = byModel.filter(m => m.hit_rate != null);
    const skipped = byModel.length - plotted.length;
    const modelNote = document.getElementById('ragRetrModelNote');
    if (modelNote) {
        modelNote.textContent = skipped > 0
            ? `${skipped}/${byModel.length} model không vẽ được — chưa đọc được câu trả lời nào để tính tỷ lệ`
            : '';
    }
    if (ensureCharts() && modelChart) {
        modelChart.data.labels = plotted.map(m => m.model);
        modelChart.data.datasets[0].data = plotted.map(m => m.hit_rate);
        modelChart.update();
    }

    const srcBody = document.getElementById('ragRetrBySource');
    const bySource = data.by_source || [];
    srcBody.innerHTML = bySource.length ? bySource.map(s => `
        <tr>
            <td>${escapeHtml(s.source)}</td>
            <td>${s.attached}</td>
            <td>${s.evaluated}</td>
            <td>${s.cited}</td>
            <td>${escapeHtml(fmtHitRate(s.hit_rate))}</td>
        </tr>`).join('') : '<tr><td colspan="5" class="loading">Không có câu hỏi nào được kèm tài liệu trong khoảng này</td></tr>';

    // Populated from everyone who attached a document, not just from those who had a
    // miss — otherwise the filter can only offer users the tab already blamed.
    mergeOptions('ragUser', (data.by_user || []).map(u => u.user_id), 'All Users');

    const zeroBody = document.getElementById('ragRetrZeroCite');
    const zero = data.zero_citation_messages || [];
    zeroBody.innerHTML = zero.length ? zero.map(z => `
        <tr>
            <td>${escapeHtml(fmtTs(z.ts))}</td>
            <td>${escapeHtml(z.user_id || '-')}</td>
            <td>${escapeHtml(z.model || '-')}</td>
            <td>${escapeHtml(z.question_preview || '-')}</td>
        </tr>`).join('')
        // 🎉 only when there was something to check. With nothing evaluated an empty
        // table means "we could not look", and celebrating that is the same mistake
        // the hit-rate itself used to make.
        : (evaluated > 0
            ? '<tr><td colspan="4" class="loading">Mọi câu trả lời đọc được đều có trích nguồn 🎉</td></tr>'
            : '<tr><td colspan="4" class="loading">Chưa đọc được câu trả lời nào trong khoảng này — không kết luận được</td></tr>');

    // Fire-and-forget: a slow comparison must not hold up the figures already on screen.
    renderRetrievalCompare(data, evaluated, extra);
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
        </tr>`).join('') : '<tr><td colspan="4" class="loading">Không có kho nào như vậy 🎉</td></tr>';

    document.getElementById('ragStorOrphanTable').innerHTML = orphan.length ? orphan.map(o => `
        <tr>
            <td>${escapeHtml(o.collection_name || '-')}</td>
            <td>${o.chunk_count}</td>
        </tr>`).join('') : '<tr><td colspan="2" class="loading">Không có dữ liệu sót nào 🎉</td></tr>';

    document.getElementById('ragStorOutlierTable').innerHTML = outlier.length ? outlier.map(o => `
        <tr>
            <td>${escapeHtml(o.filename || '-')}</td>
            <td>${escapeHtml(o.owner || '-')}</td>
            <td>${o.size_bytes ?? '-'}</td>
            <td>${o.chunk_count}</td>
            <td>${o.expected_count}</td>
        </tr>`).join('') : '<tr><td colspan="5" class="loading">Không có file nào bất thường 🎉</td></tr>';
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
