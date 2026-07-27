## MODIFIED Requirements

### Requirement: API Budget Management

The system SHALL allow administrators to manage prepaid credit per **billing account** (the account actually invoiced: `openai`, `gemini`, `vertex_ai`, `anthropic`, `xai`, `openrouter`), NOT a monthly USD cap per model brand. For each billing account the Settings tab SHALL expose a credit amount and two distinct actions:

- **Top up ("Nạp thêm")**: records a new deposit of `amount` — the system SHALL set the credit baseline to the account's **current `remaining` plus `amount`** (carrying the unspent balance forward, never double-counting past spend) and set `funded_at` to the current time, which restarts the spent-since-funding accounting from zero.
- **Correct ("Sửa")**: fixes a mistyped credit amount — the system SHALL update the amount but SHALL preserve the existing `funded_at`, so a correction is not treated as a new deposit.

The persisted configuration SHALL be used both to monitor provider credit exhaustion (alert CHECK 2) and to render the Providers tab, from a single shared source.

#### Scenario: Admin tops up a billing account

- **WHEN** an administrator enters an amount for a billing account (e.g. OpenRouter) and clicks "Nạp thêm"
- **THEN** the system carries the account's current `remaining` forward, adds the entered amount to form the new `deposited` baseline, stamps `funded_at = now`, and spent-since-funding restarts from zero

#### Scenario: Admin corrects a mistyped amount

- **WHEN** an administrator fixes the credit number for an account and clicks "Sửa"
- **THEN** the system updates the amount but leaves `funded_at` unchanged, so the correction is not counted as a new deposit

#### Scenario: Providers list matches billing accounts

- **WHEN** an administrator opens the provider budget section
- **THEN** the fields shown are the billing accounts (`openai`, `gemini`, `vertex_ai`, `anthropic`, `xai`, `openrouter`), not the model brands
