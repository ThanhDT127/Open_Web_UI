# Unified User Identity

Open WebUI owns interactive login identities. Its immutable user UUID is the
canonical identity for interactive requests. Middleware stores that UUID in
`mw_users.openwebui_user_id` and continues to own subkeys, model access, quota,
and billing usage.

Middleware supports only `admin` and `user`. Open WebUI `pending` remains an
onboarding state and cannot be mapped until approved.

Open WebUI forwards `X-OpenWebUI-User-Id` when
`ENABLE_FORWARD_USER_INFO_HEADERS=true`. Middleware trusts that header only
when the Bearer token matches `OPENWEBUI_SERVICE_KEY`. Direct subkeys remain
valid and charge the same mapped middleware record.

Use the admin reconciliation endpoint before mapping users:

```text
GET /v1/_mw/admin/users/reconciliation
PUT /v1/_mw/admin/users/{user_id}/openwebui-mapping
```

Reconciliation is read-only. Mapping is explicit and audited. Future SSO/SCIM
provisioning must create or approve the Open WebUI account first, then perform
an explicit middleware mapping and quota assignment.
