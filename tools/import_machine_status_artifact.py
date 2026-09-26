"""Import a validated Machine Doctor pipeline artifact for the central MCP."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfmi.machine_status_transport import (  # noqa: E402
    MachineStatusTransportError,
    import_machine_status_artifact,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--export-receipt", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--import-receipt", type=Path, required=True)
    parser.add_argument("--expected-node-id", required=True)
    parser.add_argument("--expected-computer-name", required=True)
    parser.add_argument("--expected-service-name", required=True)
    parser.add_argument("--expected-pipeline-name", required=True)
    parser.add_argument("--expected-definition-id", required=True)
    parser.add_argument("--expected-repository-type", required=True)
    parser.add_argument("--expected-repository-id", required=True)
    parser.add_argument("--expected-run-id", required=True)
    parser.add_argument("--expected-source-version", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        receipt = import_machine_status_artifact(
            snapshot_path=arguments.snapshot,
            export_receipt_path=arguments.export_receipt,
            destination_path=arguments.destination,
            import_receipt_path=arguments.import_receipt,
            expected_node_id=arguments.expected_node_id,
            expected_computer_name=arguments.expected_computer_name,
            expected_service_name=arguments.expected_service_name,
            expected_pipeline_name=arguments.expected_pipeline_name,
            expected_definition_id=arguments.expected_definition_id,
            expected_repository_type=arguments.expected_repository_type,
            expected_repository_id=arguments.expected_repository_id,
            expected_run_id=arguments.expected_run_id,
            expected_source_version=arguments.expected_source_version,
        )
    except (MachineStatusTransportError, OSError, ValueError) as error:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "category": getattr(error, "category", "IMPORT_FAILED"),
                    "message": str(error),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
