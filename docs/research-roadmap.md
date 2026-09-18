# CFMI Research and Robotics Roadmap

**Status:** Exploratory

**Execution model:** Start a narrow robotics experiment in parallel with bounded
CFMI work. Robotics is not dependent on completing the inference pilot or fleet.

## Immediate research focus

> How do precision and inference latency affect closed-loop task success for
> one robot policy?

Choose one policy checkpoint, one manipulation task, and one compatible
evaluation environment. Establish a reproducible reference-policy baseline in
its supported setup before attempting export, quantization, or edge deployment.
Pin observation preprocessing, action representation and scaling, control
frequency, action chunking, task initial conditions, and episode termination.
Model choice must follow embodiment and environment compatibility, not name
recognition.

Compare the reference with one changed precision configuration first. Measure
task success, failure categories, action-output differences, latency
distribution, missed control deadlines, and memory. Use a fixed held-out episode
set, repeated trials, and uncertainty estimates for success rates. Keep task
conditions and control semantics consistent across variants. Offline output
similarity is diagnostic evidence, not a substitute for closed-loop evaluation.
If investigating latency separately, use controlled delay experiments rather
than attributing every quantized-policy failure to numerical precision.

Simulator integration, ONNX export, TensorRT support, and Jetson deployment are
separate compatibility milestones, not a guaranteed plug-and-play chain. Change
one boundary at a time. Add fine-tuning, RL, world models, or physical hardware
only when a measured failure motivates that extension; hardware trials require
an explicit safety review and supervised operating limits.

CFMI contributes only the mechanisms this experiment needs: immutable
configurations, execution, evidence capture, deterministic evaluation, and
bounded retries. Do not build a general fleet or agent platform first.

## 1. Research thesis

Sections 1-8 outline an optional CFMI agent-effectiveness study. They are not
required deliverables for the first robotics experiment or the CFMI time box.

CFMI can become more than workflow automation if it answers a measurable
research question:

> How effectively can a closed-loop, agent-assisted system diagnose and
> remediate model-integration failures across transformation, optimization, and
> runtime boundaries while preserving quality and resource constraints?

The research contribution is not the number of agents or the platform name. It
is the combination of:

1. A workload-independent closed-loop lifecycle.
2. Evidence-grounded and bounded remediation.
3. A realistic corpus of model-integration failures.
4. Controlled comparison against manual and deterministic baselines.
5. Reproducible evaluation across heterogeneous hardware.

## 2. Separation between product and research goals

The engineering pilot asks:

> Can CFMI reduce model-onboarding effort without weakening release safety?

The research study asks:

> Which failures benefit from agent-assisted reasoning, under what constraints,
> and at what cost relative to deterministic automation and human engineers?

The product can succeed even if agents provide limited benefit. The research
must report that result honestly rather than making agent use a success
criterion.

## 3. Experimental conditions

For a separately scoped agent-effectiveness study, compare:

| Condition | Description |
|---|---|
| Manual | Engineer follows the documented onboarding process |
| Scripted | Deterministic workflow, known rules, and no diagnosis agent |
| Agent-assisted | Same workflow plus evidence-grounded diagnosis and bounded remediation |

All conditions should use the same:

- Model revisions
- Failure cases
- Software and hardware matrices
- Evaluation suites
- Release policies
- Time and compute accounting method

## 4. Primary research questions

### RQ1: Onboarding effectiveness

How often does each condition produce a valid release candidate within the
allowed time and compute budget?

### RQ2: Diagnosis quality

How accurately does the system classify root causes and identify the responsible
stage or component?

### RQ3: Remediation effectiveness

How often does a proposed remediation resolve the failure without violating
quality, performance, or safety gates?

### RQ4: Engineering efficiency

How much human time, elapsed time, and repeated investigation does the system
save?

### RQ5: Generalization

Do policies and remediation strategies learned from one model or hardware class
transfer to unseen models, versions, and devices?

### RQ6: Reliability and cost

What are the false-pass rate, false-block rate, flaky-run rate, token cost, GPU
cost, and infrastructure overhead?

## 5. Failure corpus

A useful benchmark should contain real and controlled failures across:

- Invalid or incomplete model metadata
- Unsupported architecture or operator
- Exporter defect
- Shape and signature mismatch
- Runtime/provider incompatibility
- Driver or dependency mismatch
- Out-of-memory failure
- Precision or quantization quality regression
- Performance regression
- Functional regression
- Corrupted or incompatible cache/artifact
- Worker interruption and infrastructure failure

Each case needs:

- Reproducible inputs
- Known or reviewed root cause
- Expected acceptable remediation classes
- Prohibited shortcuts, such as relaxing the quality gate
- Time and resource budget
- Success criteria

Real failures provide external validity. Injected failures provide coverage and
repeatability. Results should report them separately.

## 6. Metrics

### Outcome metrics

- Valid release-candidate rate
- Correct block/review rate
- False-pass and false-block rate
- End-to-end completion rate

### Diagnosis metrics

- Root-cause classification accuracy
- Top-k hypothesis recall
- Stage and owner routing accuracy
- Evidence citation correctness
- Human acceptance rate

### Efficiency metrics

- Human active time
- End-to-end elapsed time
- GPU hours
- Number of experiments and retries
- Agent token or service cost
- Artifact-cache reuse

### Quality metrics

- Accuracy or task-quality delta
- Functional-test pass rate
- Latency, throughput, and memory delta
- Reproducibility across repeated runs

