# CFMI Engineering Design Brainstorm

**Status:** Initial design brainstorm

**Scope:** Single-machine NVIDIA experiment; optional fleet expansion

Design CFMI as a deterministic control plane with replaceable stage adapters.
Agents should assist selected decisions; they should not own workflow state or
release gates.

This document records implementation proposals, decision rationale, and slice
exit criteria. The [technical design](technical-design.md) is the canonical home
for lifecycle contracts, schemas, and workflow states. The refinements below
remain proposals until approved and incorporated into those contracts; they are
not a second schema specification.

## Immediate delivery boundary

Time-box the experiment to 4-6 calendar weeks with an explicit engineering-hour
and compute cap agreed before starting. Deliver one pinned model on one RTX
machine, source-to-export correctness evidence, one reviewed optimization
configuration, deterministic gates, and a reproducible report. A classified
compatibility blocker is a useful experimental outcome, not a reason to build a
larger platform.

Use existing scripts or CI with a persisted run record and checksummed artifacts.
Do not require a new coordinator service, database, dashboard, discovery service,
or distributed scheduler. Diagnosis assistance is optional and follows a useful
scripted baseline. Stop at the cap and report results and limitations; expansion
requires a separate decision.

The component map and later slices below describe available extensions, not a
mandatory backlog. Run the first robotics experiment in parallel as described
in the [research roadmap](research-roadmap.md#13-recommended-progression).

## 1. Engineering decomposition

| Part | Pilot proposal | Later extension |
|---|---|---|
| **Candidate intake** | Accept a manually submitted, immutable Hugging Face revision and validate license, architecture, size, and required files | Daily discovery and ranking based on demand, novelty, compatibility, popularity, and hardware fit |
| **Orchestrator** | Explicit persisted transitions in existing scripts or CI, with idempotent stages, retries, budgets, and approvals | Dedicated workflow service, adaptive experiments, and concurrent campaigns |
| **Metadata store** | Persist run inputs, stage results, policies, metrics, failures, and decisions using existing storage | PostgreSQL or an internal service for concurrent work and historical queries |
| **Artifact store** | Content-addressed storage for model snapshots, ONNX graphs, optimized variants, TensorRT artifacts, logs, and reports | Cross-project artifact catalog and lineage graph |
| **Worker service** | Isolated local execution on one RTX machine with environment checks and artifact verification | Three-machine service with leases and heartbeats; later fleet and Jetson workers |
| **Scheduler** | Validate the explicitly selected local target; no distributed queue required | Capability matching, leases, capacity scheduling, and preemption |
| **Transformer** | Mobius adapter exporting one model family to ONNX with a structured compatibility report | Additional exporters, VLM/VLA compilation, and graph-repair proposals |
| **Optimizer** | Olive adapter executing one reviewed precision or quantization configuration | Bounded FP16/quantization comparison, then multi-objective search |
| **Executor** | Pinned source-model reference execution, CUDA EP export baseline, and TensorRT RTX EP optimized target | Other EPs, TensorRT/Jetson, simulator, and robot execution |
| **Evaluator** | Source-to-export parity, optimized-path quality, functional tests, latency, throughput, VRAM, initialization time, and stability | Interactive VLA episodes, safety metrics, trajectories, and sim-to-real evaluation |
| **Gate engine** | Versioned deterministic policies returning `PASS`, `FAIL`, or `REVIEW` | Product-specific policies and staged deployment gates |
| **Diagnosis/remediation** | Typed failure taxonomy, known-fix catalog, and evidence-grounded agent recommendations | Reviewed patches, adaptive retries, data requests, training, and teleoperation actions |
| **Reporting** | One evidence bundle and dashboard per run with provenance, comparisons, failures, and recommendation | Portfolio-level trends, compatibility maps, and optimization knowledge |
| **Security/governance** | Allowlisted models, pinned revisions, least-privilege identities, secret isolation, audit logs, and human-controlled publication | Policy automation and signed supply-chain attestations |
| **Observability** | Structured logs, stage metrics, distributed traces, fleet health, and GPU-hour accounting | Automated anomaly and flaky-benchmark detection |

## 2. Contract ownership

Implement adapters against the technical design's
[generic lifecycle boundary](technical-design.md#31-generic-lifecycle-boundary)
and [domain model](technical-design.md#32-domain-model), rather than coupling the
coordinator to exporter or runtime APIs.

Use the existing [core data contracts](technical-design.md#6-core-data-contracts)
as the starting drafts. Before implementation, extend and approve them to capture
source-reference provenance, run/experiment/attempt identity, shared remediation
budgets, and exact artifact-to-target evidence. Keep model artifacts generic;
ONNX and TensorRT are pilot formats, not coordinator-level assumptions.

## 3. Recommended pilot workflow

Use the canonical [workflow state model](technical-design.md#5-workflow-state-model),
including its retry, review, blocked, failed, and cancellation paths. The
following describes work and transition conditions within those states, not new
state names.

### 3.1 Establish correctness before optimization

During preflight, resolve a pinned source-model reference implementation and
evaluation plan. Capture the source execution environment and reference outputs
as evidence. In `CUDA_VALIDATION`, compare the exported model against that
reference using identical evaluation inputs, tokenizer, preprocessing, and
generation settings where applicable.

Require both source-to-export parity and absolute task-quality/functionality
thresholds before entering `OPTIMIZING`. Define numerical tolerances and
task-level acceptance rules in the frozen policy; do not require bitwise
identity for inherently nondeterministic execution. Missing reference evidence
requires review and cannot establish a passing baseline.

Compare each optimized artifact against the accepted CUDA baseline and the
mandatory absolute quality thresholds. Agreement between CUDA and TensorRT
alone cannot establish that the original export was correct.

### 3.2 Separate attempts, experiments, and linked runs

| Unit | Proposed boundary |
|---|---|
| Attempt | Re-executes a stage with identical declared inputs and configuration after a retryable failure; records a new attempt without replacing earlier evidence |
| Experiment | Executes a distinct configuration explicitly permitted by the run's frozen optimization plan; owns its artifacts, stage attempts, and results |
| Linked run | Changes the source, evaluation suite, policy, target requirements, or configuration outside the approved plan; preserves the prior run and records the reason and any required approval |

Materialize each experiment configuration immutably before execution. A retry
may use another worker only within the declared compatibility and comparison
requirements; record the actual environment for every attempt.

All attempts and experiments consume the run's applicable attempt, elapsed-time,
and compute allowances. Remediation-linked runs also share a lineage-level
budget: creating a new run does not reset it. The coordinator reserves capacity
before dispatching concurrent work and accounts for failed or interrupted work.
Unknown consumption requires reconciliation before more work is authorized.
Budget increases require an explicit, audited human decision.

### 3.3 Select and validate a release variant

The immediate experiment has one optimized variant and one required target.
The same evidence rules apply if a separately approved expansion adds targets
or fans out into reviewed FP16 and quantization experiments.
Use a selection rule fixed in the run plan to nominate a variant after initial
TensorRT RTX validation. Evaluate that variant across every required hardware
class, with a comparable CUDA performance baseline in each class.

For any approved fleet expansion, require one logical model variant and
precision configuration across all required classes. Target-specific compiled artifacts are allowed,
but must derive from that variant and carry their compatibility keys. Selecting
different quantization variants per class is deferred.

The release evidence matrix identifies the selected variant, exact executable
artifact checksum, target class, environment, suite, policy, and baseline for
each required cell. The gate evaluates that complete matrix, not a mixture of
the best results from different experiments. Missing or invalid required
evidence prevents `PASS`; an unambiguous mandatory failure yields `FAIL`,
otherwise incomplete evidence yields `REVIEW`.

If the selected variant fails fleet validation, another variant may be tried
only within the frozen plan and remaining budget. Its required matrix must be
completed before gating. Human release approval binds to the exact passing
artifact set and evidence bundle; changing either requires a new decision.

## 4. Important design decisions

1. **Use an existing workflow engine if available.** Do not build generic
   queues, retries, and dashboards unless internal infrastructure cannot provide
   them.
2. **Start with explicit submissions.** Hugging Face polling is low-value until
   the onboarding path reliably handles selected models.
3. **Separate quality from performance.** Validate the CUDA export against the
   source-model reference first. TensorRT RTX must preserve accepted quality
   while improving the explicit optimization objective.
4. **Compare within hardware classes.** A 4060 and 5090 provide coverage, not a
   valid direct regression baseline.
5. **Treat optimization as constrained search.** Optimize latency, throughput,
   and memory subject to mandatory quality and functionality constraints.
6. **Make remediation bounded.** Attempts, experiments, and linked remediation
   runs consume explicit allowances; an agent cannot reset budgets or relax gates.
7. **Capture failures as research data.** Preserve sanitized inputs, evidence,
   root cause, attempted remedies, and outcomes from the beginning.

## 5. Implementation slices and exit criteria

| Slice | Scope | Exit criteria |
|---|---|---|
| **1. Foundation** | Minimal approved contracts, persisted run state, artifact lineage, deterministic gates, and budget accounting using existing scripts or CI | Duplicate results cannot advance a run twice; changed inputs preserve history; missing evidence cannot pass; linked runs cannot reset remediation budgets |
| **2. Single-machine vertical slice** | One pinned model through source-reference execution, Mobius, CUDA EP, one reviewed Olive configuration, TensorRT RTX, and a report; include typed failures, environment fingerprints, job isolation, secret isolation, and benchmark controls | Produce a complete evidence bundle; reject an intentionally incorrect export and a faster but quality-regressed variant; repeated valid measurements follow the approved comparability and variance policy |
| **3. Fleet (optional expansion)** | Capability registration, scheduling, leases, interruption recovery, and three laptop classes | Complete the required artifact-to-target matrix; reject stale lease results; recover from disconnects without duplicate decisions; invalid power or thermal conditions cannot produce passing benchmark evidence |
| **4. Reliability hardening** | Broader failure injection, reproducibility coverage, retention, security controls, and operational observability | Coordinator restart, cancellation, and partial-upload scenarios preserve ownership, immutable history, and budgets; incomplete artifacts cannot be selected for release |
| **5. Agent assistance** | Diagnosis on a reviewed failure corpus, then bounded remediation experiments | Recommendations cite approved evidence; attempted gate or budget changes are rejected; execution remains subject to coordinator policy and required approvals |
| **6. Research evaluation** | Manual versus scripted versus agent-assisted comparison with ablations and cost accounting | Compare equivalent model/workload cohorts using predefined outcomes, including quality, failures, engineer time, elapsed time, and compute cost |

Slices 1-2 plus a manual-versus-scripted results report are the immediate
deliverable. Slices 3-6 are independently justified extensions, not sequential
requirements for starting robotics or completing the time box. Compare agents
only if an agent-assisted condition was actually implemented.

## 6. Implementation invariants

Use these as cross-slice acceptance conditions alongside the technical design's
[testing strategy](technical-design.md#12-testing-strategy):

- Optimization cannot start until source-to-export correctness and baseline
  quality pass.
- Every accepted result identifies immutable inputs, its experiment and attempt,
  output artifacts, and the actual execution environment.
- Local execution has a single authoritative run writer. If distributed workers
  are introduced, only the current job lease owner may submit an authoritative
  result; duplicate or stale submissions cannot advance state or overwrite
  accepted evidence.
- Retries and remediation cannot erase failures, reset shared budgets, or weaken
  the frozen policy.
- A release decision requires valid evidence for every mandatory target and
  approval bound to the exact selected artifacts.

## 7. First detailed design session

Review and approve the existing technical-design drafts rather than creating
parallel specifications:

1. **Run manifest:** freeze reference execution, evaluation settings, tolerances,
   target matrix, experiment selection rule, and run/lineage budget boundaries.
2. **Workflow state machine:** define baseline-gate prerequisites, experiment
   fan-out and selection, fleet aggregation, and retry/review/cancellation
   transitions using the canonical state names.
3. **Artifact model:** represent source-reference evidence, logical variants,
   target-specific compiled outputs, compatibility keys, and release evidence
   bindings.
4. **Stage-result contract:** specify run/experiment/attempt identity, lease
   ownership, typed failures, provenance, budget consumption, and authoritative
   result acceptance.

Record these decisions in the canonical technical design before implementing
slice 1. This document then tracks their rationale and delivery exit criteria.
