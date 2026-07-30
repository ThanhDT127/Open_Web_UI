// Metric registry — one declaration per scorecard metric, and the badge renderer
// that reads it.
//
// Every label, number format, delta format and colour comes from this table. Card code
// must not hard-code any of them: the same metric appears on several tabs and they are
// required to agree. It also makes the Vietnamese-label pass a one-file change instead
// of ~30 scattered edits.
//
// Timestamps shown in badges are rendered in Vietnam time (UTC+7) — the same clock the
// admin used to pick the range, and the same one period_compare.js evaluates the
// leap-day clamp in.

const VN_OFFSET_MINUTES = 7 * 60;
const MS_PER_MINUTE = 60000;

// ─── Value formatters ────────────────────────────────────────

// Humanised queue age: seconds → "45s" / "12p" / "3g 20p" / "2n 3g".
function formatAge(sec) {
    if (sec == null) return '—';
    sec = Number(sec);
    if (sec < 60) return `${Math.round(sec)}s`;
    const m = Math.floor(sec / 60);
    if (m < 60) return `${m}p`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}g ${m % 60}p`;
    const d = Math.floor(h / 24);
    return `${d}n ${h % 24}g`;
}

const FORMATTERS = {
    int: (v) => Number(v || 0).toLocaleString(),
    num1: (v) => (v == null ? '-' : Number(v).toLocaleString(undefined, { maximumFractionDigits: 1 })),
    usd4: (v) => '$' + Number(v || 0).toFixed(4),
    usd2: (v) => '$' + Number(v || 0).toFixed(2),
    usd6: (v) => '$' + Number(v || 0).toFixed(6),
    ms: (v) => (v == null ? '-' : Number(v).toFixed(0) + 'ms'),
    pct1: (v) => Number(v || 0).toFixed(1) + '%',
    ratio: (v) => (v == null ? '—' : Number(v).toFixed(2) + ':1'),
    rpm: (v) => (v == null ? '-' : Number(v).toLocaleString(undefined, { maximumFractionDigits: 3 }) + '/ph'),
    age: (v) => formatAge(v),
    days: (v) => (v == null ? '—' : Number(v).toLocaleString() + ' ngày'),
};

export function formatValue(metricKey, value) {
    const m = METRICS[metricKey];
    return (FORMATTERS[m && m.fmt] || FORMATTERS.int)(value);
}

// Money in breakdown TABLES goes through the same map the scorecards use, so the money
// format lives in one place. Exported as a formatter rather than reached through
// formatValue() because table columns are deliberately not registered as metrics — only
// scorecards are (see the dashboard-model-metrics spec) — so they have no metric key.
export const usd4 = FORMATTERS.usd4;

// ─── The registry ────────────────────────────────────────────
//
// fmt      — which formatter renders the value (and the compared value)
// delta    — 'rel'  relative %      : counts and money
//            'pp'   percentage point: metrics that ARE percentages, so 62%→68%
//                                     reads "+6 điểm %", not "+9.7%"
//            'abs'  absolute        : small headcounts
// polarity — 'up-good' | 'down-good' | 'neutral'. Colour comes from this, never from
//            the sign of the number.
// compare  — false blocks the badge entirely. Two distinct reasons, both intentional:
//            a value that is not scoped to the time window at all, and inventory or
//            configuration figures where a period delta is meaningless.

export const METRICS = {
    requests_total: {
        label: 'Total Requests', fmt: 'int', delta: 'rel', polarity: 'up-good',
    },
    cost_total_usd: {
        label: 'Total Cost', fmt: 'usd4', delta: 'rel', polarity: 'down-good',
    },
    tokens_total: {
        label: 'Total Tokens', fmt: 'int', delta: 'rel', polarity: 'down-good',
    },
    p95_latency_ms: {
        label: 'P95 Latency', fmt: 'ms', delta: 'rel', polarity: 'down-good',
    },
    error_rate_percent: {
        label: 'Error Rate', fmt: 'pct1', delta: 'pp', polarity: 'down-good',
    },
    billable_calls: {
        label: 'Billable', fmt: 'int', delta: 'rel', polarity: 'neutral',
        // More billable calls means both wider adoption and a bigger bill. Neither
        // direction is plainly good or bad, so it stays neutral rather than being
        // coloured to imply a verdict nobody agreed on.
    },

    // ── Request lens (Phase 3) — all windowed, all derived server-side in totals ──
    p50_latency_ms: {
        label: 'P50 Latency', fmt: 'ms', delta: 'rel', polarity: 'down-good',
    },
    p99_latency_ms: {
        label: 'P99 Latency', fmt: 'ms', delta: 'rel', polarity: 'down-good',
    },
    max_latency_ms: {
        label: 'Max Latency', fmt: 'ms', delta: 'rel', polarity: 'down-good',
    },
    cost_per_request: {
        label: 'Chi phí / request', fmt: 'usd6', delta: 'rel', polarity: 'down-good',
    },
    cost_per_1k_tokens: {
        label: 'Chi phí / 1k tokens', fmt: 'usd6', delta: 'rel', polarity: 'down-good',
    },
    avg_tokens_per_request: {
        label: 'TB tokens / request', fmt: 'num1', delta: 'rel', polarity: 'neutral',
    },
    tokens_in_out_ratio: {
        label: 'Tỷ lệ token vào:ra', fmt: 'ratio', delta: 'rel', polarity: 'neutral',
    },
    rpm_avg: {
        label: 'Throughput (TB)', fmt: 'rpm', delta: 'rel', polarity: 'neutral',
    },
    rpm_peak: {
        label: 'Throughput (đỉnh)', fmt: 'rpm', delta: 'rel', polarity: 'neutral',
    },

    // ── Overview tab ──
    csat_percent: {
        label: 'Mức hài lòng', fmt: 'pct1', delta: 'pp', polarity: 'up-good',
        // Bands and the minimum sample live here, not at each call site. They used to be
        // restated in overview.js and satisfaction.js — two tabs that are never seen side
        // by side, so a divergence between them would have gone unnoticed.
        //
        // minSample is 20 because that is where the 95% Wilson interval around an observed
        // 80% stops straddling the 50 band edge (58.4–91.9%). At 5 votes the same 80% could
        // truly be anything from 38% to 96%, so colouring it green states more than the
        // data supports.
        bands: { good: 80, warn: 50 },
        minSample: 20,
    },
    top10_pct_cost_share: {
        label: 'Mức tập trung chi phí', fmt: 'pct1', delta: 'pp', polarity: 'down-good',
        // Falling concentration is the good direction: cost spread across more people
        // means broader adoption and less exposure to a handful of heavy users. This is
        // an internal adoption metric, not a sales one.
    },

    // ── Adoption (Phase 4) — windowed, badge runs; source: /v1/_mw/adoption ──
    adoption_rate_percent: {
        label: 'Tỷ lệ áp dụng', fmt: 'pct1', delta: 'pp', polarity: 'up-good',
        // Internal tool: more of the provisioned staff actually using it is the good
        // direction. Numerator is roster-intersected server-side, so it never exceeds 100.
    },
    new_accounts_in_period: {
        label: 'Cấp mới trong kỳ', fmt: 'int', delta: 'abs', polarity: 'neutral',
        // Provisioning count — more/fewer is not itself good or bad. Absolute delta:
        // small headcounts make a relative % noisy.
    },
    cost_per_active_user: {
        label: 'Chi phí / người dùng thật', fmt: 'usd4', delta: 'rel', polarity: 'neutral',
        // Denominator is the RAW active count (people who actually used it), not the
        // roster-intersected adoption numerator — incurred cost is real either way.
    },

    // ── Groups scale (Phase 7b) — source: /v1/_mw/admin/analytics/groups ──
    dept_avg_cost: {
        label: 'Chi phí bình quân mỗi phòng ban', fmt: 'usd4', delta: 'rel', polarity: 'down-good',
        // Numerator is only the cost that could be attributed to a department, so the card
        // is deliberately smaller than the table's total divided by the same count. The
        // note under the scorecard is what explains that gap.
    },

    // ── Blocked from comparison ──
    department_count: {
        label: 'Số phòng ban', fmt: 'int', compare: false,
        blockedReason: 'Cơ cấu tổ chức — con số này không phụ thuộc khoảng thời gian đang '
            + 'xem, nên so kỳ sẽ luôn ra 0% và chỉ làm người đọc tưởng có ý nghĩa',
    },
    assigned_member_count: {
        label: 'Nhân sự đã có phòng ban', fmt: 'int', compare: false,
        blockedReason: 'Cơ cấu tổ chức — không phụ thuộc khoảng thời gian đang xem',
    },
    provisioned_total: {
        label: 'Tổng đã cấp', fmt: 'int', compare: false,
        blockedReason: 'Snapshot roster (mw_users chưa xóa) — tính đến hiện tại, không '
            + 'thuộc cửa sổ thời gian. Đây là mẫu số của tỷ lệ áp dụng, không phải chỉ tiêu '
            + 'so kỳ riêng.',
    },
    dormant_count: {
        label: 'Tài khoản ngủ', fmt: 'int', compare: false,
        blockedReason: 'Snapshot roster — đếm tài khoản chưa từng dùng / ngừng > 30 ngày '
            + 'tính đến hôm nay, không scoped theo range. Cùng lý do với pending_open_count.',
    },
    cost_mtd_usd: {
        label: 'Chi phí tháng này', fmt: 'usd2', compare: false,
        blockedReason: 'Thẻ này cố ý bỏ qua range toàn cục — nó tự tính từ mùng 1 '
            + '(overview.js). Neo KT/CK theo anchor chung sẽ so nhầm hai khoảng khác nhau. '
            + 'Muốn so tháng thì chọn thẳng ngày ở ô date picker.',
    },
    chats: {
        label: 'Tổng hội thoại', fmt: 'int', compare: false,
        blockedReason: 'Nguồn là bảng `chat` của Open WebUI, mà người dùng XOÁ được. '
            + 'Cửa sổ càng lùi xa càng bị xói mòn, nên so kỳ luôn nghiêng về "quá khứ '
            + 'thấp hơn hiện tại" một cách có hệ thống. Đây là hạn chế cấu trúc của nguồn, '
            + 'không phải chuyện chờ đủ lịch sử: càng nhiều người dùng thì càng tệ. '
            + '(Đo 2026-07-20: bảng `chat` chỉ có từ 28/06/2026, trong khi mw_audit_log '
            + 'có từ 04/05/2026 — cùng một response mà hai nửa dài ngắn khác nhau.)',
    },
    active_users: {
        label: 'Người dùng hoạt động', fmt: 'int', compare: false,
        blockedReason: 'Cùng nguồn và cùng lý do với `chats`. Lưu ý nếu sau này muốn mở: '
            + 'mw_audit_log có `user_id` nên COUNT(DISTINCT) trên đó cho ra một chỉ tiêu '
            + 'BẤT BIẾN so kỳ được — nhưng đó là định nghĩa khác (mọi request, không chỉ '
            + 'người có tạo hội thoại), nên phải đổi nhãn chứ không thay ngầm.',
    },
    pending_open_count: {
        label: 'Pending', fmt: 'int', compare: false,
        blockedReason: 'Không thuộc phạm vi khoảng thời gian — đếm toàn bảng mw_pending, '
            + 'nên trả cùng một giá trị ở cả ba cửa sổ. Gắn badge sẽ hiện 0% vĩnh viễn.',
    },
    pending_oldest_age_sec: {
        label: 'Tuổi kẹt lâu nhất', fmt: 'age', compare: false,
        blockedReason: 'Snapshot toàn bảng mw_pending (min(ts)) — cùng lý do với pending_open_count, '
            + 'không thuộc cửa sổ thời gian nên không so kỳ được.',
    },
    usage_missing_calls: {
        label: 'Usage Missing', fmt: 'int', compare: false,
        blockedReason: 'Chỉ số chẩn đoán chất lượng dữ liệu, không phải chỉ tiêu nghiệp vụ '
            + 'theo kỳ — miễn badge theo quyết định #9.',
    },
};

export function isComparable(metricKey) {
    const m = METRICS[metricKey];
    return !!m && m.compare !== false;
}

// ─── Classification: bands and the minimum sample behind them ────────────────

// How many observations a metric needs before its value may be ranked or coloured.
// 0 means the metric has no such requirement.
export function minSample(metricKey) {
    const m = METRICS[metricKey];
    return (m && m.minSample) || 0;
}

// 'ok' | 'warn' | 'danger', or null when the sample is too small to classify.
// Callers must treat null as "show the number, withhold the judgement" — not as
// "hide the number". A figure computed from few observations is still the only
// signal there is; what it cannot carry is a colour that reads as a verdict.
export function classify(metricKey, value, sampleSize = Infinity) {
    const m = METRICS[metricKey];
    if (!m || !m.bands || value == null) return null;
    if (sampleSize < ((m.minSample) || 0)) return null;
    const goodIsHigh = m.polarity !== 'down-good';
    const { good, warn } = m.bands;
    if (goodIsHigh) {
        if (value >= good) return 'ok';
        return value >= warn ? 'warn' : 'danger';
    }
    if (value <= good) return 'ok';
    return value <= warn ? 'warn' : 'danger';
}

// ─── Vietnam-time display (D9) ───────────────────────────────

function vnParts(iso) {
    const d = new Date(new Date(iso).getTime() + VN_OFFSET_MINUTES * MS_PER_MINUTE);
    const p = (n) => String(n).padStart(2, '0');
    return {
        date: `${p(d.getUTCDate())}/${p(d.getUTCMonth() + 1)}/${d.getUTCFullYear()}`,
        time: `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`,
    };
}

// "13/07/2026 09:00 – 20/07/2026 09:00".
// The year is ALWAYS printed. Collapsing it when both ends share one made the
// same-period-last-year window read identically to the current one — which defeats the
// only job this string has, saying which period is being compared.
export function formatVnWindow(win) {
    if (!win || !win.start || !win.end) return '';
    const a = vnParts(win.start); const b = vnParts(win.end);
    return `${a.date} ${a.time} – ${b.date} ${b.time}`;
}

// ─── Delta computation ───────────────────────────────────────

const ARROW_UP = '▲';
const ARROW_DOWN = '▼';
const MINUS = '−'; // proper minus sign, not a hyphen

function signed(n, render) {
    if (n > 0) return `${ARROW_UP} +${render(n)}`;
    if (n < 0) return `${ARROW_DOWN} ${MINUS}${render(Math.abs(n))}`;
    // No movement: say so in words. A bare "0" next to an absolute value reads like a
    // measurement rather than "nothing changed".
    return 'không đổi';
}

// Returns { text, direction } where direction is -1 / 0 / +1, or null when the
// comparison cannot be expressed at all.
export function computeDelta(metricKey, current, previous) {
    const m = METRICS[metricKey];
    if (!m || previous == null || current == null) return null;
    // The block holds here too, not only in renderDelta. These metrics produce deltas
    // that are arithmetically valid and materially wrong — `chats` would report a
    // confident −100% for a window the source table simply never covered. A future
    // caller reaching for computeDelta directly must hit the same wall.
    if (!isComparable(metricKey)) return null;
    const diff = current - previous;
    const dir = diff > 0 ? 1 : diff < 0 ? -1 : 0;

    // A percentage against a zero baseline is undefined; report the absolute move
    // instead rather than rendering an infinity as if it were a rate.
    const kind = (m.delta === 'rel' && previous === 0) ? 'abs' : m.delta;

    if (kind === 'rel') {
        const pct = (diff / Math.abs(previous)) * 100;
        return { text: signed(pct, (n) => `${n.toFixed(Math.abs(n) < 10 ? 1 : 0)}%`), direction: dir };
    }
    if (kind === 'pp') {
        return { text: signed(diff, (n) => `${n.toFixed(1)} điểm %`), direction: dir };
    }
    return { text: signed(diff, (n) => formatValue(metricKey, n)), direction: dir };
}

function toneClass(metricKey, direction) {
    const m = METRICS[metricKey];
    if (!m || direction === 0 || m.polarity === 'neutral') return 'd-neutral';
    const good = m.polarity === 'up-good' ? direction > 0 : direction < 0;
    return good ? 'd-green' : 'd-red';
}

// ─── Badge rendering ─────────────────────────────────────────

function line(prefix, metricKey, current, side) {
    const el = document.createElement('div');
    el.className = 'delta-line';

    // No data in that window: state it plainly instead of implying a zero change.
    if (!side || side.value == null) {
        el.classList.add('d-dim');
        el.textContent = `${prefix}: ${MINUS}`;
        if (side && side.window) el.title = formatVnWindow(side.window);
        return el;
    }

    const d = computeDelta(metricKey, current, side.value);
    el.classList.add(toneClass(metricKey, d ? d.direction : 0));

    const head = document.createElement('span');
    head.textContent = d ? d.text : `${prefix}:`;
    el.appendChild(head);

    const abs = document.createElement('span');
    abs.className = 'delta-abs';
    // Always print the window actually being compared — no hidden suppression rules.
    abs.textContent = `${prefix}: ${formatVnWindow(side.window)} (${formatValue(metricKey, side.value)})`;
    el.appendChild(abs);

    if (side.lengthMismatch) {
        const warn = document.createElement('span');
        warn.textContent = ' ⚠️';
        warn.title = 'Kỳ so sánh không cùng độ dài với kỳ hiện tại (năm nhuận).';
        el.appendChild(warn);
    }
    return el;
}

/**
 * Attach (or refresh) the comparison badge on the card owning `valueElementId`.
 * Metrics declared `compare: false` are skipped — deliberately, see METRICS.
 */
export function renderDelta(valueElementId, metricKey, { current, kt, ck } = {}) {
    const anchor = document.getElementById(valueElementId);
    if (!anchor) return;
    const card = anchor.closest('.metric-card') || anchor.parentElement;
    if (!card) return;

    const existing = card.querySelector('.delta-badge');
    if (existing) existing.remove();
    if (!isComparable(metricKey)) return;

    const badge = document.createElement('div');
    badge.className = 'delta-badge';
    badge.appendChild(line('KT', metricKey, current, kt));
    badge.appendChild(line('CK', metricKey, current, ck));
    card.appendChild(badge);
}
