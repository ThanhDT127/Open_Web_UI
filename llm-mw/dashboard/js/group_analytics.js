import { mwFetch, updateStatus } from './utils.js';
import { buildRangeParams } from './filters.js';
import { usd4, renderDelta } from './metrics_registry.js';
import { loadCompare, side } from './compare_data.js';

let groupCostChart = null;

// Colours for real departments.
const DEPT_PALETTE = [
    '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
    '#ec4899', '#06b6d4', '#84cc16', '#64748b', '#14b8a6',
    '#f43f5e', '#a855f7', '#d946ef', '#38bdf8', '#4ade80',
    '#facc15', '#f87171', '#fb923c', '#818cf8', '#c084fc'
];

// The "no department could be resolved" slice gets a muted colour of its own and is
// ordered last, so the real departments read as one set. It is assigned by identity
// (no group_id), not by position: the table is sorted by cost descending and that row is
// usually the largest, so it would otherwise take the first palette colour — the one that
// looks most like a department.
const UNRESOLVED_COLOR = '#475569';

function departmentsFirst(groups) {
    return [...groups.filter(g => g.group_id), ...groups.filter(g => !g.group_id)];
}

export function initGroupAnalyticsChart() {
    const ctx = document.getElementById('groupCostChart');
    if (!ctx) return;

    // eslint-disable-next-line no-undef
    groupCostChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: [],
            datasets: [{
                data: [],
                backgroundColor: DEPT_PALETTE,
                borderWidth: 0,
                cutout: '70%'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'right', labels: { color: '#e2e8f0', padding: 20 } },
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            return ' ' + usd4(context.raw);
                        }
                    }
                }
            }
        }
    });
}

function getUrlParams() {
    return buildRangeParams();
}

// Average latency is shown with the number of requests it was measured over. latency_ms is
// absent on every reconciled row, so the average never covers all successful requests —
// stating the sample size is the difference between a figure and a claim.
function latencyCell(g) {
    if (g.avg_latency_ms == null) {
        return '<span style="color:#64748b;" title="Không có request nào trong khoảng này ghi được latency">—</span>';
    }
    const n = g.latency_sample_count;
    // "64/108 req" rather than "64 mẫu": a ratio says "not all of them" without asking the
    // reader to know what a sample is, and keeps the absolute count that a percentage loses.
    const note = n == null ? '' :
        ` <span style="color:#64748b; font-size:11px;" title="Chỉ ${n} trong ${g.total_requests} request của nhóm có ghi latency — các dòng reconciled không ghi trường này, nên trung bình chỉ tính trên phần đo được">(${n}/${g.total_requests} req)</span>`;
    return `${g.avg_latency_ms.toFixed(1)}${note}`;
}

// Two things the table cannot say by itself: that the department a cost lands on is the
// CURRENT one (Open WebUI keeps no membership history, so a transfer carries the whole
// past with it), and that anyone sitting in more than one group has their cost counted
// under just one of them. Both are rules a reader would otherwise have to discover.
function renderGroupNotes(data) {
    const el = document.getElementById('groupAnalyticsNotes');
    if (!el) return;

    // The scorecard divides only the cost that IS attributable to a department, while the
    // table below also contains the unresolved row. On dev that row is 48% of all spending,
    // so adding up the table and dividing by the department count gives roughly double the
    // card. This note is the only thing that explains the gap — without it the card
    // misleads more than it informs.
    const unresolved = (data.groups || []).find(g => !g.group_id);
    const tip = 'Dòng đó gồm ba loại: nhân viên chưa được thêm vào phòng ban nào · '
        + 'tài khoản đã bị xoá khỏi Open WebUI (lịch sử chi phí vẫn được giữ) · '
        + 'định danh hệ thống không phải người dùng (ví dụ admin). '
        + 'Vì vậy tổng chi phí trong bảng sẽ lớn hơn các phòng ban cộng lại.';

    const parts = [
        `<div>📊 Ba thẻ trên chỉ tính người <strong>đã được gán phòng ban</strong> — phần còn lại nằm ở dòng ` +
        `<em>Chưa quy được phòng ban</em> trong bảng dưới` +
        // Scoped to the selected window on purpose: this share swings from 48% on the last
        // 30 days to 92% over all history. Calling it "tổng chi phí" invites the reader to
        // treat one window's number as a standing fact about the organisation.
        (unresolved ? ` (<strong>${Number(unresolved.cost_share_of_system_percent || 0).toFixed(1)}%</strong> chi phí trong khoảng đang xem)` : '') +
        `. <span style="cursor:help; border-bottom:1px dotted #64748b;" title="${tip}">ⓘ</span></div>`,
        `<div style="margin-top:6px;">🏢 Hệ thống có <strong>${data.department_count ?? '—'}</strong> phòng ban. ` +
        `Chi phí được phân bổ theo <strong>cơ cấu tổ chức hiện tại</strong> — người chuyển phòng sẽ mang ` +
        `toàn bộ lịch sử sang phòng mới, nên báo cáo của một kỳ đã qua có thể đổi số sau khi có người chuyển phòng.</div>`
    ];

    const multi = data.multi_group_user_count || 0;
    if (multi > 0) {
        parts.push(
            `<div style="margin-top:6px; color:#f59e0b;">⚠️ <strong>${multi}</strong> người thuộc nhiều nhóm — ` +
            `chi phí của họ được tính vào nhóm <strong>vào sớm nhất</strong>. ` +
            `Nếu đây là người vừa chuyển phòng, hãy xoá họ khỏi phòng ban cũ bên Open WebUI.</div>`
        );
    }
    el.innerHTML = parts.join('');
}

