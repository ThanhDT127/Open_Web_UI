// Tool access — bật/tắt tool theo group (tab Groups) và theo user (modal Edit User).
// Ghi vào bảng access_grant của Open WebUI; đây là điểm chốt quyền thật, không phải ẩn/hiện UI.
import { mwFetch, updateStatus, escapeHtml } from './utils.js';

let _editingGroupId = null;
let _editingOwUserId = null;

const BASE = '/v1/_mw/admin/tool-access';

async function getJson(path) {
    const res = await mwFetch(path);
    if (!res || !res.ok) {
        const err = res ? await res.json().catch(() => ({})) : {};
        throw new Error(err.detail || 'Request failed');
    }
    return res.json();
}

async function putToolIds(path, toolIds) {
    const res = await mwFetch(path, {
        method: 'PUT',
        body: JSON.stringify({ tool_ids: toolIds })
    });
    if (!res || !res.ok) {
        const err = res ? await res.json().catch(() => ({})) : {};
        throw new Error(err.detail || 'Save failed');
    }
    return res.json();
}

function checkedToolIds(containerId) {
    return Array.from(
        document.querySelectorAll(`#${containerId} input[type="checkbox"]:not(:disabled):checked`)
    ).map(el => el.value);
}

// ─── Groups tab: bảng phân quyền tool theo phòng ban ─────────

export async function loadGroupToolAccess() {
    const tbody = document.getElementById('groupToolAccessTable');
    if (!tbody) return;
    try {
        const data = await getJson(`${BASE}/groups`);
        const groups = data.groups || [];
        if (groups.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="no-data">Chưa có group nào</td></tr>';
            return;
        }

        tbody.innerHTML = groups.map(g => {
            const members = g.member_count || 0;
            const memberBadge = members > 0
                ? `<span class="badge badge-active">${members}</span>`
                : '<span class="badge badge-inactive" title="Bật tool cho group rỗng thì không ai dùng được">0 — rỗng</span>';
            const chips = (g.tool_ids || []).length
                ? g.tool_ids.map(t => `<span class="tool-chip">${escapeHtml(t)}</span>`).join(' ')
                : '<span class="quota-unlimited">— chưa cấp tool nào —</span>';
            return `<tr>
                <td class="user-id">${escapeHtml(g.name)}</td>
                <td>${memberBadge}</td>
                <td>${chips}</td>
                <td class="actions-cell">
                    <button class="btn-icon btn-edit" title="Bật/tắt tool"
                        onclick="window.dashboardAPI.showGroupToolModal('${encodeURIComponent(g.id)}')">✏️</button>
                </td>
            </tr>`;
        }).join('');
    } catch (err) {
        console.error('Failed to load group tool access:', err);
        tbody.innerHTML = `<tr><td colspan="4" class="error-msg">Error: ${escapeHtml(err.message)}</td></tr>`;
    }
}

export async function showGroupToolModal(groupId) {
    groupId = decodeURIComponent(groupId);
    _editingGroupId = groupId;

    document.getElementById('groupToolModalTitle').textContent = '✏️ Edit Group';
    document.getElementById('groupToolMembers').textContent = '';
    document.getElementById('groupToolList').innerHTML = '<div class="loading">Loading...</div>';
    document.getElementById('groupToolModal').style.display = 'flex';

    try {
        const data = await getJson(`${BASE}/groups/${encodeURIComponent(groupId)}`);
        const members = data.group.member_count || 0;

        document.getElementById('groupToolModalTitle').textContent =
            `✏️ Edit Group: ${data.group.name}`;
        document.getElementById('groupToolMembers').textContent = members > 0
            ? `${members} thành viên`
            : '0 thành viên — bật tool ở đây sẽ chưa có ai dùng được';

        document.getElementById('groupToolList').innerHTML = data.tools.map(t => `
            <label class="tool-row">
                <input type="checkbox" value="${escapeHtml(t.id)}" ${t.enabled ? 'checked' : ''}>
                <span class="tool-name">${escapeHtml(t.name)}</span>
                <code class="tool-id">${escapeHtml(t.id)}</code>
                ${t.public ? '<span class="badge badge-warning" title="Tool đang public cho mọi user — grant theo group không còn ý nghĩa">public</span>' : ''}
            </label>
        `).join('');
    } catch (err) {
        document.getElementById('groupToolList').innerHTML =
            `<div class="error-msg">Error: ${escapeHtml(err.message)}</div>`;
    }
}

