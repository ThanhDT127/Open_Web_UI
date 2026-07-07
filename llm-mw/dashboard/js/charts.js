// Chart.js initialization and updates — Enhanced version
// Includes: line charts (cost, tokens, requests), donut charts (users, models, request types)
import { formatTimestamp } from './utils.js';

// Chart instances
export let costChart = null;
export let tokensChart = null;
export let requestsChart = null;
export let requestTypeChart = null;
export let userCostChart = null;
export let modelCostChart = null;

// Color palette for donut/pie charts
const COLORS = [
    '#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6',
    '#06b6d4', '#ec4899', '#14b8a6', '#f97316', '#6366f1',
    '#84cc16', '#e11d48', '#0ea5e9', '#a855f7', '#22c55e',
    '#eab308', '#64748b', '#d946ef', '#0891b2', '#dc2626'
];
const OTHERS_COLOR = '#475569'; // grey for "Others" slice
const MAX_SLICES = 10; // Max slices before grouping into "Others"

// Shared line chart config
function lineChartConfig(label, color) {
    return {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: label,
                data: [],
                borderColor: color,
                backgroundColor: color + '1a',
                tension: 0.3,
                fill: true,
                pointRadius: 2,
                pointHoverRadius: 5,
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#1e293b',
                    borderColor: '#475569',
                    borderWidth: 1,
                    titleColor: '#e2e8f0',
                    bodyColor: '#cbd5e1',
                    padding: 10,
                    cornerRadius: 8
                }
            },
            scales: {
                x: {
                    ticks: { color: '#64748b', maxRotation: 45, font: { size: 11 } },
                    grid: { color: '#1e293b' }
                },
                y: {
                    ticks: { color: '#64748b', font: { size: 11 } },
                    grid: { color: '#1e293b' },
                    beginAtZero: true
                }
            }
        }
    };
}

// Shared donut chart config
// Render custom HTML legend for donut charts
function renderCustomLegend(containerId, labels, colors, values = []) {
    const container = document.getElementById(containerId);
    if (!container) return;
    
    const total = values.reduce((a, b) => a + b, 0);
    
    container.innerHTML = labels.map((label, i) => {
        const color = colors[i] || '#cbd5e1';
        const value = values[i];
        let displayLabel = label;
        
        if (value !== undefined && total > 0) {
            const pct = ((value / total) * 100).toFixed(0);
            displayLabel = `${label} (${pct}%)`;
        }
        
        return `
            <div class="legend-item" title="${label}">
                <span class="legend-dot" style="background-color: ${color};"></span>
                <span class="legend-label">${displayLabel}</span>
            </div>
        `;
    }).join('');
}

// Shared donut chart config
function donutChartConfig() {
    return {
        type: 'doughnut',
        data: { labels: [], datasets: [{ data: [], backgroundColor: COLORS, borderWidth: 0, hoverBorderWidth: 2, hoverBorderColor: '#e2e8f0' }] },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '60%',
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    backgroundColor: '#1e293b',
                    borderColor: '#475569',
                    borderWidth: 1,
                    titleColor: '#e2e8f0',
                    bodyColor: '#cbd5e1',
                    padding: 10,
                    cornerRadius: 8,
                    callbacks: {
                        label: function (ctx) {
                            const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                            const pct = total > 0 ? ((ctx.parsed / total) * 100).toFixed(1) : 0;
                            return `${ctx.label}: $${ctx.parsed.toFixed(4)} (${pct}%)`;
                        }
                    }
                }
            }
        }
    };
}

// Group items into top N + "Others"
function groupWithOthers(labels, values, maxSlices = MAX_SLICES) {
    if (labels.length <= maxSlices) {
        return {
            labels: labels,
            values: values,
            colors: COLORS.slice(0, labels.length)
        };
    }
    const topLabels = labels.slice(0, maxSlices - 1);
    const topValues = values.slice(0, maxSlices - 1);
    const othersCount = labels.length - (maxSlices - 1);
    const othersSum = values.slice(maxSlices - 1).reduce((a, b) => a + b, 0);
    topLabels.push(`Others (${othersCount} items)`);
    topValues.push(othersSum);
    const colors = COLORS.slice(0, maxSlices - 1);
    colors.push(OTHERS_COLOR);
    return { labels: topLabels, values: topValues, colors };
}

