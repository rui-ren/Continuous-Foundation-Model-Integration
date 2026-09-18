---
name: implementing-a-stage
description: Use when implementing or modifying a CFMI stage contract, adapter, or its tests.
---

# Implementing a CFMI stage

1. Read `AGENTS.md`, the task, and the relevant technical-design contract.
   Identify inputs, outputs, failure categories, environment requirements, and
   budget boundaries. Resolve missing prerequisites rather than guessing a
   model revision, GPU capability, or quality threshold.
2. Check for an existing adapter/helper. Keep runtime-specific behavior behind
   the stage boundary; do not add a registry or service for a single adapter.
3. Implement the bounded behavior and tests for success, invalid input,
   stage failure, and missing evidence. Preserve prior attempts and immutable
   checksums. A test double belongs in tests and cannot certify actual export.
4. Run `python -m tools.check --pattern test_contracts.py` when working on
   contracts, then `python -m tools.check`.
   For another test file, use its actual filename as the pattern.
5. If real model execution is in scope, obtain the required approved
   environment and manifest. CPU tests alone do not satisfy GPU acceptance.
   Stop and record a blocker if the needed capability is unavailable.
6. Hand off the diff with commands, test counts/results, evidence references,
   and unexecuted checks. Request independent review of policy/reference-data
   changes; do not silently expand the task.