// A figure that cannot be computed shows a dash WITH its reason. A bare dash reads as a
// data fault; a dash that says why reads as an answer.
function dash(reason) {
    return `<span style="color:#64748b;" title="${reason}">—</span>`;
}

function pct1(v) {
    return v == null ? dash('Không tính được') : `${Number(v).toFixed(1)}%`;
}

// Cost per head. None means there is nobody to divide by — 0 would read as "free".
function perHead(value, reason) {
    return value == null ? dash(reason) : usd4(value);
}

// Derive the one comparable figure from a window's payload.
//
// Returns null when no department spent anything in that window — not 0. loadCompare's
// contract asks for null in that case, and for good reason: a percentage change measured
// against zero is a division by zero dressed up as a number. Both past windows are empty on
// dev today (departmental spending is all inside the last 30 days), so without this the
// badge would read an invented jump instead of an honest "—".
function _pickDeptAvg(json) {
    const n = json && json.department_count;
    if (!n || !json.dept_cost_total) return null;
    return { dept_avg_cost: json.dept_cost_total / n };
}

// The three-window fetch is NOT built here — compare_data.loadCompare already does it for
// four other tabs. The plan's claim that this needs "one registry line" was wrong (the
// registry only describes formatting), but so was the assumption that a new mechanism was
// needed: the tab simply had to call the shared one.
async function renderGroupCompare(data) {
    try {
        const cmp = await loadCompare('/v1/_mw/admin/analytics/groups', _pickDeptAvg);
        const n = data.department_count;
        // Anchor on the VALUE element, never on a pre-built badge div: renderDelta clears
        // any `.delta-badge` inside the card before drawing, so a badge used as the anchor
        // deletes itself on the first render and every later one finds nothing.
        renderDelta('grpAvgCostPerDept', 'dept_avg_cost', {
            current: n > 0 && data.dept_cost_total != null ? data.dept_cost_total / n : null,
            kt: side(cmp.kt, 'dept_avg_cost'),
            ck: side(cmp.ck, 'dept_avg_cost'),
        });
    } catch (err) {
        console.error('Group compare badges failed:', err);
    }
}

function renderGroupScorecard(data) {
    const set = (id, html) => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = html;
    };
    set('grpDeptCount', data.department_count ?? '—');

    // Shown as a pair on purpose: the gap between the two is how many people have an
    // account but no department, and that gap is the reason some spending cannot be
    // attributed at all. Showing only the left number would read as total headcount.
    const assigned = data.assigned_member_count;
    const provisioned = data.provisioned_user_count;
    if (assigned == null) {
        set('grpAssignedMembers', dash('Không đọc được danh sách nhân sự'));
    } else if (provisioned == null) {
        set('grpAssignedMembers', String(assigned));
        set('grpAssignedHint', 'Không đọc được tổng số tài khoản để so');
    } else {
        set('grpAssignedMembers', `${assigned} <span style="font-size:60%; color:#94a3b8;">/ ${provisioned}</span>`);
        const gap = provisioned - assigned;
        set('grpAssignedHint', gap > 0
            ? `Còn <strong>${gap}</strong> tài khoản chưa được gán phòng ban`
            : 'Mọi tài khoản đã được gán phòng ban');
    }

    const n = data.department_count;
    set('grpAvgCostPerDept', n > 0 && data.dept_cost_total != null
        ? usd4(data.dept_cost_total / n)
        : dash('Chưa có phòng ban nào'));
}

