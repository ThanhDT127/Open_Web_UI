## ADDED Requirements

### Requirement: CRUD Operations for Model Prices
QTV SHALL be able to view, add, edit, and delete pricing configurations for LLM models.

#### Scenario: View model prices list
- **WHEN** QTV opens the Prices tab on the Dashboard
- **THEN** the system SHALL fetch the pricing configuration list via `/v1/_mw/admin/prices` and render it in a clean table showing model name, input cost (per 1M tokens), output cost (per 1M tokens), image cost, and notes.

#### Scenario: Add a new model pricing
- **WHEN** QTV fills out the Add Pricing modal with valid fields (model name, input price per 1M, output price per 1M, image cost, notes) and clicks Save
- **THEN** the system SHALL send a POST request to `/v1/_mw/admin/prices` to insert the model's pricing into the database, rewrite the backup file `prices.json`, and refresh the table view.

#### Scenario: Edit an existing model pricing
- **WHEN** QTV modifies pricing fields in the Edit Pricing modal and clicks Save
- **THEN** the system SHALL send a POST request to `/v1/_mw/admin/prices` with the updated fields, update the database and backup file `prices.json`, and refresh the table view.

#### Scenario: Delete a model pricing
- **WHEN** QTV clicks Delete on a model price entry and confirms the deletion
- **THEN** the system SHALL send a DELETE request to `/v1/_mw/admin/prices/{model_name}`, remove the entry from both database and backup file `prices.json`, and refresh the table view.
