# Hermes Machine Doctor

## Outcome and boundary

The Machine Doctor pilot lets one independently installed Windows Hermes
instance explain a point-in-time machine snapshot without receiving terminal,
PowerShell, file, SSH, service-control, process-control, or unrestricted
Windows API access.

The data flow is:

```text
fixed timeout-bounded Windows probes
  -> atomic local schema-version-2 JSON snapshot
  -> existing four-tool cfmi_fleet_status MCP
  -> local Hermes explanation
```

This is not remote fleet connectivity. It installs no service, scheduled task,
listener, gateway, or automatic remediation. The operator must rerun the
collector before requesting current evidence. Computer-name binding validates
the configured local source but is not remote authentication.

## Collected evidence

The allowlisted probes collect:

- configured and observed Windows computer name;
- derived boot ID, minute-resolution last boot time, and uptime;
- logical processor count and three timestamped CPU samples;
- physical total, available, and used bytes;
- commit/pagefile limit, available, and used bytes;
- total and free bytes for explicitly configured local drive roots;
- service-manager state for one exact Azure Pipelines agent service.

An unavailable or timed-out probe produces a typed unavailable record rather
than zero or healthy evidence. No health, memory-pressure, CPU, or disk
threshold is currently approved, so the deterministic host status remains
`unknown`. A running Windows service does not prove that the pipeline agent is
responsive. Boot identity is derived from wall-clock time and `GetTickCount64`;
clock correction or drift can change it, so a changed value is not proof that a
reboot occurred.

## Inputs required before configuration

Obtain and review:

1. the exact Windows computer name;
2. a stable node ID;
3. the exact Azure Pipelines agent Windows service name;
4. the local drive roots approved for free-space collection;
5. the installed pipeline-owned Hermes home.

Do not guess or wildcard the service name. The setup fails closed on a computer
name mismatch and rejects UNC paths, arbitrary configuration fields, and
instruction-like identifiers.

For the GPU-4090 pilot, the installed Hermes home is:

```text
%LOCALAPPDATA%\cfmi-hermes-pilot-v2
```

The exact Azure Pipelines service name still needs operator confirmation before
configuration. Keep the evidence file under the Hermes-owning user's
ACL-protected profile; do not move it to a directory writable by other local
users.

The manual GPU-4090 pipeline can resolve that exact name from the Azure Agent
root `.service` marker, verify the named Windows service, and pass it to the
configuration script. It does not wildcard-enumerate services. A successful
pipeline run retains separate non-secret installation and Machine Doctor
configuration receipts.

The deployment pipeline reuses the existing pipeline-owned Hermes runtime. It
does not run pip or reinstall Hermes. Exact version, source commit, origin,
clean-checkout, editable provenance, ownership, and a prior successful receipt
must all verify before configuration begins.

## Preview

From a reviewed checkout on the target Windows machine, open a non-elevated
Windows PowerShell session under the same identity that owns Hermes:

```powershell
$computerName = [Environment]::MachineName

.\scripts\hermes\Configure-HermesMachineDoctor.ps1 `
  -NodeId "gpu-4090-pilot" `
  -ExpectedComputerName $computerName `
  -PipelineAgentServiceName "REPLACE-WITH-EXACT-SERVICE-NAME" `
  -Volumes "C:\" `
  -HermesHome "$env:LOCALAPPDATA\cfmi-hermes-pilot-v2" `
  -WhatIf
```

Review every printed value. `-WhatIf` does not copy files, collect evidence, or
change Hermes configuration.

## Configure the local pilot

After the exact service name and preview are approved, rerun without `-WhatIf`:

```powershell
.\scripts\hermes\Configure-HermesMachineDoctor.ps1 `
  -NodeId "gpu-4090-pilot" `
  -ExpectedComputerName $computerName `
  -PipelineAgentServiceName "REPLACE-WITH-EXACT-SERVICE-NAME" `
  -Volumes "C:\" `
  -HermesHome "$env:LOCALAPPDATA\cfmi-hermes-pilot-v2" `
  -Confirm
```

The script:

- copies only the reviewed collector, schema reader, MCP server, and observer
  instructions into the dedicated Hermes home;
- writes a strict local configuration;
- performs one bounded collection;
- verifies that the MCP advertises exactly four reviewed read-only tools;
- registers that local MCP with Hermes;
- limits the CLI to `clarify` and `cfmi_fleet_status`.

It does not configure provider credentials, start the gateway, enable
delegation, or alter the Azure Pipelines service.

## Refresh and query

The configuration script prints the exact collector command. Run it before
requesting current status. The equivalent installed command is:

```powershell
$hermesHome = "$env:LOCALAPPDATA\cfmi-hermes-pilot-v2"
$python = "$hermesHome\cfmi-runtime\Scripts\python.exe"
$collector = "$hermesHome\machine-doctor\tools\windows_machine_status.py"
$config = "$hermesHome\machine-doctor\machine-doctor-config.json"

& $python $collector --config $config
```

A successful collection prints a small `SUCCEEDED` record and atomically
updates:

```text
%LOCALAPPDATA%\cfmi-hermes-pilot-v2\machine-status.json
```

Then start Hermes from the configured workspace:

```powershell
$env:HERMES_HOME = $hermesHome
Set-Location "$hermesHome\workspace-local-observer"
& "$hermesHome\cfmi-runtime\Scripts\hermes.exe" chat
```

Ask:

```text
Use get_node_status for gpu-4090-pilot. Report the observation time and
freshness, then summarize physical memory, commit pressure, CPU samples, disk
free space, and pipeline-agent service state. Keep unavailable evidence and
hypotheses explicit.
```

Evidence older than 90 seconds is stale. Rerun the collector rather than asking
Hermes to execute a command.

## Remaining blockers

- No remote transport or source authentication is implemented.
- No workload progress source is configured.
- No service-responsiveness probe is approved.
- No health thresholds or automatic diagnosis decisions are approved.
- No scheduler refreshes the snapshot.
- No remediation API or action tool exists.

Connecting the central superadmin to this evidence, adding another machine, or
enabling any action requires separate review and approval.
