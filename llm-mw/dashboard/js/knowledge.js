// Knowledge Analytics tab — inventory, KB value matrix and governance.
// Data comes from /v1/_mw/knowledge-analytics/{inventory,kb-value,governance}.
import { mwFetch, escapeHtml } from './utils.js';
import { buildRangeParams } from './filters.js';
import { formatValue } from './metrics_registry.js';

let growthChart = null;
let loading = false;

const CATEGORY_LABEL = {
    star: '⭐ Star',
    needs_tuning: '🛠️ Needs Tuning',
    dead: '💀 Dead',
    unproven: '🌱 Unproven',
};

function buildParams(extra = {}) {
    // Uses the dashboard-wide shared time range (same as the other tabs).
    return buildRangeParams(extra);
}

function fmtBytes(n) {
    if (n === null || n === undefined) return '-';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let v = Number(n), i = 0;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
    return `${v.toFixed(v >= 100 || i === 0 ? 0 : 1)} ${units[i]}`;
}

function fmtTs(ts) {
    return ts ? new Date(ts).toLocaleString() : '—';
}

// The three knowledge endpoints answer 200 with an `error` field and zeroed bodies when
// their query fails. That body is indistinguishable from a healthy install that simply
// has no knowledge bases, so painting it would state "the corpus is empty" on the
// strength of a dead connection. Show the reason and paint nothing.
//
// Returns true when the section may be rendered.
function sectionOk(bannerId, data, valueIds, tableIds) {
    const err = data && data.error;
    if (err) sectionFailed(bannerId, err, valueIds, tableIds);
    else {
        const el = document.getElementById(bannerId);
        if (el) { el.textContent = ''; el.classList.add('hidden'); }
    }
    return !err;
}

// A transport-level failure (500, network down) never reaches the `error` field, so it
// needs the same treatment. Both paths also wipe the section's figures: a banner above
// numbers left over from the previously selected range still reads as though those
// numbers describe the range now on screen — the same trap the Overview CSAT card was
// fixed for in Phase 8.
function sectionFailed(bannerId, message, valueIds = [], tableIds = []) {
    const el = document.getElementById(bannerId);
    if (el) {
        el.textContent = `Không đọc được dữ liệu: ${message}`;
        el.classList.remove('hidden');
    }
    for (const id of valueIds) {
        const v = document.getElementById(id);
        if (v) v.textContent = '—';
    }
    for (const [id, cols] of tableIds) {
        const t = document.getElementById(id);
        if (t) t.innerHTML = `<tr><td colspan="${cols}" class="loading">Không đọc được dữ liệu</td></tr>`;
    }
}

// A KB attached many times whose answers were never logged has no hit-rate — the dash
// says "not measured", which is a different statement from "measured and it was 0%".
// Two dashes that look alike must not mean opposite things, so each carries its reason.
function hitRateCell(r) {
    const unpaired = r.unpaired || 0;
    if (r.hit_rate == null) {
        const why = r.attach_count
            ? `Đính kèm ${r.attach_count} lượt nhưng không đọc được câu trả lời nào (${unpaired} lượt) — chưa đủ căn cứ để chấm chất lượng`
            : 'Chưa từng được đính kèm trong khoảng này';
        return `<span title="${escapeHtml(why)}" style="color:#64748b;">—</span>`;
    }
    const text = escapeHtml(formatValue('citation_hit_rate', r.hit_rate));
    if (!unpaired) return text;
    return `<span title="${escapeHtml(`Tính trên ${r.evaluated} câu trả lời đọc được; ${unpaired} lượt khác không ghi được câu trả lời`)}">${text} <span style="color:#64748b;">*</span></span>`;
}

// Lazy Chart.js init (may not be ready on first paint), mirroring raghealth.js.
function ensureCharts() {
    if (typeof Chart === 'undefined') return false;
    if (!growthChart) {
        const el = document.getElementById('knGrowthChart');
        if (el) {
            growthChart = new Chart(el.getContext('2d'), {
                type: 'line',
                data: {
                    labels: [], datasets: [
                        { label: 'KBs', data: [], borderColor: '#22c55e', backgroundColor: '#22c55e22', tension: 0.3, borderWidth: 2, pointRadius: 2 },
                        { label: 'Files', data: [], borderColor: '#3b82f6', backgroundColor: '#3b82f622', tension: 0.3, borderWidth: 2, pointRadius: 2 },
                    ]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { labels: { color: '#94a3b8', font: { size: 11 } } } },
                    scales: {
                        x: { ticks: { color: '#64748b', font: { size: 11 } }, grid: { color: '#1e293b' } },
                        y: { beginAtZero: true, ticks: { color: '#64748b', font: { size: 11 }, precision: 0 }, grid: { color: '#1e293b' } }
                    }
                }
            });
        }
    }
    return true;
}

// ── Inventory ──
const INVENTORY_SLOTS = [['knTotKB', 'knTotFiles', 'knTotChunks', 'knTotStorage'], [['knTypeTable', 3]]];
const KB_VALUE_SLOTS = [['knCatStar', 'knCatTuning', 'knCatDead', 'knCatUnproven'],
                        [['knValueTable', 9], ['knAmbiguousTable', 3]]];
const GOVERNANCE_SLOTS = [['knReclaimable', 'knAdhoc', 'knDangling'],
                          [['knDupTable', 5], ['knOwnerTable', 4]]];

