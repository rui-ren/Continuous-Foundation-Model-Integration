# Proposal: Continuous Foundation Model Integration

**Status:** Draft for review  
**Initial scope:** NVIDIA CUDA Execution Provider and TensorRT RTX Execution
Provider  
**Working name:** Continuous Foundation Model Integration (CFMI)

## 1. Executive summary

Foundation-model onboarding currently requires repeated manual work across model
selection, ONNX export, runtime compatibility, optimization, accuracy testing,
performance testing, packaging, and regression validation. Results can be
difficult to reproduce because they depend on model revisions, runtime
versions, hardware, local environments, and engineer-specific knowledge.

CFMI proposes a controlled automation platform that converts this workflow into
an auditable state machine. It will produce versioned artifacts, structured
test evidence, and an objective `SHIP`, `BLOCK`, or `REVIEW` recommendation.
Specialized agents may assist with model triage, failure diagnosis, and
experiment selection, while deterministic software owns execution and release
gates.

The pilot will focus on one supported model family and NVIDIA consumer hardware:

```text
Hugging Face model
    -> Mobius ONNX export
    -> CUDA EP correctness baseline
    -> Olive optimization and quantization
    -> TensorRT RTX execution
    -> accuracy, performance, and functionality gates
    -> release candidate
```

Three representative RTX laptops will be used initially. Expansion to the
larger laptop fleet and other execution providers will depend on measured pilot
results.

## 2. Problem statement

The current model-onboarding process has several recurring costs:

- Engineers repeatedly execute similar export, optimization, test, and
  packaging steps.
- Failures are diagnosed manually and useful knowledge remains in individual
  logs or engineer experience.
- Environment differences can make results difficult to compare or reproduce.
- Model, runtime, and package compatibility may be discovered late.
- Performance and accuracy evidence is not always captured in one consistent
  release record.
- Scaling the supported model catalog increases operational workload roughly in
  proportion to the number of models and hardware configurations.

The proposal does not assume that every step can be made autonomous. Its goal is
to automate repeatable work, make decisions evidence-based, and reserve human
attention for ambiguous failures and source-code changes.

## 3. Proposed outcome

At the end of the pilot, an engineer should be able to submit a pinned model
revision and receive:

1. A compatibility and resource assessment.
2. A reproducible ONNX artifact or an actionable export failure.
3. CUDA EP baseline accuracy and functionality results.
4. One or more bounded optimization experiments.
5. TensorRT RTX compatibility and performance results.
6. Results from representative RTX hardware classes.
7. A versioned evidence bundle and `SHIP`, `BLOCK`, or `REVIEW` recommendation.

All source changes, external pull requests, package publication, and production
release actions remain human-approved during the pilot.

## 4. Why NVIDIA first

Restricting the first implementation to the NVIDIA ecosystem reduces the
number of independent variables:

- CUDA EP provides a broadly applicable GPU correctness baseline.
- TensorRT RTX provides a focused optimization target for RTX hardware.
- The available RTX laptop fleet provides realistic hardware coverage without
  requiring a new production cluster.
- Common hardware and software concepts allow the team to develop reusable
  scheduling, benchmarking, and diagnostics before adding other execution
  providers.

The architecture will still expose an execution-provider interface so future
support does not require redesigning the orchestration system.

## 5. Goals

### Pilot goals

- Automate the happy path for one model family from pinned source revision to
  release recommendation.
- Establish CUDA EP as the correctness baseline.
- Validate an optimized TensorRT RTX path without exceeding defined quality
  loss.
- Execute jobs reproducibly across three representative RTX laptops.
- Capture artifacts, environment details, logs, metrics, and decisions in one
  run record.
- Classify common failures and recommend bounded next actions.
- Quantify time saved and identify the remaining manual bottlenecks.

### Longer-term goals

