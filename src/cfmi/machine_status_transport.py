"""Validate and import one Machine Doctor pipeline artifact."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any

from cfmi.fleet_status import FleetEvidenceError, validate_fleet_snapshot
from cfmi.machine_status import write_snapshot_atomic


MAX_ARTIFACT_BYTES = 1_048_576
EXPORT_RECEIPT_SCHEMA_VERSION = 1
IMPORT_RECEIPT_SCHEMA_VERSION = 1


class MachineStatusTransportError(ValueError):
    """An explicit evidence-export or import failure."""

    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


def _reject_non_finite_number(value: str) -> None:
    raise ValueError(f"non-finite number is not valid JSON: {value}")


def _load_json(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        payload = path.read_bytes()
    except FileNotFoundError as error:
        raise MachineStatusTransportError(
            "RESOURCE_UNAVAILABLE", f"{label} does not exist: {path}"
        ) from error
    except OSError as error:
        raise MachineStatusTransportError(
            "RESOURCE_UNAVAILABLE", f"{label} is unreadable: {path}"
        ) from error
    if len(payload) > MAX_ARTIFACT_BYTES:
        raise MachineStatusTransportError(
            "INPUT_INVALID",
            f"{label} exceeds the {MAX_ARTIFACT_BYTES}-byte limit",
        )
    try:
        text = payload.decode("utf-8")
    except UnicodeError as error:
        raise MachineStatusTransportError(
            "INPUT_INVALID", f"{label} is not UTF-8: {path}"
        ) from error
    try:
        value = json.loads(text, parse_constant=_reject_non_finite_number)
    except (json.JSONDecodeError, ValueError) as error:
        raise MachineStatusTransportError(
            "INPUT_INVALID", f"{label} is not valid JSON: {error}"
        ) from error
    if not isinstance(value, dict):
        raise MachineStatusTransportError(
            "INPUT_INVALID", f"{label} must be a JSON object"
        )
    return value, payload


def _require_exact_text(
    value: object,
    *,
    field: str,
    expected: str | None = None,
    case_sensitive: bool = True,
) -> str:
    if not isinstance(value, str) or not value:
        raise MachineStatusTransportError(
            "INPUT_INVALID", f"{field} must be a non-empty string"
        )
    if expected is not None:
        matches = (
            value == expected
            if case_sensitive
            else value.casefold() == expected.casefold()
        )
        if not matches:
            raise MachineStatusTransportError(
                "IDENTITY_MISMATCH", f"{field} does not match the expected value"
            )
    return value


def _write_bytes_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(3):
            try:
                os.replace(temporary_path, path)
                break
            except OSError as error:
                retryable = isinstance(error, PermissionError) or getattr(
                    error, "winerror", None
                ) in {5, 32}
                if not retryable or attempt == 2:
                    raise
                time.sleep(0.05)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except OSError:
                pass


def import_machine_status_artifact(
    *,
    snapshot_path: Path,
    export_receipt_path: Path,
    destination_path: Path,
    import_receipt_path: Path,
    expected_node_id: str,
    expected_computer_name: str,
    expected_service_name: str,
    expected_pipeline_name: str,
    expected_definition_id: str,
    expected_repository_type: str,
    expected_repository_id: str,
    expected_run_id: str,
    expected_source_version: str,
    now: datetime | None = None,
    snapshot_writer=write_snapshot_atomic,
) -> dict[str, Any]:
    """Validate one exported snapshot and atomically update central evidence."""

    snapshot_value, snapshot_bytes = _load_json(
        snapshot_path, label="machine-status snapshot"
    )
    export_receipt, _ = _load_json(
        export_receipt_path, label="machine-status export receipt"
    )
    allowed_receipt_fields = {
        "schema_version",
        "status",
        "pipeline_name",
        "definition_id",
        "repository_type",
        "repository_id",
        "run_id",
        "source_version",
        "recorded_at",
        "node_id",
        "computer_name",
        "service_name",
        "observed_at",
        "snapshot_sha256",
        "provider_configuration_action",
        "gateway_action",
        "remote_command_action",
        "remediation_action",
    }
    unknown_fields = sorted(set(export_receipt) - allowed_receipt_fields)
    if unknown_fields:
        raise MachineStatusTransportError(
            "INPUT_INVALID",
            "machine-status export receipt contains unknown fields: "
            + ", ".join(unknown_fields),
        )
    missing_fields = sorted(allowed_receipt_fields - set(export_receipt))
    if missing_fields:
        raise MachineStatusTransportError(
            "INPUT_INVALID",
            "machine-status export receipt is missing fields: "
            + ", ".join(missing_fields),
        )
    if export_receipt.get("schema_version") != EXPORT_RECEIPT_SCHEMA_VERSION:
        raise MachineStatusTransportError(
            "INPUT_INVALID",
            "machine-status export receipt schema_version must be 1",
        )
    _require_exact_text(
        export_receipt.get("status"), field="export receipt status", expected="SUCCEEDED"
    )
    _require_exact_text(
        export_receipt.get("pipeline_name"),
        field="export receipt pipeline_name",
        expected=expected_pipeline_name,
    )
    _require_exact_text(
        str(export_receipt.get("definition_id", "")),
        field="export receipt definition_id",
        expected=expected_definition_id,
    )
    _require_exact_text(
        export_receipt.get("repository_type"),
        field="export receipt repository_type",
        expected=expected_repository_type,
    )
    _require_exact_text(
        export_receipt.get("repository_id"),
        field="export receipt repository_id",
        expected=expected_repository_id,
        case_sensitive=False,
    )
    _require_exact_text(
        str(export_receipt.get("run_id", "")),
        field="export receipt run_id",
        expected=expected_run_id,
    )
    _require_exact_text(
        export_receipt.get("source_version"),
        field="export receipt source_version",
        expected=expected_source_version,
        case_sensitive=False,
    )
    if len(expected_source_version) != 40 or any(
        character not in "0123456789abcdefABCDEF"
        for character in expected_source_version
    ):
        raise MachineStatusTransportError(
            "INPUT_INVALID", "expected source version must be a 40-character Git SHA"
        )
    recorded_at = _require_exact_text(
        export_receipt.get("recorded_at"), field="export receipt recorded_at"
    )
    try:
        parsed_recorded_at = datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise MachineStatusTransportError(
            "INPUT_INVALID",
            "export receipt recorded_at must be an ISO-8601 timestamp",
        ) from error
    if parsed_recorded_at.tzinfo is None:
        raise MachineStatusTransportError(
            "INPUT_INVALID", "export receipt recorded_at must include a timezone offset"
        )
    _require_exact_text(
        export_receipt.get("node_id"),
        field="export receipt node_id",
        expected=expected_node_id,
    )
    _require_exact_text(
        export_receipt.get("computer_name"),
        field="export receipt computer_name",
        expected=expected_computer_name,
        case_sensitive=False,
    )
    _require_exact_text(
        export_receipt.get("service_name"),
        field="export receipt service_name",
        expected=expected_service_name,
    )
    for field, expected in (
        ("provider_configuration_action", "not_managed"),
        ("gateway_action", "not_started"),
        ("remote_command_action", "not_enabled"),
        ("remediation_action", "not_enabled"),
    ):
        _require_exact_text(
            export_receipt.get(field), field=f"export receipt {field}", expected=expected
        )

    snapshot_digest = hashlib.sha256(snapshot_bytes).hexdigest()
    _require_exact_text(
        export_receipt.get("snapshot_sha256"),
        field="export receipt snapshot_sha256",
        expected=snapshot_digest,
    )
    try:
        snapshot = validate_fleet_snapshot(snapshot_value)
    except FleetEvidenceError as error:
        raise MachineStatusTransportError(error.category, str(error)) from error
    if snapshot.get("schema_version") != 2:
        raise MachineStatusTransportError(
            "INPUT_INVALID", "imported Machine Doctor evidence must use schema version 2"
        )
    source_identity = snapshot["source_identity"]
    _require_exact_text(
        source_identity.get("node_id"),
        field="snapshot source_identity.node_id",
        expected=expected_node_id,
    )
    for field in ("expected_computer_name", "observed_computer_name"):
        _require_exact_text(
            source_identity.get(field),
            field=f"snapshot source_identity.{field}",
            expected=expected_computer_name,
            case_sensitive=False,
        )
    node = snapshot["nodes"][0]
    _require_exact_text(
        node.get("node_id"), field="snapshot nodes[0].node_id", expected=expected_node_id
    )
    observed_at = _require_exact_text(
        node.get("observed_at"), field="snapshot nodes[0].observed_at"
    )
    _require_exact_text(
        export_receipt.get("observed_at"),
        field="export receipt observed_at",
        expected=observed_at,
    )
    service = node["host"]["machine"]["service"]
    if service.get("status") != "available":
        raise MachineStatusTransportError(
            "RESOURCE_UNAVAILABLE",
            "snapshot service evidence must be available for identity binding",
        )
    _require_exact_text(
        service.get("service_name"),
        field="snapshot service_name",
        expected=expected_service_name,
    )

    imported_bytes = (
        json.dumps(snapshot, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    recorded_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    import_receipt = {
        "schema_version": IMPORT_RECEIPT_SCHEMA_VERSION,
        "status": "SUCCEEDED",
        "recorded_at": recorded_at.isoformat().replace("+00:00", "Z"),
        "pipeline_name": expected_pipeline_name,
        "definition_id": expected_definition_id,
        "repository_type": expected_repository_type,
        "repository_id": expected_repository_id,
        "run_id": expected_run_id,
        "source_version": expected_source_version,
        "node_id": expected_node_id,
        "computer_name": expected_computer_name,
        "service_name": expected_service_name,
        "observed_at": observed_at,
        "source_snapshot_sha256": snapshot_digest,
        "imported_snapshot_sha256": hashlib.sha256(imported_bytes).hexdigest(),
        "destination_path": str(destination_path),
    }
    destination_existed = destination_path.exists()
    prior_destination = destination_path.read_bytes() if destination_existed else None
    destination_replaced = False
    try:
        snapshot_writer(destination_path, snapshot)
        destination_replaced = True
        snapshot_writer(import_receipt_path, import_receipt)
    except (OSError, TypeError, ValueError) as error:
        if destination_replaced:
            try:
                if prior_destination is None:
                    destination_path.unlink(missing_ok=True)
                else:
                    _write_bytes_atomic(destination_path, prior_destination)
            except OSError as rollback_error:
                raise MachineStatusTransportError(
                    "WRITE_FAILED",
                    "import receipt failed and prior evidence could not be restored: "
                    f"{rollback_error}",
                ) from error
        raise MachineStatusTransportError(
            getattr(error, "category", "WRITE_FAILED"),
            f"unable to commit evidence and import receipt: {error}",
        ) from error
    return import_receipt
