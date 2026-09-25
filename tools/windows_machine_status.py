"""Collect one bounded Windows machine-status snapshot."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfmi.machine_status import (  # noqa: E402
    MachineStatusError,
    collect_machine_snapshot,
    load_machine_status_config,
    run_internal_windows_probe,
    run_probe_subprocess,
    write_snapshot_atomic,
)
from cfmi.fleet_status import validate_fleet_snapshot  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path)
    parser.add_argument("--internal-probe", choices=("boot", "cpu", "memory", "disks", "service"))
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.internal_probe:
            if arguments.config is not None:
                raise MachineStatusError(
                    "INPUT_INVALID",
                    "--config cannot be combined with --internal-probe",
                )
            payload = json.load(sys.stdin)
            if not isinstance(payload, dict):
                raise MachineStatusError(
                    "INPUT_INVALID", "probe input must be an object"
                )
            result = run_internal_windows_probe(arguments.internal_probe, payload)
            print(json.dumps(result, allow_nan=False, sort_keys=True, separators=(",", ":")))
            return 0
        if arguments.config is None:
            raise MachineStatusError("INPUT_INVALID", "--config is required")
        if os.name != "nt":
            raise MachineStatusError(
                "CAPABILITY_MISSING", "Machine Doctor collection requires Windows"
            )
        config = load_machine_status_config(arguments.config)
        snapshot = collect_machine_snapshot(
            config,
            lambda name, payload, timeout: run_probe_subprocess(
                Path(__file__), name, payload, timeout
            ),
        )
        write_snapshot_atomic(
            config.output_path,
            validate_fleet_snapshot(snapshot),
        )
        print(
            json.dumps(
                {
                    "status": "SUCCEEDED",
                    "node_id": config.node_id,
                    "output_path": str(config.output_path),
                },
                sort_keys=True,
            )
        )
        return 0
    except (MachineStatusError, OSError, ValueError) as error:
        category = getattr(error, "category", "COLLECTION_FAILED")
        print(
            json.dumps(
                {"status": "FAILED", "category": category, "message": str(error)},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
