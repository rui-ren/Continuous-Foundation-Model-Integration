# CFMI Engineering Design Brainstorm

**Status:** Initial design brainstorm

**Scope:** Single-machine NVIDIA experiment; optional fleet expansion

Design CFMI as a deterministic control plane with replaceable stage adapters.
Agents should assist selected decisions; they should not own workflow state or
release gates.

**Agents propose; deterministic gates decide from measured evidence.** Passing
finite evaluations is evidence of meeting the declared policy, not proof of
universal correctness.

This document records implementation proposals, decision rationale, and slice
exit criteria. The [technical design](technical-design.md) is the canonical home
for lifecycle contracts, schemas, and workflow states. The refinements below
remain proposals until approved and incorporated into those contracts; they are
not a second schema specification.

## Immediate delivery boundary

Time-box the experiment to 4-6 calendar weeks with an explicit engineering-hour
and compute cap agreed before starting. Deliver one pinned model on one RTX
machine, source-to-export correctness evidence, one reviewed optimization
configuration, deterministic gates, failure-case records, and a reproducible
report. A classified compatibility blocker is a useful experimental outcome,
not a reason to build a larger platform.

Use existing scripts or CI with a persisted run record and checksummed artifacts.
Do not require a new coordinator service, database, dashboard, discovery service,
or distributed scheduler. After a useful scripted baseline, the preferred
research extension is failure-corpus curation, agent diagnosis, bounded
remediation, and comparative evaluation, not fleet infrastructure. Agent work
remains conditional on useful failures and remaining budget; it is not an added
minimum deliverable. Stop at the cap and report results and limitations;
expansion requires a separate decision.

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
| **Failure corpus** | Versioned `FailureCase` artifacts captured from the first execution, with sanitized evidence and explicit label status | Curated held-out cases and a shareable benchmark where permissions and evidence support it |
| **Diagnosis/remediation** | Typed failures and recorded human/scripted diagnoses; conditional agent study after the baseline | Evidence-grounded agent diagnosis, approved bounded remediation, then reviewed patches or data/training proposals |
| **Reporting** | One evidence bundle and report per run with provenance, comparisons, failures, and recommendation | Dashboard, portfolio-level trends, compatibility maps, and optimization knowledge |
| **Security/governance** | Allowlisted models, pinned revisions, least-privilege identities, secret isolation, audit logs, and human-controlled publication | Policy automation and signed supply-chain attestations |
| **Observability** | Structured logs, stage metrics, and time/compute accounting | Distributed traces, fleet health, and automated anomaly or flaky-benchmark detection |

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

### 2.1 Failure cases as first-class artifacts

Capture a `FailureCase` from the first failed execution, including interrupted
or unsuccessful remediation. A versioned structured record in existing artifact
storage is sufficient; no benchmark service or new database is required.

| Evidence group | Proposed contents |
|---|---|
| Identity and reproduction | Case ID and revision; real or injected origin; model revision and architecture; run, experiment, and attempt references; input/configuration checksums; reproducer |
| Artifact and environment | Relevant artifact or graph fingerprints, if produced; dependency and hardware fingerprints; stage; sanitized error and log references |
| Diagnosis | Failure category; suspected causes; human and agent diagnoses recorded separately with author/model version, evidence references, and timestamps |
| Label status | Unknown, suspected, or human-verified root cause; reviewer and supporting evidence for verified labels |
| Remediation | Proposed versus executed actions; configuration or patch provenance; approvals; attempt and linked-run references |
| Cost and outcome | Human active time, elapsed time, compute and agent cost; consumed budgets; unresolved or resolved status backed by gate results |

Missing artifacts and unknown root causes stay explicit; do not invent a graph
fingerprint for a pre-export failure or promote an agent hypothesis to ground
truth. Append diagnoses and outcomes through new case revisions without
overwriting the original evidence. A passing repair alone does not establish
the root cause.

Separate private evidence from material approved for sharing. A useful internal
corpus is not automatically a publishable benchmark: broader claims require
reproducible cases, credible reviewed labels, sufficient diversity, leakage
controls, and permission to redistribute models, inputs, and diagnostic evidence.

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
7. **Capture failures as research data.** Create versioned `FailureCase`
   artifacts from day one, separating hypotheses from verified labels and
   recording unsuccessful remedies as well as successful ones.

## 5. Implementation slices and exit criteria

