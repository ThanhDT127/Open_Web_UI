// Satisfaction (CSAT) analytics module
import { mwFetch, escapeHtml } from './utils.js';
import { buildRangeParams } from './filters.js';
import { formatValue, classify, minSample } from './metrics_registry.js';

const CSAT_CLASS = { ok: 'status-ok', warn: 'status-warning', danger: 'status-error' };

// The number is always shown; only its rank and its colour are withheld below the
// minimum. Hiding it would throw away the single negative vote this system has —
// with five ratings in total, that vote is 20% of everything we know about quality.
function csatCell(pct, votes) {
    const state = classify('csat_percent', pct, votes);
    const cls = CSAT_CLASS[state] || '';
    const style = state ? 'font-weight: 700;' : 'font-weight: 700; color: #94a3b8;';
    const title = state ? '' : ` title="Chỉ ${votes} lượt đánh giá — chưa đủ ${minSample('csat_percent')} lượt để xếp hạng"`;
    return `<span class="${cls}" style="${style}"${title}>${formatValue('csat_percent', pct)}</span>`;
}

export async function refreshSatisfaction() {
    const leaderboardBody = document.getElementById('csatModelLeaderboard');
    const feedbackContainer = document.getElementById('csatRecentFeedback');
    if (!leaderboardBody) return;

    try {
        // Show loading state
        leaderboardBody.innerHTML = '<tr><td colspan="6" class="loading">Loading satisfaction data...</td></tr>';
        if (feedbackContainer) feedbackContainer.innerHTML = '<div class="loading">Loading feedback...</div>';

        // Build query params from global time range
        const params = buildRangeParams();

        const res = await mwFetch(`/v1/_mw/admin/analytics/satisfaction?${params}`);
        if (!res || !res.ok) {
            throw new Error(`HTTP ${res ? res.status : 'null'}`);
        }

        const data = await res.json();

        // ── 1. Update CSAT summary metrics ──
        //
        // No KT/CK badge on this card, deliberately — not the same oversight that left
        // failed_dashboard_logins declared-but-unwired. `csat_percent` IS comparable and
        // Overview does badge it, because Overview answers "is satisfaction moving?" for a
        // reader who sees one number. This tab is the working surface for that number: the
        // model leaderboard and the feedback list below already carry the movement in a
        // form you can act on, and a period arrow on top of them adds a second, coarser
        // verdict about the same data. If that judgement is ever revisited, the badge needs
        // `currentSample` (data.totals.total) wiring — see renderCsatCompare in overview.js.
        const scoreEl = document.getElementById('csatScoreValue');
        const posEl = document.getElementById('csatPositiveCount');
        const negEl = document.getElementById('csatNegativeCount');
        const totalEl = document.getElementById('csatTotalCount');

        if (scoreEl) scoreEl.textContent = formatValue('csat_percent', data.totals.csat_percent);
        if (posEl) posEl.textContent = data.totals.positive.toLocaleString();
        if (negEl) negEl.textContent = data.totals.negative.toLocaleString();
        if (totalEl) totalEl.textContent = data.totals.total.toLocaleString();

        // Silent when there is nothing to explain. "Total Votes" counts thumbs up plus
        // thumbs down; any feedback row carrying neither is outside CSAT, and the reader
        // is only told about that when such rows actually exist.
        const excluded = (data.totals.feedback_rows || 0) - (data.totals.total || 0);
        const noteEl = document.getElementById('csatExcludedNote');
        if (noteEl) {
            noteEl.innerHTML = excluded > 0
                ? `<span title="CSAT chỉ chia trên lượt khen và chê, nên các phản hồi không nêu khen/chê không nằm trong mẫu số">ⓘ ${excluded} phản hồi khác không nêu khen/chê, không tính vào CSAT</span>`
                : '';
        }

        // ── 2. Render Model Leaderboard table ──
        // Two tiers. The backend sorts by CSAT with vote count only as a tiebreak, so a
        // model with one lucky positive would otherwise outrank one with fifty. Models
        // below the minimum drop under a separator and lose their rank number entirely —
        // no number means nothing to compare.
        if (data.model_leaderboard && data.model_leaderboard.length > 0) {
            const floor = minSample('csat_percent');
            const ranked = data.model_leaderboard.filter(m => m.total >= floor);
            const sparse = data.model_leaderboard.filter(m => m.total < floor);

            const row = (m, rank) => `<tr>
                    <td>${rank == null ? '<span style="color:#64748b;">–</span>' : rank}</td>
                    <td>${escapeHtml(m.model_id)}</td>
                    <td style="color: #10b981; font-weight: 600;">${m.positive}</td>
                    <td style="color: #ef4444; font-weight: 600;">${m.negative}</td>
                    <td>${m.total}</td>
                    <td>${csatCell(m.csat_percent, m.total)}</td>
                </tr>`;

            const separator = sparse.length === 0 ? '' : `<tr>
                    <td colspan="6" style="padding: 6px 12px; color: #64748b; font-size: 12px; background: #0f172a;">
                        Chưa đủ ${floor} lượt đánh giá để xếp hạng
                    </td>
                </tr>`;

            leaderboardBody.innerHTML =
                ranked.map((m, i) => row(m, i + 1)).join('')
                + separator
                + sparse.map(m => row(m, null)).join('');
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
                    // Always ask the formatter, including for an empty reason — it owns
                    // the decision of what an absent reason looks like.
                    const reasonLabel = _formatReason(fb.reason);
                    const reasonMuted = !fb.reason;
                    // Three states, not two. 'unknown' means the backend could not read the
                    // records that decide between alive and deleted, so neither badge may be
                    // shown — an absent badge would read as "this account is fine".
                    const statusTag = fb.user_status === 'deleted'
                        ? ' <span style="font-size: 10px; font-weight: 600; padding: 1px 7px; border-radius: 9px; background: rgba(239,68,68,0.15); color: #f87171; vertical-align: middle;">🗑️ đã xóa</span>'
                        : fb.user_status === 'unknown'
                        ? ' <span title="Không đọc được trạng thái tài khoản — không xác định được còn hay đã xóa" style="font-size: 10px; font-weight: 600; padding: 1px 7px; border-radius: 9px; background: rgba(148,163,184,0.15); color: #94a3b8; vertical-align: middle;">❓ không rõ</span>'
                        : '';

                    return `<div class="event-line" style="padding: 10px 14px; border-bottom: 1px solid #1e293b; display: flex; gap: 12px; align-items: flex-start;">
                        <span style="font-size: 20px; ${ratingClass}">${icon}</span>
                        <div style="flex: 1; min-width: 0;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                                <span style="font-weight: 600; color: #e2e8f0;">${escapeHtml(fb.user_name)}${statusTag}</span>
                                <span style="font-size: 12px; color: #64748b;">${escapeHtml(timeAgo)}</span>
                            </div>
                            <div style="font-size: 12px; color: #94a3b8; margin-bottom: 4px;">
                                <span style="background: #1e293b; padding: 2px 8px; border-radius: 4px; font-size: 11px;">${escapeHtml(fb.model_id)}</span>
                                <span style="margin-left: 6px; background: ${reasonMuted ? '#1e293b' : '#312e81'}; color: ${reasonMuted ? '#64748b' : 'inherit'}; padding: 2px 8px; border-radius: 4px; font-size: 11px;">${escapeHtml(reasonLabel)}</span>
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

// A preference list, not an exhaustive one. Open WebUI ships new reason values with new
// versions, and the old `map[reason] || reason` fallback dumped the raw identifier onto
// the screen — `positive_attitude` and `followed_instructions_perfectly` are both already
// doing that on dev. Unknown values get humanised instead, so a reason we have not
// translated yet reads as plain text rather than as a bug.
const REASON_LABELS = {
    'accurate_information': 'Thông tin chính xác',
    'inaccurate': 'Không chính xác',
    'helpful': 'Hữu ích',
    'not_helpful': 'Không hữu ích',
    'creative': 'Sáng tạo',
    'too_long': 'Quá dài',
    'too_short': 'Quá ngắn',
    'positive_attitude': 'Thái độ tích cực',
    'followed_instructions_perfectly': 'Bám sát yêu cầu',
    'other': 'Khác',
};

const _warnedReasons = new Set();

function _formatReason(reason) {
    if (!reason) return 'Không nêu lý do';
    if (REASON_LABELS[reason]) return REASON_LABELS[reason];
    // Warn once per value: nobody reads the console in normal use, but the next person
    // debugging this tab should see immediately which labels are missing.
    if (!_warnedReasons.has(reason)) {
        _warnedReasons.add(reason);
        console.warn(`[Satisfaction] Lý do chưa có bản dịch: "${reason}"`);
    }
    const words = String(reason).replace(/_/g, ' ').trim();
    return words.charAt(0).toUpperCase() + words.slice(1);
}
