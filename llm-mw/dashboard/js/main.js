// Dashboard orchestrator: wires UI actions to modules and starts/stops loops.

import { authenticate, stopDashboardLoops, setSummaryInterval } from './auth.js';
import { setTimeRange, applyCustomRange, initAuditFilters, resolveTimeWindow } from './filters.js';
import { switchTab } from './tabs.js';
import { initCharts } from './charts.js';
import { loadSummary, connectEventStream, refreshTables } from './usage.js';
import { loadAccessData, connectAccessStream } from './access.js';
import { applyLogFilters, resetLogFilters, loadMoreLogs, exportLogsToExcel, loadLogs } from './logs.js';
import { loadAdoption } from './adoption.js';
import { refreshAnalytics, initAnalyticsChart } from './analytics.js';
import { initGroupAnalyticsChart, fetchData as refreshGroups } from './group_analytics.js';
import { refreshSatisfaction } from './satisfaction.js';
import { updateStatus } from './utils.js';
import {
	loadUsers, showCreateUserModal, showEditUserModal, closeUserModal, saveUser,
	deleteUser, rotateUserKey, toggleUserActive, syncUserNow
} from './users.js';
import {
	loadGroupToolAccess, showGroupToolModal, closeGroupToolModal, saveGroupTools
} from './tool_access.js';
import {
	saveSMTP, saveQuotaThresholds, topUpProvider, correctProviderCredit, saveNotifToggles, saveDefaultQuota, testSMTP
} from './settings.js';
import { applyRagFilters } from './raghealth.js';
import { loadOverview } from './overview.js';
import { applyKnowledgeFilters, resetKnowledgeFilters } from './knowledge.js?v=011';
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
import { startNotifications, stopNotifications } from './notifications.js';
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
		// User CRUD
		loadUsers,
		showCreateUserModal,
		showEditUserModal,
		closeUserModal,
		saveUser,
		deleteUser,
		rotateUserKey,
		toggleUserActive,
		syncUserNow,
		// Tool access (bật/tắt tool theo group / theo user)
		loadGroupToolAccess,
		showGroupToolModal,
		closeGroupToolModal,
		saveGroupTools,
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
		topUpProvider,
		correctProviderCredit,
		saveNotifToggles,
		saveDefaultQuota,
		testSMTP
	};

	// `apply` is the tab's reload hook (filters.js calls it on a time-range change), not a
	// filter handler — the tab-local filter bar was removed. No `reset`: there is nothing
	// left to reset.
	window.ragHealthAPI = {
		apply: applyRagFilters
	};

	window.knowledgeAPI = {
		apply: applyKnowledgeFilters,
		reset: resetKnowledgeFilters
	};

	window.groupAnalyticsAPI = {
		fetchData: refreshGroups
	};

	window.overviewAPI = {
		refresh: loadOverview
	};

	// Tabs that read the global range but were not being reloaded when it changed.
	// Exposed here rather than imported into filters.js directly: each of these modules
	// imports buildRangeParams FROM filters.js, so a direct import would close a cycle.
	window.rangeScopedTabs = {
		usersTab:    () => { loadUsers(); loadAdoption(); },
		accessTab:   loadAccessData,
		logsTab:     loadLogs,
		overviewTab: loadOverview,
	};

	// One-time UI init
	try {
		initCharts();
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
	startNotifications();

	// Refresh summary periodically (keeps charts/metrics fresh).
	// Re-pin the window first so presets keep rolling forward, and so every tab
	// fetching during this cycle uses the same start/end.
	const interval = setInterval(() => {
		resolveTimeWindow();
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
	stopNotifications();
	updateStatus('warning', 'Stopped');
}
