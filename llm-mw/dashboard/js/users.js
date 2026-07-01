// Users tab — Full CRUD management with modals
import { mwFetch, updateStatus } from './utils.js';

// Track current edit mode
let _editingUserId = null; // null = create mode, string = edit mode
let _usersCache = [];

export async function loadUsers() {
    const tbody = document.getElementById('usersTable');
    try {
        const res = await mwFetch('/v1/_mw/admin/users');
        if (!res || !res.ok) {
            tbody.innerHTML = '<tr><td colspan="10" class="error-msg">Failed to load</td></tr>';
            return;
        }

        const data = await res.json();
        const users = data.users || [];
        _usersCache = users;

        // Update active/total user count badges
        const totalEl = document.getElementById('totalUserCount');
        const activeEl = document.getElementById('activeUserCount');
        if (totalEl) totalEl.textContent = users.length;
        if (activeEl) activeEl.textContent = users.filter(u => u.active !== false).length;

        if (users.length === 0) {
            tbody.innerHTML = '<tr><td colspan="10" class="no-data">No users</td></tr>';
            return;
        }

        // Sort by quota usage percentage (descending, unlimited goes to bottom)
        const getPct = (q) => (q && q.limit_cost_usd > 0) ? (q.used_cost_usd / q.limit_cost_usd) : -1;
        users.sort((a, b) => getPct(b.quota) - getPct(a.quota));

        tbody.innerHTML = users.map(u => {
            const q = u.quota || {};
            const costUsed = q.used_cost_usd || 0;
            const costLimit = q.limit_cost_usd || 0;
            const period = q.period || 'monthly';
            const models = (u.allowed_models || ['*']).join(', ');
            const isActive = u.active !== false;
            const role = u.role || 'user';
            const hash = u.subkey_hash || '';
            const maskedHash = hash.length > 12 ? hash.slice(0, 6) + '...' + hash.slice(-6) : (hash || 'n/a');

            // Quota gauge
            let quotaPct = 0;
            let quotaBar = '';
            if (costLimit > 0) {
                quotaPct = Math.min((costUsed / costLimit) * 100, 100);
                const color = quotaPct >= 90 ? '#ef4444' :
                    quotaPct >= 70 ? '#f97316' :
                        quotaPct >= 50 ? '#f59e0b' : '#10b981';
                quotaBar = `
                    <div class="quota-gauge">
                        <div class="quota-gauge-fill" style="width: ${quotaPct}%; background: ${color}"></div>
                    </div>
                    <span class="quota-text" style="color: ${color}">${quotaPct.toFixed(0)}%</span>
                    <span class="quota-detail">$${costUsed.toFixed(4)} / $${costLimit.toFixed(4)}</span>
                `;
            } else {
                quotaBar = '<span class="quota-unlimited">∞ Unlimited</span>';
            }

            const statusBadge = isActive
                ? '<span class="badge badge-active">🟢 Active</span>'
                : '<span class="badge badge-inactive">🔴 Inactive</span>';

            const roleBadge = role === 'admin' ? '<span class="badge badge-admin">admin</span>'
                : role === 'manager' ? '<span class="badge badge-manager">manager</span>'
                    : '<span class="badge badge-user">user</span>';

            const uid = encodeURIComponent(u.user_id);

            return `<tr>
                <td class="user-id">${u.user_id}</td>
                <td>${roleBadge}</td>
                <td>${statusBadge}</td>
                <td class="models-cell" title="${models}">${models.length > 25 ? models.slice(0, 25) + '...' : models}</td>
                <td>${period}</td>
                <td class="cost">$${costUsed.toFixed(4)}</td>
                <td>$${costLimit > 0 ? costLimit.toFixed(4) : '∞'}</td>
                <td class="quota-cell">${quotaBar}</td>
                <td class="actions-cell">
                    ${uid === 'admin' ? `
                        <!-- System only -->
                    ` : `
                        <button class="btn-icon btn-edit" title="Edit" onclick="window.dashboardAPI.showEditUserModal('${uid}')">✏️</button>
                        <button class="btn-icon btn-toggle" title="${isActive ? 'Disable' : 'Enable'}" onclick="window.dashboardAPI.toggleUserActive('${uid}', ${!isActive})">${isActive ? '🔴' : '🟢'}</button>
                        <button class="btn-icon btn-delete" title="Delete" onclick="window.dashboardAPI.deleteUser('${uid}')">🗑️</button>
                    `}
                </td>
            </tr>`;
        }).join('');

        // Load cross-database sync status table
        await loadSyncStatus();
    } catch (err) {
        console.error('Failed to load users:', err);
        tbody.innerHTML = '<tr><td colspan="9" class="error-msg">Error: ' + err.message + '</td></tr>';
    }
}


