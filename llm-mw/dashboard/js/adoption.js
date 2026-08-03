// Adoption tab block (Phase 4) — renders the /v1/_mw/adoption payload on the Users tab:
// adoption cards + KT/CK badges, DAU/WAU chart, Pareto chart, quota histogram, dormant list.
//
// Two data domains, kept distinct (see design.md): windowed activity metrics carry a
// period-comparison badge; whole-roster snapshots (dormant, histogram, provisioned) do not.
import { mwFetch } from './utils.js';
import { buildRangeParams } from './filters.js';
import { formatValue, renderDelta } from './metrics_registry.js';
import { loadCompare, side } from './compare_data.js';

let activityChart = null;
let paretoChart = null;
let provisionedRef = 0; // horizontal reference line on the activity chart = total provisioned

// Dashed "tổng đã cấp" ceiling on the DAU/WAU chart, so WAU can be read against how many
// accounts exist. WAU MAY exceed it (historical/deleted users still active) — it's a
// guide, not a cap.
const _provisionedLinePlugin = {
    id: 'provisionedLine',
    afterDatasetsDraw(chart) {
        if (!provisionedRef || !chart.scales.y) return;
        const y = chart.scales.y.getPixelForValue(provisionedRef);
        const { left, right } = chart.chartArea;
        if (y < chart.chartArea.top || y > chart.chartArea.bottom) return;
        const ctx = chart.ctx;
        ctx.save();
        ctx.strokeStyle = '#94a3b8';
        ctx.lineWidth = 1;
        ctx.setLineDash([6, 4]);
        ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(right, y); ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = '#94a3b8';
        ctx.font = '11px sans-serif';
        ctx.textAlign = 'right';
        ctx.fillText(`Đã cấp: ${provisionedRef}`, right - 6, y - 4);
        ctx.restore();
    },
};

function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

// ── Windowed metrics: flatten the adoption payload for the compare machinery ──
// A window with zero active users is "nothing happened", not "0% to compare against" —
// return null so the badge shows "—" rather than a fake delta (mirrors overview.js).
export const pickAdoptionMetrics = (json) => {
    const a = json && json.adoption;
    if (!a || !(a.active_users > 0)) return null;
    const r = json.roster || {};
    return {
        adoption_rate_percent: a.adoption_rate_percent,
        new_accounts_in_period: r.new_accounts_in_period,
        cost_per_active_user: a.cost_per_active_user,
    };
};

async function renderCompare(adoption, roster) {
    try {
        const cmp = await loadCompare('/v1/_mw/adoption', pickAdoptionMetrics);
        const wire = (id, key, current) => renderDelta(id, key, {
            current,
            kt: side(cmp.kt, key),
            ck: side(cmp.ck, key),
        });
        wire('metricAdoptionRate', 'adoption_rate_percent', adoption.adoption_rate_percent);
        wire('metricNewAccounts', 'new_accounts_in_period', roster.new_accounts_in_period);
        wire('metricCostPerUser', 'cost_per_active_user', adoption.cost_per_active_user);
    } catch (err) {
        console.error('Adoption compare failed:', err);
    }
}

// ── Cards ────────────────────────────────────────────────────
function renderCards(data) {
    const a = data.adoption || {};
    const roster = data.roster || {};
    setText('metricAdoptionRate', formatValue('adoption_rate_percent', a.adoption_rate_percent));
    setText('metricAdoptionDetail',
        `${(a.active_provisioned || 0).toLocaleString()} đang dùng / ${(a.provisioned || 0).toLocaleString()} đã cấp`);
    setText('metricNewAccounts', formatValue('new_accounts_in_period', roster.new_accounts_in_period));
    setText('metricCostPerUser', formatValue('cost_per_active_user', a.cost_per_active_user));
    setText('metricProvisioned', formatValue('provisioned_total', roster.provisioned));
}

