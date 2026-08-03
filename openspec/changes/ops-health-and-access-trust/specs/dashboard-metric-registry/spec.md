## ADDED Requirements

### Requirement: The HTTP latency percentile is declared separately from the model latency percentile

The access tab's latency percentile SHALL be declared under its own registry key, with a label that names the HTTP layer, and SHALL NOT reuse the key already serving the model-latency percentile.

The two payloads expose a field of the same name, but they measure different things: one is the time an upstream model took to answer, the other is the duration of every HTTP request the service handled, static dashboard assets included. Sharing a registry entry would give both a single label, so two tabs would present two quantities under one name — the defect this project removed from the request-count labels.

#### Scenario: Two latency figures never share a name

- **WHEN** the access tab and the usage tab both display a latency percentile
- **THEN** each carries a label naming what it measures, and the two labels are distinct

### Requirement: Operational metrics are declared in the shared registry

The refusal rate, the rejected dashboard sign-in count, the process runtime and the free-disk figure SHALL each be declared in the shared metric registry, alongside the formatter, comparison behaviour and polarity that govern them.

The process runtime and the free-disk figure SHALL declare that period comparison does not apply to them. Neither is scoped to the selected window: one is measured from the most recent process start and the other is an instantaneous reading, so a delta against a previous window would compare a figure to itself.

The refusal rate SHALL NOT declare colour bands until an agreed threshold exists. Colour is a verdict, and no one has yet stated what proportion of refusals is acceptable for this deployment. This follows the treatment already given to the cost-concentration and knowledge-coverage figures.

#### Scenario: Inventory-style figures carry no period badge

- **WHEN** the process runtime or the free-disk figure is rendered
- **THEN** no period-comparison badge accompanies it

#### Scenario: The refusal rate is presented without a verdict

- **WHEN** the refusal rate is rendered
- **THEN** its value is shown without threshold colouring

### Requirement: The spend-anomaly threshold is declared once

The minimum series length required before a spend anomaly may be reported SHALL be declared in the shared registry, using the same minimum-sample mechanism that governs the satisfaction and citation figures.

Declaring it beside the code that renders the alert would recreate the duplicated thresholds this project has twice consolidated into the registry.

#### Scenario: The threshold has one declaration

- **WHEN** the minimum series length is changed
- **THEN** the change is made in the registry and no rendering code carries its own copy