async function loadInventory() {
    const res = await mwFetch(`/v1/_mw/knowledge-analytics/inventory?${buildParams()}`);
    if (!res || !res.ok) {
        sectionFailed('knInventoryError', `HTTP ${res ? res.status : 'không kết nối được'}`, ...INVENTORY_SLOTS);
        return;
    }
    const data = await res.json();
    if (!sectionOk('knInventoryError', data, ...INVENTORY_SLOTS)) return;
    const t = data.totals || {};

    document.getElementById('knTotKB').textContent = t.knowledge_bases ?? 0;
    document.getElementById('knTotFiles').textContent = t.files ?? 0;
    document.getElementById('knTotChunks').textContent = t.chunks ?? 0;
    document.getElementById('knTotStorage').textContent = fmtBytes(t.storage_bytes);

    if (ensureCharts() && growthChart) {
        const g = data.growth || [];
        growthChart.data.labels = g.map(b => new Date(b.ts).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }));
        growthChart.data.datasets[0].data = g.map(b => b.kbs || 0);
        growthChart.data.datasets[1].data = g.map(b => b.files || 0);
        growthChart.update();
    }

    const types = data.type_distribution || [];
    document.getElementById('knTypeTable').innerHTML = types.length ? types.map(x => `
        <tr>
            <td>${escapeHtml(x.content_type)}</td>
            <td>${x.count}</td>
            <td>${escapeHtml(fmtBytes(x.bytes))}</td>
        </tr>`).join('') : '<tr><td colspan="3" class="loading">No files</td></tr>';
}

// ── KB Value ──
async function loadKbValue() {
    const res = await mwFetch(`/v1/_mw/knowledge-analytics/kb-value?${buildParams()}`);
    if (!res || !res.ok) {
        sectionFailed('knKbValueError', `HTTP ${res ? res.status : 'không kết nối được'}`, ...KB_VALUE_SLOTS);
        return;
    }
    const data = await res.json();
    if (!sectionOk('knKbValueError', data, ...KB_VALUE_SLOTS)) return;
    const c = data.category_counts || {};

    document.getElementById('knCatStar').textContent = c.star ?? 0;
    document.getElementById('knCatTuning').textContent = c.needs_tuning ?? 0;
    document.getElementById('knCatDead').textContent = c.dead ?? 0;
    document.getElementById('knCatUnproven').textContent = c.unproven ?? 0;

    const rows = data.knowledge_bases || [];
    document.getElementById('knValueTable').innerHTML = rows.length ? rows.map(r => `
        <tr>
            <td>${escapeHtml(r.name || '(unnamed)')}</td>
            <td>${escapeHtml(r.owner || '-')}</td>
            <td>${r.attach_count}</td>
            <td>${hitRateCell(r)}</td>
            <td>${r.file_count}</td>
            <td>${r.chunk_count}</td>
            <td>${escapeHtml(fmtBytes(r.size_bytes))}</td>
            <td>${escapeHtml(fmtTs(r.last_attached))}</td>
            <td>${escapeHtml(CATEGORY_LABEL[r.category] || r.category)}</td>
        </tr>`).join('') : '<tr><td colspan="9" class="loading">No knowledge bases</td></tr>';

    const amb = data.ambiguous_sources || [];
    document.getElementById('knAmbiguousTable').innerHTML = amb.length ? amb.map(a => `
        <tr>
            <td>${escapeHtml(a.source)}</td>
            <td>${a.attach}</td>
            <td>${a.kb_count}</td>
        </tr>`).join('') : '<tr><td colspan="3" class="loading">None 🎉</td></tr>';
}

// ── Governance ──
async function loadGovernance() {
    const res = await mwFetch('/v1/_mw/knowledge-analytics/governance');
    if (!res || !res.ok) {
        sectionFailed('knGovernanceError', `HTTP ${res ? res.status : 'không kết nối được'}`, ...GOVERNANCE_SLOTS);
        return;
    }
    const data = await res.json();
    if (!sectionOk('knGovernanceError', data, ...GOVERNANCE_SLOTS)) return;
    const o = data.orphans || {};

    document.getElementById('knReclaimable').textContent = fmtBytes(data.reclaimable_bytes);
    document.getElementById('knAdhoc').textContent = o.adhoc_count ?? 0;
    document.getElementById('knDangling').textContent = o.dangling_count ?? 0;

    const dup = data.duplicates || [];
    document.getElementById('knDupTable').innerHTML = dup.length ? dup.map(d => `
        <tr>
            <td>${escapeHtml(d.filename || '-')}</td>
            <td>${d.copies}</td>
            <td>${d.kb_count}</td>
            <td>${escapeHtml(fmtBytes(d.size_bytes))}</td>
            <td>${escapeHtml(fmtBytes(d.reclaimable_bytes))}</td>
        </tr>`).join('') : '<tr><td colspan="5" class="loading">None 🎉</td></tr>';

    const owners = data.owners || [];
    document.getElementById('knOwnerTable').innerHTML = owners.length ? owners.map(w => `
        <tr>
            <td>${escapeHtml(w.owner || '-')}</td>
            <td>${w.knowledge_bases}</td>
            <td>${w.files}</td>
            <td>${escapeHtml(fmtBytes(w.storage_bytes))}</td>
        </tr>`).join('') : '<tr><td colspan="4" class="loading">No data</td></tr>';
}

export async function loadKnowledge() {
    if (loading) return;
    loading = true;
    try {
        await Promise.all([loadInventory(), loadKbValue(), loadGovernance()]);
    } catch (err) {
        console.error('Failed to load knowledge analytics:', err);
    } finally {
        loading = false;
    }
}

export function applyKnowledgeFilters() {
    loadKnowledge();
}

export function resetKnowledgeFilters() {
    // Time range is the shared dashboard control; nothing tab-local to reset.
    loadKnowledge();
}
