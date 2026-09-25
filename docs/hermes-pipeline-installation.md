# Unattended Hermes pipeline installation

**Outcome:** Install the reviewed pinned Hermes runtime and safety defaults on
one pre-approved Windows target without an interactive desktop login.

**Important:** A successful job means **staged**, not connected or ready.
The job does not authenticate GitHub Copilot, start Hermes, install a gateway
service, register a fleet node, configure remote communication, or copy
credentials.

The explicitly approved `ORT-GPU-BENCH-5` pilot additionally configures the
local read-only Machine Doctor MCP. It resolves the exact Windows service name
from the Azure Agent root `.service` marker, performs one point-in-time
collection, verifies the four-tool MCP surface, and publishes a non-secret
configuration receipt. This is local machine evidence, not remote fleet
connectivity. The pipeline does not schedule refreshes, enable remediation, or
change existing provider credentials.

After the initial successful Hermes installation, the Machine Doctor deployment
does not invoke pip again. It requires the matching pipeline-ownership marker
and a prior successful receipt, then verifies the exact Git origin, clean pinned
commit, editable `direct_url.json` provenance, executable, and reported version.
Any mismatch blocks deployment and requires separately reviewed repair; it does
not trigger automatic reinstallation.

The YAML has a default-off `repairHermesPackage` parameter for a separately
approved recovery from an interrupted pip uninstall. When explicitly enabled,
it verifies the same ownership, prior-success, identity, clean source, origin,
and commit boundaries, then restores only the editable Hermes package with
`--no-deps`. It writes a durable repair receipt and performs the complete
version/provenance verification afterward. Normal runs leave this parameter
false and never invoke pip.

## CPU architecture support

Both common 64-bit Windows architectures are supported by this pipeline:

| Target | Pipeline decision |
|---|---|
| Intel/AMD `x86_64` / `AMD64` Windows with 64-bit AMD64 Python | Supported |
| Windows ARM64 with native 64-bit ARM64 Python | Supported |
| Legacy 32-bit `x86` Windows | Rejected |
| 64-bit Windows with 32-bit Python | Rejected |
| Emulated PowerShell or mismatched Python architecture | Rejected |
| Linux | Not supported by this Windows pipeline script |

People often say “x86” when they mean a modern Intel or AMD laptop. Confirm
that the operating system and Python are **64-bit AMD64**, not 32-bit x86. The
script checks the OS, PowerShell process, and Python architectures before
changing the machine and records them in the installation receipt.

## Why identity is mandatory

Hermes configuration and provider authentication are identity-scoped. A
self-hosted pipeline agent commonly runs as a service account, `SYSTEM`, or a
different user from the person who later opens the laptop. Installing under the
wrong identity puts Hermes in the wrong profile and can create misleading
success.

The script therefore requires `-ExpectedWindowsIdentity` and fails before
installation unless it exactly matches the current Windows principal. Decide
which approved account will own and run Hermes on each machine before
deployment.

## Pipeline script

Use:

```powershell
.\scripts\hermes\Install-HermesPipeline.ps1
```

It performs these bounded actions:

- verifies Windows and the expected run identity;
- accepts native 64-bit AMD64 or ARM64 and rejects mismatched/32-bit runtimes;
- creates an isolated environment in the selected Hermes home;
- installs Hermes Agent `0.21.5` from commit
  `749220ef0007f8d87bd1531f1c24b0fe93816385`;
- verifies installed version and VCS provenance;
- applies manual approval and deny-on-cron, deny-on-one-shot, and
  deny-on-unattended defaults;
- creates the restrictive local observer workspace;
- refuses to reuse a nonempty Hermes home unless it carries a matching
  pipeline-ownership marker;
- writes a non-secret durable per-attempt receipt under
  `installation-attempts`;
- preserves failed attempt evidence and returns a nonzero exit code.

It does not write `.env`, `auth.json`, provider tokens, or messaging
credentials. It never starts or installs the gateway.

## Preview on one target

Run the preview under the same self-hosted agent identity that the deployment
job will use:

```powershell
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name

powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\hermes\Install-HermesPipeline.ps1 `
  -ExpectedWindowsIdentity $identity `
  -HermesHome "$env:LOCALAPPDATA\cfmi-hermes-pilot-v2" `
  -WhatIf
```

Review the identity and Hermes home printed by the preview. Do not accept an
unexpected service account or profile path.

## Azure Pipelines example

This example deliberately targets one named, pre-approved self-hosted Windows
agent. Use a protected branch, environment approval, and a trusted pipeline;
never run untrusted pull-request code on the target.

```yaml
parameters:
- name: targetAgent
  type: string

pool:
  name: Approved-Hermes-Pilot
  demands:
  - Agent.Name -equals ${{ parameters.targetAgent }}

steps:
- checkout: self
  persistCredentials: false

- powershell: |
    .\scripts\hermes\Install-HermesPipeline.ps1 `
      -ExpectedWindowsIdentity "$(HermesRunAsIdentity)" `
      -AgentId "local-observer" `
      -HermesHome "$env:LOCALAPPDATA\cfmi-hermes-pilot-v2" `
      -Confirm:$false
  displayName: Stage pinned Hermes runtime
