## ADDED Requirements

### Requirement: Interactive Cost Simulator and Comparison
The dashboard SHALL provide a visual simulator where QTV can input expected prompt and completion token counts and see relative simulated costs across models.

#### Scenario: Render cost comparison chart
- **WHEN** QTV views the Cost Comparison panel and modifies the simulated Input/Output token counts
- **THEN** the system SHALL dynamically calculate the simulated cost for each model using the formula: `cost = (input_tokens * input_per_1m / 1,000,000) + (output_tokens * output_per_1m / 1,000,000)`, sort models from cheapest to most expensive, and render visual progress bars representing their relative costs.