// Initialize all charts
export function initCharts() {
    costChart = new Chart(document.getElementById('costChart').getContext('2d'), lineChartConfig('Cost (USD)', '#10b981'));
    tokensChart = new Chart(document.getElementById('tokensChart').getContext('2d'), lineChartConfig('Tokens', '#3b82f6'));
    requestsChart = new Chart(document.getElementById('requestsChart').getContext('2d'), lineChartConfig('Requests', '#f59e0b'));

    // Request type pie
    const rtConfig = donutChartConfig();
    rtConfig.options.plugins.tooltip.callbacks.label = function (ctx) {
        const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
        const pct = total > 0 ? ((ctx.parsed / total) * 100).toFixed(1) : 0;
        return `${ctx.label}: ${ctx.parsed} (${pct}%)`;
    };
    requestTypeChart = new Chart(document.getElementById('requestTypeChart').getContext('2d'), rtConfig);

    // User cost donut
    userCostChart = new Chart(document.getElementById('userCostChart').getContext('2d'), donutChartConfig());

    // Model cost donut
    modelCostChart = new Chart(document.getElementById('modelCostChart').getContext('2d'), donutChartConfig());
}

// Update all charts with summary data
export async function updateCharts(summaryData) {
    if (!summaryData || !costChart) return;

    // --- Timeseries line charts ---
    const timeseries = summaryData.timeseries || [];

    if (timeseries.length === 0) {
        [costChart, tokensChart, requestsChart].forEach(c => {
            c.data.labels = [];
            c.data.datasets[0].data = [];
            c.update();
        });
    } else {
        const labels = timeseries.map(b => {
            const d = new Date(b.ts);
            return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' });
        });

        costChart.data.labels = labels;
        costChart.data.datasets[0].data = timeseries.map(b => b.cost_usd || 0);
        costChart.update();

        tokensChart.data.labels = labels;
        tokensChart.data.datasets[0].data = timeseries.map(b => b.tokens_total || 0);
        tokensChart.update();

        requestsChart.data.labels = labels;
        requestsChart.data.datasets[0].data = timeseries.map(b => b.requests_total || 0);
        requestsChart.update();
    }

    // --- Request type pie chart ---
    if (summaryData.totals) {
        const t = summaryData.totals;
        const types = [];
        const values = [];
        if (t.chat_calls > 0) { types.push('Chat'); values.push(t.chat_calls); }
        if (t.embedding_calls > 0) { types.push('Embedding'); values.push(t.embedding_calls); }
        if (t.image_calls > 0) { types.push('Image'); values.push(t.image_calls); }
        if (t.audio_calls > 0) { types.push('Audio'); values.push(t.audio_calls); }
        if (t.video_calls > 0) { types.push('Video'); values.push(t.video_calls); }

        if (values.length === 0) { types.push('No data'); values.push(1); }

        requestTypeChart.data.labels = types;
        requestTypeChart.data.datasets[0].data = values;
        requestTypeChart.data.datasets[0].backgroundColor = COLORS.slice(0, values.length);
        requestTypeChart.update();
        renderCustomLegend('requestTypeLegend', types, COLORS.slice(0, values.length), values);
    }

    // --- User cost donut chart ---
    updateUserCostChart(summaryData.breakdown_by_user || []);

    // --- Model cost donut chart ---
    updateModelCostChart(summaryData.breakdown_by_model || []);
}

// Exported: update user cost donut chart (called from usage.js on Top-N/Sort change)
export function updateUserCostChart(users) {
    if (!userCostChart) return;
    if (users.length > 0) {
        const grouped = groupWithOthers(
            users.map(u => u.user_id),
            users.map(u => u.cost_usd || 0)
        );
        userCostChart.data.labels = grouped.labels;
        userCostChart.data.datasets[0].data = grouped.values;
        userCostChart.data.datasets[0].backgroundColor = grouped.colors;
        renderCustomLegend('userCostLegend', grouped.labels, grouped.colors, grouped.values);
    } else {
        userCostChart.data.labels = ['No data'];
        userCostChart.data.datasets[0].data = [1];
        userCostChart.data.datasets[0].backgroundColor = ['#334155'];
        renderCustomLegend('userCostLegend', ['No data'], ['#334155']);
    }
    userCostChart.update();
}

// Exported: update model cost donut chart (called from usage.js on Top-N/Sort change)
export function updateModelCostChart(models) {
    if (!modelCostChart) return;
    if (models.length > 0) {
        const grouped = groupWithOthers(
            models.map(m => m.model?.replace('chat-', '') || 'unknown'),
            models.map(m => m.cost_usd || 0)
        );
        modelCostChart.data.labels = grouped.labels;
        modelCostChart.data.datasets[0].data = grouped.values;
        modelCostChart.data.datasets[0].backgroundColor = grouped.colors;
        renderCustomLegend('modelCostLegend', grouped.labels, grouped.colors, grouped.values);
    } else {
        modelCostChart.data.labels = ['No data'];
        modelCostChart.data.datasets[0].data = [1];
        modelCostChart.data.datasets[0].backgroundColor = ['#334155'];
        renderCustomLegend('modelCostLegend', ['No data'], ['#334155']);
    }
    modelCostChart.update();
}