// ─── Modal management ────────────────────────────────────────

export function showCreateUserModal() {
    _editingUserId = null;
    document.getElementById('userModalTitle').textContent = '➕ Add New User';
    document.getElementById('modalUserId').value = '';
    document.getElementById('modalUserId').disabled = false;
    document.getElementById('modalRole').value = 'user';
    document.getElementById('modalModels').value = '*';
    document.getElementById('modalLimitCost').value = '0';
    document.getElementById('modalLimitTokens').value = '0';
    document.getElementById('modalLimitImages').value = '0';
    document.getElementById('modalPeriod').value = 'monthly';
    document.getElementById('modalActive').value = 'true';
    document.getElementById('modalSaveBtn').textContent = 'Create User';
    document.getElementById('userModal').style.display = 'flex';
}


export function showEditUserModal(userId) {
    userId = decodeURIComponent(userId);
    const user = _usersCache.find(u => u.user_id === userId);
    if (!user) { alert('User not found in cache'); return; }

    _editingUserId = userId;
    const q = user.quota || {};

    document.getElementById('userModalTitle').textContent = `✏️ Edit User: ${userId}`;
    document.getElementById('modalUserId').value = userId;
    document.getElementById('modalUserId').disabled = true; // Can't change user_id
    document.getElementById('modalRole').value = user.role || 'user';
    document.getElementById('modalModels').value = (user.allowed_models || ['*']).join(', ');
    document.getElementById('modalLimitCost').value = q.limit_cost_usd || 0;
    document.getElementById('modalLimitTokens').value = q.limit_tokens || 0;
    document.getElementById('modalLimitImages').value = q.limit_image_requests || 0;
    document.getElementById('modalPeriod').value = q.period || 'monthly';
    document.getElementById('modalActive').value = String(user.active !== false);
    document.getElementById('modalSaveBtn').textContent = 'Save Changes';
    document.getElementById('userModal').style.display = 'flex';
}


export function closeUserModal() {
    document.getElementById('userModal').style.display = 'none';
    _editingUserId = null;
}


