// Dashboard orchestrator: wires UI actions to modules and starts/stops loops.

import { authenticate, stopDashboardLoops, setSummaryInterval } from './auth.js';
import { setTimeRange, applyCustomRange, initAuditFilters } from './filters.js';
import { switchTab } from './tabs.js';
import { initCharts } from './charts.js';
import { loadSummary, connectEventStream, refreshTables } from './usage.js';
import { loadAccessData, connectAccessStream } from './access.js';
import { applyLogFilters, resetLogFilters, loadMoreLogs, exportLogsToExcel } from './logs.js';
import { refreshAnalytics, initAnalyticsChart } from './analytics.js';
import { initGroupAnalyticsChart, fetchData as refreshGroups } from './group_analytics.js';
import { refreshSatisfaction } from './satisfaction.js';
import { refreshAnalytics, initAnalyticsChart } from './analytics.js';
import { initGroupAnalyticsChart, fetchData as refreshGroups } from './group_analytics.js';
import { refreshSatisfaction } from './satisfaction.js';
import { updateStatus } from './utils.js';
import {
	loadUsers, showCreateUserModal, showEditUserModal, closeUserModal, saveUser,
	deleteUser, rotateUserKey, toggleUserActive, syncUserNow
	loadUsers, showCreateUserModal, showEditUserModal, closeUserModal, saveUser,
	deleteUser, rotateUserKey, toggleUserActive, syncUserNow
} from './users.js';
import {
	saveSMTP, saveQuotaThresholds, saveBudgets, saveNotifToggles, saveDefaultQuota, testSMTP
} from './settings.js';
import { applyRagFilters, resetRagFilters } from './raghealth.js';
import { applyKnowledgeFilters, resetKnowledgeFilters } from './knowledge.js';
import {
	recalcComparison, resetSimulator, showAddPriceModal, showEditPriceModal,
	closePriceModal, savePrice, deletePrice
} from './prices.js';
import {
	showPendingModal, closePendingModal, refreshPendingList, reconcilePending, forceClearPending
} from './pending.js';
import {
	connectActiveUsersStream, disconnectActiveUsersStream
} from './active_users.js';
import {
	openExportModal, closeExportModal, downloadReport
} from './export.js';

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
		loadSummary,
		refreshAnalytics,
		refreshSatisfaction,
		loadSummary,
		refreshAnalytics,
		refreshSatisfaction,
		// User CRUD
		loadUsers,
		loadUsers,
		showCreateUserModal,
		showEditUserModal,
		closeUserModal,
		saveUser,
		deleteUser,
		rotateUserKey,
		toggleUserActive,
		syncUserNow,
		// Price CRUD & simulator
		recalcComparison,
		resetSimulator,
		showAddPriceModal,
		showEditPriceModal,
		closePriceModal,
		savePrice,
		deletePrice,
		// Pending requests details & actions
		showPendingModal,
		closePendingModal,
		refreshPendingList,
		reconcilePending,
		forceClearPending,
		// Export report modal
		openExportModal,
		closeExportModal,
		downloadReport
	};



	window.settingsAPI = {
		saveSMTP,
		saveQuotaThresholds,
		saveBudgets,
		saveNotifToggles,
		saveDefaultQuota,
		testSMTP
	};

	window.ragHealthAPI = {
		apply: applyRagFilters,
		reset: resetRagFilters
	};

	window.knowledgeAPI = {
		apply: applyKnowledgeFilters,
		reset: resetKnowledgeFilters
	};

	window.groupAnalyticsAPI = {
		fetchData: refreshGroups
	};

	// One-time UI init
	try {
		initCharts();
		initAnalyticsChart();
		initGroupAnalyticsChart();
		initAnalyticsChart();
		initGroupAnalyticsChart();
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
	connectActiveUsersStream();
	connectActiveUsersStream();

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
	disconnectActiveUsersStream();
	disconnectActiveUsersStream();
	updateStatus('warning', 'Stopped');
}