// Three states, never collapsed into one. "We could not look it up" and "there is no cap"
// are opposite meanings; showing both as a dash would be the mislabelling this tab exists
// to remove. The period stated in the header is the quota period, NOT the selected window.
function quotaCell(u) {
    switch (u.quota_state) {
        case 'unlimited':
            return '<span style="color:#94a3b8;" title="Tài khoản này không đặt hạn mức chi phí">Không giới hạn</span>';
        case 'no_account':
            return dash('Không phải tài khoản người dùng của middleware, hoặc tài khoản đã bị xoá — không có hạn mức để tra');
        case 'deleted':
            return dash('Tài khoản đã bị xoá — chi phí đã phát sinh vẫn giữ, nhưng hạn mức không còn hiệu lực');
        case 'ok': {
            const v = u.quota_percent_used;
            if (v == null) return dash('Không đọc được hạn mức');
            const color = v >= 95 ? '#ef4444' : v >= 80 ? '#f59e0b' : '#e2e8f0';
            return `<span style="color:${color};">${v.toFixed(1)}%</span>`;
        }
        default:
            return dash('Không xác định được trạng thái hạn mức');
    }
}

export async function fetchData() {
    const tbody = document.getElementById('groupAnalyticsTable');
    if (tbody) tbody.innerHTML = '<tr><td colspan="10" class="loading">Loading...</td></tr>';
    
    try {
        updateStatus('ok', 'Loading group analytics...');
        const params = getUrlParams();
        const res = await mwFetch(`/v1/_mw/admin/analytics/groups?${params}`);
        
        if (!res) return;
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        
        const data = await res.json();
        
        renderGroupScorecard(data);
        renderGroupCompare(data);
        renderGroupNotes(data);

        // Update Chart
        if (groupCostChart && data.groups) {
            const ordered = departmentsFirst(data.groups);
            groupCostChart.data.labels = ordered.map(g => g.group_name);
            groupCostChart.data.datasets[0].data = ordered.map(g => g.total_cost);
            groupCostChart.data.datasets[0].backgroundColor = ordered.map(
                (g, i) => (g.group_id ? DEPT_PALETTE[i % DEPT_PALETTE.length] : UNRESOLVED_COLOR)
            );
            groupCostChart.update();
        }

        // Update Table
        if (tbody) {
            if (!data.groups || data.groups.length === 0) {
                tbody.innerHTML = '<tr><td colspan="10" class="loading">No data found.</td></tr>';
                updateStatus('warning', 'No group data found');
                return;
            }
            
            tbody.innerHTML = data.groups.map(g => {
                const modelHtml = g.model_preferences.slice(0, 3).map(m => 
                    `<span style="background: #334155; padding: 2px 6px; border-radius: 4px; font-size: 11px; margin-right: 4px; display: inline-block; margin-bottom: 2px;">${m.model} ${m.percentage}%</span>`
                ).join('');
                
                const isDept = g.group_id != null;
                // The unresolved row has spenders but no members, so every per-head figure
                // is not applicable rather than zero.
                const noHead = 'Dòng này không phải một phòng ban nên không có nhân sự để chia';
                const noMembers = 'Phòng ban chưa có nhân sự nào';
                const noActive = 'Không ai trong phòng phát sinh request trong khoảng này';

                return `
                    <tr class="group-row hover-row" data-group-id="${g.group_id || 'uncategorized'}" style="cursor: pointer;" title="Bấm để xem chi tiết từng người trong phòng ban">
                        <td style="font-weight: bold;">${g.group_name}</td>
                        <td>${g.total_requests.toLocaleString()}</td>
                        <td>${g.total_tokens.toLocaleString()}</td>
                        <td style="color: #10b981;">${usd4(g.total_cost)}</td>
                        <td>${pct1(g.cost_share_of_system_percent)}</td>
                        <td>${isDept ? g.primary_member_count : dash(noHead)}</td>
                        <td>${perHead(g.cost_per_member, isDept ? noMembers : noHead)}</td>
                        <td>${perHead(g.cost_per_active_member, isDept ? noActive : noHead)}</td>
                        <td>${latencyCell(g)}</td>
                        <td>${modelHtml}</td>
                    </tr>
                `;
            }).join('');

            // Attach event listeners for drill-down
            tbody.querySelectorAll('.group-row').forEach(row => {
                row.addEventListener('click', () => toggleGroupDrilldown(row));
            });
        }
        updateStatus('ok', 'Group analytics updated ✓');
    } catch (e) {
        console.error('Group Analytics fetch error:', e);
        if (tbody) tbody.innerHTML = `<tr><td colspan="10" style="color: #ef4444; text-align: center;">Error: ${e.message}</td></tr>`;
        updateStatus('error', `Error: ${e.message}`);
    }
}

