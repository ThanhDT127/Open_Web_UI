// Logs tab logic - Audit log query with dropdown filters and Excel export
import { mwFetch } from './utils.js';
import { buildRangeParams } from './filters.js';
import { escapeHtml } from './utils.js';

let currentPage = 0;
const PAGE_SIZE = 50;
let allLogsData = []; // Store all loaded logs for export

// Filter state
export const logFilters = {
    user_id: '',
    model: '',
    status: '',
    sort_by: 'timestamp',
    sort_order: 'desc'
};

// Load logs with current filters
export async function loadLogs(append = false) {
    try {
        // Time range. Appended directly rather than through buildRangeParams'
        // `extra` map, because that map drops falsy values and `offset` is 0
        // on the first page.
        const params = buildRangeParams();

        // Pagination
        params.append('limit', PAGE_SIZE);
        params.append('offset', currentPage * PAGE_SIZE);

        // Filters
        if (logFilters.user_id) params.append('user_id', logFilters.user_id);
        if (logFilters.model) params.append('model', logFilters.model);
        if (logFilters.status) params.append('status', logFilters.status);

        // Sorting
        params.append('sort_by', logFilters.sort_by);
        params.append('sort_order', logFilters.sort_order);

        const res = await mwFetch(`/v1/_mw/audit/query?${params}`);
        if (!res || !res.ok) {
            showLogsError('Failed to load logs');
            return;
        }

        const data = await res.json();

        if (!data.results || data.results.length === 0) {
            if (!append) {
                document.getElementById('logsResults').innerHTML = '<tr><td colspan="7" class="no-data">No logs found</td></tr>';
                allLogsData = [];
            }
            document.getElementById('loadMoreBtn').style.display = 'none';
            return;
        }

        // Store data for export
        if (append) {
            allLogsData = allLogsData.concat(data.results);
        } else {
            allLogsData = data.results;
        }

        // Update stats
        document.getElementById('logsTotalCount').textContent = data.total;
        document.getElementById('logsShowing').textContent =
            `${currentPage * PAGE_SIZE + 1}-${Math.min((currentPage + 1) * PAGE_SIZE, data.total)}`;

        // Update dropdown options from API distinct values (independent of filters)
        if (data.distinct_users || data.distinct_models || data.distinct_statuses) {
            updateDropdownOptions(
                data.distinct_users || [],
                data.distinct_models || [],
                data.distinct_statuses || []
            );
        }

        // Render results
        const tbody = document.getElementById('logsResults');
        const rows = data.results.map(log => {
            const ts = new Date(log.timestamp || log.ts);
            const statusClass = log.status === 'error' ? 'status-error' : 'status-ok';
            const cost = (log.cost_usd || 0).toFixed(6);
            const tokens = log.tokens_total || 0;
            const duration = log.duration_ms || 0;

            return `
                <tr>
                    <td>${ts.toLocaleString()}</td>
                    <td>${escapeHtml(log.user_id || '-')}</td>
                    <td>${escapeHtml(log.model || '-')}</td>
                    <td><span class="${statusClass}">${escapeHtml(log.status || '-')}</span></td>
                    <td>$${cost}</td>
                    <td>${tokens}</td>
                    <td>${duration}</td>
                </tr>
            `;
        }).join('');

        if (append) {
            tbody.innerHTML += rows;
        } else {
            tbody.innerHTML = rows;
        }

        // Show/hide "Load More" button
        if (data.total > (currentPage + 1) * PAGE_SIZE) {
            document.getElementById('loadMoreBtn').style.display = 'block';
        } else {
            document.getElementById('loadMoreBtn').style.display = 'none';
        }

    } catch (err) {
        console.error('Failed to load logs:', err);
        showLogsError('Error loading logs: ' + err.message);
    }
}

function showLogsError(message) {
    document.getElementById('logsResults').innerHTML =
        `<tr><td colspan="7" class="error-msg">${escapeHtml(message)}</td></tr>`;
}

