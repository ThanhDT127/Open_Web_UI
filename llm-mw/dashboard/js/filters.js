// Time filters and audit log filters
import { updateStatus } from './utils.js';
import { escapeHtml } from './utils.js';

// Time range state
export let currentTimeRange = { minutes: 60 }; // Default: last 1h

// Recent audit event filters (client-side)
export let auditEvents = [];
export const auditUserOptions = new Set();
export const auditModelOptions = new Set();
export let auditFilters = { user_id: '', model: '' };

// FIX: Pass event explicitly instead of using global event
export async function setTimeRange(e, minutes) {
    // Update active button
    document.querySelectorAll('.time-btn').forEach(btn => btn.classList.remove('active'));
    e.target.classList.add('active');

    // Update state and reload
    currentTimeRange = { minutes };

    // Reload data
    if (window.dashboardAPI) {
        if (window.dashboardAPI.loadSummary) {
            window.dashboardAPI.loadSummary();
        }
        if (window.dashboardAPI.refreshAnalytics) {
            window.dashboardAPI.refreshAnalytics();
        }
        if (window.dashboardAPI.refreshSatisfaction) {
            window.dashboardAPI.refreshSatisfaction();
        }
    }
    if (window.groupAnalyticsAPI && window.groupAnalyticsAPI.fetchData) {
        window.groupAnalyticsAPI.fetchData();
    }
    // RAG Health & Knowledge share this range too; reload them when open.
    if (document.getElementById('raghealthTab')?.classList.contains('active') && window.ragHealthAPI?.apply) {
        window.ragHealthAPI.apply();
    }
    if (document.getElementById('knowledgeTab')?.classList.contains('active') && window.knowledgeAPI?.apply) {
        window.knowledgeAPI.apply();
    }
}

export async function applyCustomRange() {
    const startInput = document.getElementById('customStart');
    const endInput = document.getElementById('customEnd');
    const start = startInput.value;
    const end = endInput.value;

    if (!start || !end) {
        updateStatus('warning', 'Please select both start and end times');
        if (!start) startInput.focus();
        else endInput.focus();
        return;
    }

    // Validate: start < end
    const startDate = new Date(start);
    const endDate = new Date(end);
    if (startDate >= endDate) {
        updateStatus('error', 'Start time must be before end time');
        return;
    }

    // Clear quick button selection
    document.querySelectorAll('.time-btn').forEach(btn => btn.classList.remove('active'));

    // Update state and reload
    // Replace 'Z' with '+00:00' for backend fromisoformat compatibility
    currentTimeRange = {
        start: new Date(start).toISOString().replace('Z', '+00:00'),
        end: new Date(end).toISOString().replace('Z', '+00:00')
    };

    // Reload data
    if (window.dashboardAPI) {
        if (window.dashboardAPI.loadSummary) {
            window.dashboardAPI.loadSummary();
        }
        if (window.dashboardAPI.refreshAnalytics) {
            window.dashboardAPI.refreshAnalytics();
        }
        if (window.dashboardAPI.refreshSatisfaction) {
            window.dashboardAPI.refreshSatisfaction();
        }
    }
    if (window.groupAnalyticsAPI && window.groupAnalyticsAPI.fetchData) {
        window.groupAnalyticsAPI.fetchData();
    }
    // RAG Health & Knowledge share this range too; reload them when open.
    if (document.getElementById('raghealthTab')?.classList.contains('active') && window.ragHealthAPI?.apply) {
        window.ragHealthAPI.apply();
    }
    if (document.getElementById('knowledgeTab')?.classList.contains('active') && window.knowledgeAPI?.apply) {
        window.knowledgeAPI.apply();
    }
}

// Initialize audit filters
export function initAuditFilters() {
    const userSelect = document.getElementById('auditUserFilter');
    const modelSelect = document.getElementById('auditModelFilter');
    if (!userSelect || !modelSelect) return;

    userSelect.addEventListener('change', () => {
        auditFilters.user_id = userSelect.value || '';
        renderAuditEvents();
    });
    modelSelect.addEventListener('change', () => {
        auditFilters.model = modelSelect.value || '';
        renderAuditEvents();
    });
}

// Refresh audit filter dropdown options
export function refreshAuditFilterOptions() {
    const userSelect = document.getElementById('auditUserFilter');
    const modelSelect = document.getElementById('auditModelFilter');
    if (!userSelect || !modelSelect) return;

    const currentUser = userSelect.value || '';
    const currentModel = modelSelect.value || '';

    const sortedUsers = Array.from(auditUserOptions).sort();
    const sortedModels = Array.from(auditModelOptions).sort();

    userSelect.innerHTML = '<option value="">All users</option>' +
        sortedUsers.map(u => `<option value="${escapeHtml(u)}">${escapeHtml(u)}</option>`).join('');
    modelSelect.innerHTML = '<option value="">All models</option>' +
        sortedModels.map(m => `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`).join('');

    // Preserve selection
    userSelect.value = currentUser;
    modelSelect.value = currentModel;
}

// Check if event matches current filters
function eventMatchesAuditFilters(evt) {
    if (auditFilters.user_id && evt.user_id !== auditFilters.user_id) return false;
    if (auditFilters.model && evt.model !== auditFilters.model) return false;
    return true;
}

// Render filtered audit events
export function renderAuditEvents() {
    const eventsDiv = document.getElementById('events');
    if (!eventsDiv) return;

    const filtered = auditEvents.filter(eventMatchesAuditFilters).slice(0, 50);
    if (filtered.length === 0) {
        eventsDiv.innerHTML = '<div class="loading">No events match the current filters.</div>';
        return;
    }

    eventsDiv.innerHTML = '';
    for (const data of filtered) {
        const line = document.createElement('div');
        line.className = 'event-line';

        const time = new Date(data.ts).toLocaleTimeString();
        const statusClass = `status-${data.status}`;

        line.innerHTML = `
            <span class="event-time">${escapeHtml(time)}</span>
            <span class="event-status ${escapeHtml(statusClass)}">${escapeHtml(String(data.status || '').toUpperCase())}</span>
            <span class="event-detail">
                ${escapeHtml(data.user_id || '')} | ${escapeHtml(data.model || '')} |
                ${escapeHtml(String(data.tokens_total || 0))} tokens |
                $${escapeHtml(Number(data.cost_usd || 0).toFixed(6))}
            </span>
        `;
        eventsDiv.appendChild(line);
    }
}

// Add new event to buffer and render
export function addAuditEvent(data) {
    if (!data) return;

    // Track unique user_id and model for filter options
    if (data.user_id) auditUserOptions.add(String(data.user_id));
    if (data.model) auditModelOptions.add(String(data.model));

    // Keep buffer of 200 events for filtering
    auditEvents.unshift(data);
    if (auditEvents.length > 200) auditEvents.length = 200;

    refreshAuditFilterOptions();
    renderAuditEvents();
}

// Clear audit events (on stream reconnect)
export function clearAuditEvents() {
    auditEvents = [];
    auditUserOptions.clear();
    auditModelOptions.clear();
    refreshAuditFilterOptions();
}
