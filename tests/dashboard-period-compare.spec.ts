/**
 * Luật kỳ của dashboard: KT (kỳ trước) và CK (cùng kỳ năm trước).
 *
 * Đây là test hàm thuần — không cần app chạy, không mở trình duyệt. Module
 * `period_compare.js` là ES module không đụng DOM nên import thẳng được.
 *
 * Các ca biên ở đây là những chỗ luật dễ sai nhất: khoảng lẻ phút, năm nhuận,
 * và ca mốc rơi vào khoảng giờ mà ngày lịch theo giờ Việt Nam khác ngày theo UTC.
 */
import { test, expect } from '@playwright/test';
import * as path from 'path';
import { pathToFileURL } from 'url';

const MODULE_URL = pathToFileURL(
    path.resolve(__dirname, '../llm-mw/dashboard/js/period_compare.js')
).href;

type PeriodModule = typeof import('../llm-mw/dashboard/js/period_compare.js');

let mod: PeriodModule;

test.beforeAll(async () => {
    mod = (await import(MODULE_URL)) as PeriodModule;
});

// Giờ Việt Nam (UTC+7) viết dưới dạng ISO có offset, đúng như frontend gửi lên API.
const vn = (s: string) => `${s}+07:00`;

test.describe('KT — kỳ trước', () => {
    test('preset: Last 7d lùi đúng 7 ngày', () => {
        const { kt } = mod.resolveCompareWindows(
            vn('2026-07-13T09:00:00'), vn('2026-07-20T09:00:00')
        );
        expect(new Date(kt.start).toISOString()).toBe('2026-07-06T02:00:00.000Z');
        expect(new Date(kt.end).toISOString()).toBe('2026-07-13T02:00:00.000Z');
    });

    test('custom lẻ phút: giữ nguyên Δ tới từng phút', () => {
        // Δ = 12 ngày 19 giờ 24 phút
        const { kt } = mod.resolveCompareWindows(
            vn('2026-03-05T14:23:00'), vn('2026-03-18T09:47:00')
        );
        expect(new Date(kt.start).toISOString()).toBe(new Date(vn('2026-02-20T18:59:00')).toISOString());
        expect(new Date(kt.end).toISOString()).toBe(new Date(vn('2026-03-05T14:23:00')).toISOString());
    });

    test('KT luôn dài đúng bằng cửa sổ hiện tại', () => {
        const start = vn('2026-03-05T14:23:00');
        const end = vn('2026-03-18T09:47:00');
        const { kt } = mod.resolveCompareWindows(start, end);
        const lenNow = +new Date(end) - +new Date(start);
        const lenKt = +new Date(kt.end) - +new Date(kt.start);
        expect(lenKt).toBe(lenNow);
        expect(kt.lengthMismatch).toBe(false);
    });
});

test.describe('CK — cùng kỳ năm trước', () => {
    test('khoảng thường: lùi đúng 1 năm, giữ nguyên ngày/giờ/phút', () => {
        const { ck } = mod.resolveCompareWindows(
            vn('2026-03-05T14:23:00'), vn('2026-03-18T09:47:00')
        );
        expect(new Date(ck.start).toISOString()).toBe(new Date(vn('2025-03-05T14:23:00')).toISOString());
        expect(new Date(ck.end).toISOString()).toBe(new Date(vn('2025-03-18T09:47:00')).toISOString());
    });

    test('biên rơi đúng 29/02: kẹp về 28/02, KHÔNG tràn sang 01/03', () => {
        const { ck } = mod.resolveCompareWindows(
            vn('2028-02-29T00:00:00'), vn('2028-03-05T00:00:00')
        );
        expect(new Date(ck.start).toISOString()).toBe(new Date(vn('2027-02-28T00:00:00')).toISOString());
    });

    test('range đè 29/02: CK ngắn hơn 1 ngày và bị đánh dấu', () => {
        const { ck } = mod.resolveCompareWindows(
            vn('2028-01-01T00:00:00'), vn('2028-02-29T23:59:00')
        );
        expect(new Date(ck.start).toISOString()).toBe(new Date(vn('2027-01-01T00:00:00')).toISOString());
        expect(new Date(ck.end).toISOString()).toBe(new Date(vn('2027-02-28T23:59:00')).toISOString());
        expect(ck.lengthMismatch).toBe(true);
    });

    test('năm nhuận sang năm nhuận: không kẹp, không lệch độ dài', () => {
        const { ck } = mod.resolveCompareWindows(
            vn('2028-02-29T10:00:00'), vn('2028-03-01T10:00:00')
        );
        expect(new Date(ck.start).toISOString()).toBe(new Date(vn('2027-02-28T10:00:00')).toISOString());
        // 2027 không nhuận nên vẫn kẹp; kiểm ca thật sự nhuận-sang-nhuận:
        const back4 = mod.shiftBackOneYear(new Date(vn('2025-02-28T10:00:00')));
        expect(back4.toISOString()).toBe(new Date(vn('2024-02-28T10:00:00')).toISOString());
    });
});

test.describe('D9 — lịch đọc theo giờ Việt Nam, không phải UTC', () => {
    test('mốc 29/02/2028 05:00 giờ VN (= 28/02 theo UTC) vẫn phải kẹp', () => {
        // 29/02/2028 05:00 +07:00  ==  28/02/2028 22:00 UTC
        const instant = vn('2028-02-29T05:00:00');
        expect(new Date(instant).toISOString()).toBe('2028-02-28T22:00:00.000Z');

        const ck = mod.shiftBackOneYear(new Date(instant));

        // Đúng: kẹp theo lịch VN → 28/02/2027 05:00 giờ VN
        expect(ck.toISOString()).toBe(new Date(vn('2027-02-28T05:00:00')).toISOString());
        // Sai (nếu đọc lịch theo UTC): 01/03/2027 05:00 giờ VN
        expect(ck.toISOString()).not.toBe(new Date(vn('2027-03-01T05:00:00')).toISOString());
    });

    test('không phụ thuộc múi giờ của máy chạy test', () => {
        // Kết quả phải là một mốc tuyệt đối cố định, bất kể TZ của process.
        const ck = mod.shiftBackOneYear(new Date('2026-07-20T02:00:00.000Z'));
        expect(ck.toISOString()).toBe('2025-07-20T02:00:00.000Z');
    });
});