- Schedule work across the full available NVIDIA laptop fleet.
- Support additional model architectures and modalities.
- Add controlled source-patch and pull-request proposal workflows.
- Rebuild and validate dependent runtime or application packages when required.
- Add additional execution providers and hardware backends.
- Use historical outcomes to improve model triage and optimization search.

## 6. Non-goals for the pilot

- Automatically onboarding every newly published Hugging Face model.
- Unattended merging, package publication, or production release.
- Supporting every quantization algorithm or precision.
- Supporting multiple model modalities or unrelated architecture families.
- Comparing raw performance across unlike GPU classes.
- Training or fine-tuning models.
- Replacing runtime, exporter, or optimization test suites.
- Building a general-purpose agent framework.

## 7. Users and stakeholders

| Stakeholder | Need |
|---|---|
| Model onboarding engineer | Repeatable execution and actionable failures |
| Runtime engineer | Compatibility evidence and minimized reproductions |
| Performance engineer | Controlled benchmarks and comparable baselines |
| Release owner | Auditable ship/block evidence |
| Engineering manager | Throughput, cost, reliability, and adoption metrics |
| Security/repository owner | Controlled credentials and approved code changes |

## 8. Pilot user experience

An authorized engineer submits a manifest:

```yaml
model:
  repository: organization/model-name
  revision: immutable-commit-sha
  family: selected-pilot-family

targets:
  baseline: cuda
  optimized: tensorrt-rtx
  hardware_classes:
    - rtx-4060-laptop
    - second-representative-class
    - third-representative-class

constraints:
  maximum_accuracy_regression_percent: 1.0
  minimum_performance_improvement_percent: 10.0
  maximum_vram_mb: 8192
```

The system returns a dashboard or report containing:

- Current stage and complete state history
- Input and environment provenance
- Produced artifacts and checksums
- Accuracy, functionality, latency, throughput, memory, and stability results
- Comparisons only against valid hardware and software baselines
- Failure category, evidence, and recommended next action
- Final release recommendation and any required human approvals

## 9. Success metrics

Pilot baselines will be measured before implementation. Targets should be
confirmed after the baseline is known rather than selected only for appearance.

| Metric | Pilot target |
|---|---|
| Supported model-family happy path | End-to-end automated |
| Reproducibility | Same manifest produces equivalent gate decisions |
| Provenance | 100% of runs record model, software, hardware, and artifact versions |
| Manual execution time | At least 50% lower than measured baseline |
| Failure reporting | All failed stages produce a classified, actionable report |
| Fleet reliability | Interrupted or disconnected jobs recover without duplicate release decisions |
| Quality protection | No optimized artifact passes beyond configured regression threshold |
| Release safety | No source merge or publication occurs without human approval |

Secondary metrics include queue time, stage duration, cache reuse, worker
utilization, flaky-run rate, diagnosis acceptance rate, and onboarding lead
time.

## 10. Pilot plan

### Phase 0: Baseline and selection - Week 1

- Select one model family and one representative model.
- Document the current manual workflow and ownership boundaries.
- Measure current elapsed time, human time, success rate, and common failures.
- Pin supported driver, CUDA, ORT, TensorRT RTX, Olive, Mobius, and package
  versions.
- Define accuracy, functionality, memory, and performance gates.

**Exit:** approved manifest, environment matrix, metrics baseline, and gate
definitions.

### Phase 1: Single-machine deterministic pipeline - Weeks 2-3

- Implement the workflow state machine and run record.
- Integrate export, CUDA EP validation, one bounded optimization path, and
  TensorRT RTX validation.
- Store immutable artifacts and structured evidence.
- Produce a final release recommendation without autonomous code changes.

**Exit:** one model completes end-to-end on one machine with reproducible
results.

### Phase 2: Representative fleet - Week 4

- Install the worker service on three hardware classes.
- Register hardware/software capabilities.
- Add job leases, heartbeats, timeouts, retries, and artifact caching.
- Add hardware-aware scheduling and same-class performance comparison.

**Exit:** the same candidate completes required tests across three representative
workers, including recovery from an interrupted worker.

