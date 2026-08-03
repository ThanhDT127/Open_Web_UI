import { mwFetch } from './utils.js';
import { currentTimeRange, buildRangeParams } from './filters.js';
import { renderDelta } from './metrics_registry.js';
import { loadCompare, side } from './compare_data.js';

// ── Period-comparison badges ─────────────────────────────────
// This endpoint names the same three metrics differently from /summary
// (`requests` vs `requests_total`, and so on). Normalise here rather than declaring them
// twice in the registry: one metric must have exactly one declaration, otherwise the two
// tabs showing it can drift apart in format or colour — the thing the registry exists to
// prevent.
function _normaliseTotals(t) {
    if (!t) return null;
    return {
        requests_total: t.requests,
        tokens_total: t.tokens,
        cost_total_usd: t.cost_usd,
        chats: t.chats,
        active_users: t.active_users,
    };
}

const _pickChatTotals = (json) => {
    const t = json && json.totals;
    return t && t.requests > 0 ? _normaliseTotals(t) : null;
};

// `analyticsTotalChats` and `analyticsActiveUsers` are listed on purpose even though the
// registry blocks them: their source is Open WebUI's `chat` table, which users can delete
// from, so any past window is eroded and a comparison would report a confident, false
// drop. Listing them here means the block is exercised rather than assumed.
const _COMPARE_CARDS = [
    ['analyticsTotalMessages', 'requests_total'],
    ['analyticsTotalTokens', 'tokens_total'],
    ['analyticsTotalCost', 'cost_total_usd'],
    ['analyticsTotalChats', 'chats'],
    ['analyticsActiveUsers', 'active_users'],
];

async function _renderCompare(rawTotals) {
    try {
        const current = _normaliseTotals(rawTotals);
        const cmp = await loadCompare('/v1/_mw/admin/analytics/chat', _pickChatTotals);
        for (const [elementId, key] of _COMPARE_CARDS) {
            renderDelta(elementId, key, {
                current: current[key],
                kt: side(cmp.kt, key),
                ck: side(cmp.ck, key),
            });
        }
    } catch (err) {
        console.error('Chat analytics compare badges failed:', err);
    }
}

let analyticsDualChart = null;
let analyticsHourlyChart = null;
let analyticsModelChart = null;

export function initAnalyticsChart() {
    // 1. Dual Axis Chart (Daily Trend)
    const ctxDual = document.getElementById('analyticsDualChart');
    if (ctxDual) {
        analyticsDualChart = new Chart(ctxDual, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Lượt gọi',
                        data: [],
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        yAxisID: 'y',
                        tension: 0.3,
                        fill: true
                    },
                    {
                        label: 'Chi phí (USD)',
                        data: [],
                        borderColor: '#10b981',
                        backgroundColor: 'rgba(16, 185, 129, 0.1)',
                        yAxisID: 'y1',
                        tension: 0.3,
                        fill: true
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { labels: { color: '#cbd5e1' } },
                    tooltip: { backgroundColor: '#1e293b', titleColor: '#fff', bodyColor: '#cbd5e1' }
                },
                scales: {
                    x: { ticks: { color: '#94a3b8' }, grid: { color: '#334155' } },
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        ticks: { color: '#94a3b8' },
                        grid: { color: '#334155' },
                        title: { display: true, text: 'Lượt gọi', color: '#3b82f6' },
                        beginAtZero: true
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        ticks: { color: '#94a3b8' },
                        grid: { drawOnChartArea: false },
                        title: { display: true, text: 'Chi phí (USD)', color: '#10b981' },
                        beginAtZero: true
                    }
                }
            }
        });
    }

    // 2. Hourly Activity Bar Chart
    const ctxHourly = document.getElementById('analyticsHourlyChart');
    if (ctxHourly) {
        analyticsHourlyChart = new Chart(ctxHourly, {
            type: 'bar',
            data: {
                labels: Array.from({ length: 24 }, (_, i) => `${i}h`),
                datasets: [{
                    // Each bar is one clock hour summed across every day in the window, so
                    // the legend must not read as a per-day figure.
                    label: 'Lượt gọi (cộng dồn mọi ngày)',
                    data: [],
                    backgroundColor: '#8b5cf6', // Purple
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { backgroundColor: '#1e293b', titleColor: '#fff', bodyColor: '#cbd5e1' }
                },
                scales: {
                    x: { ticks: { color: '#94a3b8' }, grid: { display: false } },
                    y: {
                        ticks: { color: '#94a3b8', precision: 0 },
                        grid: { color: '#334155' },
                        beginAtZero: true
                    }
                }
            }
        });
    }

    // 3. Model Breakdown Doughnut Chart
    const ctxModel = document.getElementById('analyticsModelChart');
    if (ctxModel) {
        analyticsModelChart = new Chart(ctxModel, {
            type: 'doughnut',
            data: {
                labels: [],
                datasets: [{
                    data: [],
                    backgroundColor: [
                        '#3b82f6', '#10b981', '#f59e0b', '#ef4444',
                        '#8b5cf6', '#ec4899', '#14b8a6', '#f97316'
                    ],
                    borderWidth: 0,
                    hoverOffset: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'right', labels: { color: '#cbd5e1', font: { size: 11 } } },
                    tooltip: {
                        backgroundColor: '#1e293b',
                        callbacks: {
                            label: function (context) {
                                const val = context.raw;
                                return ` $${val.toFixed(4)}`;
                            }
                        }
                    }
                },
                cutout: '70%'
            }
        });
    }
}

