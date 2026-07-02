import { mwFetch, updateStatus } from './utils.js';
import { currentTimeRange } from './filters.js';

let groupCostChart = null;

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
                backgroundColor: [
                    '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
                    '#ec4899', '#06b6d4', '#84cc16', '#64748b', '#14b8a6',
                    '#f43f5e', '#a855f7', '#d946ef', '#38bdf8', '#4ade80',
                    '#facc15', '#f87171', '#fb923c', '#818cf8', '#c084fc'
                ],
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
                            return ` $${context.raw.toFixed(4)}`;
                        }
                    }
                }
            }
        }
    });
}

function getUrlParams() {
    const params = new URLSearchParams();
    if (currentTimeRange && currentTimeRange.minutes) {
        params.append('minutes', currentTimeRange.minutes);
    } else if (currentTimeRange && currentTimeRange.start && currentTimeRange.end) {
        params.append('start', currentTimeRange.start);
        params.append('end', currentTimeRange.end);
    } else {
        params.append('minutes', 43200); // 30d default
    }
    return params;
}

export async function fetchData() {
    const tbody = document.getElementById('groupAnalyticsTable');
    if (tbody) tbody.innerHTML = '<tr><td colspan="7" class="loading">Loading...</td></tr>';
    
    try {
        updateStatus('ok', 'Loading group analytics...');
        const params = getUrlParams();
        const res = await mwFetch(`/v1/_mw/admin/analytics/groups?${params}`);
        
        if (!res) return;
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        
        const data = await res.json();
        
        // Update Chart
        if (groupCostChart && data.groups) {
            groupCostChart.data.labels = data.groups.map(g => g.group_name);
            groupCostChart.data.datasets[0].data = data.groups.map(g => g.total_cost);
            groupCostChart.update();
        }
        
        // Update Table
        if (tbody) {
            if (!data.groups || data.groups.length === 0) {
                tbody.innerHTML = '<tr><td colspan="7" class="loading">No data found.</td></tr>';
                updateStatus('warning', 'No group data found');
                return;
            }
            
            tbody.innerHTML = data.groups.map(g => {
                const modelHtml = g.model_preferences.slice(0, 3).map(m => 
                    `<span style="background: #334155; padding: 2px 6px; border-radius: 4px; font-size: 11px; margin-right: 4px; display: inline-block; margin-bottom: 2px;">${m.model} ${m.percentage}%</span>`
                ).join('');
                
                return `
                    <tr class="group-row hover-row" data-group-id="${g.group_id || 'uncategorized'}" style="cursor: pointer;" title="Click to view users in this group">
                        <td style="font-family: monospace; color: #94a3b8;">${g.group_id || 'N/A'}</td>
                        <td style="font-weight: bold;">${g.group_name}</td>
                        <td>${g.total_requests.toLocaleString()}</td>
                        <td>${g.total_tokens.toLocaleString()}</td>
                        <td style="color: #10b981;">$${g.total_cost.toFixed(4)}</td>
                        <td>${g.avg_latency_ms.toFixed(1)}</td>
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
        if (tbody) tbody.innerHTML = `<tr><td colspan="7" style="color: #ef4444; text-align: center;">Error: ${e.message}</td></tr>`;
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
    drilldownRow.innerHTML = `<td colspan="7" style="padding: 0; background: #0f172a; border-bottom: 1px solid #1e293b;">
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
            drilldownRow.innerHTML = `<td colspan="7" style="padding: 0; background: #0f172a; border-bottom: 1px solid #1e293b;">
                <div style="padding: 16px; border-left: 4px solid #3b82f6; color: #94a3b8;">No active users found in this time range.</div>
            </td>`;
            return;
        }

        const userRows = data.users.map(u => `
            <tr style="background: transparent;">
                <td style="border: none; padding: 6px 12px; font-family: monospace; color: #94a3b8;">${u.user_id}</td>
                <td style="border: none; padding: 6px 12px;">${u.user_name}</td>
                <td style="border: none; padding: 6px 12px;">${u.total_requests.toLocaleString()}</td>
                <td style="border: none; padding: 6px 12px;">${u.total_tokens.toLocaleString()}</td>
                <td style="border: none; padding: 6px 12px; color: #10b981;">$${u.total_cost.toFixed(4)}</td>
            </tr>
        `).join('');

        // Reusing max-height and overflow-y-auto to match quota management tables
        drilldownRow.innerHTML = `<td colspan="7" style="padding: 0; background: #0f172a; border-bottom: 1px solid #1e293b;">
            <div style="padding: 16px; border-left: 4px solid #3b82f6;">
                <div style="max-height: 250px; overflow-y: auto; background: #1e293b; border-radius: 6px; border: 1px solid #334155;">
                    <table style="width: 100%; border-collapse: collapse; margin: 0; font-size: 13px;">
                        <thead style="background: #334155; position: sticky; top: 0;">
                            <tr>
                                <th style="border: none; padding: 8px 12px; text-align: left; color: #94a3b8;">Email</th>
                                <th style="border: none; padding: 8px 12px; text-align: left; color: #94a3b8;">Name</th>
                                <th style="border: none; padding: 8px 12px; text-align: left; color: #94a3b8;">Requests</th>
                                <th style="border: none; padding: 8px 12px; text-align: left; color: #94a3b8;">Tokens</th>
                                <th style="border: none; padding: 8px 12px; text-align: left; color: #94a3b8;">Cost</th>
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
        drilldownRow.innerHTML = `<td colspan="7" style="padding: 0; background: #0f172a; border-bottom: 1px solid #1e293b;">
            <div style="padding: 16px; border-left: 4px solid #ef4444; color: #ef4444;">Failed to load users: ${e.message}</div>
        </td>`;
    }
}