| Slice | Scope | Exit criteria |
|---|---|---|
| **1. Foundation** | Minimal approved contracts including `FailureCase`, persisted run state, artifact lineage, deterministic gates, and budget accounting using existing scripts or CI | Duplicate results cannot advance a run twice; changed inputs preserve history; missing evidence cannot pass; linked runs cannot reset remediation budgets |
| **2. Single-machine vertical slice** | One pinned model through source-reference execution, Mobius, CUDA EP, one reviewed Olive configuration, TensorRT RTX, and a report; capture failures with typed errors, environment fingerprints, job/secret isolation, interruption accounting, and benchmark controls | Produce a complete evidence bundle; reject an intentionally incorrect export and a faster but quality-regressed variant; failed stages produce traceable cases; interrupted execution preserves evidence and budgets |
| **3. Corpus curation and agent diagnosis (conditional)** | Reproduce captured cases, review labels, define comparison conditions, split development and held-out cases, then implement evidence-grounded diagnosis | Freeze the evaluation protocol before agent tuning; hypotheses cite evidence; unknown labels remain explicit; held-out answers are unavailable to the agent |
| **4. Bounded remediation (conditional)** | Execute only approved actions through the existing workflow with immutable artifacts and shared budgets | Reject policy or budget bypasses; changes require applicable approvals and re-enter all affected correctness gates; record failed, exhausted, and successful remedies |
| **5. Comparative research evaluation (conditional)** | Human versus scripted versus agent-assisted comparison on held-out cases using the protocol below | Report diagnosis and verified remediation outcomes, quality violations, human time, elapsed time, and cost, including unresolved cases and limitations |

Slices 1-2 plus captured failure cases and a manual-versus-scripted results
report are the immediate deliverable. Slices 3-5 are the preferred research
extension only when the evidence and budget justify them. Compare agents only
if an agent-assisted condition was actually implemented.

Fleet validation, dashboards, dedicated coordinator/database services, and
distributed scheduling are optional branches, not steps before the agent study.
Add fleet support only when a specific experiment needs multi-device evidence;
then require capability matching, lease ownership, and disconnect recovery.
Broader reliability hardening can follow demonstrated need, but local isolation,
immutable evidence, interruption accounting, and deterministic gates are
mandatory from the first executable slice. Repeated benchmark measurements must
meet the approved comparability and variance policy; invalid power or thermal
conditions cannot produce passing performance evidence.

### 5.1 Comparative evaluation protocol

Before building or tuning the diagnosis agent, fix the question: how effectively
can each condition diagnose and remediate integration failures under the same
quality, action, and resource constraints?

- Give human, scripted, and agent-assisted conditions equivalent starting
  evidence, environment access, permitted actions, and time/compute limits.
  Record human assistance and agent-service cost separately.
- Split development and held-out cases by shared underlying failure/reproducer
  lineage, not by individual retry. Keep verified causes and successful fixes
  out of held-out prompts, retrieval, and tuning; reset artifacts and execution
  state between conditions to prevent cross-condition answer leakage.
- Freeze gates, success definitions, stopping rules, and the action catalog.
  Score diagnosis correctness only against reviewed labels; report unlabeled
  cases separately rather than treating agreement as ground truth.
- Count remediation success only after the proposed action is executed and all
  affected mandatory gates pass. Include failures, budget exhaustion, quality
  violations, and review outcomes in the results.
- Report real and injected failures separately, case counts, repeated trials
  where outcomes vary, and uncertainty. Limit conclusions to the observed
  models, environments, and failure families.

### 5.2 Robotics proceeds independently

Start the narrow robotics reference experiment now, not after slices 2 or 5.
Reuse evidence and evaluation mechanisms when they help; a shared interface
alone does not demonstrate generalization. Jetson is an execution target and
Isaac Lab is an evaluation environment, not interchangeable adapters.

Observation/action compatibility, control frequency, reset and termination
semantics, and trajectory capture need explicit domain-specific contracts.
Establish one supported policy/task baseline before changing precision or
runtime, and treat export, TensorRT support, and edge deployment as separate
compatibility milestones. Physical trials require separate safety review.

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
   bindings; include versioned `FailureCase` evidence and separate diagnosis
   hypotheses from reviewed root-cause labels.
4. **Stage-result contract:** specify run/experiment/attempt identity, lease
   ownership, typed failures, provenance, budget consumption, and authoritative
   result acceptance.

Record these decisions in the canonical technical design before implementing
slice 1. This document then tracks their rationale and delivery exit criteria.
