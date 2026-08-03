## ADDED Requirements

### Requirement: Classification thresholds are declared in the registry

Where a metric is classified into bands for display — good/warning/danger colouring, or a minimum sample below which the value is not ranked — those thresholds SHALL be declared in the central registry alongside that metric's label, format and polarity.

Display modules SHALL read the thresholds from the registry. They SHALL NOT restate threshold values inline, because a threshold restated in two modules is a threshold that will eventually disagree with itself, and the disagreement is invisible: the two surfaces are on different tabs and are never seen side by side.

#### Scenario: One metric shown on two tabs classifies identically

- **WHEN** the same metric is displayed on two different tabs
- **THEN** both surfaces derive their band boundaries from the one registry entry, so they cannot classify the same value differently

#### Scenario: Changing a threshold touches one place

- **WHEN** a metric's band boundary is changed
- **THEN** the change is made in the registry entry alone, and every surface showing that metric picks up the new boundary without further edits

#### Scenario: A minimum-sample threshold is declared like any other

- **WHEN** a metric requires a minimum number of observations before it may be ranked or coloured
- **THEN** that minimum is declared in the registry entry rather than in the module that renders the table
