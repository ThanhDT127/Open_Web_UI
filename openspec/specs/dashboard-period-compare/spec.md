# dashboard-period-compare Specification

## Purpose
TBD - created by archiving change dashboard-period-compare. Update Purpose after archive.
## Requirements
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

The badge SHALL always print the dates of the window being compared, rendered in Vietnam time (UTC+7) so that they match the clock the admin used to pick the range. The system SHALL NOT suppress a comparison line based on window overlap, on the magnitude of the difference, or on any implicit rule. The only grounds for showing less than a full comparison are the two defined cases: a window holding no data, and a window failing the metric's declared minimum number of observations. Both are stated in this specification and both are legible on screen.

#### Scenario: Both comparison lines render

- **WHEN** a Total Cost card of `$412.86` has KT `$349.88` and CK `$443.94`
- **THEN** the badge shows a KT line and a CK line, each carrying its arrow, percentage, window dates and absolute value

#### Scenario: Overlapping comparison windows are shown, not hidden

- **WHEN** the admin picks a custom range long enough that the CK window overlaps the KT window
- **THEN** both lines still render with their explicit dates, allowing the reader to see the overlap rather than having a line silently disappear

#### Scenario: Suppression happens only on stated grounds

- **WHEN** a comparison is not fully rendered
- **THEN** the cause is either an empty window or a sample below the metric's declared minimum, and no other rule reduces what is shown

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

Caching a past window rests on that window's contents being settled. This holds for metrics drawn from the middleware's own append-only request log, which admits no edit or deletion path. It does not hold for metrics drawn from tables the product's users own, where a past window's contents may still change; for those, a cached comparison is a reading taken at fetch time rather than a constant. Where this distinction affects how a value should be interpreted, it SHALL be recorded alongside the caching behaviour so that later work does not extend the caching on a premise that does not hold.

#### Scenario: Periodic refresh does not re-fetch closed periods

- **WHEN** the periodic refresh runs while a tab is open and the global range is unchanged
- **THEN** only the current window is re-fetched, the comparison values are served from cache, and no additional comparison requests are issued

#### Scenario: Range change invalidates the cache

- **WHEN** the admin changes the global range
- **THEN** the comparison windows for the new range are fetched once and cached, and subsequent periodic refreshes reuse them

#### Scenario: The settled-window assumption is recorded, not assumed

- **WHEN** a comparison is served from a source whose past rows can still be edited or removed
- **THEN** the caching behaviour records that its windows are readings rather than constants, so later work does not lengthen the cache or persist the values on a false premise

### Requirement: A comparison rests on evidence in both the current and the compared window

Where a metric declares a minimum number of observations, the system SHALL apply that minimum to the current window and to each compared window. A metric that declares no minimum SHALL be unaffected.

The two failures carry different meanings and SHALL be treated differently. Where the **current** window falls below the minimum, the card can support no comparison at all and the system SHALL render no badge: a card that withholds the colour from its own value because the sample is too small, and then renders a coloured arrow computed from that same sample, contradicts itself in favour of the stronger claim. Where a **compared** window falls below the minimum, only that baseline is unusable, and the system SHALL render that line as carrying no usable figure while leaving the other line intact — a comparison that is properly supported SHALL NOT be discarded because the other one is not.

Each metric SHALL be assessed against its own denominator. Two metrics served by one response may rest on different counts, and those counts thin out independently; assessing both against a single count would either withhold a comparison that is supported or publish one that is not.

#### Scenario: A thin current window renders no badge

- **WHEN** the current window holds 1 rating and the metric requires 20
- **THEN** no badge is rendered, and the card's own value and its sample-size caption remain unchanged

#### Scenario: A thin baseline does not discard a sound one

- **WHEN** the current window and the previous-period window both meet the minimum but the same-period-last-year window does not
- **THEN** the previous-period line renders its comparison and the same-period line renders as carrying no usable figure

#### Scenario: A card does not contradict its own caption

- **WHEN** a card withholds the colour from its value because the sample is below the metric's minimum
- **THEN** it does not render a coloured comparison arrow derived from that same sample

#### Scenario: Two metrics in one response are judged separately

- **WHEN** one response carries a hit-rate resting on evaluated answers and a coverage rate resting on questions asked, and only the second denominator meets its minimum
- **THEN** the coverage comparison renders and the hit-rate comparison does not

### Requirement: A card with too little evidence renders no badge rather than a badge of dashes

Where the current window falls below the metric's minimum, the system SHALL render no badge. It SHALL NOT render a badge whose lines are all em dashes.

A badge of dashes states that the compared windows held nothing, which places the reason on the past. The reason here is the present: this card has too little evidence to compare anything, and its own detail line already says so. Rendering the two situations identically puts the reader's attention on the wrong window.

At the level of a single comparison line the two do coincide, and that is intended: a baseline that is empty and a baseline that is too thin are both unusable as a baseline, so both render as no usable figure on that line.

#### Scenario: A thin card is silent rather than dashed

- **WHEN** the current window is below the metric's minimum
- **THEN** the card carries no badge at all, rather than a badge reading `KT: — / CK: —`

