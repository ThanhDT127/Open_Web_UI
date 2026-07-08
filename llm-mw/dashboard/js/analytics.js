import { mwFetch } from './utils.js';
import { currentTimeRange } from './filters.js';

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
                        label: 'Requests',
                        data: [],
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        yAxisID: 'y',
                        tension: 0.3,
                        fill: true
                    },
                    {
                        label: 'Cost (USD)',
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
                        title: { display: true, text: 'Requests', color: '#3b82f6' },
                        beginAtZero: true
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        ticks: { color: '#94a3b8' },
                        grid: { drawOnChartArea: false },
                        title: { display: true, text: 'Cost (USD)', color: '#10b981' },
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
                    label: 'Requests',
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
        tableBody.innerHTML = '<tr><td colspan="9" class="loading">Loading analytics...</td></tr>';

        const params = new URLSearchParams();
        if (currentTimeRange && currentTimeRange.minutes) {
            params.append('minutes', currentTimeRange.minutes);
        } else if (currentTimeRange && currentTimeRange.start && currentTimeRange.end) {
            params.append('start', currentTimeRange.start);
            params.append('end', currentTimeRange.end);
        } else {
            params.append('minutes', 43200); // 30d default
        }

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
                modelsTable.innerHTML = '<tr><td colspan="3" style="text-align:center; color:#64748b;">No data</td></tr>';
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

                tr.innerHTML = `
                    <td class="rank">${index + 1}</td>
                    <td style="font-weight: 500; color: #60a5fa;">${user.user_id}</td>
                    <td>${user.display_name || '-'}</td>
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
