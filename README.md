# Continuous Foundation Model Integration

Continuous Foundation Model Integration (CFMI) is a proposed NVIDIA-first
platform for discovering, adapting, optimizing, validating, and releasing
foundation models into production inference runtimes.

CFMI applies continuous-integration principles to model onboarding:

```text
Model candidate
    -> ONNX export
    -> CUDA EP correctness baseline
    -> TensorRT RTX optimization
    -> validation on the selected RTX target
    -> accuracy and performance gates
    -> release candidate or diagnosed retry
```

Its reusable core is intentionally runtime- and workload-independent:

```text
Candidate -> Transform -> Optimize -> Execute -> Evaluate -> Remediate
                ^                                             |
                +---------------- bounded retry ---------------+
```

The immediate deliverable is a time-boxed, single-machine experiment: one model
family, one NVIDIA software stack, a reviewed optimization configuration, and a
reproducible evidence report. Fleet scheduling and broader platform work are
optional expansions, not prerequisites.

Robotics experimentation starts in parallel with one policy, one task, and one
compatible evaluation environment. Its first question is how precision and
inference latency affect closed-loop task success. Reuse CFMI's evidence and
evaluation mechanisms only where useful; robotics does not wait for CFMI,
agent assistance, or fleet completion.

## Documents

- [Feature proposal](docs/feature-proposal.md) - business case, pilot scope,
  resources, success metrics, risks, and approval request.
- [Technical design](docs/technical-design.md) - architecture, lifecycle
  contracts, fleet scheduling, gates, security, and acceptance criteria.
- [Engineering design brainstorm](docs/engineering-design.md) - component-level
  proposals, core decisions, and implementation slices.
- [Research and robotics roadmap](docs/research-roadmap.md) - experimental
  questions, evaluation plan, publication path, and future VLA extension.
- [AI-driven development](docs/development.md) - setup, agent workflow, CPU
  checks, review requirements, and the separate GPU acceptance boundary.

## Development

Use Python 3.12. The CPU foundation needs no third-party packages or GPU:

```text
python -m tools.check
```

Read [AGENTS.md](AGENTS.md) before making changes. Tasks and pull requests should
be small, contract-driven, and backed by executable evidence. AI development
assistance is independent of the optional runtime remediation agent.

## Project status

Early development foundation: immutable evidence records, a fake adapter in
tests, CPU checks, and agent guidance. Real model adapters, GPU acceptance,
workflow persistence, and release automation are not implemented.
