// Export Report modal logic - format selection + time range, triggers file download
import { currentTimeRange, buildRangeParams } from './filters.js';
import { updateStatus } from './utils.js';

export function openExportModal() {
    const modal = document.getElementById('exportModal');
    if (!modal) return;

    const display = document.getElementById('exportTimeRangeDisplay');
    if (display) {
        if (currentTimeRange.minutes) {
            display.textContent = `Last ${currentTimeRange.minutes} minutes (dashboard time filter)`;
        } else {
            const start = new Date(currentTimeRange.start).toLocaleString();
            const end = new Date(currentTimeRange.end).toLocaleString();
            display.textContent = `${start} → ${end} (dashboard time filter)`;
        }
    }

    modal.style.display = 'flex';
}

export function closeExportModal() {
    const modal = document.getElementById('exportModal');
    if (modal) modal.style.display = 'none';
}

export function downloadReport() {
    const format = document.getElementById('exportFormatCsv')?.checked ? 'csv' : 'xlsx';

    // Same window the dashboard is showing, so the report matches what's on screen.
    const params = buildRangeParams({ format });

    const url = `/v1/_mw/export/report?${params}`;
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', '');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    updateStatus('ok', `Generating ${format.toUpperCase()} report...`);
    closeExportModal();
}
