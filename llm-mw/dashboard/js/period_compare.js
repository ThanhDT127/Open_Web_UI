// Period comparison rules — the single source of truth for "where does the previous
// period / same period last year start and end".
//
// Two rules, no lookup table, no special cases:
//   KT (previous period)      = [start − Δ, start)          where Δ = end − start
//   CK (same period last year)= [start − 1 year, end − 1 year], clamping 29/02 → 28/02
//
// "Cùng kỳ" means the same period LAST YEAR, matching Vietnamese business usage and
// Power BI SAMEPERIODLASTYEAR / GA4 / Adobe Analytics. It is deliberately NOT a shorter
// shift such as −24h or −28d.
//
// Calendar fields are evaluated in Vietnam time (UTC+7), not in UTC and not in the
// browser's local zone. This matters only for the leap-day clamp, but there it decides
// a full 24 hours: 29/02/2028 05:00 Vietnam time is 28/02/2028 in UTC, so reading the
// calendar date in UTC would skip the clamp and land the comparison a day late.

// Vietnam has observed no DST since 1975, so a fixed offset is safe here.
const VN_OFFSET_MINUTES = 7 * 60;
const MS_PER_MINUTE = 60000;

function isLeapYear(year) {
    return (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
}

// Read a UTC instant as the calendar fields a person in Vietnam would see.
export function toVnFields(date) {
    const shifted = new Date(date.getTime() + VN_OFFSET_MINUTES * MS_PER_MINUTE);
    return {
        year: shifted.getUTCFullYear(),
        month: shifted.getUTCMonth(), // 0-based
        day: shifted.getUTCDate(),
        hours: shifted.getUTCHours(),
        minutes: shifted.getUTCMinutes(),
        seconds: shifted.getUTCSeconds(),
        ms: shifted.getUTCMilliseconds(),
    };
}

export function fromVnFields(f) {
    const asUtc = Date.UTC(f.year, f.month, f.day, f.hours, f.minutes, f.seconds, f.ms);
    return new Date(asUtc - VN_OFFSET_MINUTES * MS_PER_MINUTE);
}

function toDate(value) {
    return value instanceof Date ? new Date(value.getTime()) : new Date(value);
}

// Backends parse with fromisoformat(), which rejects the 'Z' suffix.
export function toIsoParam(date) {
    return date.toISOString().replace('Z', '+00:00');
}

// Subtract exactly one calendar year, preserving month/day/hour/minute in Vietnam time.
// 29 February in a leap year clamps to 28 February — it never rolls forward into March.
export function shiftBackOneYear(instant) {
    const f = toVnFields(toDate(instant));
    const targetYear = f.year - 1;
    const isLeapDay = f.month === 1 && f.day === 29;
    return fromVnFields({
        ...f,
        year: targetYear,
        day: isLeapDay && !isLeapYear(targetYear) ? 28 : f.day,
    });
}

// KT — the window immediately before the current one, of identical length.
// Pure timestamp arithmetic: no rounding to calendar boundaries, no lookup on Δ.
export function previousPeriod(start, end) {
    const s = toDate(start);
    const delta = toDate(end).getTime() - s.getTime();
    return { start: new Date(s.getTime() - delta), end: new Date(s.getTime()) };
}

// CK — the same calendar window one year earlier.
export function samePeriodLastYear(start, end) {
    return { start: shiftBackOneYear(start), end: shiftBackOneYear(end) };
}

// A comparison window can end up shorter than the current one when the current window
// spans 29 February and the prior year has no such day. Callers flag this in the badge.
export function windowLengthMismatch(current, other) {
    const lenCurrent = toDate(current.end).getTime() - toDate(current.start).getTime();
    const lenOther = toDate(other.end).getTime() - toDate(other.start).getTime();
    return lenCurrent !== lenOther;
}

// Everything a caller needs for one current window, as ISO strings ready for the API.
// Note the KT end equals the current start; backends filter with `ts <= end`, so a row
// landing on that exact instant is counted in both windows. Sub-millisecond collisions
// only — this mirrors the existing inclusive-bounds behaviour rather than changing it.
export function resolveCompareWindows(start, end) {
    const current = { start: toDate(start), end: toDate(end) };
    const kt = previousPeriod(current.start, current.end);
    const ck = samePeriodLastYear(current.start, current.end);
    const asParams = (w) => ({ start: toIsoParam(w.start), end: toIsoParam(w.end) });
    return {
        current: asParams(current),
        kt: { ...asParams(kt), lengthMismatch: windowLengthMismatch(current, kt) },
        ck: { ...asParams(ck), lengthMismatch: windowLengthMismatch(current, ck) },
    };
}
