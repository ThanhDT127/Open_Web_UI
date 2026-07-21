// Overview tab — executive summary cards (Phase 1).
// Reuses existing data where possible: System Health + Cost Concentration read the
// global-range summary already fetched by usage.js (getLastSummary); CSAT uses the
// satisfaction analytics endpoint; Cost MTD fetches summary for the current month.
import { mwFetch } from './utils.js';
import { buildRangeParams } from './filters.js';
import { getLastSummary } from './usage.js';
import { renderDelta } from './metrics_registry.js';
import { loadCompare, side } from './compare_data.js';

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

    // Fire-and-forget: a slow comparison must not hold up the current figures.
    renderSummaryCompare(totals);
}

// ── Period-comparison badges ─────────────────────────────────
// Only three Overview cards can carry one. "Chi phí tháng này" deliberately ignores the
// global range (it anchors to the 1st of the month) so the shared anchor would compare
// two different spans; it is declared compare:false in the registry. "Tỷ lệ sử dụng" and
// "Chi phí / người dùng thật" are Phase 4 placeholders with no id and no data yet.

// A window with no requests in it has no rates to speak of — csat/error/concentration all
// come back as zeros that mean "nothing happened", not "the value is zero".
const _pickSummaryTotals = (json) => {
    const t = json && json.totals;
    return t && t.requests_total > 0 ? t : null;
};
const _pickCsatTotals = (json) => {
    const t = json && json.totals;
    return t && t.total > 0 ? t : null;
};

async function renderSummaryCompare(totals) {
    try {
        // Same endpoint and same window as usage.js, so this resolves off the shared
        // cache rather than issuing a second pair of requests.
        const cmp = await loadCompare('/v1/_mw/summary', _pickSummaryTotals);
        renderDelta('ovHealthValue', 'error_rate_percent', {
            current: totals.error_rate_percent,
            kt: side(cmp.kt, 'error_rate_percent'),
            ck: side(cmp.ck, 'error_rate_percent'),
        });
        renderDelta('ovConcentrationValue', 'top10_pct_cost_share', {
            current: totals.top10_pct_cost_share,
            kt: side(cmp.kt, 'top10_pct_cost_share'),
            ck: side(cmp.ck, 'top10_pct_cost_share'),
        });
    } catch (err) {
        console.error('Overview summary compare failed:', err);
    }
}

async function renderCsatCompare(current) {
    try {
        const cmp = await loadCompare('/v1/_mw/admin/analytics/satisfaction', _pickCsatTotals);
        renderDelta('ovCsatValue', 'csat_percent', {
            current,
            kt: side(cmp.kt, 'csat_percent'),
            ck: side(cmp.ck, 'csat_percent'),
        });
    } catch (err) {
        console.error('Overview CSAT compare failed:', err);
    }
}

// ── CSAT: satisfaction analytics for the global range ──
async function loadCsat() {
    try {
        const params = buildRangeParams();
        const res = await mwFetch(`/v1/_mw/admin/analytics/satisfaction?${params}`);
        if (!res || !res.ok) throw new Error(`HTTP ${res ? res.status : 'null'}`);
        const data = await res.json();
        const pct = data && data.totals ? data.totals.csat_percent : null;
        const total = data && data.totals ? data.totals.total : 0;
        setText('ovCsatValue', pct != null ? `${pct}%` : '—');
        setText('ovCsatDetail', `${(total || 0).toLocaleString()} lượt đánh giá`);
        // Thresholds mirror satisfaction.js: >=80 ok, >=50 warn, else danger.
        setCardState('ovCardCsat', pct == null ? null : pct >= 80 ? 'ok' : pct >= 50 ? 'warn' : 'danger');
        renderCsatCompare(pct);
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
