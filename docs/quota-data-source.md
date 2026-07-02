# Quota Data Source

PostgreSQL `mw_users` is the runtime source of truth for quota limits, period
usage, resets, dashboard values, and alerts. Request-time code must use targeted
single-user database operations and must not rewrite the complete user list.

`llm-mw/users.json` is a generated recovery snapshot. Refresh it explicitly:

```powershell
python scripts/snapshot_middleware_users.py
```

To compare persisted quota values with the quota-status projection and recent
alert snapshots:

```powershell
python scripts/diagnose_quota_consistency.py
```

For the June 3, 2026 `adminrd` alert, the committed limit was `0.008 USD`. The
old alert formatter displayed it as `$0.01`; a dashboard displaying `$10` did
not represent the committed middleware quota record.
