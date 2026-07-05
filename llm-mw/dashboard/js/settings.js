// Settings tab — Runtime system configuration management
import { mwFetch, updateStatus } from './utils.js';

let _configCache = null;

export async function loadSettings() {
    try {
        const res = await mwFetch('/v1/_mw/admin/alerts/config');
        if (!res || !res.ok) {
            // Error handling already done in mwFetch for 403
            if (res) updateStatus('error', 'Failed to load settings');
            return;
        }

        const config = await res.json();
        _configCache = config;

        // 1. Populate SMTP Form
        const smtp = config.smtp || {};
        document.getElementById('smtpEnabled').checked = smtp.enabled || false;
        document.getElementById('smtpHost').value = smtp.host || '';
        document.getElementById('smtpPort').value = smtp.port || 587;
        document.getElementById('smtpUser').value = smtp.username || '';
        document.getElementById('smtpFrom').value = smtp.from_email || '';
        document.getElementById('smtpPassEnv').value = smtp.password_env || 'SMTP_PASSWORD';
        document.getElementById('smtpTls').checked = smtp.use_tls !== false;
        
        const adminAlerts = config.admin_alerts || {};
        document.getElementById('adminEmails').value = (adminAlerts.emails || []).join(', ');

        // 2. Populate Quota Thresholds
        // 2. Populate Quota Thresholds
        const userAlerts = config.user_alerts || {};
        
        // Take the last two thresholds from the existing array (or default to 80, 100)
        let thresholds = adminAlerts.per_user_quota?.thresholds || [80, 100];
        if (thresholds.length >= 3) {
            thresholds = [thresholds[thresholds.length - 2], thresholds[thresholds.length - 1]];
        }
        
        document.getElementById('thresholdWarning').value = thresholds[0] || 80;
        document.getElementById('thresholdCritical').value = thresholds[1] || 100;

        // 3. Populate API Budgets
        const budgets = adminAlerts.api_budgets || {};
        document.getElementById('budgetOpenAI').value = budgets.openai?.budget_usd || 0;
        document.getElementById('budgetGemini').value = budgets.gemini?.budget_usd || 0;
        document.getElementById('budgetXai').value = budgets.xai?.budget_usd || 0;
        document.getElementById('budgetAnthropic').value = budgets.anthropic?.budget_usd || 0;
        document.getElementById('budgetDeepseek').value = budgets.deepseek?.budget_usd || 0;

        // 4. Populate Notification Toggles
        document.getElementById('toggleUserEmail').checked = userAlerts.send_email || false;
        document.getElementById('toggleAdminEmail').checked = adminAlerts.send_email_realtime || false;
        document.getElementById('toggleDashboardAlerts').checked = adminAlerts.dashboard_alerts_enabled || false;
        document.getElementById('toggleDailyDigest').checked = adminAlerts.daily_digest_enabled || false;

    } catch (err) {
        console.error('Failed to load settings:', err);
        updateStatus('error', 'Error loading settings: ' + err.message);
    }
}

async function _savePartialConfig(partialData, sectionName) {
    try {
        const res = await mwFetch('/v1/_mw/admin/alerts/config', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(partialData)
        });

        if (!res || !res.ok) {
            if (res) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.error || 'Update failed');
            }
            return false; // Error handled by mwFetch for 403
        }

        updateStatus('ok', `${sectionName} updated ✓`);
        // Refresh cache
        const result = await res.json();
        _configCache = result.config;
        return true;
    } catch (err) {
        alert('Error: ' + err.message);
        return false;
    }
}

export async function saveSMTP() {
    const emailsStr = document.getElementById('adminEmails').value;
    const emails = emailsStr.split(',').map(e => e.trim()).filter(e => e);

    const data = {
        smtp: {
            enabled: document.getElementById('smtpEnabled').checked,
            host: document.getElementById('smtpHost').value.trim(),
            port: parseInt(document.getElementById('smtpPort').value) || 587,
            username: document.getElementById('smtpUser').value.trim(),
            from_email: document.getElementById('smtpFrom').value.trim(),
            password_env: document.getElementById('smtpPassEnv').value.trim() || 'SMTP_PASSWORD',
            use_tls: document.getElementById('smtpTls').checked
        },
        admin_alerts: {
            emails: emails
        }
    };
    await _savePartialConfig(data, 'SMTP settings');
}

export async function saveQuotaThresholds() {
    const warn = parseInt(document.getElementById('thresholdWarning').value) || 80;
    const crit = parseInt(document.getElementById('thresholdCritical').value) || 100;

    const data = {
        admin_alerts: {
            per_user_quota: {
                thresholds: [warn, crit]
            },
            api_budgets: {
                openai: { thresholds: [warn, crit] },
                gemini: { thresholds: [warn, crit] },
                xai: { thresholds: [warn, crit] },
                anthropic: { thresholds: [warn, crit] },
                deepseek: { thresholds: [warn, crit] }
            }
        },
        user_alerts: {
            thresholds: [warn, crit]
        }
    };
    await _savePartialConfig(data, 'Global Quota thresholds');
}

export async function saveBudgets() {
    const data = {
        admin_alerts: {
            api_budgets: {
                openai: { budget_usd: parseFloat(document.getElementById('budgetOpenAI').value) || 0 },
                gemini: { budget_usd: parseFloat(document.getElementById('budgetGemini').value) || 0 },
                xai: { budget_usd: parseFloat(document.getElementById('budgetXai').value) || 0 },
                anthropic: { budget_usd: parseFloat(document.getElementById('budgetAnthropic').value) || 0 },
                deepseek: { budget_usd: parseFloat(document.getElementById('budgetDeepseek').value) || 0 }
            }
        }
    };
    await _savePartialConfig(data, 'API budgets');
}

export async function saveNotifToggles() {
    const data = {
        user_alerts: {
            send_email: document.getElementById('toggleUserEmail').checked
        },
        admin_alerts: {
            send_email_realtime: document.getElementById('toggleAdminEmail').checked,
            dashboard_alerts_enabled: document.getElementById('toggleDashboardAlerts').checked,
            daily_digest_enabled: document.getElementById('toggleDailyDigest').checked
        }
    };
    await _savePartialConfig(data, 'Notification toggles');
}

export async function testSMTP() {
    updateStatus('pending', 'Sending test email...');
    try {
        const res = await mwFetch('/v1/_mw/admin/alerts/test-email', {
            method: 'POST'
        });

        if (!res || !res.ok) {
            if (res) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.error || 'Test failed');
            }
            return; // Error handled by mwFetch for 403
        }

        const data = await res.json();
        updateStatus('ok', `Test email sent to ${data.to.join(', ')} ✓`);
    } catch (err) {
        alert('SMTP Test failed: ' + err.message);
        updateStatus('error', 'SMTP Test failed');
    }
}
