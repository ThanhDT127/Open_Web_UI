// Time filters and audit log filters
import { updateStatus } from './utils.js';
import { escapeHtml } from './utils.js';

// Time range state — the admin's SELECTION, not the window used for fetching.
// Kept in its original shape ({minutes} or {start,end}) because callers still read it
// for display and for bucket-size hints (see buildRangeParams below).
export let currentTimeRange = { minutes: 60 }; // Default: last 1h

// The selection resolved into an absolute window, pinned once per refresh cycle.
// Every tab in a cycle fetches the same window, so two tabs showing the same metric
// cannot disagree just because they were loaded a few seconds apart.
let resolvedWindow = null;

function toIsoParam(date) {
    // Backends parse with fromisoformat(); normalise the 'Z' suffix they choke on.
    return date.toISOString().replace('Z', '+00:00');
}

// Recompute the absolute window from the current selection. Call at the start of a
// refresh cycle and whenever the selection changes — presets keep rolling forward,
// they are just pinned for the duration of one cycle.
// Announce that the admin picked a different range. compare_data.js listens and drops
// its cache. An event rather than a direct call, so filters.js and compare_data.js do
// not import each other into a cycle.
function announceRangeChange() {
    try { document.dispatchEvent(new CustomEvent('range:changed')); } catch (e) { /* noop */ }
}

export function resolveTimeWindow() {
    if (currentTimeRange.start && currentTimeRange.end) {
        resolvedWindow = { start: currentTimeRange.start, end: currentTimeRange.end };
    } else {
        const minutes = currentTimeRange.minutes || 60;
        const end = new Date();
        const start = new Date(end.getTime() - minutes * 60 * 1000);
        resolvedWindow = { start: toIsoParam(start), end: toIsoParam(end) };
    }
    return resolvedWindow;
}

export function getTimeWindow() {
    return resolvedWindow || resolveTimeWindow();
}

// Single builder for every dashboard request's time parameters.
// Replaces 10 hand-rolled copies that each evaluated their own Date.now().
export function buildRangeParams(extra = {}) {
    const win = getTimeWindow();
    const params = new URLSearchParams();
    params.append('start', win.start);
    params.append('end', win.end);
    // `minutes` still travels for preset selections. The window always comes from
    // start/end — every backend resolver prefers those when present — but
    // get_chat_analytics keys its bucket size off `minutes`, so dropping it would
    // silently switch that tab's chart from hourly to daily buckets.
    if (currentTimeRange.minutes) {
        params.append('minutes', currentTimeRange.minutes);
    }
    for (const [k, v] of Object.entries(extra)) {
        if (v) params.append(k, v);
    }
    return params;
}

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
    resolveTimeWindow();
    announceRangeChange();

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
    resolveTimeWindow();
    announceRangeChange();

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