### Phase 3: Diagnosis assistance and demonstration - Weeks 5-6

- Add structured failure classification.
- Add an agent-assisted diagnosis summary grounded in logs and known remedies.
- Demonstrate successful and intentionally failing runs.
- Compare pilot results against the manual baseline.
- Recommend whether to expand, revise, or stop.

**Exit:** stakeholder demonstration, measured impact report, and next-phase
decision.

## 11. Required resources

### People

- One directly responsible engineer for the pilot.
- Part-time review from Mobius/export, Olive/optimization, runtime, performance,
  and release owners.
- A manager or product owner authorized to confirm priorities and success
  criteria.

### Infrastructure

- One coordinator service and persistent metadata store.
- Artifact storage with retention and access controls.
- Three initial RTX laptops with stable power and network access.
- Existing benchmark datasets and permitted model credentials.
- CI or service identities with least-privilege access.

The pilot should use existing infrastructure where practical. It should not
require all 20 laptops before demonstrating value.

## 12. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Project scope expands across models and runtimes | Pilot does not finish | Enforce one family, two EPs, three workers |
| Results vary by laptop power or thermal state | False regression decisions | Record power/thermal state; warm up; repeat; compare within hardware class |
| Driver and package version drift | Non-reproducible failures | Pin supported matrices and reject noncompliant workers |
| Unsupported ONNX operators or dynamic shapes | Export/runtime failure | Capability preflight and explicit unsupported classification |
| Optimization search consumes excessive compute | Fleet congestion | Bounded experiment budgets and early stopping |
| Accuracy tests do not represent product quality | Unsafe optimization | Agree on task-specific datasets and thresholds with owners |
| Agent proposes incorrect remediation | Wasted time or unsafe changes | Ground recommendations in evidence; require review; never merge automatically |
| Laptop disconnects or sleeps | Lost or duplicated work | Leases, checkpoints, idempotent jobs, and heartbeat expiration |
| Credentials or model licenses are mishandled | Security/compliance issue | Secret store, least privilege, license metadata, approved model allowlist |
| Platform becomes a custom CI replacement | High maintenance burden | Integrate existing CI, storage, and observability where possible |

## 13. Alternatives considered

### Continue manual onboarding

Lowest implementation cost, but recurring work and knowledge fragmentation
remain. This is acceptable if model onboarding volume is too low to recover the
pilot investment.

### Add scripts without orchestration

Useful for individual stages, but does not provide end-to-end state,
cross-machine scheduling, provenance, recovery, or a release decision. Stage
scripts should still be reused by CFMI.

### Build a fully autonomous multi-agent system immediately

Potentially impressive but carries high reliability and scope risk. The proposed
design instead makes agents advisory and keeps execution and release decisions
deterministic.

### Adopt a general workflow platform

An existing workflow system may provide scheduling and retries. The pilot should
evaluate reuse rather than building generic infrastructure; CFMI's unique value
is the model-specific contracts, gates, and diagnostics.

## 14. Decision requested

Approve a time-boxed 4-6 week pilot with:

- One selected model family
- CUDA EP and TensorRT RTX EP
- Three representative RTX laptops
- Existing approved evaluation datasets
- Named reviewers for export, runtime, performance, and release

At the end of the pilot, continue only if measured results demonstrate reduced
manual effort, reproducible evidence, and a credible path to supporting
additional models.

## 15. Suggested manager discussion

The proposal should be introduced as operational improvement and reusable
inference infrastructure, not as an agent demonstration:

> We repeatedly perform the same model export, optimization, compatibility, and
> regression work. I propose a bounded NVIDIA-first pilot that captures this
> process as a reproducible workflow and produces objective release evidence.
> Agents will assist diagnosis only where reasoning adds value; deterministic
> gates will protect quality and releases. After 4-6 weeks, we will compare
> onboarding time and reliability against the current manual baseline and decide
> whether expansion is justified.
