#requires -Version 7.4

# Legacy filename retained as a fail-closed migration guard. Hermes Agent has
# no OpenClaw-compatible Node Host, pairing, or device-status-only service.
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

throw @"
OpenClaw node installation is prohibited and has been removed.

Hermes Agent is supported only as a central, operator-controlled assistant in
this prototype. Do not install an agent runtime on fleet nodes or treat Hermes
SSH access as an OpenClaw Node Host equivalent.

Keep node_exporter/GPU telemetry and workload supervision deterministic. A
restricted SSH adapter requires a separate reviewed implementation with an
approved host inventory, key policy, command allowlist, audit path, and retry
budget. Use Install-OpenClawSuperAdmin.ps1 for the central Hermes installation.
"@
