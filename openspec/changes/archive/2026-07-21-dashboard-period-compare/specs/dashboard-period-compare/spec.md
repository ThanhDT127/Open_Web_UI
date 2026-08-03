## ADDED Requirements

### Requirement: Previous-period window (KT)

For any dashboard time range `[start, end)`, the system SHALL derive the previous-period window as `[start − Δ, start)` where `Δ = end − start`.

This SHALL be pure timestamp arithmetic: no rounding to calendar boundaries, no snapping to whole days, no lookup table keyed on the range length. The rule SHALL apply identically to preset buttons, arbitrary custom ranges, and calendar-anchored cards (e.g. Cost MTD).

#### Scenario: Preset range

- **WHEN** the admin selects `Last 7d` and the resolved window is `13/07/2026 09:00 → 20/07/2026 09:00`
- **THEN** KT is `06/07/2026 09:00 → 13/07/2026 09:00`

#### Scenario: Arbitrary custom range with non-round length

- **WHEN** the admin picks `05/03/2026 14:23` to `18/03/2026 09:47` (Δ = 12 days 19 hours 24 minutes)
- **THEN** KT is `20/02/2026 18:59 → 05/03/2026 14:23`, preserving the exact Δ down to the minute

#### Scenario: Calendar-anchored card uses the same rule

- **WHEN** the Cost MTD card covers `01/07/2026 00:00 → 20/07/2026 14:30`
- **THEN** KT is the immediately preceding window of equal length, so both sides compare the same number of hours rather than a partial month against a whole month

### Requirement: Same-period-last-year window (CK)

The system SHALL derive the same-period-last-year window by subtracting exactly one calendar year from both bounds, preserving month, day, hour and minute: `CK = [start − 1 year, end − 1 year]`.

When a bound falls on 29 February and the target year is not a leap year, the system SHALL clamp that bound to 28 February of the target year. Clamping SHALL NOT roll the date forward into March.

Calendar dates SHALL be evaluated in Vietnam time (UTC+7) when deciding whether the clamp applies, so that a timestamp whose Vietnam-time date is 29 February is clamped even when its UTC date is 28 February.

The term "cùng kỳ" SHALL mean same period last year, matching Vietnamese business convention and the behaviour of Power BI `SAMEPERIODLASTYEAR`, GA4 and Adobe Analytics. The system SHALL NOT substitute a shorter shift (such as −24h, −7d or −28d) for CK.

#### Scenario: Ordinary range

- **WHEN** the current window is `05/03/2026 14:23 → 18/03/2026 09:47`
- **THEN** CK is `05/03/2025 14:23 → 18/03/2025 09:47`

#### Scenario: Bound falls on a leap day

- **WHEN** the current window starts at `29/02/2028 00:00`
- **THEN** the CK start is clamped to `28/02/2027 00:00`, not `01/03/2027`

#### Scenario: Leap day differs between Vietnam time and UTC

- **WHEN** the current window starts at `29/02/2028 05:00` Vietnam time, which is `28/02/2028 22:00` UTC
- **THEN** the clamp applies on the Vietnam-time date and the CK start is `28/02/2027 05:00` Vietnam time, rather than the `01/03/2027 05:00` Vietnam time that would result from evaluating the calendar date in UTC

#### Scenario: Range spans a leap day

- **WHEN** the current window is `01/01/2028 00:00 → 29/02/2028 23:59` (60 days)
- **THEN** CK is `01/01/2027 00:00 → 28/02/2027 23:59` (59 days), one day shorter, and the length mismatch is flagged per the window-length requirement

### Requirement: One shared time window across all tabs

The dashboard SHALL resolve the selected global range into absolute `start` / `end` timestamps once per refresh cycle, and every tab and every comparison window in that cycle SHALL be derived from those same absolute timestamps.

Preset buttons expressed in minutes SHALL be converted to absolute timestamps at resolution time rather than each caller independently evaluating "now". All dashboard requests SHALL send absolute `start` / `end` parameters.

#### Scenario: Two tabs report the same number

- **WHEN** the admin selects `Last 24h`, views the Usage tab, then switches to the Overview tab within the same refresh cycle
- **THEN** both tabs request the identical window and the metrics they share display identical values and identical comparison badges

#### Scenario: Rolling behaviour preserved

- **WHEN** a refresh cycle elapses while `Last 1h` remains selected
- **THEN** the window is re-resolved against the new "now", so the range keeps rolling forward rather than freezing at the moment of selection

### Requirement: Comparison badge display

Each comparison-eligible metric card SHALL render a badge with up to two lines, KT first then CK. Each line SHALL show the direction indicator, the delta, the compared window's actual dates, and the compared absolute value.

The badge SHALL always print the dates of the window being compared, rendered in Vietnam time (UTC+7) so that they match the clock the admin used to pick the range. The system SHALL NOT suppress a comparison line based on window overlap, on the magnitude of the difference, or on any other implicit rule beyond the missing-data case defined below.

#### Scenario: Both comparison lines render

- **WHEN** a Total Cost card of `$412.86` has KT `$349.88` and CK `$443.94`
- **THEN** the badge shows a KT line and a CK line, each carrying its arrow, percentage, window dates and absolute value

#### Scenario: Overlapping comparison windows are shown, not hidden

- **WHEN** the admin picks a custom range long enough that the CK window overlaps the KT window
- **THEN** both lines still render with their explicit dates, allowing the reader to see the overlap rather than having a line silently disappear

### Requirement: Missing data and zero-baseline handling

When a comparison window contains no data, the system SHALL render that line as an em dash (`CK: —`) using the dimmed style, with no arrow and no percentage.

When a comparison window contains data but the compared metric value is zero, the system SHALL NOT render a relative percentage. It SHALL render the absolute change instead, so that a division by zero is never presented as a percentage.

#### Scenario: No year-ago data exists

- **WHEN** the CK window predates the first row in the audit log
- **THEN** the CK line renders as `CK: —` in the dimmed style, and no percentage is computed

#### Scenario: Comparison baseline is zero

- **WHEN** the KT window recorded a metric value of `0` and the current window records `12`
- **THEN** the badge reports the absolute change `+12` rather than a percentage

### Requirement: Window length mismatch indicator

When the comparison window and the current window differ in length, the system SHALL mark that comparison line with a warning indicator and explain the cause on hover.

#### Scenario: Leap-year length mismatch

- **WHEN** the current window is 60 days long and its CK window is 59 days long because the prior year had no 29 February
- **THEN** the CK line carries a warning indicator and a hover explanation stating that the comparison period is one day shorter

### Requirement: Comparison data refresh cadence

Comparison windows SHALL be fetched when the global range changes or when a tab is opened, and SHALL be cached per module and window. The periodic refresh that keeps the current window live SHALL NOT re-fetch comparison windows.

#### Scenario: Periodic refresh does not re-fetch closed periods

- **WHEN** the periodic refresh runs while a tab is open and the global range is unchanged
- **THEN** only the current window is re-fetched, the comparison values are served from cache, and no additional comparison requests are issued

#### Scenario: Range change invalidates the cache

- **WHEN** the admin changes the global range
- **THEN** the comparison windows for the new range are fetched once and cached, and subsequent periodic refreshes reuse them
