from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from cfmi.machine_status import MachineStatusConfig, collect_machine_snapshot
from cfmi.machine_status_transport import (
    MachineStatusTransportError,
    import_machine_status_artifact,
)
from tools.check import ROOT


NOW = datetime(2026, 9, 25, 23, 30, 0, tzinfo=timezone.utc)
NODE_ID = "gpu-4090-pilot"
COMPUTER_NAME = "ORT-GPU-BENCH-5"
SERVICE_NAME = "vstsagent.aiinfra.FoundryLocal-GPU-4090.ORT-GPU-BENCH-5"
PIPELINE_NAME = "CFMI-Hermes-GPU4090-Status-Export"
DEFINITION_ID = "2400"
REPOSITORY_TYPE = "GitHub"
REPOSITORY_ID = "rui-ren/Continuous-Foundation-Model-Integration"
RUN_ID = "1446000"
SOURCE_VERSION = "a" * 40


def valid_probe_results() -> dict[str, dict]:
    return {
        "boot": {
            "boot_id": "b" * 64,
            "last_boot_at": "2026-09-25T08:00:00Z",
            "uptime_seconds": 55_800,
            "derivation": "test-double",
        },
        "cpu": {
            "logical_processor_count": 32,
            "sample_interval_seconds": 1.0,
            "samples": [
                {
                    "observed_at": f"2026-09-25T23:29:5{index}Z",
                    "utilization_percent": 10.0 + index,
                }
                for index in range(3)
            ],
        },
        "memory": {
            "physical_total_bytes": 68_000,
            "physical_available_bytes": 34_000,
            "physical_used_bytes": 34_000,
            "commit_limit_bytes": 96_000,
            "commit_available_bytes": 48_000,
            "commit_used_bytes": 48_000,
        },
        "disks": {
            "volumes": [
                {"root": "C:\\", "total_bytes": 1_000_000, "free_bytes": 400_000}
            ]
        },
        "service": {"service_name": SERVICE_NAME, "state": "running"},
    }


def valid_snapshot(output_path: Path) -> dict:
    config = MachineStatusConfig(
        node_id=NODE_ID,
        expected_computer_name=COMPUTER_NAME,
        service_name=SERVICE_NAME,
        volumes=("C:\\",),
        output_path=output_path,
    )
    results = valid_probe_results()
    return collect_machine_snapshot(
        config,
        lambda name, payload, timeout: results[name],
        now=lambda: NOW,
        observed_computer_name=COMPUTER_NAME,
    )


class MachineStatusTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.snapshot_path = self.root / "artifact" / "machine-status.json"
        self.export_receipt_path = self.root / "artifact" / "export-receipt.json"
        self.destination_path = self.root / "central" / "fleet-status.json"
        self.import_receipt_path = self.root / "central" / "imports" / "run.json"
        self.snapshot_path.parent.mkdir()
        self.snapshot_path.write_text(
            json.dumps(valid_snapshot(self.snapshot_path), sort_keys=True),
            encoding="utf-8",
        )
        self.write_export_receipt()

    def export_receipt(self) -> dict:
        snapshot = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
        return {
            "schema_version": 1,
            "status": "SUCCEEDED",
            "pipeline_name": PIPELINE_NAME,
            "definition_id": DEFINITION_ID,
            "repository_type": REPOSITORY_TYPE,
            "repository_id": REPOSITORY_ID,
            "run_id": RUN_ID,
            "source_version": SOURCE_VERSION,
            "recorded_at": "2026-09-25T23:30:02Z",
            "node_id": NODE_ID,
            "computer_name": COMPUTER_NAME,
            "service_name": SERVICE_NAME,
            "observed_at": snapshot["nodes"][0]["observed_at"],
            "snapshot_sha256": hashlib.sha256(
                self.snapshot_path.read_bytes()
            ).hexdigest(),
            "provider_configuration_action": "not_managed",
            "gateway_action": "not_started",
            "remote_command_action": "not_enabled",
            "remediation_action": "not_enabled",
        }

    def write_export_receipt(self, value: dict | None = None) -> None:
        self.export_receipt_path.write_text(
            json.dumps(value or self.export_receipt(), sort_keys=True),
            encoding="utf-8",
        )

    def import_artifact(self) -> dict:
        return import_machine_status_artifact(
            snapshot_path=self.snapshot_path,
            export_receipt_path=self.export_receipt_path,
            destination_path=self.destination_path,
            import_receipt_path=self.import_receipt_path,
            expected_node_id=NODE_ID,
            expected_computer_name=COMPUTER_NAME,
            expected_service_name=SERVICE_NAME,
            expected_pipeline_name=PIPELINE_NAME,
            expected_definition_id=DEFINITION_ID,
            expected_repository_type=REPOSITORY_TYPE,
            expected_repository_id=REPOSITORY_ID,
            expected_run_id=RUN_ID,
            expected_source_version=SOURCE_VERSION,
            now=NOW,
        )

    def test_valid_artifact_is_imported_atomically_with_receipt(self) -> None:
        receipt = self.import_artifact()

        imported = json.loads(self.destination_path.read_text(encoding="utf-8"))
        persisted_receipt = json.loads(
            self.import_receipt_path.read_text(encoding="utf-8")
        )
        self.assertEqual(imported["source_identity"]["node_id"], NODE_ID)
        self.assertEqual(receipt, persisted_receipt)
        self.assertEqual(receipt["status"], "SUCCEEDED")
        self.assertEqual(receipt["run_id"], RUN_ID)
        self.assertEqual(receipt["source_version"], SOURCE_VERSION)

    def test_cli_imports_the_same_strict_artifact(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "import_machine_status_artifact.py"),
                "--snapshot",
                str(self.snapshot_path),
                "--export-receipt",
                str(self.export_receipt_path),
                "--destination",
                str(self.destination_path),
                "--import-receipt",
                str(self.import_receipt_path),
                "--expected-node-id",
                NODE_ID,
                "--expected-computer-name",
                COMPUTER_NAME,
                "--expected-service-name",
                SERVICE_NAME,
                "--expected-pipeline-name",
                PIPELINE_NAME,
                "--expected-definition-id",
                DEFINITION_ID,
                "--expected-repository-type",
                REPOSITORY_TYPE,
                "--expected-repository-id",
                REPOSITORY_ID,
                "--expected-run-id",
                RUN_ID,
                "--expected-source-version",
                SOURCE_VERSION,
            ],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )

        self.assertEqual(completed.stderr, "")
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertTrue(self.destination_path.exists())
        self.assertTrue(self.import_receipt_path.exists())

    def test_hash_mismatch_preserves_existing_destination(self) -> None:
        self.destination_path.parent.mkdir()
        prior = b'{"prior":true}'
        self.destination_path.write_bytes(prior)
        receipt = self.export_receipt()
        receipt["snapshot_sha256"] = "0" * 64
        self.write_export_receipt(receipt)

        with self.assertRaisesRegex(MachineStatusTransportError, "snapshot_sha256"):
            self.import_artifact()

        self.assertEqual(self.destination_path.read_bytes(), prior)
        self.assertFalse(self.import_receipt_path.exists())

    def test_receipt_write_failure_restores_prior_destination(self) -> None:
        self.destination_path.parent.mkdir()
        prior = b'{"prior":true}\n'
        self.destination_path.write_bytes(prior)

        def failing_receipt_writer(path: Path, value: dict) -> None:
            if path == self.import_receipt_path:
                raise OSError("simulated receipt failure")
            from cfmi.machine_status import write_snapshot_atomic

            write_snapshot_atomic(path, value)

        with self.assertRaisesRegex(
            MachineStatusTransportError, "simulated receipt failure"
        ):
            import_machine_status_artifact(
                snapshot_path=self.snapshot_path,
                export_receipt_path=self.export_receipt_path,
                destination_path=self.destination_path,
                import_receipt_path=self.import_receipt_path,
                expected_node_id=NODE_ID,
                expected_computer_name=COMPUTER_NAME,
                expected_service_name=SERVICE_NAME,
                expected_pipeline_name=PIPELINE_NAME,
                expected_definition_id=DEFINITION_ID,
                expected_repository_type=REPOSITORY_TYPE,
                expected_repository_id=REPOSITORY_ID,
                expected_run_id=RUN_ID,
                expected_source_version=SOURCE_VERSION,
                now=NOW,
                snapshot_writer=failing_receipt_writer,
            )

        self.assertEqual(self.destination_path.read_bytes(), prior)
        self.assertFalse(self.import_receipt_path.exists())

    def test_wrong_identity_service_run_or_source_version_is_rejected(self) -> None:
        cases = (
            ("node_id", "other-node"),
            ("computer_name", "WRONG-HOST"),
            ("service_name", "other-service"),
            ("definition_id", "2401"),
            ("repository_type", "TfsGit"),
            ("repository_id", "other/repository"),
            ("run_id", "1446001"),
            ("source_version", "b" * 40),
        )
        for field, value in cases:
            with self.subTest(field=field):
                receipt = self.export_receipt()
                receipt[field] = value
                self.write_export_receipt(receipt)
                with self.assertRaises(MachineStatusTransportError) as failure:
                    self.import_artifact()
                self.assertEqual(failure.exception.category, "IDENTITY_MISMATCH")
                self.assertFalse(self.destination_path.exists())

    def test_unknown_receipt_fields_and_invalid_snapshot_are_rejected(self) -> None:
        receipt = self.export_receipt()
        receipt["terminal_command"] = "whoami"
        self.write_export_receipt(receipt)
        with self.assertRaisesRegex(
            MachineStatusTransportError, "unknown fields"
        ):
            self.import_artifact()

        receipt = self.export_receipt()
        self.snapshot_path.write_text('{"schema_version":2}', encoding="utf-8")
        receipt["snapshot_sha256"] = hashlib.sha256(
            self.snapshot_path.read_bytes()
        ).hexdigest()
        self.write_export_receipt(receipt)
        with self.assertRaises(MachineStatusTransportError):
            self.import_artifact()
        self.assertFalse(self.destination_path.exists())


if __name__ == "__main__":
    unittest.main()
