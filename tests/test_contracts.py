from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
import unittest

from cfmi.contracts import (
    ArtifactDigest,
    Failure,
    FailureCategory,
    StageStatus,
)
from tests.fakes import fake_export


class StageResultTests(unittest.TestCase):
    def setUp(self) -> None:
        self.result = fake_export(b"fixture")
        self.failure = Failure(FailureCategory.EXPORT_DEFECT, "Injected export defect")

    def test_fake_success_has_reproducible_evidence(self) -> None:
        self.assertEqual(self.result, fake_export(b"fixture"))
        self.assertEqual(self.result.status, StageStatus.SUCCEEDED)
        self.assertEqual(self.result.inputs[0].sha256, sha256(b"fixture").hexdigest())
        self.assertEqual(
            self.result.outputs[0].sha256, sha256(b"fake:fixture").hexdigest()
        )
        self.assertNotEqual(self.result.inputs, fake_export(b"changed").inputs)

    def test_failed_execution_retains_input_and_reason(self) -> None:
        result = fake_export(b"fixture", failure=self.failure)
        self.assertEqual(result.status, StageStatus.FAILED)
        self.assertEqual(result.inputs, self.result.inputs)
        self.assertEqual(result.failure, self.failure)
        self.assertEqual(result.outputs, ())

    def test_blocked_execution_is_not_success(self) -> None:
        result = fake_export(b"fixture", failure=self.failure, blocked=True)
        self.assertEqual(result.status, StageStatus.BLOCKED)
        with self.assertRaisesRegex(ValueError, "requires a failure"):
            fake_export(b"fixture", blocked=True)

    def test_failed_and_blocked_results_require_typed_reason(self) -> None:
        for status in (StageStatus.FAILED, StageStatus.BLOCKED):
            for failure in (None, "an untyped error"):
                with self.subTest(status=status, failure=failure):
                    with self.assertRaisesRegex(ValueError, "typed failure"):
                        replace(self.result, status=status, failure=failure)

    def test_success_requires_output_and_no_failure(self) -> None:
        with self.assertRaisesRegex(ValueError, "require outputs"):
            replace(self.result, outputs=())
        with self.assertRaisesRegex(ValueError, "cannot contain a failure"):
            replace(self.result, failure=self.failure)

    def test_input_evidence_is_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "submitted manifest"):
            replace(self.result, inputs=())

    def test_attempt_must_be_a_positive_integer(self) -> None:
        for attempt in (0, -1, True, 1.5, "1"):
            with self.subTest(attempt=attempt):
                with self.assertRaisesRegex(ValueError, "positive integer"):
                    replace(self.result, attempt=attempt)

    def test_identifiers_are_required(self) -> None:
        for field in ("run_id", "worker_id"):
            for value in ("", " ", None):
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(ValueError, "non-empty string"):
                        replace(self.result, **{field: value})

    def test_unknown_stage_and_status_are_rejected(self) -> None:
        for field, value in (("stage", "EXPORTING"), ("status", "SUCCEEDED")):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    replace(self.result, **{field: value})

    def test_digest_format_is_checked(self) -> None:
        for digest in ("", "sha256-value", "A" * 64, "g" * 64, "a" * 63, None):
            with self.subTest(digest=digest):
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    ArtifactDigest("output", digest)
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    replace(self.result, environment_fingerprint=digest)

    def test_artifact_name_is_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "artifact name"):
            ArtifactDigest("", "a" * 64)

    def test_artifact_collections_are_immutable_and_typed(self) -> None:
        for field in ("inputs", "outputs"):
            for value in ([self.result.inputs[0]], ("untyped",)):
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(ValueError, "tuple of ArtifactDigest"):
                        replace(self.result, **{field: value})

    def test_duplicate_artifact_names_are_rejected(self) -> None:
        for field in ("inputs", "outputs"):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "unique artifact names"):
                    replace(self.result, **{field: self.result.inputs * 2})

    def test_failure_requires_known_category_and_message(self) -> None:
        with self.assertRaisesRegex(ValueError, "FailureCategory"):
            Failure("UNKNOWN", "reason")
        with self.assertRaisesRegex(ValueError, "failure message"):
            Failure(FailureCategory.EXPORT_DEFECT, " ")

    def test_retry_is_a_new_record_without_mutating_prior_failure(self) -> None:
        failed = fake_export(b"fixture", failure=self.failure)
        retried = fake_export(b"fixture", attempt=2)
        self.assertEqual(failed.attempt, 1)
        self.assertEqual(failed.status, StageStatus.FAILED)
        self.assertEqual(retried.attempt, 2)
        self.assertEqual(failed.inputs, retried.inputs)
        with self.assertRaises(FrozenInstanceError):
            setattr(failed, "status", StageStatus.SUCCEEDED)
        with self.assertRaises(FrozenInstanceError):
            setattr(failed.inputs[0], "sha256", "a" * 64)
