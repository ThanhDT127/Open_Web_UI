## Why

Open WebUI and the middleware currently maintain separate user records without a reliable identity mapping. Open WebUI has the login account and group membership, while the middleware has the subkey, model access, and quota; this prevents safe SSO onboarding, group quotas, and accurate user administration.

The dashboard also exposes `admin`, `manager`, and `user`, but middleware persistence does not reliably store the role. The requested role model is simpler: only `admin` and `user`.

## What Changes

- Define the Open WebUI user UUID as the canonical identity for interactive users.
- Add an explicit mapping between Open WebUI users and middleware quota/access records.
- Provide a reconciliation process that reports unmatched, duplicate, missing, and disabled users without silently deleting data.
- Allow middleware users to retain API subkeys while associating those credentials with the canonical user identity.
- Simplify dashboard and middleware roles to only `admin` and `user`.
- Migrate existing `manager` records to `user`.
- Persist roles correctly in the middleware database and expose the persisted value through admin APIs.
- Prepare a supported provisioning path for future SSO/SCIM users without implementing SSO in this change.
- Protect user quota lookup so a user cannot request another user's quota by supplying an arbitrary user ID.

## Capabilities

### New Capabilities

- `unified-user-identity`: Mapping, reconciliation, and provisioning contract between Open WebUI users and middleware users.
- `simplified-user-roles`: Persisted two-role model using only `admin` and `user`.

### Modified Capabilities

<!-- No existing capability requirement is modified. -->

## Impact

- Affected middleware modules: user schema and migrations, authentication, user admin APIs, quota status API, dashboard users tab.
- Affected Open WebUI integration: read access to Open WebUI user identity and future SSO/SCIM provisioning hooks.
- Existing middleware users and subkeys require a controlled migration and reconciliation report.
- This change establishes the foundation for later SSO, department/group quota, and group analytics changes.