async function toggleGroupDrilldown(row) {
    const groupId = row.getAttribute('data-group-id');
    const nextRow = row.nextElementSibling;

    // If already expanded, just toggle visibility
    if (nextRow && nextRow.classList.contains('group-drilldown-row')) {
        const isHidden = nextRow.style.display === 'none';
        nextRow.style.display = isHidden ? 'table-row' : 'none';
        return;
    }

    // Otherwise, fetch and insert new row
    const drilldownRow = document.createElement('tr');
    drilldownRow.className = 'group-drilldown-row';
    drilldownRow.innerHTML = `<td colspan="10" style="padding: 0; background: #0f172a; border-bottom: 1px solid #1e293b;">
        <div style="padding: 16px; border-left: 4px solid #3b82f6;">
            <div class="loading" style="text-align: left; margin: 0;">Loading users...</div>
        </div>
    </td>`;
    row.parentNode.insertBefore(drilldownRow, row.nextSibling);

    try {
        const params = getUrlParams();
        const res = await mwFetch(`/v1/_mw/admin/analytics/groups/${groupId}/users?${params}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        if (!data.users || data.users.length === 0) {
            drilldownRow.innerHTML = `<td colspan="10" style="padding: 0; background: #0f172a; border-bottom: 1px solid #1e293b;">
                <div style="padding: 16px; border-left: 4px solid #3b82f6; color: #94a3b8;">No active users found in this time range.</div>
            </td>`;
            return;
        }

        const cell = 'border: none; padding: 6px 12px;';
        const userRows = data.users.map(u => `
            <tr style="background: transparent;">
                <td style="${cell} font-family: monospace; color: #94a3b8;">${u.user_id}</td>
                <td style="${cell}">${u.user_name}</td>
                <td style="${cell}">${u.total_requests.toLocaleString()}</td>
                <td style="${cell}">${u.total_tokens.toLocaleString()}</td>
                <td style="${cell} color: #10b981;">${usd4(u.total_cost)}</td>
                <td style="${cell}">${pct1(u.cost_share_of_group_percent)}</td>
                <td style="${cell}">${quotaCell(u)}</td>
            </tr>
        `).join('');

        // Reusing max-height and overflow-y-auto to match quota management tables
        drilldownRow.innerHTML = `<td colspan="10" style="padding: 0; background: #0f172a; border-bottom: 1px solid #1e293b;">
            <div style="padding: 16px; border-left: 4px solid #3b82f6;">
                <div style="max-height: 250px; overflow-y: auto; background: #1e293b; border-radius: 6px; border: 1px solid #334155;">
                    <table style="width: 100%; border-collapse: collapse; margin: 0; font-size: 13px;">
                        <thead style="background: #334155; position: sticky; top: 0;">
                            <tr>
                                <th style="border: none; padding: 8px 12px; text-align: left; color: #94a3b8;">Email</th>
                                <th style="border: none; padding: 8px 12px; text-align: left; color: #94a3b8;">Tên</th>
                                <th style="border: none; padding: 8px 12px; text-align: left; color: #94a3b8;">Requests</th>
                                <th style="border: none; padding: 8px 12px; text-align: left; color: #94a3b8;">Tokens</th>
                                <th style="border: none; padding: 8px 12px; text-align: left; color: #94a3b8;">Chi tiêu (khoảng đang xem)</th>
                                <th style="border: none; padding: 8px 12px; text-align: left; color: #94a3b8;">Tỷ trọng trong phòng</th>
                                <th style="border: none; padding: 8px 12px; text-align: left; color: #94a3b8;">Đã dùng hạn mức (kỳ này)</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${userRows}
                        </tbody>
                    </table>
                </div>
            </div>
        </td>`;
    } catch (e) {
        drilldownRow.innerHTML = `<td colspan="10" style="padding: 0; background: #0f172a; border-bottom: 1px solid #1e293b;">
            <div style="padding: 16px; border-left: 4px solid #ef4444; color: #ef4444;">Failed to load users: ${e.message}</div>
        </td>`;
    }
}