export async function saveUser() {
    const btn = document.getElementById('modalSaveBtn');
    const originalText = btn.textContent;
    btn.textContent = 'Saving...';
    btn.disabled = true;

    try {
        const models = document.getElementById('modalModels').value
            .split(',').map(m => m.trim()).filter(m => m);

        if (_editingUserId) {
            // UPDATE existing user
            const body = {
                role: document.getElementById('modalRole').value,
                active: document.getElementById('modalActive').value === 'true',
                allowed_models: models,
                limit_cost_usd: parseFloat(document.getElementById('modalLimitCost').value) || 0,
                limit_tokens: parseInt(document.getElementById('modalLimitTokens').value) || 0,
                limit_image_requests: parseInt(document.getElementById('modalLimitImages').value) || 0,
            };

            const res = await mwFetch(`/v1/_mw/admin/users/${encodeURIComponent(_editingUserId)}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });

            if (!res || !res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || 'Update failed');
            }

            updateStatus('ok', `User ${_editingUserId} updated ✓`);
        } else {
            // CREATE new user
            const userId = document.getElementById('modalUserId').value.trim();
            if (!userId) { alert('User ID is required'); return; }

            const body = {
                user_id: userId,
                role: document.getElementById('modalRole').value,
                allowed_models: models,
                limit_cost_usd: parseFloat(document.getElementById('modalLimitCost').value) || 0,
                limit_tokens: parseInt(document.getElementById('modalLimitTokens').value) || 0,
                limit_image_requests: parseInt(document.getElementById('modalLimitImages').value) || 0,
                period: document.getElementById('modalPeriod').value,
            };

            const res = await mwFetch('/v1/_mw/admin/users', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });

            if (!res || !res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || 'Create failed');
            }

            const result = await res.json();
            updateStatus('ok', `User ${userId} created ✓`);

            // Show subkey modal
            if (result.subkey) {
                _showSubkeyModal(result.subkey, userId);
            }
        }

        closeUserModal();
        await loadUsers();
    } catch (err) {
        alert('Error: ' + err.message);
        console.error('Save user error:', err);
    } finally {
        btn.textContent = originalText;
        btn.disabled = false;
    }
}


// ─── Actions ─────────────────────────────────────────────────

export async function deleteUser(userId) {
    userId = decodeURIComponent(userId);
    if (!confirm(`⚠️ Are you sure you want to DELETE user "${userId}"?\n\nThis action is PERMANENT and cannot be undone.`)) return;
    if (!confirm(`🛑 FINAL CONFIRMATION\n\nDeleting user: ${userId}\n\nAll subkeys will be invalidated.\nContinue?`)) return;

    try {
        const res = await mwFetch(`/v1/_mw/admin/users/${encodeURIComponent(userId)}`, {
            method: 'DELETE'
        });

        if (!res || !res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Delete failed');
        }

        updateStatus('ok', `User ${userId} deleted ✓`);
        await loadUsers();
    } catch (err) {
        alert('Delete error: ' + err.message);
    }
}


export async function rotateUserKey(userId) {
    userId = decodeURIComponent(userId);
    if (!confirm(`🔑 Rotate key for "${userId}"?\n\nThe current key will be INVALIDATED immediately.\nA new key will be generated and shown ONCE.`)) return;

    try {
        const res = await mwFetch(`/v1/_mw/admin/users/${encodeURIComponent(userId)}/rotate_key`, {
            method: 'POST'
        });

        if (!res || !res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Rotate failed');
        }

        const result = await res.json();
        updateStatus('ok', `Key rotated for ${userId} ✓`);

        if (result.subkey) {
            _showSubkeyModal(result.subkey, userId);
        }

        await loadUsers();
    } catch (err) {
        alert('Rotate key error: ' + err.message);
    }
}


export async function toggleUserActive(userId, activate) {
    userId = decodeURIComponent(userId);
    const action = activate ? 'enable' : 'disable';

    try {
        const res = await mwFetch(`/v1/_mw/admin/users/${encodeURIComponent(userId)}/${action}`, {
            method: 'POST'
        });

        if (!res || !res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `${action} failed`);
        }

        updateStatus('ok', `User ${userId} ${action}d ✓`);
        await loadUsers();
    } catch (err) {
        alert(`${action} error: ` + err.message);
    }
}


// ─── Subkey modal ────────────────────────────────────────────

function _showSubkeyModal(subkey, userId) {
    document.getElementById('subkeyPlaintext').textContent = subkey;
    document.getElementById('subkeyUserId').textContent = userId;
    // Reset copy button text
    const copyBtn = document.querySelector('#subkeyModal .btn-sm');
    if (copyBtn) copyBtn.textContent = '📋 Copy';
    document.getElementById('subkeyModal').style.display = 'flex';
}

export async function loadSyncStatus() {
    const tbody = document.getElementById('syncTable');
    if (!tbody) return;
    try {
        const res = await mwFetch('/v1/_mw/admin/users/sync-status');
        if (!res || !res.ok) {
            tbody.innerHTML = '<tr><td colspan="7" class="error-msg">Failed to load sync status</td></tr>';
            return;
        }
        const data = await res.json();
        const users = data.users || [];
        if (users.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="no-data">No accounts found in databases</td></tr>';
            return;
        }

        // Sort by status priority (mismatch -> pending_ow_approval -> pending_sync -> orphan_middleware -> synced)
        const weight = { 'mismatch': 4, 'pending_ow_approval': 3, 'pending_sync': 2, 'orphan_middleware': 1, 'synced': 0 };
        users.sort((a, b) => (weight[b.status] || 0) - (weight[a.status] || 0));

        tbody.innerHTML = users.map(u => {
            const email = u.email || '';
            const name = u.name || '';
            const owRole = u.ow_role || 'n/a';
            const mwActive = u.mw_active !== null ? (u.mw_active ? '🟢 Active' : '🔴 Inactive') : 'n/a';
            
            // Mask subkey if it exists
            const rawSubkey = u.subkey || '';
            const maskedSubkey = rawSubkey ? rawSubkey.slice(0, 8) + '...' + rawSubkey.slice(-8) : 'n/a';

            // Badges
            let statusBadge = '';
            if (u.status === 'synced') {
                statusBadge = '<span class="badge badge-active" style="background:#10b981">✓ Synced</span>';
            } else if (u.status === 'pending_sync') {
                statusBadge = '<span class="badge badge-warning" style="background:#f59e0b;color:#000">⏳ Pending Sync</span>';
            } else if (u.status === 'mismatch') {
                statusBadge = '<span class="badge badge-danger" style="background:#ef4444">⚠️ Mismatch</span>';
            } else if (u.status === 'orphan_middleware') {
                statusBadge = '<span class="badge badge-inactive" style="background:#64748b">👻 Orphan MW</span>';
            } else if (u.status === 'pending_ow_approval') {
                statusBadge = '<span class="badge badge-warning" style="background:#64748b;color:#fff">⌛ OW Approval Needed</span>';
            }

            const uid = encodeURIComponent(email);
            
            // Render sync action button
            let actionBtn = '';
            if (u.status === 'pending_ow_approval') {
                actionBtn = `<button class="btn btn-sm btn-secondary" style="opacity: 0.5;" disabled>Requires Role</button>`;
            } else if (u.status !== 'synced') {
                actionBtn = `<button class="btn btn-sm btn-primary" onclick="window.dashboardAPI.syncUserNow('${uid}')">Sync Now</button>`;
            } else {
                actionBtn = `<button class="btn btn-sm btn-secondary" style="opacity: 0.5;" disabled>Synced</button>`;
            }

            // Special override for 'admin' system account
            if (email === 'admin') {
                statusBadge = '<span class="badge badge-active" style="background:#4f46e5">🔑 Dashboard Manager</span>';
                actionBtn = '<button class="btn btn-sm btn-secondary" style="opacity: 0.5;" disabled>System Only</button>';
            }

            return `<tr>
                <td class="user-id">${email}</td>
                <td>${name}</td>
                <td><span class="badge" style="background:#334155">${owRole}</span></td>
                <td>${mwActive}</td>
                <td>${statusBadge}</td>
                <td>${actionBtn}</td>
            </tr>`;
        }).join('');

    } catch (err) {
        console.error('Failed to load sync status:', err);
        tbody.innerHTML = '<tr><td colspan="6" class="error-msg">Error: ' + err.message + '</td></tr>';
    }
}

export async function syncUserNow(userId) {
    userId = decodeURIComponent(userId);
    if (!confirm(`Force synchronize and align status for user ${userId}?`)) return;

    try {
        const res = await mwFetch('/v1/_mw/admin/users/sync-now', {
            method: 'POST',
            body: JSON.stringify({ user_id: userId })
        });
        if (res && res.ok) {
            updateStatus('ok', `User ${userId} synced successfully ✓`);
            // Reload tables
            await loadUsers();
        } else {
            const err = await res.json().catch(() => ({}));
            alert(`Failed to sync: ${err.error || 'Unknown error'}`);
        }
    } catch (err) {
        alert(`Error: ${err.message}`);
    }
}
