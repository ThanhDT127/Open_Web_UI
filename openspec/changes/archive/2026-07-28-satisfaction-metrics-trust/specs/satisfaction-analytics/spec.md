## ADDED Requirements

### Requirement: Ranking and colour coding require a minimum sample

A satisfaction score computed from a handful of votes SHALL NOT be presented as if it were comparable to one computed from many. The system SHALL define a minimum vote count below which a CSAT figure is neither ranked nor colour-coded.

The figure itself SHALL still be displayed together with its vote count, because refusing to show it would discard the only quality signal the system has. What is withheld is the *authority* of the number, not the number.

The minimum SHALL apply to every surface that ranks or colours by CSAT — currently the model leaderboard on the Satisfaction tab and the satisfaction scorecard on the Overview tab.

#### Scenario: A model below the minimum is shown but not ranked

- **WHEN** a model has fewer votes than the minimum in the selected window
- **THEN** its row appears below a separator that states the minimum, carries no rank number, and its CSAT percentage is rendered in a neutral colour

#### Scenario: A model at or above the minimum is ranked normally

- **WHEN** a model has at least the minimum number of votes
- **THEN** its row appears in the ranked tier, carries a rank number, and its CSAT percentage is colour-coded by the declared thresholds

#### Scenario: Ranking never puts a low-sample model above a high-sample one

- **WHEN** one model has 1 positive vote and another has 50 positive and 5 negative votes
- **THEN** the model with 55 votes is ranked and the model with 1 vote is not, so the 100% figure cannot outrank the 90% figure

#### Scenario: The Overview scorecard obeys the same minimum

- **WHEN** total votes across all models are below the minimum
- **THEN** the Overview satisfaction card still shows its percentage and vote count, but in a neutral state rather than a good/warning/danger state

### Requirement: Every feedback reason renders as readable text

Open WebUI adds new feedback reason values across versions. The system SHALL NOT display a raw machine identifier to the reader when it encounters a reason it has no translation for.

The translation table SHALL be treated as a preference list, not an exhaustive list: known values render in Vietnamese, and any other value SHALL be transformed into readable text rather than emitted verbatim.

#### Scenario: A known reason renders in Vietnamese

- **WHEN** feedback carries the reason `not_helpful`
- **THEN** the feed displays the Vietnamese label for it

#### Scenario: An unknown reason renders readably instead of as a raw identifier

- **WHEN** feedback carries a reason absent from the translation table, such as `followed_instructions_perfectly`
- **THEN** the feed displays it as readable text rather than the raw snake_case value, and the unknown value is logged so it can be translated later

#### Scenario: Feedback with no reason states that plainly

- **WHEN** feedback carries an empty reason
- **THEN** the feed states that no reason was given, rather than rendering an empty cell

### Requirement: CSAT is rounded once, at the point of display

The aggregation SHALL return the unrounded satisfaction ratio. Rounding SHALL happen exactly once, in the display layer, using the shared percentage formatter rather than per-call-site formatting.

Truncation SHALL NOT be used in place of rounding: truncation biases every value downward, and a value truncated in the backend cannot be recovered by any consumer.

#### Scenario: A repeating ratio is rounded, not truncated

- **WHEN** 2 of 3 votes are positive
- **THEN** the displayed figure is the rounded value, not the truncated one

#### Scenario: Every surface shows the same rounded figure

- **WHEN** the same window is viewed on the Satisfaction tab, the Overview card, and the exported Excel file
- **THEN** all three show the same rounded percentage, and none of them shows an unrounded floating-point value

### Requirement: Vote-count labels state exactly what is counted

The satisfaction total counts positive and negative votes only; it is the denominator of CSAT and SHALL NOT include feedback rows that carry neither. Every label attached to that figure SHALL say so.

The aggregation SHALL additionally report the total number of feedback rows in the window. When that total exceeds the vote count, the difference SHALL be surfaced to the reader; when the two are equal, nothing extra is shown.

#### Scenario: Labels name votes, not feedback in general

- **WHEN** the vote total is displayed on the Overview card or in the exported Excel file
- **THEN** the label identifies it as positive-and-negative votes rather than as total feedback

#### Scenario: Feedback outside the vote scale is surfaced, not silently dropped

- **WHEN** the window contains feedback rows whose rating is neither positive nor negative
- **THEN** the reader is told how many such rows exist and that they are excluded from CSAT

#### Scenario: No note appears when there is nothing to explain

- **WHEN** every feedback row in the window carries a positive or negative rating
- **THEN** no extra note is displayed

### Requirement: Rated-answer coverage counts only requests a user can rate

The system SHALL report what share of AI answers received a rating. The denominator SHALL count only requests that produce a rateable answer — chat completions — and SHALL exclude request types that carry no rating control, such as embedding calls.

The denominator SHALL be derived from the audit log rather than from Open WebUI chat records, because a user deleting a chat removes the chat but not the feedback attached to it; a denominator that erodes while the numerator does not would make coverage drift upward over time and read as improvement.

The request-counting helper SHALL live alongside the shared usage aggregation and SHALL resolve its time window through the same resolver, so that a single place defines what counts as a request.

The metric's label SHALL name answers rather than messages, because messages are not what is counted.

#### Scenario: Embedding traffic is excluded from the denominator

- **WHEN** a window contains both chat completions and embedding requests
- **THEN** the coverage denominator counts only the chat completions

#### Scenario: Coverage does not exceed the count of rateable answers

- **WHEN** coverage is computed for any window
- **THEN** the denominator is less than or equal to the total request count reported by the shared usage aggregation, and the two are not required to be equal

#### Scenario: Feedback on a deleted chat still counts

- **WHEN** a user deletes a chat that contains a rated answer
- **THEN** the rating remains in the numerator and the corresponding request remains in the denominator, so coverage does not move as a result of the deletion

#### Scenario: The two time bases are labelled distinctly

- **WHEN** coverage is displayed
- **THEN** the label makes clear that ratings are counted by when they were given, which is a different clock from when the answer was produced

### Requirement: Satisfaction aggregation is a pure function that fails loudly

The satisfaction aggregation SHALL be exposed as a pure function taking a resolved time window, separate from the HTTP handler. Consumers other than the HTTP layer — notably the report export — SHALL call the pure function.

A failure to read feedback data SHALL propagate. It SHALL NOT be converted into an empty result, because an empty result is indistinguishable from "nobody has rated anything" and would let an incomplete report be delivered as though it were complete.

#### Scenario: The export calls the aggregation directly

- **WHEN** the Excel report is generated
- **THEN** it obtains satisfaction data from the pure function rather than by invoking the HTTP handler

#### Scenario: A data failure stops the report instead of emptying a sheet

- **WHEN** the feedback query fails while an Excel report is being generated
- **THEN** the request fails with an error, and no file is produced containing a satisfaction sheet full of zeros
