## ADDED Requirements

### Requirement: A metric may declare a minimum sample without declaring colour bands

A metric SHALL be able to declare a minimum sample size independently of whether it declares colour bands. The minimum is used to caption a thin window and to withhold a period comparison, neither of which requires a threshold of good and bad.

Where nobody has stated what value of a metric is acceptable, the metric SHALL NOT be given bands. A colour is a verdict, and inventing one publishes a judgement no one authorised.

#### Scenario: A metric with a minimum but no bands is never coloured

- **WHEN** a metric declares a minimum sample and no bands
- **THEN** its value is displayed without an accent at any sample size, and the minimum still governs its caption and its comparison badge

#### Scenario: Thresholds shared with backend logic are declared once

- **WHEN** a band edge corresponds to a threshold the backend also applies
- **THEN** the two carry the same value, so the card and the backend classification cannot drift apart

### Requirement: Withholding a comparison is distinguishable from an empty period

The registry SHALL expose a way to remove a card's comparison badge without drawing one. Rendering an empty badge states that the compared periods held no data; withholding the comparison because the current window is below the metric's minimum sample is a different statement, and the card's own caption already carries it.

Two different reasons SHALL NOT share one rendering.

#### Scenario: A below-minimum window shows no badge at all

- **WHEN** the current window's sample is below the metric's minimum
- **THEN** the card carries no comparison badge, rather than a badge reading as though the compared periods were empty

#### Scenario: A previously drawn badge does not survive

- **WHEN** a card is re-rendered into a state that withholds its comparison
- **THEN** any badge drawn for an earlier window is removed
