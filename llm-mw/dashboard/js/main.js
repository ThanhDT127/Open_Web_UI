// Dashboard orchestrator: wires UI actions to modules and starts/stops loops.

import { authenticate, stopDashboardLoops, setSummaryInterval } from './auth.js';
import { setTimeRange, applyCustomRange, initAuditFilters } from './filters.js';
import { switchTab } from './tabs.js';
import { initCharts } from './charts.js';
import { loadSummary, connectEventStream, refreshTables } from './usage.js';
import { loadAccessData, connectAccessStream } from './access.js';
import { applyLogFilters, resetLogFilters, loadMoreLogs, exportLogsToExcel } from './logs.js';
import { updateStatus } from './utils.js';
import {
	showCreateUserModal, showEditUserModal, closeUserModal, saveUser,
	deleteUser, rotateUserKey, toggleUserActive
} from './users.js';
import {
	saveSMTP, saveQuotaThresholds, saveBudgets, saveNotifToggles, testSMTP
} from './settings.js';
import { applyRagFilters, resetRagFilters } from './raghealth.js';

// Expose a stable API for inline HTML handlers (window.dashboardAPI.*)
export async function initAPI() {
	window.dashboardAPI = {
		authenticate,
		setTimeRange,
		applyCustomRange,
		switchTab,
		applyLogFilters,
		resetLogFilters,
		loadMoreLogs,
		exportLogsToExcel,
		refreshUsage: refreshTables,
		// User CRUD
		showCreateUserModal,
		showEditUserModal,
		closeUserModal,
		saveUser,
		deleteUser,
		rotateUserKey,
		toggleUserActive
	};

	window.settingsAPI = {
		saveSMTP,
		saveQuotaThresholds,
		saveBudgets,
		saveNotifToggles,
		testSMTP
	};

	window.ragHealthAPI = {
		apply: applyRagFilters,
		reset: resetRagFilters
	};

	// One-time UI init
	try {
		initCharts();
	} catch (e) {
		// Chart.js may not be ready yet; summary load will still work.
		console.warn('Charts init failed:', e);
	}
	initAuditFilters();
}

export function startDashboard() {
	// Initial load
	loadSummary();
	connectEventStream();

	// Refresh summary periodically (keeps charts/metrics fresh)
	const interval = setInterval(() => {
		loadSummary();
	}, 15000);
	setSummaryInterval(interval);

	// If access tab is already active, start its stream too
	const accessTab = document.getElementById('accessTab');
	if (accessTab && accessTab.classList.contains('active')) {
		loadAccessData();
		connectAccessStream();
	}

	updateStatus('ok', 'Authenticated ✓');
}

export function stopDashboard() {
	stopDashboardLoops();
	updateStatus('warning', 'Stopped');
}
