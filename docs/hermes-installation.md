# Reproducing the Hermes Agent configuration

This runbook reproduces the reviewed Hermes Agent configuration on a Windows
machine where a human operator logs in and runs Hermes locally. Each
installation is independent. Installing Hermes on several machines does not
pair them, create a fleet, enable remote control, or let one Hermes instance
control another.

The implemented fleet topology still uses one central read-only observer over
operator-supplied evidence. Do not use this runbook as an unattended fleet
deployment or replace deterministic telemetry and workload supervisors with
per-node agents.

The proposed communication path is documented in
[Hermes fleet communication design](hermes-fleet-communication.md). It uses
authenticated deterministic exporters and a collector, not direct
Hermes-to-Hermes conversation.

## Installed configuration

The repository installer:

- creates an isolated virtual environment under
  `%LOCALAPPDATA%\hermes\cfmi-runtime`;
- installs Hermes Agent `0.21.5` from upstream commit
  `749220ef0007f8d87bd1531f1c24b0fe93816385`;
- verifies the installed version and VCS provenance;
- configures manual command approval and denies cron, one-shot, and unattended
  approvals;
- creates a local observer workspace with restrictive `AGENTS.md`
  instructions;
- does not collect model credentials, start a gateway, install a background
  service, or enable terminal, file, browser, SSH, or computer-use tools.

The optional observer configurator adds the local read-only
`cfmi_fleet_status` MCP and bounded temporary subagents. Its four tools can read
an approved fleet evidence file and this machine's physical-memory counters.
It cannot execute commands or connect to other machines.

## Prerequisites

Use an approved repository checkout and a normal, non-elevated PowerShell
session. Confirm all of the following on every machine:

- Windows with PowerShell 7.4 or newer;
- Python 3.11, 3.12, or 3.13 available as `python`;
- Git available to pip;
- access to the approved Python package index and the pinned upstream GitHub
  commit;
- this repository checked out locally.

From the repository root, inspect the prerequisites:

```powershell
$PSVersionTable.PSVersion
python --version
git --version
git --no-pager status --short
```

Do not copy `%LOCALAPPDATA%\hermes` from another machine. It may contain
machine-local configuration and provider credentials.

## Install one local instance

First preview the operation:

```powershell
pwsh -NoProfile -File .\scripts\openclaw\Install-OpenClawSuperAdmin.ps1 `
  -AgentId local-observer `
  -WhatIf
```

The `openclaw` directory and script name are retained for compatibility. The
script installs Hermes only; it does not install or invoke OpenClaw.

Run the reviewed pinned installation and approve the PowerShell confirmation:

```powershell
pwsh -NoProfile -File .\scripts\openclaw\Install-OpenClawSuperAdmin.ps1 `
  -AgentId local-observer
```

Define the installed executable for the rest of the session and verify it:

```powershell
$hermes = "$env:LOCALAPPDATA\hermes\cfmi-runtime\Scripts\hermes.exe"
& $hermes --version
```

The output must report `v0.21.5`. A different or missing version is a failed
installation, not an acceptable fallback.

## Configure the model provider

Provider authentication is interactive and local to each machine:

```powershell
& $hermes setup
```

Select only an organization-approved provider. The current central machine uses
the GitHub Copilot provider with `gpt-5.6-sol`. To reproduce that selection,
run the interactive model picker after setup:

```powershell
& $hermes model
& $hermes status
```

Select **GitHub Copilot** and **gpt-5.6-sol**, then confirm that `hermes status`
reports both values. Model availability and authorization are determined by
the account used on that machine; do not substitute a fallback and report it
as equivalent. The installer does not copy the current machine's login or any
token. Never paste provider credentials into documentation, source control,
chat, or a fleet evidence file. Do not use `--insecure` to work around TLS or
corporate network failures.

Start the minimum local profile from its observer workspace:

```powershell
Set-Location "$env:LOCALAPPDATA\hermes\workspace-local-observer"
& $hermes chat --toolsets clarify
```

At this point Hermes is a local interactive assistant. Stop here on machines
that do not need the read-only CFMI observer tools.

## Add the read-only observer profile

Run this section only on a machine intended to inspect approved CFMI evidence
or report its own physical-memory counters:

```powershell
Set-Location <path-to-Continuous-Foundation-Model-Integration>
pwsh -NoProfile -File .\scripts\hermes\Configure-HermesFleetObserver.ps1 `
  -HermesExecutable $hermes
```

The script validates the exact four-tool MCP surface before registering it. A
missing `%LOCALAPPDATA%\hermes\fleet-status.json` is expected until an approved
exporter supplies evidence; fleet queries must then return
`RESOURCE_UNAVAILABLE`.

Verify the configuration:

```powershell
& $hermes mcp test cfmi_fleet_status
& $hermes tools list --platform cli
& $hermes gateway status
& $hermes -z "What is the memory usage on this machine?"
```

Expected results:

- MCP discovery reports exactly `list_nodes`, `get_node_status`,
  `get_job_progress`, and `get_local_system_status`;
- CLI toolsets contain `clarify`, `delegation`, and
  `cfmi_fleet_status`;
- terminal, file, browser, cron, messaging administration, and computer-use
  remain disabled;
- the gateway reports that it is not running;
- the memory question reports live local physical-memory evidence.

## Machine-by-machine checklist

Record non-secret deployment evidence for each manually installed machine:

| Check | Required result |
|---|---|
| Machine owner and purpose reviewed | Recorded outside the repository |
| Installer preview | No unexpected paths or actions |
| Hermes version | `0.21.5` |
| Upstream commit | `749220ef0007f8d87bd1531f1c24b0fe93816385` |
| Provider and model | GitHub Copilot and `gpt-5.6-sol`, configured locally |
| Broad toolsets | Disabled |
| Gateway/background service | Stopped/not installed |
| Local memory query | Live evidence, if observer profile is configured |
| Fleet query without evidence | `RESOURCE_UNAVAILABLE`, not healthy |

Use a separate local login and provider authorization appropriate for each
machine. Do not share `%LOCALAPPDATA%\hermes\.env`, model-provider tokens, SSH
keys, or messaging credentials between machines.

## Reinstallation and updates

Rerunning the installer revalidates the pinned source. Use `-Force` only when a
reviewed repair requires reinstalling dependencies:

```powershell
pwsh -NoProfile -File .\scripts\openclaw\Install-OpenClawSuperAdmin.ps1 `
  -AgentId local-observer `
  -Force
```

Do not substitute a newer release, tag, branch, or unreviewed commit at
deployment time. Updating Hermes requires changing both the pinned version and
commit in the repository, reviewing the diff, and rerunning the CPU checks.

## Explicit limitations

- There is no Hermes Node Host, pairing protocol, fleet discovery, or remote
  command channel in this repository.
- Installing Hermes on every machine does not make the central observer aware
  of those machines.
- The repository does not provide automated rollout, upgrade orchestration,
  credential distribution, or uninstall automation.
- CPU checks validate repository contracts and scripts; they do not certify GPU
  operation, remote fleet acceptance, or robot control.