// Update dropdown options from API-provided distinct values
function updateDropdownOptions(users, models, statuses) {
    const userSelect = document.getElementById('filterUserId');
    const modelSelect = document.getElementById('filterModel');
    const statusSelect = document.getElementById('filterStatus');

    if (!userSelect || !modelSelect) return;

    const currentUser = logFilters.user_id;
    const currentModel = logFilters.model;
    const currentStatus = logFilters.status;

    // Update users dropdown
    const userOptions = users.map(u =>
        `<option value="${escapeHtml(u)}" ${u === currentUser ? 'selected' : ''}>${escapeHtml(u)}</option>`
    ).join('');
    userSelect.innerHTML = '<option value="">All Users</option>' + userOptions;

    // Update models dropdown
    const modelOptions = models.map(m =>
        `<option value="${escapeHtml(m)}" ${m === currentModel ? 'selected' : ''}>${escapeHtml(m)}</option>`
    ).join('');
    modelSelect.innerHTML = '<option value="">All Models</option>' + modelOptions;

    // Update status dropdown (if dynamic)
    if (statusSelect && statuses && statuses.length > 0) {
        const statusOptions = statuses.map(s =>
            `<option value="${escapeHtml(s)}" ${s === currentStatus ? 'selected' : ''}>${escapeHtml(s)}</option>`
        ).join('');
        statusSelect.innerHTML = '<option value="">All Status</option>' + statusOptions;
    }
}

// Apply filters
export function applyLogFilters() {
    // Read filter inputs
    logFilters.user_id = document.getElementById('filterUserId').value;
    logFilters.model = document.getElementById('filterModel').value;
    logFilters.status = document.getElementById('filterStatus').value;
    logFilters.sort_by = document.getElementById('sortBy').value;
    logFilters.sort_order = document.getElementById('sortOrder').value;

    // Reset to first page
    currentPage = 0;

    // Reload logs
    loadLogs(false);
}

// Reset filters
export function resetLogFilters() {
    logFilters.user_id = '';
    logFilters.model = '';
    logFilters.status = '';
    logFilters.sort_by = 'timestamp';
    logFilters.sort_order = 'desc';

    // Reset UI
    document.getElementById('filterUserId').value = '';
    document.getElementById('filterModel').value = '';
    document.getElementById('filterStatus').value = '';
    document.getElementById('sortBy').value = 'timestamp';
    document.getElementById('sortOrder').value = 'desc';

    // Reset page and reload (API will return fresh distinct values)
    currentPage = 0;
    loadLogs(false);
}

// Load more (pagination)
export function loadMoreLogs() {
    currentPage++;
    loadLogs(true);
}

// Export to Excel
export function exportLogsToExcel() {
    if (!allLogsData || allLogsData.length === 0) {
        alert('No data to export. Please load logs first.');
        return;
    }

    try {
        // Prepare CSV content
        const headers = ['Timestamp', 'User ID', 'Model', 'Status', 'Cost (USD)', 'Tokens', 'Duration (ms)', 'Endpoint'];
        const csvRows = [headers.join(',')];

        allLogsData.forEach(log => {
            const row = [
                `"${new Date(log.timestamp || log.ts).toISOString()}"`,
                `"${(log.user_id || '-').replace(/"/g, '""')}"`,
                `"${(log.model || '-').replace(/"/g, '""')}"`,
                `"${(log.status || '-').replace(/"/g, '""')}"`,
                (log.cost_usd || 0).toFixed(6),
                log.tokens_total || 0,
                log.duration_ms || 0,
                `"${(log.endpoint || '-').replace(/"/g, '""')}"`
            ];
            csvRows.push(row.join(','));
        });

        const csvContent = csvRows.join('\n');

        // Create download link
        const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.setAttribute('href', url);

        // Generate filename with timestamp
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        link.setAttribute('download', `audit_logs_${timestamp}.csv`);

        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);

        console.log(`Exported ${allLogsData.length} logs to CSV`);
    } catch (err) {
        console.error('Failed to export logs:', err);
        alert('Failed to export logs: ' + err.message);
    }
}
