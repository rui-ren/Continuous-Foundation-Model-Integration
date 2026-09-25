# Read-only fleet status MCP

## Outcome and boundary

This slice gives the central Hermes observer four local, read-only tools:

- `list_nodes`
- `get_node_status`
- `get_job_progress`
- `get_local_system_status`

The server is a local stdio subprocess. It opens no listening port, authenticates
to no node, executes no command, and exposes no mutation tool. It does not
collect telemetry itself. Exporters or an approved aggregation process must
write fleet evidence atomically. `get_local_system_status` reads only physical
memory counters from the superadmin host through the operating-system API.

This is not a fleet controller, scheduler, discovery service, dashboard, or
runtime diagnosis agent. It does not authorize connecting all machines.

## Evidence contracts

The reader continues to accept the original UTF-8 JSON `schema_version: 1`
contract:

```json
{
  "schema_version": 1,
  "source": "approved-aggregator",
  "nodes": [
    {
      "node_id": "bench-node-01",
      "observed_at": "2026-09-24T20:00:00Z",
      "reachability": {"status": "reachable"},
      "host": {"status": "healthy"},
      "workloads": [
        {
          "workload_id": "inference-a",
          "status": "running",
          "observed_at": "2026-09-24T20:00:00Z",
          "progress": {"completed_requests": 120}
        }
      ]
    }
  ]
}
```

Allowed reachability states are `reachable`, `unreachable`, and `unknown`.
Allowed host states are `healthy`, `warning`, `critical`, and `unknown`.
Allowed workload states are `queued`, `running`, `succeeded`, `failed`,
`blocked`, `paused`, and `unknown`.

`observed_at` must include a timezone. Evidence at most 90 seconds old is
reported as `live`; older evidence is `stale`; a missing timestamp is `missing`.
A timestamp more than five seconds in the future is invalid rather than fresh.
A missing/unreadable/invalid file produces an explicit tool error and is never
represented as an empty healthy fleet.

The sample at `examples/fleet-status.sample.json` is labeled
`sample-only-not-live` and must not be used as operational evidence.

Schema version 2 adds one strict local Windows Machine Doctor node. Its source
must be `local-windows-machine-doctor`; `source_identity` binds the configured
node ID and expected computer name to the observed local name. The node's
`host.machine` object has six required sections:

- `identity`;
- `boot`;
- `cpu`;
- `memory`;
- `disks`;
- `service`.

Each probe section is either `available` with typed raw evidence or
`unavailable` with a category and sanitized reason. CPU evidence requires at
least three timestamped utilization samples. Memory retains physical and
commit/pagefile byte counters; disk evidence covers only configured local drive
roots. A service-manager `running` state is not a responsiveness claim.

The pilot does not define health thresholds, so version-2 `host.status` remains
`unknown` with reason `thresholds_not_approved`. Workload evidence is explicitly
unavailable until an approved source exists. Unknown version-2 fields and
unknown schema versions are rejected. Version 1 behavior remains unchanged.

## Run and test locally

```powershell
$env:CFMI_FLEET_STATUS_PATH = (
  Resolve-Path .\examples\fleet-status.sample.json
)
python .\tools\fleet_status_mcp.py
```

The process speaks newline-delimited MCP JSON-RPC over stdin/stdout. Normally
Hermes owns this subprocess; direct execution is useful only for protocol
debugging.

Register the server with the installed Hermes profile:

```powershell
.\scripts\hermes\Configure-HermesFleetObserver.ps1
hermes mcp test cfmi_fleet_status
```

The default evidence path is
`%LOCALAPPDATA%\hermes\fleet-status.json`. If it does not exist, tool calls
report `RESOURCE_UNAVAILABLE`. The configuration validates that the local
server advertises exactly the four reviewed read-only tools before marking
that narrow server `trust: full`, disables parallel tool calls, and keeps
manual/deny approval defaults. Evidence content remains untrusted data; this
setting only prevents non-interactive leaf subagents from deadlocking on an
approval prompt for the prevalidated local tools.

The central observer also enables Hermes' built-in `delegation` toolset for up
to four temporary local leaf subagents. Children inherit the read-only MCP but
cannot delegate recursively, request interactive approvals, write shared
memory, schedule work, or gain terminal/file tools that the parent does not
have. Dangerous child commands remain auto-denied. This is local analysis
fan-out on the superadmin machine, not 14 persistent fleet agents.

## Rollout sequence

1. Validate MCP behavior against the sample and malformed fixtures.
2. Define one non-actuating bench machine's approved telemetry source.
3. Write one atomic snapshot to the configured evidence path.
4. Verify freshness, missing-data, disconnect, and malicious-text handling.
5. Measure collector overhead and evidence lag.
6. Review results before adding another node.

Do not connect 14 machines at once or use this MCP rollout sequence to install
Hermes on additional nodes. Remote transport, credentials, inventory
ownership, retention, and node identity remain approval prerequisites.

For the separately installed one-machine Windows Hermes pilot, follow
[Hermes Machine Doctor](hermes-machine-doctor.md). That local pilot reads its
own point-in-time snapshot and does not create fleet connectivity.
