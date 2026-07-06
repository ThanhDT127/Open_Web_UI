## 1. Dependencies & Setup

- [x] 1.1 Add `openpyxl` to `llm-mw/requirements.txt`
- [x] 1.2 Verify openpyxl is installable in the Docker container (check Dockerfile if needed)

## 2. Backend — Data Collection Layer

- [x] 2.1 Create `llm-mw/api/export_report.py` with helper functions that collect data from existing APIs:
  - `_collect_summary(start, end)` — aggregate usage metrics from `mw_audit_log` (reuse logic from `summary.py`)
  - `_collect_top_users(start, end)` — per-user breakdown with display names from OW `user` table
  - `_collect_top_models(start, end)` — model breakdown by cost and requests
  - `_collect_groups(start, end)` — group analytics (reuse logic from `group_analytics.py`, graceful fallback if OW unavailable)
  - `_collect_chat_analytics(start, end)` — chat/message stats + leaderboard (reuse logic from `analytics.py`)
  - `_collect_satisfaction(start, end)` — feedback totals + model CSAT (reuse logic from `analytics.py`)
  - `_collect_audit_log(start, end, limit=50000)` — raw audit records sorted by timestamp DESC

## 3. Backend — Excel Generation

- [x] 3.1 Implement `_generate_xlsx(data, start, end)` function using openpyxl:
  - Sheet 1 "Tổng quan": summary metrics in a key-value table format
  - Sheet 2 "Top Users": user breakdown table with headers
  - Sheet 3 "Top Models": model breakdown table
  - Sheet 4 "Phòng ban": group analytics table (show fallback message if data unavailable)
  - Sheet 5 "Chat Analytics": chat stats + user leaderboard
  - Sheet 6 "Satisfaction": CSAT totals + model leaderboard
  - Sheet 7 "Audit Log": raw audit records (capped 50K rows)
- [x] 3.2 Apply formatting: bold headers with colored background, auto-width columns, freeze header row, and AutoFilter enabled on header row for each tabular sheet

## 4. Backend — CSV Streaming

- [x] 4.1 Implement `_generate_csv_stream(start, end)` as a Python generator that yields CSV rows from `mw_audit_log` using server-side cursor (avoid loading all rows into memory)
- [x] 4.2 Include UTF-8 BOM prefix and all audit log columns

## 5. Backend — API Endpoint & Routing

- [x] 5.1 Create the `export_report(request, format, start, end)` handler in `export_report.py`:
  - Parse and validate `format` param (xlsx or csv, default xlsx)
  - Parse `start`/`end` time range params (reuse existing timezone handling)
  - Call `require_admin_or_session(request)` for auth
  - For xlsx: collect all data → generate workbook → return StreamingResponse with appropriate Content-Type and Content-Disposition headers
  - For csv: return StreamingResponse from CSV generator
  - Build filename using `strftime('%Y%m%d')` on the already-parsed `cutoff`/`end_time` datetime objects (not the raw ISO query string) to avoid filesystem-unsafe characters like `:`
- [x] 5.2 Register the route `GET /v1/_mw/export/report` in `main.py`

## 6. Frontend — Export Modal UI

- [x] 6.1 Add "📥 Export Report" button in dashboard header area (after status bar, before tabs) in `index.html`
- [x] 6.2 Add export modal HTML in `index.html` with format radio buttons (Excel/CSV) and current time range display
- [x] 6.3 Create `dashboard/js/export.js` with:
  - `openExportModal()` — show modal, pre-fill time range from current dashboard filter
  - `closeExportModal()` — hide modal
  - `downloadReport()` — construct URL with format and time range params, trigger browser download via hidden `<a>` element
- [x] 6.4 Import and wire `export.js` in `main.js`, expose API on `window.dashboardAPI`
- [x] 6.5 Add modal and button CSS styles in `dashboard/css/dashboard.css` (reused existing `.btn-export`/`.modal-*`/`.form-group`/`.btn` classes; only inline-style overrides needed for the radio row, no new CSS rules required)

## 7. Testing & Verification

- [x] 7.1 Test Excel export: verify the downloaded .xlsx file opens correctly with 7 sheets, data is populated, formatting is applied — verified against live rebuilt container: all 7 sheets present with real data, AutoFilter + freeze panes confirmed via openpyxl inspection
- [x] 7.2 Test CSV export: verify streaming download works, file has BOM, all columns present — verified: BOM `efbbbf` present, 19 columns, row count matches Audit Log sheet
- [x] 7.3 Test auth: verify unauthenticated requests return 401/403 — verified: returns HTTP 403
- [x] 7.4 Test with empty time range: verify report generates with empty/zero data without errors — verified: future date range (2030) generates valid xlsx with empty sheets, no crash; missing start/end falls back to last-60-min default
- [x] 7.5 Test OW DB unavailable scenario: verify Excel generates with fallback messages on affected sheets — verified via empty-groups code path (same fallback branch triggered when group data is empty): "Phòng ban" sheet shows single fallback message row