```

`HermesRunAsIdentity` is not a password. Set it to the exact expected
`DOMAIN\account` or `MACHINE\account` value for that agent service. The script
does not accept a password or token.

Do not use a matrix, wildcard demand, discovery query, or all-agent fan-out for
the first deployment. Run one non-actuating bench machine, inspect its receipt,
and review the result before selecting another target.

## AIFoundryLocal GPU-4090 pilot

The repository includes
`.pipelines/hermes-gpu4090-pilot.yml` for one manual pilot:

- organization/project: `aiinfra.visualstudio.com/AIFoundryLocal`;
- queue: `FoundryLocal-GPU-4090`;
- exact agent demand: `ORT-GPU-BENCH-5`;
- expected Windows identity: `NORTHAMERICA\ruiren`;
- architecture: native AMD64 Windows, PowerShell, and Python;
- dedicated pipeline-owned home:
  `%LOCALAPPDATA%\cfmi-hermes-pilot-v2`;
- triggers: disabled for commits and pull requests;
- output: one non-secret installation receipt artifact.

The pool inspection on 2026-09-25 found `ORT-GPU-BENCH-5` online and
`ORT-GPU-BENCH-6` offline. Do not remove the exact agent demand or redirect the
pilot to the offline machine.

Before creating or running the definition, remove secrets from agent system
capabilities and rotate any value that was previously exposed there. Agent
capabilities are pool metadata, not an approved secret store. The pilot must
not run untrusted pull-request code on this credentialed self-hosted pool.

The current repository is hosted on GitHub, while the example
`FoundryLocal-Diomedes-CUDA` definition uses the unrelated `test-results`
Azure Repos repository. Creating the Hermes definition therefore requires an
approved GitHub service connection for
`rui-ren/Continuous-Foundation-Model-Integration`; do not point the pipeline at
`test-results` merely to reuse definition 2331.

The pilot agent does not have `pwsh.exe`, and its network path returned altered
bytes for the official portable PowerShell release. The pipeline does not
bypass that control or relax the digest. Instead, only the unattended pipeline
installer and its shared package module support the agent's built-in Windows
PowerShell 5.1. The interactive installer and observer configurator retain
their PowerShell 7.4 requirement. The pipeline does not modify PowerShell,
PATH, Windows services, or registry settings.

Hermes' pinned source rejects wheel/sdist builds by design. The installer
therefore maintains a dedicated source checkout under the pipeline-owned home,
verifies the exact Git origin and commit, requires a clean checkout, installs
it editable with the approved Python environment, and verifies editable
`direct_url.json` provenance. A failed run updates the ownership marker and
attempt receipt to `FAILED`, allowing a later reviewed retry without deleting
failure evidence.

## Generic PowerShell pipeline step

For another trusted orchestration system:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\hermes\Install-HermesPipeline.ps1 `
  -ExpectedWindowsIdentity "DOMAIN\approved-hermes-service" `
  -AgentId "local-observer" `
  -HermesHome "$env:LOCALAPPDATA\cfmi-hermes-pilot-v2" `
  -Confirm:$false
```

The checkout must have access to the approved Python index and the pinned
upstream Git commit. Windows PowerShell 5.1, Python 3.11-3.13, and Git must
already be installed. The script does not alter drivers, system Python,
machine-wide Git configuration, firewall rules, or Windows services.

## Pipeline acceptance evidence

Collect the job log and the new JSON receipt from:

```text
<HermesHome>\installation-attempts\<attempt-id>.json
```

Required receipt fields:

- `status` is `SUCCEEDED`;
- `windows_identity` matches the approved account;
- `os_architecture`, `powershell_process_architecture`, and
  `python_architecture` are matching `X64`/`AMD64` or `Arm64`/`ARM64` values;
- `python_bits` is `64`;
- `hermes_version` is `0.21.5`;
- `hermes_commit` is
  `749220ef0007f8d87bd1531f1c24b0fe93816385`;
- `provider_configuration_action` is `not_managed_by_pipeline`;
- `gateway_action` is `not_started_by_pipeline`;
- `fleet_connectivity_action` is `not_configured_by_pipeline`.

The final three fields record only what this pipeline did. They do not certify
the absence of provider credentials, another Hermes installation, or an
independently configured gateway elsewhere on the machine.

## Provider authentication limitation

The current central machine uses GitHub Copilot with `gpt-5.6-sol`. Its OAuth
login is interactive and user-scoped. This pipeline must not copy the central
machine's auth files or token to other laptops.

Without an approved non-interactive provider identity, each staged installation
cannot answer model requests. Resolving that requires a separate security and
licensing decision, such as an organization-approved machine/service identity
or provider credential delivered through an approved secret store. Do not add
such a secret to YAML, command-line arguments, source control, installation
receipts, or fleet evidence.

## Fleet limitation

Running this job on several machines produces several independent dormant
installations. It does not make them subagents, connect them to the superadmin,
or publish telemetry. The proposed read-only communication path remains:

```text
machine exporter -> authenticated collector -> fleet-status.json
                 -> local MCP -> superadmin Hermes
```

See [Hermes fleet communication design](hermes-fleet-communication.md) before
implementing any node transport. Do not enable SSH, terminal, A2A, messaging,
gateway services, or remote commands as a shortcut.

## Reinstallation

The script is idempotent and revalidates the pinned source. A reviewed repair
may add `-Force` to reinstall dependencies. Every invocation creates a new
attempt receipt so earlier success and failure evidence remains available.

The version and commit are source-controlled constants, not pipeline
parameters. Changing either is a repository change requiring review and CPU
checks.
