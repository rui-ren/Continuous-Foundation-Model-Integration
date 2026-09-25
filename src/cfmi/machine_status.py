"""Bounded Windows machine-status collection for the read-only Hermes pilot."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import ctypes
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any


CONFIG_SCHEMA_VERSION = 1
SNAPSHOT_SCHEMA_VERSION = 2
SOURCE_NAME = "local-windows-machine-doctor"

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SERVICE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.$_-]{0,255}$")
_VOLUME_PATTERN = re.compile(r"^[A-Za-z]:\\$")
_PROBE_NAMES = ("boot", "cpu", "memory", "disks", "service")


class MachineStatusError(ValueError):
    """An explicit machine-status collection or validation failure."""

    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


@dataclass(frozen=True)
class MachineStatusConfig:
    node_id: str
    expected_computer_name: str
    service_name: str
    volumes: tuple[str, ...]
    output_path: Path
    sample_count: int = 3
    sample_interval_seconds: float = 1.0
    probe_timeout_seconds: float = 5.0
    total_timeout_seconds: float = 30.0


ProbeRunner = Callable[[str, Mapping[str, Any], float], dict[str, Any]]
ReplaceFile = Callable[
    [
        str | bytes | os.PathLike[str] | os.PathLike[bytes],
        str | bytes | os.PathLike[str] | os.PathLike[bytes],
    ],
    None,
]
Sleep = Callable[[float], None]


def _require_identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_PATTERN.fullmatch(value):
        raise MachineStatusError(
            "INPUT_INVALID",
            f"{field} must match {_IDENTIFIER_PATTERN.pattern}",
        )
    return value


def _require_number(
    value: object,
    field: str,
    *,
    minimum: float,
    maximum: float,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MachineStatusError("INPUT_INVALID", f"{field} must be a number")
    number = float(value)
    if not minimum <= number <= maximum:
        raise MachineStatusError(
            "INPUT_INVALID",
            f"{field} must be between {minimum} and {maximum}",
        )
    return number


def load_machine_status_config(path: Path) -> MachineStatusConfig:
    """Load one strict, local Machine Doctor configuration."""

    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise MachineStatusError(
            "RESOURCE_UNAVAILABLE", f"configuration file does not exist: {path}"
        ) from error
    except UnicodeError as error:
        raise MachineStatusError(
            "INPUT_INVALID", f"configuration file is not UTF-8: {path}"
        ) from error
    except OSError as error:
        raise MachineStatusError(
            "RESOURCE_UNAVAILABLE", f"configuration file is unreadable: {path}"
        ) from error
    try:
        value = json.loads(raw, parse_constant=_reject_non_finite_number)
    except (json.JSONDecodeError, ValueError) as error:
        raise MachineStatusError(
            "INPUT_INVALID", f"configuration file is not valid JSON: {error}"
        ) from error
    if not isinstance(value, dict):
        raise MachineStatusError("INPUT_INVALID", "configuration must be an object")

    allowed = {
        "schema_version",
        "node_id",
        "expected_computer_name",
        "service_name",
        "volumes",
        "output_path",
        "sample_count",
        "sample_interval_seconds",
        "probe_timeout_seconds",
        "total_timeout_seconds",
    }
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise MachineStatusError(
            "INPUT_INVALID", f"unknown configuration fields: {', '.join(unknown)}"
        )
    if value.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise MachineStatusError(
            "INPUT_INVALID",
            f"schema_version must be {CONFIG_SCHEMA_VERSION}",
        )

    node_id = _require_identifier(value.get("node_id"), "node_id")
    expected_name = _require_identifier(
        value.get("expected_computer_name"), "expected_computer_name"
    )
    service_name = value.get("service_name")
    if not isinstance(service_name, str) or not _SERVICE_PATTERN.fullmatch(service_name):
        raise MachineStatusError(
            "INPUT_INVALID",
            f"service_name must match {_SERVICE_PATTERN.pattern}",
        )
    volumes = value.get("volumes")
    if (
        not isinstance(volumes, list)
        or not volumes
        or any(not isinstance(item, str) for item in volumes)
    ):
        raise MachineStatusError(
            "INPUT_INVALID", "volumes must be a nonempty string array"
        )
    normalized_volumes = tuple(sorted({item.upper() for item in volumes}))
    if len(normalized_volumes) != len(volumes):
        raise MachineStatusError("INPUT_INVALID", "volumes must not contain duplicates")
    if any(not _VOLUME_PATTERN.fullmatch(item) for item in normalized_volumes):
        raise MachineStatusError(
            "INPUT_INVALID", r"volumes must contain local drive roots such as C:\\"
        )
    output_value = value.get("output_path")
    if not isinstance(output_value, str) or not output_value.strip():
        raise MachineStatusError(
            "INPUT_INVALID", "output_path must be a nonempty string"
        )
    output_path = Path(output_value).expanduser()
    if not output_path.is_absolute():
        raise MachineStatusError("INPUT_INVALID", "output_path must be absolute")

    sample_count_value = value.get("sample_count", 3)
    if (
        isinstance(sample_count_value, bool)
        or not isinstance(sample_count_value, int)
        or not 3 <= sample_count_value <= 10
    ):
        raise MachineStatusError(
            "INPUT_INVALID", "sample_count must be an integer between 3 and 10"
        )
    sample_interval = _require_number(
        value.get("sample_interval_seconds", 1.0),
        "sample_interval_seconds",
        minimum=0.1,
        maximum=5.0,
    )
    probe_timeout = _require_number(
        value.get("probe_timeout_seconds", 5.0),
        "probe_timeout_seconds",
        minimum=1.0,
        maximum=15.0,
    )
    total_timeout = _require_number(
        value.get("total_timeout_seconds", 30.0),
        "total_timeout_seconds",
        minimum=5.0,
        maximum=60.0,
    )
    minimum_cpu_time = sample_count_value * sample_interval + 1.0
    if minimum_cpu_time >= total_timeout:
        raise MachineStatusError(
            "INPUT_INVALID",
            "CPU sampling must leave time for the other bounded probes",
        )
    return MachineStatusConfig(
        node_id=node_id,
        expected_computer_name=expected_name,
        service_name=service_name,
        volumes=normalized_volumes,
        output_path=output_path,
        sample_count=sample_count_value,
        sample_interval_seconds=sample_interval,
        probe_timeout_seconds=probe_timeout,
        total_timeout_seconds=total_timeout,
    )


def _reject_non_finite_number(value: str) -> None:
    raise ValueError(f"non-finite number is not valid JSON: {value}")


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _unavailable(category: str, message: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "reason": {"category": category, "message": message},
    }


def _validate_nonnegative_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MachineStatusError(
            "PROBE_INVALID", f"{field} must be a non-negative integer"
        )
    return value


def _validate_probe_result(
    name: str,
    value: object,
    config: MachineStatusConfig,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MachineStatusError("PROBE_INVALID", f"{name} probe returned no object")
    result = dict(value)
    if name == "boot":
        boot_id = result.get("boot_id")
        last_boot_at = result.get("last_boot_at")
        if (
            not isinstance(boot_id, str)
            or not re.fullmatch(r"[a-f0-9]{64}", boot_id)
            or not isinstance(last_boot_at, str)
        ):
            raise MachineStatusError("PROBE_INVALID", "boot probe returned invalid data")
    elif name == "cpu":
        logical = _validate_nonnegative_integer(
            result.get("logical_processor_count"), "logical_processor_count"
        )
        samples = result.get("samples")
        if logical < 1 or not isinstance(samples, list) or len(samples) != config.sample_count:
            raise MachineStatusError(
                "PROBE_INVALID",
                f"cpu probe must return {config.sample_count} samples",
            )
        for index, sample in enumerate(samples):
            if not isinstance(sample, dict):
                raise MachineStatusError(
                    "PROBE_INVALID", f"cpu sample {index} must be an object"
                )
            utilization = sample.get("utilization_percent")
            if (
                isinstance(utilization, bool)
                or not isinstance(utilization, (int, float))
                or not 0 <= float(utilization) <= 100
                or not isinstance(sample.get("observed_at"), str)
            ):
                raise MachineStatusError(
                    "PROBE_INVALID", f"cpu sample {index} is invalid"
                )
    elif name == "memory":
        for field in (
            "physical_total_bytes",
            "physical_available_bytes",
            "physical_used_bytes",
            "commit_limit_bytes",
            "commit_available_bytes",
            "commit_used_bytes",
        ):
            _validate_nonnegative_integer(result.get(field), field)
        if (
            result["physical_available_bytes"] > result["physical_total_bytes"]
            or result["physical_used_bytes"]
            != result["physical_total_bytes"] - result["physical_available_bytes"]
            or result["commit_available_bytes"] > result["commit_limit_bytes"]
            or result["commit_used_bytes"]
            != result["commit_limit_bytes"] - result["commit_available_bytes"]
        ):
            raise MachineStatusError(
                "PROBE_INVALID", "memory probe returned inconsistent counters"
            )
    elif name == "disks":
        volumes = result.get("volumes")
        if not isinstance(volumes, list) or len(volumes) != len(config.volumes):
            raise MachineStatusError(
                "PROBE_INVALID", "disk probe did not return every configured volume"
            )
        returned_roots = []
        for volume in volumes:
            if not isinstance(volume, dict):
                raise MachineStatusError(
                    "PROBE_INVALID", "disk volume evidence must be an object"
                )
            returned_roots.append(volume.get("root"))
            total = _validate_nonnegative_integer(
                volume.get("total_bytes"), "total_bytes"
            )
            free = _validate_nonnegative_integer(volume.get("free_bytes"), "free_bytes")
            if free > total:
                raise MachineStatusError(
                    "PROBE_INVALID", "disk free bytes exceed total bytes"
                )
        if tuple(returned_roots) != config.volumes:
            raise MachineStatusError(
                "PROBE_INVALID", "disk probe returned unexpected volume roots"
            )
    elif name == "service":
        if result.get("service_name") != config.service_name:
            raise MachineStatusError(
                "PROBE_INVALID", "service probe returned a different service name"
            )
        if result.get("state") not in {
            "missing",
            "stopped",
            "start_pending",
            "stop_pending",
            "running",
            "continue_pending",
            "pause_pending",
            "paused",
        }:
            raise MachineStatusError(
                "PROBE_INVALID", "service probe returned an unknown state"
            )
    else:
        raise MachineStatusError("INPUT_INVALID", f"unknown probe: {name}")
    return result


def collect_machine_snapshot(
    config: MachineStatusConfig,
    runner: ProbeRunner,
    *,
    now: Callable[[], datetime] | None = None,
    monotonic: Callable[[], float] | None = None,
    observed_computer_name: str | None = None,
) -> dict[str, Any]:
    """Collect one local snapshot without granting Hermes an execution surface."""

    current_time = now or (lambda: datetime.now(timezone.utc))
    monotonic_time = monotonic or time.monotonic
    computer_name = (
        observed_computer_name
        or os.environ.get("COMPUTERNAME")
        or socket.gethostname()
    )
    if computer_name.casefold() != config.expected_computer_name.casefold():
        raise MachineStatusError(
            "IDENTITY_MISMATCH",
            "observed computer name does not match expected_computer_name",
        )

    started = monotonic_time()
    evidence: dict[str, dict[str, Any]] = {}
    payloads: dict[str, dict[str, Any]] = {
        "boot": {"computer_name": computer_name},
        "cpu": {
            "sample_count": config.sample_count,
            "sample_interval_seconds": config.sample_interval_seconds,
        },
        "memory": {},
        "disks": {"volumes": list(config.volumes)},
        "service": {"service_name": config.service_name},
    }
    for name in _PROBE_NAMES:
        elapsed = monotonic_time() - started
        remaining = config.total_timeout_seconds - elapsed
        if remaining <= 0:
            evidence[name] = _unavailable(
                "TIMEOUT", "total collection timeout expired"
            )
            continue
        requested_timeout = config.probe_timeout_seconds
        if name == "cpu":
            requested_timeout = max(
                requested_timeout,
                config.sample_count * config.sample_interval_seconds + 1.0,
            )
        timeout = min(requested_timeout, remaining)
        try:
            result = runner(name, payloads[name], timeout)
            evidence[name] = {
                "status": "available",
                **_validate_probe_result(name, result, config),
            }
        except MachineStatusError as error:
            evidence[name] = _unavailable(error.category, str(error))

    observed_at = current_time()
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "source": SOURCE_NAME,
        "source_identity": {
            "binding": "configured-local-computer-name",
            "node_id": config.node_id,
            "expected_computer_name": config.expected_computer_name,
            "observed_computer_name": computer_name,
        },
        "nodes": [
            {
                "node_id": config.node_id,
                "observed_at": _utc_text(observed_at),
                "reachability": {
                    "status": "reachable",
                    "basis": "collector_executed_locally",
                },
                "host": {
                    "status": "unknown",
                    "reason": "thresholds_not_approved",
                    "machine": {
                        "identity": {
                            "status": "available",
                            "expected_computer_name": config.expected_computer_name,
                            "observed_computer_name": computer_name,
                            "matches": True,
                        },
                        **evidence,
                    },
                },
                "workload_evidence": {
                    "status": "unavailable",
                    "reason": {
                        "category": "NOT_CONFIGURED",
                        "message": "no approved workload progress source is configured",
                    },
                },
                "workloads": [],
            }
        ],
    }


def write_snapshot_atomic(
    path: Path,
    snapshot: Mapping[str, Any],
    *,
    replace: ReplaceFile = os.replace,
    sleep: Sleep = time.sleep,
) -> None:
    """Atomically replace one snapshot while preserving the previous complete file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(
                snapshot,
                handle,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(3):
            try:
                replace(temporary_path, path)
                break
            except OSError as error:
                retryable = isinstance(error, PermissionError) or getattr(
                    error, "winerror", None
                ) in {5, 32}
                if not retryable or attempt == 2:
                    raise
                sleep(0.05)
        temporary_path = None
    except (OSError, TypeError, ValueError) as error:
        cleanup_message = ""
        if temporary_path is not None:
            try:
                temporary_path.unlink()
                temporary_path = None
            except OSError as cleanup_error:
                cleanup_message = f"; temporary-file cleanup also failed: {cleanup_error}"
        raise MachineStatusError(
            "WRITE_FAILED",
            f"unable to atomically write machine evidence: {error}{cleanup_message}",
        ) from error


def run_probe_subprocess(
    script_path: Path,
    name: str,
    payload: Mapping[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    """Execute one allowlisted probe in a timeout-bounded child process."""

    try:
        completed = subprocess.run(
            [sys.executable, str(script_path), "--internal-probe", name],
            input=json.dumps(payload, allow_nan=False),
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise MachineStatusError("TIMEOUT", f"{name} probe timed out") from error
    except OSError as error:
        raise MachineStatusError(
            "RESOURCE_UNAVAILABLE", f"{name} probe could not start: {error}"
        ) from error
    if completed.returncode != 0:
        message = completed.stderr.strip().splitlines()
        detail = message[-1] if message else f"exit code {completed.returncode}"
        raise MachineStatusError(
            "RESOURCE_UNAVAILABLE", f"{name} probe failed: {detail[:300]}"
        )
    try:
        value = json.loads(
            completed.stdout,
            parse_constant=_reject_non_finite_number,
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise MachineStatusError(
            "PROBE_INVALID", f"{name} probe returned invalid JSON"
        ) from error
    if not isinstance(value, dict):
        raise MachineStatusError(
            "PROBE_INVALID", f"{name} probe returned no object"
        )
    return value


def run_internal_windows_probe(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Run one fixed Windows API probe selected by the parent collector."""

    if os.name != "nt":
        raise MachineStatusError(
            "CAPABILITY_MISSING", "Windows machine probes require Windows"
        )
    probes: dict[str, Callable[[Mapping[str, Any]], dict[str, Any]]] = {
        "boot": _probe_windows_boot,
        "cpu": _probe_windows_cpu,
        "memory": _probe_windows_memory,
        "disks": _probe_windows_disks,
        "service": _probe_windows_service,
    }
    try:
        probe = probes[name]
    except KeyError as error:
        raise MachineStatusError("INPUT_INVALID", f"unknown probe: {name}") from error
    return probe(payload)


class _FileTime(ctypes.Structure):
    _fields_ = [("low", ctypes.c_ulong), ("high", ctypes.c_ulong)]


def _filetime_value(value: _FileTime) -> int:
    return (int(value.high) << 32) + int(value.low)


def _probe_windows_boot(payload: Mapping[str, Any]) -> dict[str, Any]:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_tick_count = kernel32.GetTickCount64
    get_tick_count.restype = ctypes.c_ulonglong
    before = datetime.now(timezone.utc)
    uptime_ms = int(get_tick_count())
    after = datetime.now(timezone.utc)
    midpoint = before + (after - before) / 2
    boot = midpoint - timedelta(milliseconds=uptime_ms)
    boot = boot.replace(second=0, microsecond=0)
    computer_name = str(payload.get("computer_name", "")).casefold()
    boot_text = _utc_text(boot)
    boot_id = hashlib.sha256(
        f"{computer_name}|{boot_text}".encode("utf-8")
    ).hexdigest()
    return {
        "boot_id": boot_id,
        "last_boot_at": boot_text,
        "uptime_seconds": uptime_ms // 1000,
        "derivation": "GetTickCount64",
    }


def _read_system_times() -> tuple[int, int, int]:
    idle = _FileTime()
    kernel = _FileTime()
    user = _FileTime()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_system_times = kernel32.GetSystemTimes
    get_system_times.argtypes = [
        ctypes.POINTER(_FileTime),
        ctypes.POINTER(_FileTime),
        ctypes.POINTER(_FileTime),
    ]
    get_system_times.restype = ctypes.c_int
    if not get_system_times(
        ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return _filetime_value(idle), _filetime_value(kernel), _filetime_value(user)


def _probe_windows_cpu(payload: Mapping[str, Any]) -> dict[str, Any]:
    sample_count = int(payload["sample_count"])
    interval = float(payload["sample_interval_seconds"])
    previous = _read_system_times()
    samples = []
    for _ in range(sample_count):
        time.sleep(interval)
        current = _read_system_times()
        idle_delta = current[0] - previous[0]
        total_delta = current[1] - previous[1] + current[2] - previous[2]
        if total_delta <= 0 or idle_delta < 0 or idle_delta > total_delta:
            raise OSError("GetSystemTimes returned inconsistent counters")
        utilization = ((total_delta - idle_delta) / total_delta) * 100
        samples.append(
            {
                "observed_at": _utc_text(datetime.now(timezone.utc)),
                "utilization_percent": round(utilization, 1),
            }
        )
        previous = current
    return {
        "logical_processor_count": os.cpu_count() or 0,
        "sample_interval_seconds": interval,
        "samples": samples,
    }


class _MemoryStatus(ctypes.Structure):
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


def _probe_windows_memory(payload: Mapping[str, Any]) -> dict[str, Any]:
    del payload
    status = _MemoryStatus()
    status.length = ctypes.sizeof(status)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    global_memory_status = kernel32.GlobalMemoryStatusEx
    global_memory_status.argtypes = [ctypes.POINTER(_MemoryStatus)]
    global_memory_status.restype = ctypes.c_int
    if not global_memory_status(ctypes.byref(status)):
        raise ctypes.WinError(ctypes.get_last_error())
    physical_total = int(status.total_physical_bytes)
    physical_available = int(status.available_physical_bytes)
    commit_limit = int(status.total_page_file_bytes)
    commit_available = int(status.available_page_file_bytes)
    return {
        "physical_total_bytes": physical_total,
        "physical_available_bytes": physical_available,
        "physical_used_bytes": physical_total - physical_available,
        "commit_limit_bytes": commit_limit,
        "commit_available_bytes": commit_available,
        "commit_used_bytes": commit_limit - commit_available,
    }


def _probe_windows_disks(payload: Mapping[str, Any]) -> dict[str, Any]:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_disk_free_space = kernel32.GetDiskFreeSpaceExW
    get_disk_free_space.argtypes = [
        ctypes.c_wchar_p,
        ctypes.POINTER(ctypes.c_ulonglong),
        ctypes.POINTER(ctypes.c_ulonglong),
        ctypes.POINTER(ctypes.c_ulonglong),
    ]
    get_disk_free_space.restype = ctypes.c_int
    results = []
    for root in payload["volumes"]:
        available = ctypes.c_ulonglong()
        total = ctypes.c_ulonglong()
        free = ctypes.c_ulonglong()
        if not get_disk_free_space(
            root,
            ctypes.byref(available),
            ctypes.byref(total),
            ctypes.byref(free),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        results.append(
            {
                "root": root,
                "total_bytes": int(total.value),
                "free_bytes": int(free.value),
            }
        )
    return {"volumes": results}


class _ServiceStatusProcess(ctypes.Structure):
    _fields_ = [
        ("service_type", ctypes.c_ulong),
        ("current_state", ctypes.c_ulong),
        ("controls_accepted", ctypes.c_ulong),
        ("win32_exit_code", ctypes.c_ulong),
        ("service_specific_exit_code", ctypes.c_ulong),
        ("check_point", ctypes.c_ulong),
        ("wait_hint", ctypes.c_ulong),
        ("process_id", ctypes.c_ulong),
        ("service_flags", ctypes.c_ulong),
    ]


def _probe_windows_service(payload: Mapping[str, Any]) -> dict[str, Any]:
    service_name = str(payload["service_name"])
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    open_manager = advapi32.OpenSCManagerW
    open_manager.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_ulong]
    open_manager.restype = ctypes.c_void_p
    open_service = advapi32.OpenServiceW
    open_service.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_ulong]
    open_service.restype = ctypes.c_void_p
    query_status = advapi32.QueryServiceStatusEx
    query_status.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_ubyte),
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    query_status.restype = ctypes.c_int
    close_handle = advapi32.CloseServiceHandle
    close_handle.argtypes = [ctypes.c_void_p]
    close_handle.restype = ctypes.c_int

    manager = open_manager(None, None, 0x0001)
    if not manager:
        raise ctypes.WinError(ctypes.get_last_error())
    service = None
    try:
        service = open_service(manager, service_name, 0x0004)
        if not service:
            error = ctypes.get_last_error()
            if error == 1060:
                return {"service_name": service_name, "state": "missing"}
            raise ctypes.WinError(error)
        status = _ServiceStatusProcess()
        needed = ctypes.c_ulong()
        buffer = ctypes.cast(ctypes.byref(status), ctypes.POINTER(ctypes.c_ubyte))
        if not query_status(
            service,
            0,
            buffer,
            ctypes.sizeof(status),
            ctypes.byref(needed),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        states = {
            1: "stopped",
            2: "start_pending",
            3: "stop_pending",
            4: "running",
            5: "continue_pending",
            6: "pause_pending",
            7: "paused",
        }
        try:
            state = states[int(status.current_state)]
        except KeyError as error:
            raise OSError(
                f"service returned unknown state {status.current_state}"
            ) from error
        return {"service_name": service_name, "state": state}
    finally:
        if service:
            close_handle(service)
        close_handle(manager)