export async function refreshAnalytics() {
    const tableBody = document.getElementById('analyticsLeaderboardTable');
    if (!tableBody) return;

    try {
        tableBody.innerHTML = '<tr><td colspan="9" class="loading">Đang tải...</td></tr>';

        // buildRangeParams still carries `minutes` for presets — get_chat_analytics
        // picks its bucket size from it, and the label formatting below reads it too.
        const params = buildRangeParams();

        const res = await mwFetch(`/v1/_mw/admin/analytics/chat?${params}`);

        if (!res.ok) {
            throw new Error(`HTTP ${res.status}`);
        }

        const data = await res.json();

        // 1. Update summary metrics
        document.getElementById('analyticsTotalChats').textContent = data.totals.chats.toLocaleString();
        document.getElementById('analyticsTotalMessages').textContent = data.totals.requests.toLocaleString();
        document.getElementById('analyticsTotalTokens').textContent = data.totals.tokens.toLocaleString();
        document.getElementById('analyticsTotalCost').textContent = `$${data.totals.cost_usd.toFixed(4)}`;

        const activeUsersEl = document.getElementById('analyticsActiveUsers');
        if (activeUsersEl) {
            activeUsersEl.textContent = (data.totals.active_users || 0).toLocaleString();
        }

        _renderCompare(data.totals);

        // 2. Render Dual Axis Chart (Daily Trend)
        if (analyticsDualChart && data.timeseries) {
            const m = currentTimeRange?.minutes;
            const isHourly = m && m <= 1440;
            const labels = data.timeseries.map(ts => {
                // ts.period is like "2026-06-28" or "2026-06-28 14:00"
                if (isHourly) {
                    return ts.period.split(' ')[1]; // Extract "14:00"
                } else {
                    const d = new Date(ts.period);
                    return `${d.getMonth() + 1}/${d.getDate()}`;
                }
            });
            const requests = data.timeseries.map(ts => ts.requests);
            const costs = data.timeseries.map(ts => ts.cost_usd);

            analyticsDualChart.data.labels = labels;
            analyticsDualChart.data.datasets[0].data = requests;
            analyticsDualChart.data.datasets[1].data = costs;
            analyticsDualChart.update();
        }

        // 3. Render Hourly Activity Chart
        if (analyticsHourlyChart && data.hourly_activity) {
            const activityData = data.hourly_activity.map(ha => ha.count);
            analyticsHourlyChart.data.datasets[0].data = activityData;
            analyticsHourlyChart.update();
        }

        // 4. Render Model Breakdown Chart
        if (analyticsModelChart && data.model_breakdown) {
            analyticsModelChart.data.labels = data.model_breakdown.map(m => m.model);
            analyticsModelChart.data.datasets[0].data = data.model_breakdown.map(m => m.cost_usd);
            analyticsModelChart.update();
        }

        // 5. Render Top Models Table
        const modelsTable = document.getElementById('analyticsTopModelsTable');
        if (modelsTable && data.model_breakdown) {
            modelsTable.innerHTML = '';
            if (data.model_breakdown.length === 0) {
                modelsTable.innerHTML = '<tr><td colspan="3" style="text-align:center; color:#64748b;">Chưa có dữ liệu</td></tr>';
            } else {
                data.model_breakdown.forEach(m => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td style="font-weight: 500; font-size:12px;">${m.model}</td>
                        <td style="font-size:12px;">${m.requests.toLocaleString()}</td>
                        <td style="color: #10b981; font-size:12px;">$${m.cost_usd.toFixed(4)}</td>
                    `;
                    modelsTable.appendChild(tr);
                });
            }
        }

        // 6. Render Leaderboard
        if (data.leaderboard && data.leaderboard.length > 0) {
            tableBody.innerHTML = '';
            const totalCost = data.totals.cost_usd;

            data.leaderboard.forEach((user, index) => {
                const tr = document.createElement('tr');

                let sharePct = 0;
                if (totalCost > 0) {
                    sharePct = (user.cost_usd / totalCost) * 100;
                }

                const statusTag = user.user_status === 'deleted'
                    ? ' <span style="font-size: 10px; font-weight: 600; padding: 1px 7px; border-radius: 9px; background: rgba(239,68,68,0.15); color: #f87171;">🗑️ đã xóa</span>'
                    : user.user_status === 'disabled'
                        ? ' <span style="font-size: 10px; font-weight: 600; padding: 1px 7px; border-radius: 9px; background: rgba(245,158,11,0.15); color: #fbbf24;">🔒 disabled</span>'
                        : '';

                tr.innerHTML = `
                    <td class="rank">${index + 1}</td>
                    <td style="font-weight: 500; color: #60a5fa;">${user.user_id}</td>
                    <td>${user.display_name || '-'}${statusTag}</td>
                    <td>${user.chat_count.toLocaleString()}</td>
                    <td>${user.request_count.toLocaleString()}</td>
                    <td>${user.tokens.toLocaleString()}</td>
                    <td style="color: #10b981; font-weight: bold; font-family: 'JetBrains Mono', monospace;">$${user.cost_usd.toFixed(4)}</td>
                    <td>
                        <div class="progress-bar" style="width: 80px; height: 12px;">
                            <div class="progress-fill" style="width: ${Math.min(sharePct, 100)}%; background: #10b981;"></div>
                            <span class="progress-text" style="font-size:8px;">${sharePct.toFixed(1)}%</span>
                        </div>
                    </td>
                    <td><span class="badge" style="background:#334155;">${user.top_model}</span></td>
                `;
                tableBody.appendChild(tr);
            });
        } else {
            tableBody.innerHTML = '<tr><td colspan="9" style="text-align:center; padding: 20px; color: #64748b;">No analytics data found for this period.</td></tr>';
        }

    } catch (e) {
        console.error('Failed to load chat analytics:', e);
        tableBody.innerHTML = `<tr><td colspan="9" class="error-msg">Error loading analytics: ${e.message}</td></tr>`;
    }
}
