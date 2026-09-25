"""Read-only fleet evidence loading and freshness classification."""

from collections.abc import Callable
from copy import deepcopy
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any


SUPPORTED_SCHEMA_VERSIONS = frozenset({1, 2})
DEFAULT_STALE_AFTER_SECONDS = 90

_REACHABILITY_STATES = frozenset({"reachable", "unreachable", "unknown"})
_HOST_STATES = frozenset({"healthy", "warning", "critical", "unknown"})
_WORKLOAD_STATES = frozenset(
    {"queued", "running", "succeeded", "failed", "blocked", "paused", "unknown"}
)
_EVIDENCE_STATES = frozenset({"available", "unavailable"})
_SERVICE_STATES = frozenset(
    {
        "missing",
        "stopped",
        "start_pending",
        "stop_pending",
        "running",
        "continue_pending",
        "pause_pending",
        "paused",
    }
)


class FleetEvidenceError(ValueError):
    """An explicit failure to load or query fleet evidence."""

    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


def _reject_non_finite_number(value: str) -> None:
    raise ValueError(f"non-finite number is not valid JSON: {value}")


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FleetEvidenceError("INPUT_INVALID", f"{field} must be a non-empty string")
    return value.strip()


def _parse_timestamp(value: object, field: str) -> datetime:
    text = _require_text(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise FleetEvidenceError(
            "INPUT_INVALID", f"{field} must be an ISO-8601 timestamp"
        ) from error
    if parsed.tzinfo is None:
        raise FleetEvidenceError(
            "INPUT_INVALID", f"{field} must include a timezone offset"
        )
    return parsed.astimezone(timezone.utc)


def _validate_state(value: object, field: str, allowed: frozenset[str]) -> str:
    state = _require_text(value, field)
    if state not in allowed:
        choices = ", ".join(sorted(allowed))
        raise FleetEvidenceError(
            "INPUT_INVALID", f"{field} must be one of: {choices}"
        )
    return state


def _reject_unknown_fields(
    value: dict[str, Any],
    field: str,
    allowed: frozenset[str],
) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise FleetEvidenceError(
            "INPUT_INVALID",
            f"{field} contains unknown fields: {', '.join(unknown)}",
        )


def _require_nonnegative_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FleetEvidenceError(
            "INPUT_INVALID", f"{field} must be a non-negative integer"
        )
    return value


def _validate_unavailable_reason(value: object, field: str) -> None:
    if not isinstance(value, dict):
        raise FleetEvidenceError("INPUT_INVALID", f"{field} must be an object")
    _reject_unknown_fields(value, field, frozenset({"category", "message"}))
    _require_text(value.get("category"), f"{field}.category")
    _require_text(value.get("message"), f"{field}.message")


def _validate_machine_section(
    value: object,
    field: str,
    *,
    available_fields: frozenset[str],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FleetEvidenceError("INPUT_INVALID", f"{field} must be an object")
    state = _validate_state(value.get("status"), f"{field}.status", _EVIDENCE_STATES)
    if state == "unavailable":
        _reject_unknown_fields(value, field, frozenset({"status", "reason"}))
        _validate_unavailable_reason(value.get("reason"), f"{field}.reason")
    else:
        _reject_unknown_fields(
            value,
            field,
            frozenset({"status"}) | available_fields,
        )
    return value


def _validate_machine_evidence(
    value: object,
    field: str,
    *,
    expected_computer_name: str,
) -> None:
    if not isinstance(value, dict):
        raise FleetEvidenceError("INPUT_INVALID", f"{field} must be an object")
    required_sections = frozenset(
        {"identity", "boot", "cpu", "memory", "disks", "service"}
    )
    _reject_unknown_fields(value, field, required_sections)
    missing = sorted(required_sections - set(value))
    if missing:
        raise FleetEvidenceError(
            "INPUT_INVALID",
            f"{field} is missing fields: {', '.join(missing)}",
        )

    identity = _validate_machine_section(
        value["identity"],
        f"{field}.identity",
        available_fields=frozenset(
            {"expected_computer_name", "observed_computer_name", "matches"}
        ),
    )
    if identity.get("status") != "available":
        raise FleetEvidenceError(
            "INPUT_INVALID", f"{field}.identity must be available"
        )
    configured_name = _require_text(
        identity.get("expected_computer_name"),
        f"{field}.identity.expected_computer_name",
    )
    observed_name = _require_text(
        identity.get("observed_computer_name"),
        f"{field}.identity.observed_computer_name",
    )
    if (
        configured_name.casefold() != expected_computer_name.casefold()
        or observed_name.casefold() != expected_computer_name.casefold()
        or identity.get("matches") is not True
    ):
        raise FleetEvidenceError(
            "INPUT_INVALID", f"{field}.identity does not match source_identity"
        )

    boot = _validate_machine_section(
        value["boot"],
        f"{field}.boot",
        available_fields=frozenset(
            {"boot_id", "last_boot_at", "uptime_seconds", "derivation"}
        ),
    )
    if boot.get("status") == "available":
        boot_id = _require_text(boot.get("boot_id"), f"{field}.boot.boot_id")
        if len(boot_id) != 64 or any(character not in "0123456789abcdef" for character in boot_id):
            raise FleetEvidenceError(
                "INPUT_INVALID", f"{field}.boot.boot_id must be a SHA-256 digest"
            )
        _parse_timestamp(boot.get("last_boot_at"), f"{field}.boot.last_boot_at")
        _require_nonnegative_integer(
            boot.get("uptime_seconds"), f"{field}.boot.uptime_seconds"
        )
        _require_text(boot.get("derivation"), f"{field}.boot.derivation")

    cpu = _validate_machine_section(
        value["cpu"],
        f"{field}.cpu",
        available_fields=frozenset(
            {"logical_processor_count", "sample_interval_seconds", "samples"}
        ),
    )
    if cpu.get("status") == "available":
        logical_processors = _require_nonnegative_integer(
            cpu.get("logical_processor_count"),
            f"{field}.cpu.logical_processor_count",
        )
        if logical_processors < 1:
            raise FleetEvidenceError(
                "INPUT_INVALID",
                f"{field}.cpu.logical_processor_count must be positive",
            )
        interval = cpu.get("sample_interval_seconds")
        if (
            isinstance(interval, bool)
            or not isinstance(interval, (int, float))
            or interval <= 0
        ):
            raise FleetEvidenceError(
                "INPUT_INVALID",
                f"{field}.cpu.sample_interval_seconds must be positive",
            )
        samples = cpu.get("samples")
        if not isinstance(samples, list) or len(samples) < 3:
            raise FleetEvidenceError(
                "INPUT_INVALID",
                f"{field}.cpu.samples must contain at least three samples",
            )
        for index, sample in enumerate(samples):
            sample_field = f"{field}.cpu.samples[{index}]"
            if not isinstance(sample, dict):
                raise FleetEvidenceError(
                    "INPUT_INVALID", f"{sample_field} must be an object"
                )
            _reject_unknown_fields(
                sample,
                sample_field,
                frozenset({"observed_at", "utilization_percent"}),
            )
            _parse_timestamp(sample.get("observed_at"), f"{sample_field}.observed_at")
            utilization = sample.get("utilization_percent")
            if (
                isinstance(utilization, bool)
                or not isinstance(utilization, (int, float))
                or not 0 <= utilization <= 100
            ):
                raise FleetEvidenceError(
                    "INPUT_INVALID",
                    f"{sample_field}.utilization_percent must be between 0 and 100",
                )

    memory = _validate_machine_section(
        value["memory"],
        f"{field}.memory",
        available_fields=frozenset(
            {
                "physical_total_bytes",
                "physical_available_bytes",
                "physical_used_bytes",
                "commit_limit_bytes",
                "commit_available_bytes",
                "commit_used_bytes",
            }
        ),
    )
    if memory.get("status") == "available":
        for name in (
            "physical_total_bytes",
            "physical_available_bytes",
            "physical_used_bytes",
            "commit_limit_bytes",
            "commit_available_bytes",
            "commit_used_bytes",
        ):
            _require_nonnegative_integer(memory.get(name), f"{field}.memory.{name}")
        if (
            memory["physical_available_bytes"] > memory["physical_total_bytes"]
            or memory["physical_used_bytes"]
            != memory["physical_total_bytes"] - memory["physical_available_bytes"]
            or memory["commit_available_bytes"] > memory["commit_limit_bytes"]
            or memory["commit_used_bytes"]
            != memory["commit_limit_bytes"] - memory["commit_available_bytes"]
        ):
            raise FleetEvidenceError(
                "INPUT_INVALID", f"{field}.memory counters are inconsistent"
            )

    disks = _validate_machine_section(
        value["disks"],
        f"{field}.disks",
        available_fields=frozenset({"volumes"}),
    )
    if disks.get("status") == "available":
        volumes = disks.get("volumes")
        if not isinstance(volumes, list) or not volumes:
            raise FleetEvidenceError(
                "INPUT_INVALID", f"{field}.disks.volumes must be nonempty"
            )
        roots: set[str] = set()
        for index, volume in enumerate(volumes):
            volume_field = f"{field}.disks.volumes[{index}]"
            if not isinstance(volume, dict):
                raise FleetEvidenceError(
                    "INPUT_INVALID", f"{volume_field} must be an object"
                )
            _reject_unknown_fields(
                volume,
                volume_field,
                frozenset({"root", "total_bytes", "free_bytes"}),
            )
            root = _require_text(volume.get("root"), f"{volume_field}.root")
            if root in roots:
                raise FleetEvidenceError(
                    "INPUT_INVALID", f"duplicate disk root: {root}"
                )
            roots.add(root)
            total = _require_nonnegative_integer(
                volume.get("total_bytes"), f"{volume_field}.total_bytes"
            )
            free = _require_nonnegative_integer(
                volume.get("free_bytes"), f"{volume_field}.free_bytes"
            )
            if free > total:
                raise FleetEvidenceError(
                    "INPUT_INVALID", f"{volume_field}.free_bytes exceeds total_bytes"
                )

    service = _validate_machine_section(
        value["service"],
        f"{field}.service",
        available_fields=frozenset({"service_name", "state"}),
    )
    if service.get("status") == "available":
        _require_text(service.get("service_name"), f"{field}.service.service_name")
        _validate_state(
            service.get("state"),
            f"{field}.service.state",
            _SERVICE_STATES,
        )


def _validate_version_two(value: dict[str, Any]) -> None:
    _reject_unknown_fields(
        value,
        "snapshot",
        frozenset({"schema_version", "source", "source_identity", "nodes"}),
    )
    if value.get("source") != "local-windows-machine-doctor":
        raise FleetEvidenceError(
            "INPUT_INVALID",
            "schema version 2 source must be local-windows-machine-doctor",
        )
    source_identity = value.get("source_identity")
    if not isinstance(source_identity, dict):
        raise FleetEvidenceError(
            "INPUT_INVALID", "source_identity must be an object"
        )
    _reject_unknown_fields(
        source_identity,
        "source_identity",
        frozenset(
            {
                "binding",
                "node_id",
                "expected_computer_name",
                "observed_computer_name",
            }
        ),
    )
    if source_identity.get("binding") != "configured-local-computer-name":
        raise FleetEvidenceError(
            "INPUT_INVALID", "source_identity.binding is unsupported"
        )
    source_node_id = _require_text(
        source_identity.get("node_id"), "source_identity.node_id"
    )
    expected_name = _require_text(
        source_identity.get("expected_computer_name"),
        "source_identity.expected_computer_name",
    )
    observed_name = _require_text(
        source_identity.get("observed_computer_name"),
        "source_identity.observed_computer_name",
    )
    if expected_name.casefold() != observed_name.casefold():
        raise FleetEvidenceError(
            "INPUT_INVALID", "source_identity computer names do not match"
        )
    nodes = value.get("nodes")
    if not isinstance(nodes, list) or len(nodes) != 1:
        raise FleetEvidenceError(
            "INPUT_INVALID", "schema version 2 local snapshot must contain one node"
        )
    node = nodes[0]
    if not isinstance(node, dict):
        raise FleetEvidenceError("INPUT_INVALID", "nodes[0] must be an object")
    _reject_unknown_fields(
        node,
        "nodes[0]",
        frozenset(
            {
                "node_id",
                "observed_at",
                "reachability",
                "host",
                "workload_evidence",
                "workloads",
            }
        ),
    )
    if node.get("node_id") != source_node_id:
        raise FleetEvidenceError(
            "INPUT_INVALID", "source_identity.node_id does not match nodes[0].node_id"
        )
    _parse_timestamp(node.get("observed_at"), "nodes[0].observed_at")
    reachability = node.get("reachability")
    if not isinstance(reachability, dict):
        raise FleetEvidenceError(
            "INPUT_INVALID", "nodes[0].reachability must be an object"
        )
    _reject_unknown_fields(
        reachability,
        "nodes[0].reachability",
        frozenset({"status", "basis"}),
    )
    if (
        reachability.get("status") != "reachable"
        or reachability.get("basis") != "collector_executed_locally"
    ):
        raise FleetEvidenceError(
            "INPUT_INVALID",
            "nodes[0].reachability must describe the local collector execution",
        )
    if node.get("workloads") != []:
        raise FleetEvidenceError(
            "INPUT_INVALID",
            "nodes[0].workloads must be empty while workload evidence is unavailable",
        )
    workload_evidence = node.get("workload_evidence")
    if not isinstance(workload_evidence, dict):
        raise FleetEvidenceError(
            "INPUT_INVALID", "nodes[0].workload_evidence must be an object"
        )
    _reject_unknown_fields(
        workload_evidence,
        "nodes[0].workload_evidence",
        frozenset({"status", "reason"}),
    )
    if workload_evidence.get("status") != "unavailable":
        raise FleetEvidenceError(
            "INPUT_INVALID",
            "nodes[0].workload_evidence.status must be unavailable in the pilot",
        )
    _validate_unavailable_reason(
        workload_evidence.get("reason"), "nodes[0].workload_evidence.reason"
    )
    host = node.get("host")
    if not isinstance(host, dict):
        raise FleetEvidenceError("INPUT_INVALID", "nodes[0].host must be an object")
    _reject_unknown_fields(
        host,
        "nodes[0].host",
        frozenset({"status", "reason", "machine"}),
    )
    if host.get("status") != "unknown" or host.get("reason") != "thresholds_not_approved":
        raise FleetEvidenceError(
            "INPUT_INVALID",
            "nodes[0].host must remain unknown without approved thresholds",
        )
    _validate_machine_evidence(
        host.get("machine"),
        "nodes[0].host.machine",
        expected_computer_name=expected_name,
    )


def _validate_snapshot(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FleetEvidenceError("INPUT_INVALID", "fleet evidence must be a JSON object")
    schema_version = value.get("schema_version")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise FleetEvidenceError(
            "INPUT_INVALID",
            "schema_version must be one of: "
            + ", ".join(str(item) for item in sorted(SUPPORTED_SCHEMA_VERSIONS)),
        )
    if schema_version == 2:
        _validate_version_two(value)
    nodes = value.get("nodes")
    if not isinstance(nodes, list):
        raise FleetEvidenceError("INPUT_INVALID", "nodes must be a JSON array")

    node_ids: set[str] = set()
    for node_index, node in enumerate(nodes):
        prefix = f"nodes[{node_index}]"
        if not isinstance(node, dict):
            raise FleetEvidenceError("INPUT_INVALID", f"{prefix} must be an object")
        node_id = _require_text(node.get("node_id"), f"{prefix}.node_id")
        if node_id in node_ids:
            raise FleetEvidenceError(
                "INPUT_INVALID", f"duplicate node_id: {node_id}"
            )
        node_ids.add(node_id)
        if node.get("observed_at") is not None:
            _parse_timestamp(node["observed_at"], f"{prefix}.observed_at")

        reachability = node.get("reachability", {})
        if not isinstance(reachability, dict):
            raise FleetEvidenceError(
                "INPUT_INVALID", f"{prefix}.reachability must be an object"
            )
        _validate_state(
            reachability.get("status", "unknown"),
            f"{prefix}.reachability.status",
            _REACHABILITY_STATES,
        )

        host = node.get("host", {})
        if not isinstance(host, dict):
            raise FleetEvidenceError("INPUT_INVALID", f"{prefix}.host must be an object")
        _validate_state(
            host.get("status", "unknown"),
            f"{prefix}.host.status",
            _HOST_STATES,
        )

        workloads = node.get("workloads", [])
        if not isinstance(workloads, list):
            raise FleetEvidenceError(
                "INPUT_INVALID", f"{prefix}.workloads must be an array"
            )
        workload_ids: set[str] = set()
        for workload_index, workload in enumerate(workloads):
            workload_prefix = f"{prefix}.workloads[{workload_index}]"
            if not isinstance(workload, dict):
                raise FleetEvidenceError(
                    "INPUT_INVALID", f"{workload_prefix} must be an object"
                )
            workload_id = _require_text(
                workload.get("workload_id"), f"{workload_prefix}.workload_id"
            )
            if workload_id in workload_ids:
                raise FleetEvidenceError(
                    "INPUT_INVALID",
                    f"duplicate workload_id '{workload_id}' on node '{node_id}'",
                )
            workload_ids.add(workload_id)
            _validate_state(
                workload.get("status", "unknown"),
                f"{workload_prefix}.status",
                _WORKLOAD_STATES,
            )
            if workload.get("observed_at") is not None:
                _parse_timestamp(
                    workload["observed_at"], f"{workload_prefix}.observed_at"
                )
            progress = workload.get("progress", {})
            if not isinstance(progress, dict):
                raise FleetEvidenceError(
                    "INPUT_INVALID", f"{workload_prefix}.progress must be an object"
                )

    return deepcopy(value)


def validate_fleet_snapshot(value: object) -> dict[str, Any]:
    """Validate and copy an in-memory fleet snapshot."""

    return _validate_snapshot(value)


def load_fleet_snapshot(path: Path) -> dict[str, Any]:
    """Load and validate one immutable fleet evidence snapshot."""

    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise FleetEvidenceError(
            "RESOURCE_UNAVAILABLE", f"fleet evidence file does not exist: {path}"
        ) from error
    except UnicodeError as error:
        raise FleetEvidenceError(
            "INPUT_INVALID", f"fleet evidence file is not UTF-8: {path}"
        ) from error
    except OSError as error:
        raise FleetEvidenceError(
            "RESOURCE_UNAVAILABLE", f"fleet evidence file is unreadable: {path}"
        ) from error
    try:
        value = json.loads(raw, parse_constant=_reject_non_finite_number)
    except (json.JSONDecodeError, ValueError) as error:
        raise FleetEvidenceError(
            "INPUT_INVALID", f"fleet evidence is not valid JSON: {error}"
        ) from error
    return _validate_snapshot(value)


def classify_observation(
    observed_at: object,
    *,
    now: datetime,
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
) -> dict[str, Any]:
    """Return explicit evidence freshness without treating missing data as healthy."""

    if observed_at is None:
        return {"evidence_state": "missing", "age_seconds": None}
    observed = _parse_timestamp(observed_at, "observed_at")
    current = now.astimezone(timezone.utc)
    if (observed - current).total_seconds() > 5:
        raise FleetEvidenceError(
            "INPUT_INVALID", "observed_at is more than 5 seconds in the future"
        )
    precise_age_seconds = max(0.0, (current - observed).total_seconds())
    age_seconds = int(precise_age_seconds)
    state = "live" if precise_age_seconds <= stale_after_seconds else "stale"
    return {"evidence_state": state, "age_seconds": age_seconds}


def read_local_system_status() -> dict[str, Any]:
    """Read local physical-memory counters without executing a command."""

    try:
        if os.name == "nt":
            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("memory_load_percent", ctypes.c_ulong),
                    ("total_physical_bytes", ctypes.c_ulonglong),
                    ("available_physical_bytes", ctypes.c_ulonglong),
                    ("total_page_file_bytes", ctypes.c_ulonglong),
                    ("available_page_file_bytes", ctypes.c_ulonglong),
                    ("total_virtual_bytes", ctypes.c_ulonglong),
                    ("available_virtual_bytes", ctypes.c_ulonglong),
                    ("available_extended_virtual_bytes", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            global_memory_status = kernel32.GlobalMemoryStatusEx
            global_memory_status.argtypes = [ctypes.POINTER(MemoryStatus)]
            global_memory_status.restype = ctypes.c_int
            if not global_memory_status(ctypes.byref(status)):
                raise ctypes.WinError(ctypes.get_last_error())
            total_bytes = int(status.total_physical_bytes)
            available_bytes = int(status.available_physical_bytes)
        else:
            page_size = int(os.sysconf("SC_PAGE_SIZE"))
            total_bytes = page_size * int(os.sysconf("SC_PHYS_PAGES"))
            available_bytes = page_size * int(os.sysconf("SC_AVPHYS_PAGES"))
    except (AttributeError, OSError, ValueError) as error:
        raise FleetEvidenceError(
            "RESOURCE_UNAVAILABLE", f"local memory counters are unavailable: {error}"
        ) from error

    if total_bytes <= 0 or not 0 <= available_bytes <= total_bytes:
        raise FleetEvidenceError(
            "RESOURCE_UNAVAILABLE", "local memory counters are invalid"
        )
    used_bytes = total_bytes - available_bytes
    return {
        "scope": "local-superadmin-host",
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "memory": {
            "total_bytes": total_bytes,
            "available_bytes": available_bytes,
            "used_bytes": used_bytes,
            "used_percent": round((used_bytes / total_bytes) * 100, 1),
        },
    }


class FleetStatusReader:
    """Query a file-backed snapshot without any mutation surface."""

    def __init__(
        self,
        path: Path,
        *,
        now: Callable[[], datetime] | None = None,
        stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
    ) -> None:
        self._path = path
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._stale_after_seconds = stale_after_seconds

    def _snapshot(self) -> dict[str, Any]:
        return load_fleet_snapshot(self._path)

    def _freshness(self, observed_at: object) -> dict[str, Any]:
        return classify_observation(
            observed_at,
            now=self._now(),
            stale_after_seconds=self._stale_after_seconds,
        )

    def list_nodes(self) -> dict[str, Any]:
        snapshot = self._snapshot()
        nodes = []
        for node in snapshot["nodes"]:
            nodes.append(
                {
                    "node_id": node["node_id"],
                    "source": node.get("source", snapshot.get("source", "unspecified")),
                    **self._freshness(node.get("observed_at")),
                    "observed_at": node.get("observed_at"),
                    "reachability": deepcopy(node.get("reachability", {"status": "unknown"})),
                    "host": deepcopy(node.get("host", {"status": "unknown"})),
                    "workload_count": len(node.get("workloads", [])),
                }
            )
        return {
            "schema_version": snapshot["schema_version"],
            "snapshot_source": snapshot.get("source", "unspecified"),
            "nodes": nodes,
        }

    def get_node_status(self, node_id: str) -> dict[str, Any]:
        requested = _require_text(node_id, "node_id")
        snapshot = self._snapshot()
        for node in snapshot["nodes"]:
            if node["node_id"] == requested:
                return {
                    **deepcopy(node),
                    **self._freshness(node.get("observed_at")),
                    "snapshot_source": snapshot.get("source", "unspecified"),
                }
        raise FleetEvidenceError("INPUT_INVALID", f"unknown node_id: {requested}")

    def get_job_progress(self, node_id: str, workload_id: str) -> dict[str, Any]:
        requested_node = _require_text(node_id, "node_id")
        requested_workload = _require_text(workload_id, "workload_id")
        node = self.get_node_status(requested_node)
        for workload in node.get("workloads", []):
            if workload["workload_id"] == requested_workload:
                return {
                    "node_id": requested_node,
                    **deepcopy(workload),
                    **self._freshness(workload.get("observed_at")),
                    "snapshot_source": node["snapshot_source"],
                }
        raise FleetEvidenceError(
            "INPUT_INVALID",
            f"unknown workload_id '{requested_workload}' on node '{requested_node}'",
        )
