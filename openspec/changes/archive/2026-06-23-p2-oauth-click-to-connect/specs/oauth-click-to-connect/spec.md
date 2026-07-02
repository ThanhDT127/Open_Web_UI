## ADDED Requirements

### Requirement: Middleware Database Storage for Tokens
The Middleware database SHALL store user OAuth tokens securely in a table `mw_user_integrations` and encrypt the `access_token` and `refresh_token` using AES-256 with the secret key `MW_SECRET`.

#### Scenario: Successfully storing credentials
- **WHEN** the OAuth callback exchanges a code for tokens
- **THEN** the system encrypts the tokens and saves them in the database associated with the user's subkey hash

### Requirement: OAuth Authorization Flow Endpoints
The Middleware SHALL expose a redirection endpoint `/v1/_mw/oauth/connect` to start the OAuth flow for supported providers (Google Workspace, GitHub, Microsoft Office 365) and a callback endpoint `/v1/_mw/oauth/callback` to handle the authorization response.

#### Scenario: User initiates OAuth connection
- **WHEN** the user visits `/v1/_mw/oauth/connect?provider=google_gmail&subkey=<subkey>`
- **THEN** the Middleware redirects the browser to the official Google OAuth consent screen

### Requirement: Integration Token Verification in Tools
The Custom Tools in OpenWebUI SHALL check for existing and active user OAuth connections by calling the Middleware API `/v1/_mw/integrations/get_token` with the user's subkey, and return a connection request message if the connection is missing or expired.

#### Scenario: Running Gmail Tool without active connection
- **WHEN** the user runs the Gmail Tool but has not authorized their Gmail account
- **THEN** the tool returns a markdown message showing a secure link to connect their account via `/v1/_mw/oauth/connect`
