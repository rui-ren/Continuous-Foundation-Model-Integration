"""Serve read-only CFMI fleet evidence over MCP stdio."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfmi.fleet_status import (  # noqa: E402
    FleetEvidenceError,
    FleetStatusReader,
    read_local_system_status,
)


SERVER_NAME = "cfmi-fleet-status"
SERVER_VERSION = "0.1.0"
DEFAULT_PROTOCOL_VERSION = "2025-06-18"

TOOLS = (
    {
        "name": "list_nodes",
        "description": "List known fleet nodes with explicit evidence freshness.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "destructiveHint": False},
    },
    {
        "name": "get_node_status",
        "description": "Get reachability, host, and workload evidence for one node.",
        "inputSchema": {
            "type": "object",
            "properties": {"node_id": {"type": "string", "minLength": 1}},
            "required": ["node_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False},
    },
    {
        "name": "get_job_progress",
        "description": "Get the last reported progress evidence for one workload.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string", "minLength": 1},
                "workload_id": {"type": "string", "minLength": 1},
            },
            "required": ["node_id", "workload_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False},
    },
    {
        "name": "get_local_system_status",
        "description": "Read this superadmin machine's physical-memory usage.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "destructiveHint": False},
    },
)


def _reader() -> FleetStatusReader:
    configured_path = os.environ.get("CFMI_FLEET_STATUS_PATH")
    if not configured_path:
        raise FleetEvidenceError(
            "RESOURCE_UNAVAILABLE", "CFMI_FLEET_STATUS_PATH is not configured"
        )
    return FleetStatusReader(Path(configured_path))


def _tool_result(payload: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    payload, allow_nan=False, sort_keys=True, separators=(",", ":")
                ),
            }
        ],
        "structuredContent": payload,
        "isError": is_error,
    }


def _call_tool(name: object, arguments: object) -> dict[str, Any]:
    if not isinstance(name, str):
        return _tool_result(
            {"category": "INPUT_INVALID", "message": "tool name must be a string"},
            is_error=True,
        )
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return _tool_result(
            {"category": "INPUT_INVALID", "message": "tool arguments must be an object"},
            is_error=True,
        )
    try:
        if name == "get_local_system_status":
            if arguments:
                raise FleetEvidenceError(
                    "INPUT_INVALID", "get_local_system_status does not accept arguments"
                )
            return _tool_result(read_local_system_status())
        reader = _reader()
        if name == "list_nodes":
            if arguments:
                raise FleetEvidenceError(
                    "INPUT_INVALID", "list_nodes does not accept arguments"
                )
            return _tool_result(reader.list_nodes())
        if name == "get_node_status":
            return _tool_result(reader.get_node_status(arguments.get("node_id")))
        if name == "get_job_progress":
            return _tool_result(
                reader.get_job_progress(
                    arguments.get("node_id"), arguments.get("workload_id")
                )
            )
        raise FleetEvidenceError("INPUT_INVALID", f"unknown read-only tool: {name}")
    except FleetEvidenceError as error:
        return _tool_result(
            {"category": error.category, "message": str(error)}, is_error=True
        )


def handle_request(request: object) -> dict[str, Any] | None:
    if not isinstance(request, dict):
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32600, "message": "Invalid Request"},
        }
    request_id = request.get("id")
    method = request.get("method")
    if not isinstance(method, str):
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32600, "message": "Invalid Request"},
        }
    if request_id is None:
        return None
    if method == "initialize":
        params = request.get("params")
        requested_version = (
            params.get("protocolVersion") if isinstance(params, dict) else None
        )
        protocol_version = (
            requested_version
            if isinstance(requested_version, str)
            else DEFAULT_PROTOCOL_VERSION
        )
        result = {
            "protocolVersion": protocol_version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": list(TOOLS)}
    elif method == "tools/call":
        params = request.get("params")
        if not isinstance(params, dict):
            result = _tool_result(
                {"category": "INPUT_INVALID", "message": "params must be an object"},
                is_error=True,
            )
        else:
            result = _call_tool(params.get("name"), params.get("arguments"))
    else:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def main() -> int:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            }
        else:
            response = handle_request(request)
        if response is not None:
            sys.stdout.write(
                json.dumps(response, allow_nan=False, separators=(",", ":")) + "\n"
            )
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
