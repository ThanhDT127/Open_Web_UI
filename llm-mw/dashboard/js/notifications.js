/**
 * Notification module for LLM Middleware Dashboard.
 * Polls for unread notifications and renders bell icon + dropdown panel.
 */

import { mwFetch, escapeHtml } from './utils.js';

let _pollInterval = null;

// ─── API helpers ────────────────────────────────────────────

async function fetchUnreadCount() {
    try {
        const resp = await mwFetch('/v1/_mw/admin/notifications/unread');
        if (!resp || !resp.ok) return 0;
        const data = await resp.json();
        return data.unread || 0;
    } catch { return 0; }
}

async function fetchNotifications(limit = 30) {
    try {
        const resp = await mwFetch(`/v1/_mw/admin/notifications?limit=${limit}`);
        if (!resp || !resp.ok) return [];
        const data = await resp.json();
        return data.notifications || [];
    } catch { return []; }
}

async function doMarkRead(id) {
    try {
        await mwFetch(`/v1/_mw/admin/notifications/${id}/read`, { method: 'POST' });
    } catch { /* ignore */ }
}

async function doMarkAllRead() {
    try {
        await mwFetch('/v1/_mw/admin/notifications/read-all', { method: 'POST' });
        updateBadge(0);
        await renderPanel();
    } catch { /* ignore */ }
}

// ─── UI helpers ─────────────────────────────────────────────

function updateBadge(count) {
    const badge = document.getElementById('notifBadge');
    if (!badge) return;
    if (count > 0) {
        badge.textContent = count > 99 ? '99+' : count;
        badge.style.display = '';
    } else {
        badge.style.display = 'none';
    }
}

function levelIcon(level) {
    switch (level) {
        case 'critical': return '🚨';
        case 'warning': return '⚠️';
        default: return 'ℹ️';
    }
}

function timeAgo(isoStr) {
    if (!isoStr) return '';
    const diff = Date.now() - new Date(isoStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'vừa xong';
    if (mins < 60) return `${mins}p trước`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h trước`;
    const days = Math.floor(hrs / 24);
    return `${days}d trước`;
}

async function renderPanel() {
    const list = document.getElementById('notifList');
    if (!list) return;

    const items = await fetchNotifications();

    if (!items.length) {
        list.innerHTML = '<div class="notif-empty">Không có thông báo nào 🎉</div>';
        return;
    }

    list.innerHTML = items.map(n => `
        <div class="notif-item ${n.read ? '' : 'unread'} notif-level-${n.level}"
             data-id="${n.id}" onclick="window.notifAPI.clickItem(${n.id})">
            <div class="notif-item-header">
                <span class="notif-icon">${levelIcon(n.level)}</span>
                <span class="notif-title">${escapeHtml(n.title)}</span>
                <span class="notif-time">${timeAgo(n.ts)}</span>
            </div>
            <div class="notif-message">${escapeHtml(n.message)}</div>
        </div>
    `).join('');
}

// ─── Toggle / click handlers ────────────────────────────────

function toggle() {
    const panel = document.getElementById('notifPanel');
    if (!panel) return;
    const visible = panel.style.display !== 'none';
    panel.style.display = visible ? 'none' : '';
    if (!visible) renderPanel();
}

async function clickItem(id) {
    await doMarkRead(id);
    const item = document.querySelector(`.notif-item[data-id="${id}"]`);
    if (item) item.classList.remove('unread');
    const count = await fetchUnreadCount();
    updateBadge(count);
}

// Close panel when clicking outside
document.addEventListener('click', (e) => {
    const wrapper = document.querySelector('.notif-bell-wrapper');
    const panel = document.getElementById('notifPanel');
    if (wrapper && panel && !wrapper.contains(e.target)) {
        panel.style.display = 'none';
    }
});

// ─── Polling ────────────────────────────────────────────────

async function poll() {
    const count = await fetchUnreadCount();
    updateBadge(count);
}

// ─── Init ───────────────────────────────────────────────────

export function initNotifications() {
    window.notifAPI = { toggle, markAllRead: doMarkAllRead, clickItem };
}

/** Chỉ poll sau khi đã đăng nhập: poll lúc chưa có cookie sẽ ăn 403, và handler 403
 *  đá người dùng về màn login — kể cả phiên vừa đăng nhập thành công. */
export function startNotifications() {
    if (_pollInterval) return;
    poll();
    _pollInterval = setInterval(poll, 30000);
}

export function stopNotifications() {
    if (_pollInterval) {
        clearInterval(_pollInterval);
        _pollInterval = null;
    }
}