// ── DAU/WAU line chart ───────────────────────────────────────
function renderActivity(series, provisioned) {
    const canvas = document.getElementById('adoptionActivityChart');
    if (!canvas || typeof Chart === 'undefined') return;
    provisionedRef = provisioned || 0;
    const labels = series.map(p => p.date);
    const wau = series.map(p => p.wau);
    const dau = series.map(p => p.dau);

    if (!activityChart) {
        activityChart = new Chart(canvas.getContext('2d'), {
            type: 'line',
            plugins: [_provisionedLinePlugin],
            data: {
                labels,
                datasets: [
                    {
                        label: 'Hoạt động trong tuần (7 ngày)', data: wau,
                        borderColor: '#3b82f6', backgroundColor: '#3b82f61a',
                        tension: 0.3, fill: true, pointRadius: 2, borderWidth: 2,
                    },
                    {
                        label: 'Hoạt động trong ngày', data: dau,
                        borderColor: '#64748b', backgroundColor: 'transparent',
                        borderDash: [4, 3], tension: 0.3, fill: false, pointRadius: 1, borderWidth: 1,
                    },
                ],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { display: true, labels: { color: '#cbd5e1', font: { size: 11 } } },
                    tooltip: {
                        backgroundColor: '#1e293b', borderColor: '#475569', borderWidth: 1,
                        titleColor: '#e2e8f0', bodyColor: '#cbd5e1', padding: 10, cornerRadius: 8,
                    },
                },
                scales: {
                    x: { ticks: { color: '#64748b', maxRotation: 45, font: { size: 11 } }, grid: { color: '#1e293b' } },
                    y: { ticks: { color: '#64748b', font: { size: 11 } }, grid: { color: '#1e293b' }, beginAtZero: true },
                },
            },
        });
    } else {
        activityChart.data.labels = labels;
        activityChart.data.datasets[0].data = wau;
        activityChart.data.datasets[1].data = dau;
        activityChart.update();
    }
}

// ── Pareto: per-user cost bars + cumulative-share line ───────
function renderPareto(pareto) {
    const canvas = document.getElementById('adoptionParetoChart');
    if (!canvas || typeof Chart === 'undefined') return;
    const users = (pareto.breakdown_by_user || []).slice(0, 15); // already sorted by cost desc
    const totalCost = (pareto.breakdown_by_user || []).reduce((s, u) => s + (u.cost_usd || 0), 0);
    const labels = users.map(u => (u.user_id || '').split('@')[0] || u.user_id);
    const costs = users.map(u => Number((u.cost_usd || 0).toFixed(4)));
    let running = 0;
    const cumulative = users.map(u => {
        running += (u.cost_usd || 0);
        return totalCost > 0 ? Number((running / totalCost * 100).toFixed(1)) : 0;
    });

    if (!paretoChart) {
        paretoChart = new Chart(canvas.getContext('2d'), {
            data: {
                labels,
                datasets: [
                    {
                        type: 'bar', label: 'Chi phí (USD)', data: costs,
                        backgroundColor: '#10b981', yAxisID: 'y', order: 2,
                    },
                    {
                        type: 'line', label: 'Luỹ kế % tổng chi phí', data: cumulative,
                        borderColor: '#f59e0b', backgroundColor: 'transparent',
                        tension: 0.2, pointRadius: 2, borderWidth: 2, yAxisID: 'y1', order: 1,
                    },
                ],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: {
                    legend: { display: true, labels: { color: '#cbd5e1', font: { size: 11 } } },
                    tooltip: {
                        backgroundColor: '#1e293b', borderColor: '#475569', borderWidth: 1,
                        titleColor: '#e2e8f0', bodyColor: '#cbd5e1', padding: 10, cornerRadius: 8,
                    },
                },
                scales: {
                    x: { ticks: { color: '#64748b', maxRotation: 60, font: { size: 10 } }, grid: { color: '#1e293b' } },
                    y: { ticks: { color: '#64748b', font: { size: 11 } }, grid: { color: '#1e293b' }, beginAtZero: true },
                    y1: {
                        position: 'right', min: 0, max: 100,
                        ticks: { color: '#f59e0b', font: { size: 11 }, callback: v => v + '%' },
                        grid: { drawOnChartArea: false },
                    },
                },
            },
        });
    } else {
        paretoChart.data.labels = labels;
        paretoChart.data.datasets[0].data = costs;
        paretoChart.data.datasets[1].data = cumulative;
        paretoChart.update();
    }
}

