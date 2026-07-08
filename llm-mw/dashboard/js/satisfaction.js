// Satisfaction (CSAT) analytics module
import { mwFetch, escapeHtml } from './utils.js';
import { currentTimeRange } from './filters.js';

export async function refreshSatisfaction() {
    const leaderboardBody = document.getElementById('csatModelLeaderboard');
    const feedbackContainer = document.getElementById('csatRecentFeedback');
    if (!leaderboardBody) return;

    try {
        // Show loading state
        leaderboardBody.innerHTML = '<tr><td colspan="6" class="loading">Loading satisfaction data...</td></tr>';
        if (feedbackContainer) feedbackContainer.innerHTML = '<div class="loading">Loading feedback...</div>';

        // Build query params from global time range
        const params = new URLSearchParams();
        if (currentTimeRange && currentTimeRange.minutes) {
            params.append('minutes', currentTimeRange.minutes);
        } else if (currentTimeRange && currentTimeRange.start && currentTimeRange.end) {
            params.append('start', currentTimeRange.start);
            params.append('end', currentTimeRange.end);
        } else {
            params.append('minutes', 43200); // 30d default
        }

        const res = await mwFetch(`/v1/_mw/admin/analytics/satisfaction?${params}`);
        if (!res || !res.ok) {
            throw new Error(`HTTP ${res ? res.status : 'null'}`);
        }

        const data = await res.json();

        // ── 1. Update CSAT summary metrics ──
        const scoreEl = document.getElementById('csatScoreValue');
        const posEl = document.getElementById('csatPositiveCount');
        const negEl = document.getElementById('csatNegativeCount');
        const totalEl = document.getElementById('csatTotalCount');

        if (scoreEl) scoreEl.textContent = `${data.totals.csat_percent}%`;
        if (posEl) posEl.textContent = data.totals.positive.toLocaleString();
        if (negEl) negEl.textContent = data.totals.negative.toLocaleString();
        if (totalEl) totalEl.textContent = data.totals.total.toLocaleString();

        // ── 2. Render Model Leaderboard table ──
        if (data.model_leaderboard && data.model_leaderboard.length > 0) {
            leaderboardBody.innerHTML = data.model_leaderboard.map((m, i) => {
                const csatClass = m.csat_percent >= 80 ? 'status-ok'
                    : m.csat_percent >= 50 ? 'status-warning'
                    : 'status-error';
                return `<tr>
                    <td>${i + 1}</td>
                    <td>${escapeHtml(m.model_id)}</td>
                    <td style="color: #10b981; font-weight: 600;">${m.positive}</td>
                    <td style="color: #ef4444; font-weight: 600;">${m.negative}</td>
                    <td>${m.total}</td>
                    <td><span class="${csatClass}" style="font-weight: 700;">${m.csat_percent}%</span></td>
                </tr>`;
            }).join('');
        } else {
            leaderboardBody.innerHTML = '<tr><td colspan="6" class="loading">Chưa có dữ liệu đánh giá nào trong khoảng thời gian này.</td></tr>';
        }

        // ── 3. Render Recent Feedback feed ──
        if (feedbackContainer) {
            if (data.recent_feedback && data.recent_feedback.length > 0) {
                feedbackContainer.innerHTML = data.recent_feedback.map(fb => {
                    const icon = fb.rating === 1 ? '👍' : fb.rating === -1 ? '👎' : '➖';
                    const ratingClass = fb.rating === 1 ? 'color: #10b981;' : fb.rating === -1 ? 'color: #ef4444;' : 'color: #94a3b8;';
                    const timeAgo = _formatTimeAgo(fb.created_at);
                    const reasonLabel = fb.reason ? _formatReason(fb.reason) : '';

                    return `<div class="event-line" style="padding: 10px 14px; border-bottom: 1px solid #1e293b; display: flex; gap: 12px; align-items: flex-start;">
                        <span style="font-size: 20px; ${ratingClass}">${icon}</span>
                        <div style="flex: 1; min-width: 0;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                                <span style="font-weight: 600; color: #e2e8f0;">${escapeHtml(fb.user_name)}</span>
                                <span style="font-size: 12px; color: #64748b;">${escapeHtml(timeAgo)}</span>
                            </div>
                            <div style="font-size: 12px; color: #94a3b8; margin-bottom: 4px;">
                                <span style="background: #1e293b; padding: 2px 8px; border-radius: 4px; font-size: 11px;">${escapeHtml(fb.model_id)}</span>
                                ${reasonLabel ? `<span style="margin-left: 6px; background: #312e81; padding: 2px 8px; border-radius: 4px; font-size: 11px;">${escapeHtml(reasonLabel)}</span>` : ''}
                            </div>
                            ${fb.comment ? `<div style="color: #cbd5e1; font-size: 13px; margin-top: 4px; font-style: italic;">"${escapeHtml(fb.comment)}"</div>` : ''}
                        </div>
                    </div>`;
                }).join('');
            } else {
                feedbackContainer.innerHTML = '<div class="loading">Chưa có phản hồi nào trong khoảng thời gian này.</div>';
            }
        }

    } catch (err) {
        console.error('Failed to load satisfaction data:', err);
        leaderboardBody.innerHTML = `<tr><td colspan="6" class="loading" style="color: #ef4444;">Error: ${escapeHtml(err.message)}</td></tr>`;
    }
}

// ── Helpers ──

function _formatTimeAgo(epoch) {
    if (!epoch) return '';
    const now = Date.now() / 1000;
    const diff = now - epoch;
    if (diff < 60) return 'Vừa xong';
    if (diff < 3600) return `${Math.floor(diff / 60)} phút trước`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} giờ trước`;
    return `${Math.floor(diff / 86400)} ngày trước`;
}

function _formatReason(reason) {
    const map = {
        'accurate_information': 'Thông tin chính xác',
        'inaccurate': 'Không chính xác',
        'helpful': 'Hữu ích',
        'not_helpful': 'Không hữu ích',
        'creative': 'Sáng tạo',
        'too_long': 'Quá dài',
        'too_short': 'Quá ngắn',
        'other': 'Khác'
    };
    return map[reason] || reason;
}
