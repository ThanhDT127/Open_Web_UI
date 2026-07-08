// Pending requests detail modal logic
import { mwFetch, updateStatus } from './utils.js';

export async function showPendingModal() {
    document.getElementById('pendingModal').style.display = 'flex';
    await refreshPendingList();
}

export function closePendingModal() {
    document.getElementById('pendingModal').style.display = 'none';
}

export async function refreshPendingList() {
    const tbody = document.getElementById('pendingTableBody');
    if (!tbody) return;

    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding: 20px; color: #64748b;">Loading pending requests...</td></tr>';

    try {
        const res = await mwFetch('/v1/_mw/admin/pending');
        if (!res || !res.ok) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding: 20px; color: #ef4444;">Không thể tải danh sách pending</td></tr>';
            return;
        }

        const data = await res.json();
        renderPendingTable(data);
    } catch (err) {
        console.error('Failed to load pending requests:', err);
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 20px; color: #ef4444;">Lỗi: ${err.message}</td></tr>`;
        updateStatus('error', 'Failed to load pending requests');
    }
}

function renderPendingTable(requests) {
    const tbody = document.getElementById('pendingTableBody');
    if (!tbody) return;

    if (!requests || requests.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding: 20px; color: #64748b;">Không có request pending nào đang chạy</td></tr>';
        return;
    }

    const now = Math.floor(Date.now() / 1000);

    tbody.innerHTML = requests.map(req => {
        const elapsedSecs = Math.max(0, now - req.started_at);
        let durationText = '';
        if (elapsedSecs < 60) {
            durationText = `${elapsedSecs} giây trước`;
        } else if (elapsedSecs < 3600) {
            durationText = `${Math.floor(elapsedSecs / 60)} phút trước`;
        } else {
            durationText = `${Math.floor(elapsedSecs / 3600)} giờ ${Math.floor((elapsedSecs % 3600) / 60)} phút trước`;
        }

        // Highlight requests running for more than 10 minutes (600s) as stuck (yellow status badge in CSS)
        const isStuck = elapsedSecs > 600;
        const durationStyle = isStuck ? 'color: #f59e0b; font-weight: bold;' : 'color: #10b981;';
        
        const reqId = req.request_id;
        const userId = req.user_id;
        const model = req.model;

        return `<tr>
            <td style="font-family: monospace; font-size: 11px;"><code>${reqId}</code></td>
            <td><span class="user-badge">${userId}</span></td>
            <td><span class="model-badge">${model}</span></td>
            <td><span style="font-size: 12px; color: #94a3b8;">${req.endpoint}</span></td>
            <td style="${durationStyle}">${durationText}</td>
            <td class="actions-cell">
                <button class="btn-icon" style="padding: 2px 6px; font-size: 14px;" title="Reconcile (Đồng bộ)" onclick="window.dashboardAPI.reconcilePending('${reqId}', '${userId}', '${model}')">🔄</button>
                <button class="btn-icon" style="padding: 2px 6px; font-size: 14px;" title="Force Clear (Xóa kẹt)" onclick="window.dashboardAPI.forceClearPending('${reqId}')">🗑️</button>
            </td>
        </tr>`;
    }).join('');
}

export async function reconcilePending(requestId, userId, model) {
    if (!confirm(`Bạn có chắc chắn muốn chạy Reconcile đối soát cho request ID: ${requestId}?\nHệ thống sẽ quét log LiteLLM để tính tiền cho user ${userId}.`)) {
        return;
    }

    updateStatus('pending', `Đang đối soát ${requestId}...`);
    try {
        const res = await mwFetch('/admin/reconcile', {
            method: 'POST',
            body: JSON.stringify({
                request_id: requestId,
                user_id: userId,
                model: model
            })
        });

        if (!res) return; // mwFetch handles 403

        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.detail || 'Reconcile failed');
        }

        updateStatus('ok', `Đối soát thành công! Chi phí: $${data.cost_usd}`);
        alert(`Đối soát thành công!\nSố lượng tokens: ${data.total_tokens}\nChi phí: $${data.cost_usd}`);
        await refreshPendingList();
        
        // Refresh usage tables and summary counters on the main dashboard tab
        if (window.dashboardAPI.loadSummary) {
            await window.dashboardAPI.loadSummary();
        }
    } catch (err) {
        console.error(err);
        alert(`Lỗi đối soát: ${err.message}`);
        updateStatus('error', `Reconcile thất bại: ${err.message}`);
    }
}

export async function forceClearPending(requestId) {
    if (!confirm(`CẢNH BÁO: Bạn đang thực hiện Force Clear (Xóa kẹt) cho request ID:\n${requestId}\n\nHành động này sẽ XÓA CỨNG request khỏi danh sách pending mà KHÔNG TÍNH CHI PHÍ hay TRỪ QUOTA của người dùng.\nBạn có chắc chắn muốn tiếp tục?`)) {
        return;
    }

    updateStatus('pending', `Đang xóa kẹt ${requestId}...`);
    try {
        const res = await mwFetch(`/v1/_mw/admin/pending/${requestId}`, {
            method: 'DELETE'
        });

        if (!res) return;

        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.detail || 'Force clear failed');
        }

        updateStatus('ok', `Đã xóa kẹt request ${requestId} thành công.`);
        await refreshPendingList();
        
        // Refresh usage tables and summary counters on the main dashboard tab
        if (window.dashboardAPI.loadSummary) {
            await window.dashboardAPI.loadSummary();
        }
    } catch (err) {
        console.error(err);
        alert(`Lỗi xóa kẹt: ${err.message}`);
        updateStatus('error', `Force clear thất bại: ${err.message}`);
    }
}