An agent-generated explanation is not evidence of correctness. Only verified
execution and deterministic gate results count as successful remediation.

## 7. Ablation studies

Potential ablations include:

- Agent diagnosis with and without structured failure taxonomy
- Agent diagnosis with and without historical failure retrieval
- Free-form remediation versus approved action catalog
- Single-agent versus specialized-stage agents
- Static experiment plan versus adaptive experiment selection
- Full logs versus summarized structured evidence
- Hardware-aware versus hardware-agnostic scheduling
- Unbounded retry versus explicit compute and attempt budgets

The initial study should prioritize a small number of ablations that explain
where performance gains originate.

## 8. Publication path

### Option A: Inference systems

Possible paper framing:

> Closed-Loop Agent-Assisted Integration of Foundation Models Across
> Heterogeneous Inference Runtimes

Expected contributions:

- Closed-loop systems architecture
- Failure taxonomy and benchmark corpus
- Bounded remediation mechanism
- Evaluation across multiple models and RTX hardware classes
- Manual versus scripted versus agent-assisted comparison

Suitable venue categories include ML systems, industry systems, inference,
runtime, compiler, benchmarking, and agent reliability tracks. A venue should
be selected only after the contribution and experimental maturity are clear.

### Option B: Embodied deployment

Possible later framing:

> Closed-Loop Deployment and Adaptation of Vision-Language-Action Models on
> Edge Robotics Hardware

This is a separate research direction, not dependent on publishing the inference
study. Report simulation-only results as such; real-hardware or sim-to-real
claims require physical-task evidence. Do not broaden either paper's claims
beyond the experiments actually completed.

## 9. Robotics generalization

The generic lifecycle maps to robotics as follows:

| Generic stage | Inference pilot | Robotics extension |
|---|---|---|
| Candidate | Hugging Face model | VLA or world-model checkpoint |
| Transform | Mobius ONNX export | VLA export or compilation |
| Optimize | Olive precision search | TensorRT, quantization, resolution, action/runtime tuning |
| Execute | CUDA/TensorRT RTX | Jetson or robot compute |
| Evaluate | Accuracy and performance suite | Simulation, hardware-in-loop, and task episodes |
| Remediate | Config or reviewed source change | Config, data request, fine-tuning, or training proposal |

Reuse provenance, budgets, evidence, and evaluation contracts where demonstrated
useful. A shared coordinator or scheduler is optional, not an architectural
prerequisite. Candidate, transformer, executor, and evaluator implementations
change by domain.

## 10. Robotics evaluation contract

Unlike static LLM evaluation, a VLA evaluator interacts with an environment:

```text
observation -> policy -> action -> environment -> next observation
                                      |
                                      v
                              trajectory evidence
```

A robotics evaluation result may include:

- Task success rate
- Collision or safety-event rate
- Completion time
- Human intervention rate
- Trajectory efficiency
- Control-loop and inference latency
- Memory and power use
- Sim-to-real performance delta

The gate policy must identify mandatory safety metrics separately from
optimization objectives. Improved speed can never compensate for a failed
safety gate.

## 11. Teleoperation and data remediation

Teleoperation fits the lifecycle only as a governed remediation action:

```text
Failure trajectories
    -> cluster and diagnose
    -> identify missing scenario coverage
    -> request approved demonstrations
    -> create a versioned dataset
    -> train a new versioned candidate
    -> re-enter evaluation from the beginning
```

The system must not silently trigger data collection or training. A request
records the scenario definition, quantity, ownership, privacy and safety
requirements, budget, and expected evaluation impact.

## 12. World-model and simulation gates

Simulation and, when validated for the task, world models may reduce physical
evaluation cost. The following is a possible later evaluation sequence, not a
mandatory chain for the first experiment:

```text
Candidate
    -> static compatibility
    -> optimized engine
    -> simulator gate
    -> large scenario or world-model gate
    -> hardware-in-loop gate
    -> controlled real-robot gate
```

Candidates advance from cheaper, safer evaluation to more expensive and
realistic evaluation. Simulation evidence cannot replace physical evidence
until correlation is measured and acceptable for the intended task.

## 13. Recommended progression

Run two bounded tracks concurrently, with robotics receiving most of the
experimental effort. A roughly 70/30 robotics/CFMI allocation is a planning
starting point, not an experimentally established optimum; agree explicit hours
and compute limits before scheduling work.

| Milestone | Robotics track | CFMI support track |
|---|---|---|
| Establish baseline | Run one compatible policy on one task in its supported reference environment | Record one pinned inference workload and the manual baseline on one RTX machine |
| First comparison | Evaluate one precision change with closed-loop task and latency metrics | Automate execute/evaluate/report with immutable inputs, typed failures, and bounded retries |
| Time-box review at 4-6 weeks | Report baseline, comparison results, or a reproducible compatibility blocker | Report manual versus scripted effort, quality protection, compute cost, and limitations; stop unless a specific extension is approved |
| Evidence-driven extension | Choose one next step: export/runtime optimization, edge deployment, or data/fine-tuning | Add diagnosis assistance only for recurring failures; add fleet support only if multi-device evidence is needed |

A negative or incomplete result does not justify automatically extending the
time box. Preserve the evidence and explicitly decide whether to stop, narrow,
or fund another experiment. World models and RL remain later branches unless
selected as the primary research question in a separate plan.

The goal is one robotics experiment with a small reusable evaluation harness,
not two large platforms that must eventually converge.