export function closeGroupToolModal() {
    document.getElementById('groupToolModal').style.display = 'none';
    _editingGroupId = null;
}

export async function saveGroupTools() {
    if (!_editingGroupId) return;
    const btn = document.getElementById('groupToolSaveBtn');
    const original = btn.textContent;
    btn.textContent = 'Saving...';
    btn.disabled = true;

    try {
        const toolIds = checkedToolIds('groupToolList');
        const result = await putToolIds(
            `${BASE}/groups/${encodeURIComponent(_editingGroupId)}`, toolIds
        );
        updateStatus('ok', `Quyền tool đã lưu (+${result.added.length} / -${result.removed.length}) ✓`);
        closeGroupToolModal();
        await loadGroupToolAccess();
    } catch (err) {
        alert('Error: ' + err.message);
    } finally {
        btn.textContent = original;
        btn.disabled = false;
    }
}

// ─── Edit User modal: phần tool của một user ─────────────────

/** Dựng phần tool trong modal Edit User. `openwebuiUserId` rỗng ⇒ ẩn hẳn phần này. */
export async function loadUserToolAccess(openwebuiUserId) {
    const section = document.getElementById('modalToolsSection');
    const list = document.getElementById('modalToolsList');
    const hint = document.getElementById('modalToolsGroups');
    if (!section) return;

    _editingOwUserId = openwebuiUserId || null;
    if (!openwebuiUserId) {
        section.style.display = 'none';
        return;
    }

    section.style.display = 'block';
    hint.textContent = '';
    list.innerHTML = '<div class="loading">Loading...</div>';

    try {
        const data = await getJson(`${BASE}/users/${encodeURIComponent(openwebuiUserId)}`);
        hint.textContent = data.groups.length
            ? `Group: ${data.groups.map(g => g.name).join(', ')}`
            : 'Chưa thuộc group nào — chỉ có quyền cấp riêng bên dưới';

        list.innerHTML = data.tools.map(t => {
            // Tool đã có qua group/public: hiện là đã bật nhưng khóa lại, vì bỏ tick ở đây
            // không thu hồi được — quyền đó đến từ group, phải sửa ở Edit Group.
            const inherited = t.inherited_from.length > 0;
            const locked = (inherited || t.public) && !t.direct;
            let tag = '';
            if (t.public) {
                tag = '<span class="badge badge-warning">public</span>';
            } else if (inherited) {
                tag = `<span class="badge badge-user" title="Kế thừa từ group — sửa trong Edit Group">từ ${escapeHtml(t.inherited_from.join(', '))}</span>`;
            }
            return `
                <label class="tool-row ${locked ? 'tool-row-locked' : ''}">
                    <input type="checkbox" value="${escapeHtml(t.id)}"
                        ${t.direct || locked ? 'checked' : ''} ${locked ? 'disabled' : ''}>
                    <span class="tool-name">${escapeHtml(t.name)}</span>
                    <code class="tool-id">${escapeHtml(t.id)}</code>
                    ${tag}
                </label>`;
        }).join('');
    } catch (err) {
        list.innerHTML = `<div class="error-msg">Error: ${escapeHtml(err.message)}</div>`;
        _editingOwUserId = null;   // đọc hỏng thì đừng ghi đè grant bằng form rỗng
    }
}

/** Lưu grant riêng của user. No-op nếu user chưa map sang Open WebUI. */
export async function saveUserToolAccess() {
    if (!_editingOwUserId) return;
    await putToolIds(
        `${BASE}/users/${encodeURIComponent(_editingOwUserId)}`,
        checkedToolIds('modalToolsList')
    );
}

export function resetUserToolAccess() {
    _editingOwUserId = null;
    const section = document.getElementById('modalToolsSection');
    if (section) section.style.display = 'none';
}
