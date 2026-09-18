"""Immutable evidence records for output-producing execution stages."""

from dataclasses import dataclass
from enum import Enum
import re


class Stage(Enum):
    PREFLIGHT = "PREFLIGHT"
    EXPORTING = "EXPORTING"
    CUDA_VALIDATION = "CUDA_VALIDATION"
    OPTIMIZING = "OPTIMIZING"
    TRT_RTX_VALIDATION = "TRT_RTX_VALIDATION"
    FLEET_VALIDATION = "FLEET_VALIDATION"


class StageStatus(Enum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class FailureCategory(Enum):
    INPUT_INVALID = "INPUT_INVALID"
    LICENSE_OR_POLICY_BLOCK = "LICENSE_OR_POLICY_BLOCK"
    RESOURCE_UNAVAILABLE = "RESOURCE_UNAVAILABLE"
    ENVIRONMENT_MISMATCH = "ENVIRONMENT_MISMATCH"
    DOWNLOAD_FAILURE = "DOWNLOAD_FAILURE"
    EXPORT_UNSUPPORTED = "EXPORT_UNSUPPORTED"
    EXPORT_DEFECT = "EXPORT_DEFECT"
    RUNTIME_UNSUPPORTED = "RUNTIME_UNSUPPORTED"
    RUNTIME_DEFECT = "RUNTIME_DEFECT"
    OUT_OF_MEMORY = "OUT_OF_MEMORY"
    QUALITY_REGRESSION = "QUALITY_REGRESSION"
    PERFORMANCE_REGRESSION = "PERFORMANCE_REGRESSION"
    FUNCTIONAL_REGRESSION = "FUNCTIONAL_REGRESSION"
    INFRASTRUCTURE_TRANSIENT = "INFRASTRUCTURE_TRANSIENT"
    UNKNOWN_REQUIRES_REVIEW = "UNKNOWN_REQUIRES_REVIEW"


def _require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")


def _require_sha256(value: str, field: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256 hex digest")


@dataclass(frozen=True)
class ArtifactDigest:
    name: str
    sha256: str

    def __post_init__(self) -> None:
        _require_text(self.name, "artifact name")
        _require_sha256(self.sha256, "artifact sha256")


@dataclass(frozen=True)
class Failure:
    category: FailureCategory
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.category, FailureCategory):
            raise ValueError("failure category must be a FailureCategory")
        _require_text(self.message, "failure message")


@dataclass(frozen=True)
class StageResult:
    run_id: str
    stage: Stage
    attempt: int
    status: StageStatus
    worker_id: str
    environment_fingerprint: str
    inputs: tuple[ArtifactDigest, ...]
    outputs: tuple[ArtifactDigest, ...]
    failure: Failure | None = None

    def __post_init__(self) -> None:
        _require_text(self.run_id, "run_id")
        _require_text(self.worker_id, "worker_id")
        if not isinstance(self.stage, Stage):
            raise ValueError("stage must be a Stage")
        if not isinstance(self.status, StageStatus):
            raise ValueError("status must be a StageStatus")
        if type(self.attempt) is not int or self.attempt < 1:
            raise ValueError("attempt must be a positive integer")
        _require_sha256(self.environment_fingerprint, "environment_fingerprint")
        for field, artifacts in (("inputs", self.inputs), ("outputs", self.outputs)):
            if not isinstance(artifacts, tuple) or any(
                not isinstance(artifact, ArtifactDigest) for artifact in artifacts
            ):
                raise ValueError(f"{field} must be a tuple of ArtifactDigest records")
            if len({artifact.name for artifact in artifacts}) != len(artifacts):
                raise ValueError(f"{field} must have unique artifact names")
        if not self.inputs:
            raise ValueError("inputs must identify at least the submitted manifest")
        if self.status is StageStatus.SUCCEEDED:
            if not self.outputs:
                raise ValueError("successful output-producing stages require outputs")
            if self.failure is not None:
                raise ValueError("successful stages cannot contain a failure")
        elif not isinstance(self.failure, Failure):
            raise ValueError("failed or blocked stages require a typed failure")
