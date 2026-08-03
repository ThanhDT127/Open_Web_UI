// Overview tab — executive summary cards (Phase 1).
// Reuses existing data where possible: System Health + Cost Concentration read the
// global-range summary already fetched by usage.js (getLastSummary); CSAT uses the
// satisfaction analytics endpoint; Cost MTD fetches summary for the current month.
import { mwFetch } from './utils.js';
import { buildRangeParams } from './filters.js';
import { getLastSummary } from './usage.js';
import { renderDelta, formatValue, classify, minSample } from './metrics_registry.js';
import { loadCompare, side } from './compare_data.js';
import { pickAdoptionMetrics } from './adoption.js';
import { toVnFields, fromVnFields } from './period_compare.js';

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

    renderCostAnomaly(summary);

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

// `total` is the vote count behind the percentage — thumbs up plus thumbs down. It travels
// as the sample so renderDelta can hold the badge to the same evidence bar the card already
// applies to its own colour: until this, the card refused to colour a figure drawn from
// three votes and then rendered a coloured arrow computed from those same three.
//
// On short ranges the badge will usually be absent, and that is the intended steady state
// rather than a symptom of a young database: rating is voluntary, so only a fraction of
// chats carry one, and the default range is Last 1h. The badge returns on the 30- and
// 90-day ranges — which is where a satisfaction trend starts to mean something anyway.
async function renderCsatCompare(current, currentSample) {
    try {
        const cmp = await loadCompare('/v1/_mw/admin/analytics/satisfaction', _pickCsatTotals);
        renderDelta('ovCsatValue', 'csat_percent', {
            current,
            currentSample,
            kt: side(cmp.kt, 'csat_percent', 'total'),
            ck: side(cmp.ck, 'csat_percent', 'total'),
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
        setText('ovCsatValue', pct != null ? formatValue('csat_percent', pct) : '—');
        // "lượt khen/chê", not "lượt đánh giá": this counts thumbs up plus thumbs down,
        // which is the CSAT denominator — feedback carrying neither is excluded.
        const floor = minSample('csat_percent');
        const detail = `${(total || 0).toLocaleString()} lượt khen/chê`;
        setText('ovCsatDetail', total > 0 && total < floor ? `${detail} · chưa đủ ${floor} để đánh giá` : detail);
        // Bands and the minimum sample come from the registry — see classify(). Below the
        // minimum the card keeps its number but drops to a neutral state, because a colour
        // is a verdict and five votes cannot support one.
        setCardState('ovCardCsat', classify('csat_percent', pct, total));
        // Same `total` that gates the colour above now gates the badge — one evidence bar
        // for the whole card.
        renderCsatCompare(pct, total);
    } catch (err) {
        console.error('Overview CSAT load failed:', err);
        setText('ovCsatValue', '—');
        // Clear the detail line too. It carries a vote count, and leaving the previous
        // range's count under a dashed value reads as though it belonged to the range
        // now selected — a stale number wearing a fresh one's clothes.
        setText('ovCsatDetail', '—');
    }
}

// ── Spend anomaly (Phase 10) ──
// Pure arithmetic over the series the chart already retrieved: no endpoint, no re-query,
// same reasoning that put the period comparison in the browser in Phase 2.
const COST_ANOMALY_MULTIPLE = 2;

function renderCostAnomaly(summary) {
    const el = document.getElementById('ovCostAnomaly');
    if (!el) return;
    const hide = () => { el.style.display = 'none'; };

    const series = (summary && summary.timeseries) || [];
    // The last bucket is still accumulating. Comparing a partial total against
    // full-bucket means compares two different quantities, so it is dropped rather
    // than reported as unusually low.
    const closed = series.slice(0, -1);

    const floor = minSample('cost_anomaly_series');
    if (closed.length < floor) {
        // The reason is the series length, not the absence of a spike. On a short series
        // "twice the mean" is routine, and an alarm that fires routinely gets ignored.
        return hide();
    }

    const costs = closed.map(b => Number(b.cost_usd) || 0);
    const mean = costs.reduce((a, b) => a + b, 0) / costs.length;
    const last = costs[costs.length - 1];
    if (!(mean > 0) || !(last > mean * COST_ANOMALY_MULTIPLE)) return hide();

    el.style.display = '';
    el.textContent = `⚠️ Chi phí kỳ gần nhất cao bất thường: `
        + `${formatValue('cost_anomaly_series', last)} so với trung bình chuỗi `
        + `${formatValue('cost_anomaly_series', mean)} `
        + `(gấp ${(last / mean).toFixed(1)} lần, trên ${closed.length} kỳ đã đóng).`;
}

// ── System health infrastructure signals (Phase 10) ──
// Reads /v1/_mw/health, which always answers 200: a degraded dependency is this report's
// content, not a failure to produce it. `/health` keeps the 200/503 contract the
// container probe needs. Not scoped to the global range — these are instantaneous.
async function loadHealthInfra() {
    try {
        const res = await mwFetch('/v1/_mw/health');
        if (!res || !res.ok) throw new Error(`HTTP ${res ? res.status : 'null'}`);
        const h = await res.json();

        const litellm = h.litellm === 'ok'
            ? '🟢 LiteLLM ổn'
            : `🔴 LiteLLM ${h.litellm || 'không rõ'}`;
        const disk = h.disk_free_gb != null
            ? `💾 ${formatValue('disk_free_gb', h.disk_free_gb)} trống`
            : '💾 —';
        setText('ovHealthInfra', `${litellm} · ${disk}`);

        // "Uptime" would read as an outage report on a healthy system that was simply
        // redeployed minutes ago — the figure resets to zero on every deploy.
        setText('ovHealthUptime', h.uptime_seconds != null
            ? `${METRIC_LABEL_UPTIME}: ${formatValue('uptime_seconds', h.uptime_seconds)}`
              + ' · số của worker vừa trả lời, có thể nhích giữa hai lần tải'
            : '');
    } catch (err) {
        console.error('Overview health infra load failed:', err);
        // Clear both the figure and its caption. A caption left under a removed number
        // reads as though it still describes something (the Phase 8 CSAT lesson).
        setText('ovHealthInfra', '—');
        setText('ovHealthUptime', '');
    }
}

const METRIC_LABEL_UPTIME = 'Chạy liên tục từ lần khởi động gần nhất';

// ── Cost MTD: summary for the current calendar month (ignores global range) ──
async function loadCostMtd() {
    try {
        const now = new Date();
        // Anchor the 1st in Vietnam time, not UTC. UTC midnight of the 1st is 07:00 in
        // Vietnam, so a UTC anchor read the whole previous month as "this month" during
        // the first 7 hours of every month, and dropped those 7 hours for the rest of it.
        // Matches how user quota periods anchor server-side (core/quota.py::period_anchor_ms).
        const vnNow = toVnFields(now);
        const monthStart = fromVnFields({
            year: vnNow.year, month: vnNow.month, day: 1,
            hours: 0, minutes: 0, seconds: 0, ms: 0,
        });
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

// ── Adoption + Cost-per-user cards (Phase 4 — resolves the Phase 1 placeholders) ──
async function loadAdoptionCards() {
    try {
        const params = buildRangeParams();
        const res = await mwFetch(`/v1/_mw/adoption?${params}`);
        if (!res || !res.ok) throw new Error(`HTTP ${res ? res.status : 'null'}`);
        const data = await res.json();
        const a = data && data.adoption ? data.adoption : {};
        setText('ovAdoptionValue', formatValue('adoption_rate_percent', a.adoption_rate_percent));
        setText('ovAdoptionDetail',
            `${(a.active_provisioned || 0).toLocaleString()} đang dùng / ${(a.provisioned || 0).toLocaleString()} đã cấp`);
        setText('ovCpuValue', formatValue('cost_per_active_user', a.cost_per_active_user));
        renderAdoptionCompare(a);
    } catch (err) {
        console.error('Overview adoption load failed:', err);
        setText('ovAdoptionValue', '—');
        setText('ovCpuValue', '—');
        // Same reason as the CSAT card: this line carries counts, so it must not
        // survive a failed reload and pass for the current range.
        setText('ovAdoptionDetail', '—');
    }
}

async function renderAdoptionCompare(a) {
    try {
        const cmp = await loadCompare('/v1/_mw/adoption', pickAdoptionMetrics);
        renderDelta('ovAdoptionValue', 'adoption_rate_percent', {
            current: a.adoption_rate_percent,
            kt: side(cmp.kt, 'adoption_rate_percent'),
            ck: side(cmp.ck, 'adoption_rate_percent'),
        });
        renderDelta('ovCpuValue', 'cost_per_active_user', {
            current: a.cost_per_active_user,
            kt: side(cmp.kt, 'cost_per_active_user'),
            ck: side(cmp.ck, 'cost_per_active_user'),
        });
    } catch (err) {
        console.error('Overview adoption compare failed:', err);
    }
}

// Full refresh triggered on tab open / manual refresh.
export async function loadOverview() {
    const summary = getLastSummary();
    if (summary) {
        renderFromSummary(summary);
    }
    await Promise.all([loadCsat(), loadCostMtd(), loadAdoptionCards(), loadHealthInfra()]);
}

// Keep the reused-summary cards live when the global summary refreshes
// (range change or the periodic 15s reload) while Overview is visible.
document.addEventListener('summary:updated', (e) => {
    const overviewTab = document.getElementById('overviewTab');
    if (overviewTab && overviewTab.classList.contains('active')) {
        renderFromSummary(e.detail || getLastSummary());
    }
});
