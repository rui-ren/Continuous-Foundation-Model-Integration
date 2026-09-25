from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from cfmi.fleet_status import FleetEvidenceError, FleetStatusReader
from tools.check import ROOT


NOW = datetime(2026, 9, 24, 20, 0, 0, tzinfo=timezone.utc)


def fleet_snapshot(*, observed_at: str | None = "2026-09-24T19:59:30Z") -> dict:
    return {
        "schema_version": 1,
        "source": "test-fixture",
        "nodes": [
            {
                "node_id": "bench-01",
                "observed_at": observed_at,
                "reachability": {"status": "reachable"},
                "host": {"status": "healthy"},
                "workloads": [
                    {
                        "workload_id": "job-01",
                        "status": "running",
                        "observed_at": observed_at,
                        "progress": {"step": 12},
                    }
                ],
            }
        ],
    }


class FleetStatusReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.path = Path(self.temporary_directory.name) / "fleet.json"

    def write_snapshot(self, snapshot: dict) -> None:
        self.path.write_text(json.dumps(snapshot), encoding="utf-8")

    def reader(self) -> FleetStatusReader:
        return FleetStatusReader(self.path, now=lambda: NOW)

    def test_live_node_and_workload_report_explicit_freshness(self) -> None:
        self.write_snapshot(fleet_snapshot())
        listed = self.reader().list_nodes()
        self.assertEqual(listed["snapshot_source"], "test-fixture")
        self.assertEqual(listed["nodes"][0]["evidence_state"], "live")
        self.assertEqual(listed["nodes"][0]["age_seconds"], 30)

        progress = self.reader().get_job_progress("bench-01", "job-01")
        self.assertEqual(progress["evidence_state"], "live")
        self.assertEqual(progress["progress"], {"step": 12})

    def test_old_observation_is_stale_not_live(self) -> None:
        self.write_snapshot(fleet_snapshot(observed_at="2026-09-24T19:55:00Z"))
        status = self.reader().get_node_status("bench-01")
        self.assertEqual(status["evidence_state"], "stale")
        self.assertEqual(status["age_seconds"], 300)

    def test_fractional_age_over_threshold_is_stale(self) -> None:
        self.write_snapshot(fleet_snapshot(observed_at="2026-09-24T20:00:00Z"))
        reader = FleetStatusReader(
            self.path,
            now=lambda: datetime(
                2026, 9, 24, 20, 1, 30, 900000, tzinfo=timezone.utc
            ),
        )
        status = reader.get_node_status("bench-01")
        self.assertEqual(status["evidence_state"], "stale")
        self.assertEqual(status["age_seconds"], 90)

    def test_missing_timestamp_is_missing_not_healthy_evidence(self) -> None:
        self.write_snapshot(fleet_snapshot(observed_at=None))
        status = self.reader().get_node_status("bench-01")
        self.assertEqual(status["evidence_state"], "missing")
        self.assertIsNone(status["age_seconds"])

    def test_future_observation_is_rejected(self) -> None:
        self.write_snapshot(fleet_snapshot(observed_at="2026-09-24T20:00:06Z"))
        with self.assertRaisesRegex(FleetEvidenceError, "future"):
            self.reader().get_node_status("bench-01")

    def test_missing_file_and_unknown_identifiers_fail_explicitly(self) -> None:
        with self.assertRaisesRegex(FleetEvidenceError, "does not exist") as missing:
            self.reader().list_nodes()
        self.assertEqual(missing.exception.category, "RESOURCE_UNAVAILABLE")

        self.write_snapshot(fleet_snapshot())
        with self.assertRaisesRegex(FleetEvidenceError, "unknown node_id"):
            self.reader().get_node_status("unknown")
        with self.assertRaisesRegex(FleetEvidenceError, "unknown workload_id"):
            self.reader().get_job_progress("bench-01", "unknown")

    def test_duplicate_nodes_and_invalid_status_are_rejected(self) -> None:
        duplicate = fleet_snapshot()
        duplicate["nodes"].append(duplicate["nodes"][0])
        self.write_snapshot(duplicate)
        with self.assertRaisesRegex(FleetEvidenceError, "duplicate node_id"):
            self.reader().list_nodes()

        invalid = fleet_snapshot()
        invalid["nodes"][0]["host"]["status"] = "fine"
        self.write_snapshot(invalid)
        with self.assertRaisesRegex(FleetEvidenceError, "host.status must be one of"):
            self.reader().list_nodes()

    def test_unknown_schema_version_is_rejected(self) -> None:
        snapshot = fleet_snapshot()
        snapshot["schema_version"] = 3
        self.write_snapshot(snapshot)
        with self.assertRaisesRegex(FleetEvidenceError, "schema_version must be one of"):
            self.reader().list_nodes()

    def test_invalid_utf8_and_non_finite_numbers_are_rejected(self) -> None:
        self.path.write_bytes(b"\xff")
        with self.assertRaisesRegex(FleetEvidenceError, "not UTF-8"):
            self.reader().list_nodes()

        self.path.write_text(
            '{"schema_version":1,"source":"test","nodes":[],'
            '"invalid_number":NaN}',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(FleetEvidenceError, "not valid JSON"):
            self.reader().list_nodes()


class FleetStatusMcpTests(unittest.TestCase):
    def run_server(self, requests: list[dict], *, evidence_path: Path) -> list[dict]:
        environment = os.environ.copy()
        environment["CFMI_FLEET_STATUS_PATH"] = str(evidence_path)
        completed = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "fleet_status_mcp.py")],
            input="".join(json.dumps(request) + "\n" for request in requests),
            text=True,
            capture_output=True,
            check=True,
            env=environment,
        )
        self.assertEqual(completed.stderr, "")
        return [json.loads(line) for line in completed.stdout.splitlines()]

    def test_server_advertises_only_four_read_only_tools(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            responses = self.run_server(
                [
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {"protocolVersion": "2025-06-18"},
                    },
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                ],
                evidence_path=Path(directory) / "missing.json",
            )
        self.assertEqual(responses[0]["result"]["serverInfo"]["name"], "cfmi-fleet-status")
        tools = responses[1]["result"]["tools"]
        self.assertEqual(
            [tool["name"] for tool in tools],
            [
                "list_nodes",
                "get_node_status",
                "get_job_progress",
                "get_local_system_status",
            ],
        )
        self.assertTrue(all(tool["annotations"]["readOnlyHint"] for tool in tools))
        self.assertTrue(all(not tool["annotations"]["destructiveHint"] for tool in tools))

    def test_tool_call_returns_structured_data_and_explicit_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fleet.json"
            path.write_text(json.dumps(fleet_snapshot()), encoding="utf-8")
            responses = self.run_server(
                [
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": "list_nodes", "arguments": {}},
                    },
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {
                            "name": "get_local_system_status",
                            "arguments": {},
                        },
                    },
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {"name": "restart_node", "arguments": {}},
                    },
                ],
                evidence_path=path,
            )
        self.assertFalse(responses[0]["result"]["isError"])
        self.assertEqual(
            responses[0]["result"]["structuredContent"]["nodes"][0]["node_id"],
            "bench-01",
        )
        local_memory = responses[1]["result"]["structuredContent"]["memory"]
        self.assertGreater(local_memory["total_bytes"], 0)
        self.assertGreaterEqual(local_memory["used_bytes"], 0)
        self.assertLessEqual(local_memory["used_bytes"], local_memory["total_bytes"])
        self.assertTrue(responses[2]["result"]["isError"])
        self.assertEqual(
            responses[2]["result"]["structuredContent"]["category"], "INPUT_INVALID"
        )


if __name__ == "__main__":
    unittest.main()
