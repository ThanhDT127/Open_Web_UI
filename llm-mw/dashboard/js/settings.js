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
        const userAlerts = config.user_alerts || {};
        
        // Take the last two thresholds from the existing array (or default to 80, 100)
        let thresholds = adminAlerts.per_user_quota?.thresholds || [80, 100];
        if (thresholds.length >= 3) {
            thresholds = [thresholds[thresholds.length - 2], thresholds[thresholds.length - 1]];
        }
        
        document.getElementById('thresholdWarning').value = thresholds[0] || 80;
        document.getElementById('thresholdCritical').value = thresholds[1] || 100;

        // 3. Populate provider prepaid credit rows (Phase 6)
        _renderProviderCredits(adminAlerts.api_budgets || {});

        // 4. Populate Default Quota for lazy-provisioned users
        const defaultQuota = config.provisioning?.default_quota || {};
        document.getElementById('defaultQuotaCost').value = defaultQuota.limit_cost_usd ?? 2.0;
        document.getElementById('defaultQuotaPeriod').value = defaultQuota.period || 'monthly';
        _renderDefaultQuotaHint(config);

        // 5. Populate Notification Toggles
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

// ── Provider prepaid credit (Phase 6) ───────────────────────────────
function _fmtFunded(iso) {
    if (!iso) return 'chưa nạp';
    try {
        const d = new Date(iso);
        return d.toLocaleDateString('vi-VN') + ' ' + d.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
    } catch { return iso; }
}

function _renderProviderCredits(budgets) {
    const host = document.getElementById('providerCreditRows');
    if (!host) return;
    const names = Object.keys(budgets);
    if (!names.length) {
        host.innerHTML = '<div class="no-data">Chưa có billing account nào</div>';
        return;
    }
    host.innerHTML = names.map(name => {
        const p = budgets[name] || {};
        const dep = Number(p.deposited || 0);
        return `
            <div class="form-group" style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
                <label style="min-width:110px"><strong>${name}</strong></label>
                <span class="quota-detail" style="min-width:200px">Số dư: $${dep.toFixed(2)} · nạp: ${_fmtFunded(p.funded_at)}</span>
                <input type="number" step="0.01" min="0" id="credit_${name}" placeholder="Số tiền" style="width:120px">
                <button type="button" class="btn-apply" onclick="window.settingsAPI.topUpProvider('${name}')">Nạp thêm</button>
                <button type="button" class="btn-secondary" onclick="window.settingsAPI.correctProviderCredit('${name}')">Sửa</button>
            </div>`;
    }).join('');
}

export async function topUpProvider(account) {
    const el = document.getElementById(`credit_${account}`);
    const amount = parseFloat(el && el.value);
    if (!amount || amount <= 0) { alert('Nhập số tiền nạp (> 0)'); return; }
    const res = await mwFetch('/v1/_mw/providers/topup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account, amount })
    });
    if (res && res.ok) { alert(`Đã nạp thêm $${amount} vào ${account}`); loadSettings(); }
    else { alert('Nạp thất bại'); }
}

// "Sửa" — correct a mistyped balance WITHOUT counting it as a new top-up. Reuses the
// existing deep-merge alert-config endpoint so funded_at is preserved untouched.
export async function correctProviderCredit(account) {
    const el = document.getElementById(`credit_${account}`);
    const val = parseFloat(el && el.value);
    if (isNaN(val) || val < 0) { alert('Nhập số dư đúng (>= 0)'); return; }
    if (!confirm(`Sửa số dư ${account} thành $${val}? (giữ nguyên mốc nạp)`)) return;
    const data = { admin_alerts: { api_budgets: { [account]: { deposited: val } } } };
    await _savePartialConfig(data, `Sửa credit ${account}`);
    loadSettings();
}

function _renderDefaultQuotaHint(config) {
    const el = document.getElementById('defaultQuotaHint');
    if (!el) return;
    const dq = config?.provisioning?.default_quota || {};
    const cost = Number(dq.limit_cost_usd ?? 2.0);
    el.textContent = `$${cost.toFixed(2)} / ${dq.period || 'monthly'}`;
}

// Called when the Users tab opens — fetches config once and fills the banner hint
export async function updateDefaultQuotaHint() {
    try {
        if (!_configCache) {
            const res = await mwFetch('/v1/_mw/admin/alerts/config');
            if (!res || !res.ok) return;
            _configCache = await res.json();
        }
        _renderDefaultQuotaHint(_configCache);
    } catch (err) {
        console.error('Failed to load default quota hint:', err);
    }
}

export async function saveDefaultQuota() {
    const cost = parseFloat(document.getElementById('defaultQuotaCost').value);
    if (!cost || cost <= 0) {
        alert('Cost Limit must be greater than 0');
        return;
    }
    const data = {
        provisioning: {
            default_quota: {
                limit_cost_usd: cost,
                period: document.getElementById('defaultQuotaPeriod').value
            }
        }
    };
    const ok = await _savePartialConfig(data, 'Default provisioning quota');
    if (ok) _renderDefaultQuotaHint(_configCache);
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
