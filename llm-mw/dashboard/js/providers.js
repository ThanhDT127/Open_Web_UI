// Providers tab (Phase 6 — change dashboard-provider-budget).
// Prepaid credit per billing account: funded / spent-since-funding / remaining / runway.
// NOT scoped by the global time-range filter — always shows current credit state (D7).
import { mwFetch } from './utils.js';

function _color(pct) {
    // Same thresholds as the user quota gauge (users.js) for visual consistency.
    if (pct >= 90) return '#ef4444';
    if (pct >= 75) return '#f97316';
    if (pct >= 50) return '#f59e0b';
    return '#10b981';
}

function _statusBadge(status) {
    const map = {
        ok: ['#10b981', 'Ổn'],
        warn: ['#f97316', '⚠ Sắp cạn'],
        critical: ['#ef4444', '⚠ Cạn/vượt'],
        unknown: ['#9ca3af', '—'],
    };
    const [c, label] = map[status] || map.unknown;
    return `<span class="badge" style="background:${c}22;color:${c}">${label}</span>`;
}

function _runwayText(days) {
    if (days === null || days === undefined) return '<span class="quota-detail">— (chưa đủ dữ liệu)</span>';
    if (days <= 0) return '<span style="color:#ef4444">Đã cạn</span>';
    if (days >= 365) return '&gt; 1 năm';
    return `~${days.toFixed(days < 10 ? 1 : 0)} ngày`;
}

function _setText(id, v) {
    const el = document.getElementById(id);
    if (el) el.textContent = v;
}

export async function loadProviders() {
    const tbody = document.getElementById('providersTable');
    try {
        const res = await mwFetch('/v1/_mw/providers');
        if (!res || !res.ok) throw new Error(`HTTP ${res ? res.status : 'null'}`);
        const data = await res.json();
        if (data.error) throw new Error(data.error);

        const t = data.totals || {};
        _setText('provProviderCount', t.provider_count ?? '—');
        // 4 decimals, matching the "Đã tiêu" column below: at 2 decimals a real spend
        // under half a cent renders as "$0.00" while the table shows it as non-zero.
        _setText('provTotalRemaining', t.total_remaining != null ? `$${t.total_remaining.toFixed(4)}` : '—');
        _setText('provTotalSpent', t.total_spent != null ? `$${t.total_spent.toFixed(4)}` : '—');
        _setText('provTotalModels', data.total_models ?? '—');

        const rows = data.providers || [];
        if (!rows.length) {
            tbody.innerHTML = '<tr><td colspan="6" class="no-data">Chưa có provider nào được cấu hình</td></tr>';
            return;
        }

        tbody.innerHTML = rows.map(p => {
            const isOther = p.name === 'other';
            const pct = p.used_percent;
            let creditCell;
            if (isOther || pct === null || pct === undefined) {
                creditCell = '<span class="quota-detail">— (không có credit cấp)</span>';
            } else {
                const c = _color(pct);
                creditCell = `
                    <div class="quota-gauge"><div class="quota-gauge-fill" style="width:${Math.min(pct, 100)}%;background:${c}"></div></div>
                    <span class="quota-text" style="color:${c}">${pct.toFixed(1)}%</span>`;
            }
            const deposited = p.deposited != null ? `$${p.deposited.toFixed(2)}` : '—';
            const remaining = p.remaining != null ? `$${p.remaining.toFixed(2)}` : '—';
            return `
                <tr>
                    <td><strong>${p.name}</strong>${p.enabled ? '' : ' <span class="quota-detail">(tắt)</span>'}</td>
                    <td>${deposited}</td>
                    <td class="cost">$${(p.spent || 0).toFixed(4)}</td>
                    <td>${creditCell}<div class="quota-detail">còn ${remaining}</div></td>
                    <td>${isOther ? '—' : _runwayText(p.runway_days)}</td>
                    <td>${_statusBadge(p.status)}</td>
                </tr>`;
        }).join('');
    } catch (err) {
        console.error('Providers load failed:', err);
        if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="no-data">Không tải được dữ liệu provider</td></tr>';
    }
}
