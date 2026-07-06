// Export Report modal logic - format selection + time range, triggers file download
import { currentTimeRange } from './filters.js';
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

    const params = new URLSearchParams();
    params.append('format', format);
    if (currentTimeRange.minutes) {
        const end = new Date();
        const start = new Date(end.getTime() - currentTimeRange.minutes * 60 * 1000);
        params.append('start', start.toISOString());
        params.append('end', end.toISOString());
    } else {
        params.append('start', currentTimeRange.start);
        params.append('end', currentTimeRange.end);
    }

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