#### Scenario: An unusable baseline reads the same however it became unusable

- **WHEN** one compared window is empty and another is populated but below the minimum, on a card whose current window meets the minimum
- **THEN** both lines render as carrying no usable figure, since neither can serve as a baseline

### Requirement: The evidence rule is enforced where the badge is rendered, not on each surface

The minimum-observation rule SHALL be applied at the point where a comparison badge is rendered — the one place that resolves a metric's declaration together with the current window and both compared windows. A tab SHALL NOT be required to implement the rule in order to be correct.

A rule that each surface must remember is a rule that a new surface will omit, and the omission has no symptom: the badge renders, the arithmetic is valid, and nothing on screen reveals that the figure behind it cannot support the claim. Placing the rule where every badge already passes through makes correctness the default rather than an act of recall. Enforcement SHALL NOT be placed where the metric's identity is unknown, since the applicable minimum cannot be resolved there.

A surface SHALL supply the observation count its metric rests on, since only the surface knows which field of its payload carries that count. Where a metric declares a minimum and its surface supplies no count, the system SHALL report the omission rather than infer whether the threshold was met.

#### Scenario: A newly added tab inherits the rule

- **WHEN** a tab is added that renders a comparison badge for a metric declaring a minimum, and that tab implements no threshold logic of its own
- **THEN** the comparison is still withheld when either window falls below the minimum

#### Scenario: The rule is stated once

- **WHEN** the minimum for a metric is changed in the registry
- **THEN** every surface displaying that metric changes behaviour together, with no per-surface edit

#### Scenario: A missing observation count is reported, not guessed

- **WHEN** a surface renders a badge for a metric declaring a minimum but supplies no observation count
- **THEN** the system reports the omission, rather than silently withholding the badge or silently treating the threshold as met

### Requirement: A comparison badge attaches to the card's value element

The system SHALL identify the card to badge by the element displaying the metric's value. It SHALL reject an element that is itself a comparison badge, rather than proceeding.

The renderer locates the card from the element it is given and then clears any existing badge within that card. An element that is both the anchor and a badge is therefore removed by the renderer's own cleanup, leaving nothing for the next render to find: the first render succeeds and every later one silently leaves the previous range's delta beneath the new range's number. The failure produces a plausible badge rather than a visible error, so it survives review; rejecting the malformed anchor is what converts it into something noticeable.

#### Scenario: A stale badge does not survive a range change

- **WHEN** a card's comparison is rendered, the admin changes the global range, and the tab is re-opened
- **THEN** the badge shows the new range's comparison, not the previous range's

#### Scenario: A malformed anchor is refused

- **WHEN** a caller passes the id of an element that is itself a comparison badge
- **THEN** the renderer declines to render and reports the misuse, rather than removing the element and failing silently thereafter

### Requirement: A comparable declaration has a consumer, and every omission is recorded

Where a metric is declared comparable in the registry, at least one surface displaying it SHALL be wired to render its comparison badge. Where a metric is not to be compared at all, its declaration SHALL carry the reason.

Being wired is not the same as being visible. A wired surface may still withhold its badge on the evidence grounds defined above; that is the rule working, not an unwired declaration. This requirement concerns whether any code path exists to render the comparison at all.

A declaration with no consumer anywhere is indistinguishable from an oversight. The registry is read as the statement of intent for every metric, so a comparable declaration that no surface acts on leaves the next reader unable to tell whether the comparison was rejected or forgotten.

A metric may appear on several surfaces and carry a badge on some but not others. That is permitted — an operational tab and an executive tab answer different questions, and a comparison that serves one may be noise on the other. Where a surface displays a comparable metric without a badge, the omission SHALL be recorded, so that it reads as a decision rather than as the same oversight this requirement exists to catch.

#### Scenario: A declared comparison has somewhere to appear

- **WHEN** a metric is declared comparable in the registry
- **THEN** at least one card displaying it is wired to render a comparison badge, whether or not the current data lets that badge appear

#### Scenario: A metric carries a badge on one surface and not another

- **WHEN** the same comparable metric appears on two tabs and only one badges it
- **THEN** the tab that omits the badge records why, and the omission is not treated as a defect

#### Scenario: A total refusal is recorded rather than implied

- **WHEN** a displayed metric is deliberately never compared on any surface
- **THEN** its declaration records the reason, so the absence of a badge everywhere is legible as a decision

### Requirement: A ratio normalised by a window-invariant denominator discloses that denominator

Where a card divides a windowed quantity by a denominator that does not vary with the selected window, the card SHALL disclose that the denominator reflects present structure rather than the structure of the window being shown.

Under a relative delta such a denominator cancels entirely, so the badge reports the movement of the numerator alone while the label names a per-unit quantity. The figure is correct and the delta is correct; what misleads is the reader's assumption that a per-unit trend reflects movement in both terms. Applied to a past window, the division also normalises that window by a structure that may not have existed at the time.

#### Scenario: A per-unit card names the basis of its denominator

- **WHEN** a card divides windowed cost by a count taken from present organisational structure
- **THEN** the card states that the divisor is the current structure, so its delta is not read as a change in the per-unit figure
