# Hermes Microsoft Teams bot

## Current state

The central Hermes observer has the bundled Microsoft Teams adapter, but the
gateway is stopped and no Teams identity exists. The Microsoft tenant requires
every Entra application to carry a valid Service Management Reference (SMR).
The `ruiren-dev` resource group has no SMR metadata and the current user owns no
application from which a legitimate reference can be inferred.

Do not invent an SMR, use an unrelated service's identifier, expose a developer
tunnel, or create a public endpoint directly to the laptop. These would bypass
the tenant's ownership and ingress controls.

## Required approvals and inputs

Obtain these values before provisioning:

1. The Service Tree/asset identifier whose owners accept responsibility for
   the CFMI Hermes observer.
2. An approved, stable HTTPS endpoint ending in `/api/messages`.
3. Confirmation that `ruiren-dev` is the approved resource group for the free
   Azure Bot registration.
4. Teams administrator approval for the custom app package and its
   `personal`/`groupChat` scopes.
5. The Teams user IDs or UPNs allowed to use the bot.

The messaging endpoint must terminate through managed ingress with TLS,
authentication/validation, monitoring, and an owner. A laptop-only Hermes
process is not directly reachable by Teams.

## Provisioning

After the prerequisites are approved:

```powershell
.\scripts\hermes\New-HermesTeamsBot.ps1 `
  -ServiceManagementReference "<approved-service-tree-id>" `
  -MessagingEndpoint "https://<approved-host>/api/messages"
```

The script:

- creates a single-tenant Entra application with the supplied SMR;
- creates a one-year client secret and stores it only in the local Hermes
  `.env` file without printing it;
- creates an `F0` Azure Bot registration in `ruiren-dev`;
- enables the Microsoft Teams channel;
- limits Teams to the configured user, requires mentions, and disallows
  allow-all access; and
- keeps the Hermes gateway stopped and bound to loopback.

The script is idempotent for existing resources. Secret rotation requires an
explicit `-RotateSecret`. Existing applications and bots must exactly match the
approved SMR, single-tenant identity, `F0` SKU, and endpoint or the script fails
closed. A newly created secret is stored before later Azure operations, so a
partial failure does not lose the credential. Use `-WhatIf` to inspect the full
intended operation sequence.

## Remaining Teams app package

After the Azure Bot exists, create an organization-owned Teams app package
whose bot ID is the Entra application ID and whose scopes include `personal`
and `groupChat`. The package also needs approved publisher, privacy, terms, and
icon assets. Submit it through the Teams admin process; do not sideload it into
the production tenant without approval.

Only after managed ingress and the app package are approved should an operator
start the Hermes gateway. The Teams tool surface remains restricted to
`clarify` and the read-only `cfmi_fleet_status` MCP.
