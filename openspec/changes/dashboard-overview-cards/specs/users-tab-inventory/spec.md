## ADDED Requirements

### Requirement: Total Users inventory card

The Users tab SHALL display a Total Users card showing the count of non-deleted accounts in `mw_users`. The card SHALL reuse the data already loaded by the Users tab (`loadUsers`) and MUST NOT introduce a new backend endpoint. It coexists with the status badge and is retained per leader requirement even though the badge also surfaces the total.

#### Scenario: Total Users card reflects account count

- **WHEN** the Users tab loads
- **THEN** the Total Users card shows the number of non-deleted accounts, sourced from the same data as the user table

### Requirement: Vietnamese status badge

The Users tab status badge SHALL read `Đang bật: X · Tổng: Y`, where `X` is the count of non-disabled accounts (unchanged semantics: `active !== false`) and `Y` is the total account count. The label MUST NOT be changed to "Đã dùng" (used), because the underlying count is enabled-status, not actual-usage — relabeling it as usage would misrepresent the number.

#### Scenario: Badge shows enabled and total counts

- **WHEN** the Users tab loads
- **THEN** the badge displays `Đang bật: <non-disabled count> · Tổng: <total count>` with the numeric values unchanged from current behavior
