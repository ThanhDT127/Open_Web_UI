// Fetches the two comparison windows (KT / CK) for a dashboard endpoint.
//
// Deliberately NOT part of period_compare.js: that module stays pure date arithmetic
// with no imports, so it can be unit-tested in plain Node. This one talks to the
// network and reads shared filter state.
//
// No backend change is involved — every dashboard endpoint already accepts absolute
// start/end, so a past window is just another ordinary request.

import { mwFetch } from './utils.js';
import { getTimeWindow, currentTimeRange } from './filters.js';
import { resolveCompareWindows } from './period_compare.js';

// The window the comparison is anchored to. Refreshed only on an explicit trigger
// (range change, tab open) — NOT on the 15s poll: recomputing it every tick would make the
// cache key churn so nothing ever hit.
//
// Caching a past window assumes its contents are settled. That holds for everything drawn
// from mw_request_log / mw_audit_log — append-only, no retention job, no path by which a
// user can edit or delete a row. It does NOT hold for metrics read out of Open WebUI's own
// tables: `feedback` carries created_at AND updated_at, Open WebUI rewrites the row in
// place, and the query filters on created_at while reading the CURRENT rating (measured
// 03/08/2026: all five rows had been rewritten, one of them 22 hours later; `version`
// stayed 0 and no history table exists, so the earlier value is unrecoverable). For those,
// a cached comparison is a reading taken at fetch time, not a constant.
//
// This does not make the CSAT figures wrong — satisfaction is an opinion, and an opinion
// read as it currently stands is the honest reading; a rating the user withdrew should
// stop being counted. The note is here so that later work does not lengthen this cache or
// persist KT values on the premise that a closed period cannot move.
let anchorWindow = null;
const cache = new Map(); // `${path}|${start}|${end}` -> Promise<object|null>

// filters.js fires this when the admin picks a different range.
try {
    document.addEventListener('range:changed', () => invalidateCompareCache());
} catch (e) { /* non-browser context (unit tests) */ }

export function refreshCompareAnchor() {
    anchorWindow = getTimeWindow();
    return anchorWindow;
}

export function invalidateCompareCache() {
    cache.clear();
    anchorWindow = null;
}

function getAnchor() {
    return anchorWindow || refreshCompareAnchor();
}

// Note on the empty CK window: mw_audit_log's first row is 04/05/2026, so the
// same-period-last-year window is legitimately empty until ~05/2027 and the badge shows
// "—" for it. That is the honest rendering and it is left as is — a demo figure sitting
// in a real dashboard is one screenshot away from being read as a fact.
//
// ─── Fetch ───────────────────────────────────────────────────

function windowParams(win) {
    const params = new URLSearchParams();
    params.append('start', win.start);
    params.append('end', win.end);
    // Mirrors buildRangeParams: some endpoints key their bucket size off `minutes`.
    if (currentTimeRange.minutes) params.append('minutes', currentTimeRange.minutes);
    return params;
}

// Caches the RAW response, not the picked result. Two modules read the same endpoint
// with different pick functions — Overview and Usage both read /summary — and the cache
// key cannot include `pick`. Caching the picked value would silently hand the second
// caller the first caller's extraction.
// `extra` belongs in the key. It reached the request but not the key until RAG Health
// became the first caller to pass it, at which point switching the tab's model filter
// would have been served the previous filter's response — a badge comparing this model's
// present against another model's past, with nothing on screen to reveal it.
function extraKey(extra) {
    const pairs = Object.entries(extra || {}).filter(([, v]) => v);
    if (!pairs.length) return '';
    pairs.sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
    return '|' + pairs.map(([k, v]) => `${k}=${v}`).join('&');
}

async function fetchWindow(path, win, extra) {
    const key = `${path}|${win.start}|${win.end}${extraKey(extra)}`;
    if (cache.has(key)) return cache.get(key);

    const promise = (async () => {
        const params = windowParams(win);
        for (const [k, v] of Object.entries(extra || {})) if (v) params.append(k, v);
        try {
            const res = await mwFetch(`${path}?${params}`);
            if (!res || !res.ok) return null;
            return await res.json();
        } catch (err) {
            // A failed comparison must never take the card down with it; the badge
            // just renders as "no data".
            console.error(`Compare fetch failed for ${path}:`, err);
            return null;
        }
    })();

    cache.set(key, promise);
    return promise;
}

/**
 * Load both comparison windows for one endpoint.
 *
 * `pick(json)` extracts the values object, and SHOULD return null when the window holds
 * no data at all — that is what makes the badge show "—" instead of a fake zero change.
 *
 * Returns { kt, ck }, each `{ totals, window, lengthMismatch }`.
 */
export async function loadCompare(path, pick, { extra } = {}) {
    const anchor = getAnchor();
    const win = resolveCompareWindows(anchor.start, anchor.end);

    // Both past windows in flight at once — they are independent.
    const [ktJson, ckJson] = await Promise.all([
        fetchWindow(path, win.kt, extra),
        fetchWindow(path, win.ck, extra),
    ]);
    const apply = (json) => (json == null ? null : pick(json));
    return {
        kt: { totals: apply(ktJson), window: win.kt, lengthMismatch: win.kt.lengthMismatch },
        ck: { totals: apply(ckJson), window: win.ck, lengthMismatch: win.ck.lengthMismatch },
    };
}

/**
 * Shape one side for renderDelta: pull a single metric out of a side's totals.
 *
 * `sampleField` names the field in that payload holding the metric's denominator — the
 * observation count renderDelta weighs against minSample(). It is passed by the caller
 * rather than declared in the registry because the name belongs to the endpoint, not to
 * the metric: the same quantity is `total` on /satisfaction, `evaluated` on RAG retrieval
 * and `total_requests` on its coverage half. A registry that named one of them would be
 * wrong everywhere else.
 *
 * Omit it for metrics that declare no minimum — `sample` then stays undefined and
 * renderDelta has nothing to check.
 */
export function side(sideObj, metricKey, sampleField) {
    if (!sideObj) return null;
    const totals = sideObj.totals;
    return {
        value: totals ? totals[metricKey] : null,
        sample: totals && sampleField ? totals[sampleField] : undefined,
        window: sideObj.window,
        lengthMismatch: sideObj.lengthMismatch,
    };
}
