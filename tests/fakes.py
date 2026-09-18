"""Test doubles: no model execution or GPU acceptance."""

from hashlib import sha256

from cfmi.contracts import (
    ArtifactDigest,
    Failure,
    Stage,
    StageResult,
    StageStatus,
)


def fake_export(
    payload: bytes,
    *,
    attempt: int = 1,
    failure: Failure | None = None,
    blocked: bool = False,
) -> StageResult:
    if blocked and failure is None:
        raise ValueError("blocked fake execution requires a failure")
    status = StageStatus.SUCCEEDED
    if failure is not None:
        status = StageStatus.BLOCKED if blocked else StageStatus.FAILED
    return StageResult(
        run_id="fake-run",
        stage=Stage.EXPORTING,
        attempt=attempt,
        status=status,
        worker_id="fake-cpu-worker",
        environment_fingerprint=sha256(b"fake-cpu-environment").hexdigest(),
        inputs=(ArtifactDigest("fake-input", sha256(payload).hexdigest()),),
        outputs=(
            (ArtifactDigest("fake-output", sha256(b"fake:" + payload).hexdigest()),)
            if failure is None
            else ()
        ),
        failure=failure,
    )