// ── Quota histogram: HTML bars (no extra Chart instance) ─────
const _QUOTA_BUCKETS = [
    ['0-25', '0–25%', '#10b981'], ['25-50', '25–50%', '#22c55e'],
    ['50-75', '50–75%', '#eab308'], ['75-90', '75–90%', '#f97316'],
    ['>90', '> 90%', '#ef4444'], ['unlimited', 'Không giới hạn', '#64748b'],
];
function renderQuotaHistogram(hist) {
    const container = document.getElementById('quotaHistogram');
    if (!container) return;
    hist = hist || {};
    const max = Math.max(1, ..._QUOTA_BUCKETS.map(([k]) => hist[k] || 0));
    container.innerHTML = _QUOTA_BUCKETS.map(([key, label, color]) => {
        const n = hist[key] || 0;
        const pct = Math.round(n / max * 100);
        return `
            <div style="display:flex; align-items:center; gap:10px; margin:6px 0;">
                <div style="width:110px; color:#94a3b8; font-size:13px;">${label}</div>
                <div style="flex:1; background:#1e293b; border-radius:6px; overflow:hidden; height:18px;">
                    <div style="width:${pct}%; height:100%; background:${color};"></div>
                </div>
                <div style="width:44px; text-align:right; color:#cbd5e1; font-size:13px;">${n.toLocaleString()}</div>
            </div>`;
    }).join('');
}

// ── Dormant table ────────────────────────────────────────────
function fmtDate(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    const p = (n) => String(n).padStart(2, '0');
    return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()}`;
}
function renderDormant(dormant) {
    dormant = dormant || {};
    setText('dormantNeverCount', (dormant.never_used_count || 0).toLocaleString());
    setText('dormantStoppedCount', (dormant.stopped_count || 0).toLocaleString());
    const tbody = document.getElementById('dormantTable');
    if (!tbody) return;
    const rows = dormant.accounts || [];
    if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="loading">Không có tài khoản ngủ 🎉</td></tr>';
        return;
    }
    tbody.innerHTML = rows.map(u => {
        const never = u.last_seen == null;
        // Colour tier by silence: never used → red, long-stopped → orange, just over → yellow.
        const dot = never ? '🔴' : (u.days_silent >= 60 ? '🟠' : '🟡');
        const status = u.active ? 'Đang bật' : 'Đã tắt';
        return `<tr>
            <td>${dot} ${u.user_id || ''}</td>
            <td>${fmtDate(u.created_at)}</td>
            <td>${never ? '— chưa bao giờ' : fmtDate(u.last_seen)}</td>
            <td>${(u.days_silent || 0).toLocaleString()} ngày</td>
            <td>${status}</td>
        </tr>`;
    }).join('');
}

// ── Entry point ──────────────────────────────────────────────
export async function loadAdoption() {
    try {
        const params = buildRangeParams();
        const res = await mwFetch(`/v1/_mw/adoption?${params}`);
        if (!res || !res.ok) throw new Error(`HTTP ${res ? res.status : 'null'}`);
        const data = await res.json();
        if (data.error) throw new Error(data.error);

        renderCards(data);
        renderActivity(data.activity_series || [], (data.roster || {}).provisioned);
        renderPareto(data.pareto || {});
        renderQuotaHistogram(data.quota_histogram);
        renderDormant(data.dormant);

        // Fire-and-forget: a slow comparison must not hold up the current figures.
        renderCompare(data.adoption || {}, data.roster || {});
    } catch (err) {
        console.error('Adoption load failed:', err);
        setText('metricAdoptionRate', '—');
        setText('metricCostPerUser', '—');
    }
}
