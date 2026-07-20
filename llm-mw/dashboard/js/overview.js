// Overview tab — executive summary cards (Phase 1).
// Reuses existing data where possible: System Health + Cost Concentration read the
// global-range summary already fetched by usage.js (getLastSummary); CSAT uses the
// satisfaction analytics endpoint; Cost MTD fetches summary for the current month.
import { mwFetch } from './utils.js';
import { currentTimeRange } from './filters.js';
import { getLastSummary } from './usage.js';

// Apply an ok/warn/danger accent state to a metric-card element.
function setCardState(cardId, state) {
    const el = document.getElementById(cardId);
    if (!el) return;
    el.classList.remove('ok', 'warn', 'danger');
    if (state) el.classList.add(state);
}

function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

// ── System Health + Cost Concentration: reuse global-range summary ──
function renderFromSummary(summary) {
    const totals = summary && summary.totals;
    if (!totals) return;

    // System Health: error rate (primary) + P95 latency (detail).
    const err = Number(totals.error_rate_percent) || 0;
    setText('ovHealthValue', `${err.toFixed(2)}%`);
    const p95 = totals.p95_latency_ms;
    setText('ovHealthDetail', p95 != null ? `P95: ${Math.round(p95)} ms` : 'P95: —');
    // Thresholds per catalog §3.1: <1% ok, 1–5% warn, >5% danger.
    setCardState('ovCardHealth', err < 1 ? 'ok' : err <= 5 ? 'warn' : 'danger');

    // Cost Concentration: top 10% of users' share of total cost. No documented
    // hard threshold — render neutral (no accent) until leader confirms one.
    const share = totals.top10_pct_cost_share;
    setText('ovConcentrationValue', share != null ? `${share}%` : '—');
}

// ── CSAT: satisfaction analytics for the global range ──
async function loadCsat() {
    try {
        const params = new URLSearchParams();
        if (currentTimeRange && currentTimeRange.minutes) {
            params.append('minutes', currentTimeRange.minutes);
        } else if (currentTimeRange && currentTimeRange.start && currentTimeRange.end) {
            params.append('start', currentTimeRange.start);
            params.append('end', currentTimeRange.end);
        } else {
            params.append('minutes', 43200); // 30d default
        }
        const res = await mwFetch(`/v1/_mw/admin/analytics/satisfaction?${params}`);
        if (!res || !res.ok) throw new Error(`HTTP ${res ? res.status : 'null'}`);
        const data = await res.json();
        const pct = data && data.totals ? data.totals.csat_percent : null;
        const total = data && data.totals ? data.totals.total : 0;
        setText('ovCsatValue', pct != null ? `${pct}%` : '—');
        setText('ovCsatDetail', `${(total || 0).toLocaleString()} lượt đánh giá`);
        // Thresholds mirror satisfaction.js: >=80 ok, >=50 warn, else danger.
        setCardState('ovCardCsat', pct == null ? null : pct >= 80 ? 'ok' : pct >= 50 ? 'warn' : 'danger');
    } catch (err) {
        console.error('Overview CSAT load failed:', err);
        setText('ovCsatValue', '—');
    }
}

// ── Cost MTD: summary for the current calendar month (ignores global range) ──
async function loadCostMtd() {
    try {
        const now = new Date();
        const monthStart = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1, 0, 0, 0));
        const params = new URLSearchParams();
        params.append('start', monthStart.toISOString());
        params.append('end', now.toISOString());
        const res = await mwFetch(`/v1/_mw/summary?${params}`);
        if (!res || !res.ok) throw new Error(`HTTP ${res ? res.status : 'null'}`);
        const data = await res.json();
        const cost = data && data.totals ? data.totals.cost_total_usd : null;
        setText('ovSpendValue', cost != null ? `$${Number(cost).toFixed(2)}` : '—');
    } catch (err) {
        console.error('Overview Cost MTD load failed:', err);
        setText('ovSpendValue', '—');
    }
}

// Full refresh triggered on tab open / manual refresh.
export async function loadOverview() {
    const summary = getLastSummary();
    if (summary) {
        renderFromSummary(summary);
    }
    await Promise.all([loadCsat(), loadCostMtd()]);
}

// Keep the reused-summary cards live when the global summary refreshes
// (range change or the periodic 15s reload) while Overview is visible.
document.addEventListener('summary:updated', (e) => {
    const overviewTab = document.getElementById('overviewTab');
    if (overviewTab && overviewTab.classList.contains('active')) {
        renderFromSummary(e.detail || getLastSummary());
    }
});
