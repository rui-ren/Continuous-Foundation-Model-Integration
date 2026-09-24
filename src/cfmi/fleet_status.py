"""Read-only fleet evidence loading and freshness classification."""

from collections.abc import Callable
from copy import deepcopy
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
DEFAULT_STALE_AFTER_SECONDS = 90

_REACHABILITY_STATES = frozenset({"reachable", "unreachable", "unknown"})
_HOST_STATES = frozenset({"healthy", "warning", "critical", "unknown"})
_WORKLOAD_STATES = frozenset(
    {"queued", "running", "succeeded", "failed", "blocked", "paused", "unknown"}
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


def _validate_snapshot(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FleetEvidenceError("INPUT_INVALID", "fleet evidence must be a JSON object")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise FleetEvidenceError(
            "INPUT_INVALID",
            f"schema_version must be {SCHEMA_VERSION}",
        )
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
            "schema_version": SCHEMA_VERSION,
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
