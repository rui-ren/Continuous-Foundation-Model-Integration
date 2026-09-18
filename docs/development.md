# AI-driven development

AI implements bounded changes; executable checks provide evidence; a human
reviews scope and acceptance. This development workflow is independent of the
optional runtime diagnosis/remediation agent.

## Current implementation boundary

The repository has a standard-library Python 3.12 foundation, not a working
model-onboarding pipeline:

| Implemented | Not implemented |
|---|---|
| Agent instructions, task/PR templates, and two development playbooks | Autonomous assignment, merging, publication, or a multi-agent service |
| Immutable artifact-digest, failure, and stage-result records | Persisted run state, scheduling, budget enforcement, or a full manifest schema |
| CPU tests with a fake export adapter | Mobius, CUDA, Olive, TensorRT RTX, or robotics integrations |
| A CPU runner that rejects empty/incomplete results and matching CI configuration | GPU acceptance, static type checking, linting, or package publication |

The stage-result implementation covers the minimal internal contract described
in [technical design section 6.3.1](technical-design.md#631-current-cpu-prototype).
It checks evidence structure, not artifact bytes, numerical correctness, or
release eligibility. A `SUCCEEDED` stage record is not a passing release gate.

## Setup and commands

Install/use Python 3.12. There are no third-party dependencies for the foundation;
no `pip install`, model download, GPU, credentials, or network access is needed
to run the checks. From the repository root:

```text
python -m tools.check
python -m tools.check --pattern test_contracts.py
python -m tools.check --pattern test_check.py
```

The full command is the local/CI acceptance command for this foundation. Test
filenames use `test_*.py`. The runner imports `src/cfmi` from this checkout and
prints selected/executed counts. Empty selection, failures, errors, skips,
expected failures, and unexpected successes return a nonzero exit code.

Tests deliberately inject invalid values at the contract boundary and exercise
the runner's failure paths. No static type-check claim is made for this suite.
Keep tests fast, CPU-only, and independent of model downloads. If a real
integration is unavailable, report it as not run or blocked rather than hiding
it behind a passing fake adapter.

## Task-to-review workflow

1. Use the **Bounded implementation task** issue form to define the outcome,
   governing contract, allowed scope, non-goals, acceptance evidence, and caps.
2. Have one agent implement the change on an isolated branch/worktree. Read
   [AGENTS.md](../AGENTS.md) and the appropriate playbook first.
3. Run targeted checks during development, then the full CPU command. Retain
   failure evidence rather than overwriting it.
4. Obtain an independent review of the diff and use the PR template to identify
   commands/results, artifact evidence, limitations, and sensitive changes.
5. A human decides whether to merge. A successful AI review is not proof of
   correctness and does not waive required evidence.

Example first task:

> Add JSON serialization for the approved stage-result contract. Round-trip
> successful, failed, and blocked records; reject unknown fields and unsupported
> schema versions. Do not implement a database, GPU adapter, or release gate.
> Define the serialization mapping in the technical design before implementing.

The example is future work, not an implemented command or assigned task.

## CI and repository settings

The `CPU checks` workflow runs the same command on GitHub-hosted Ubuntu and
Windows with Python 3.12, a read-only token, no persisted checkout credentials,
and commit-pinned actions. It neither publishes nor invokes a self-hosted GPU.
Remote execution starts only after the workflow is committed and pushed.

A maintainer should configure a main-branch ruleset requiring pull requests,
human approval, and both CPU matrix checks after they have run successfully.
The files alone do not enforce branch protection; repository settings have not
been changed by this setup.

## GPU evidence is a separate milestone

Before implementing a real adapter, select and review one model and immutable
source revision, tokenizer/preprocessing, evaluation dataset, policy, precision
configuration, environment versions, hardware identity, and compute budget.
There is intentionally no runnable placeholder experiment manifest: a fake
revision or guessed tolerance must not look like an approved experiment.

The future GPU command must fail or block when a required test is unselected,
skipped, lacks hardware, or uses an unintended provider fallback. Keep
source-to-export parity, optimized-path quality, and performance as distinct
claims. Serialize GPU measurements and record power/thermal conditions,
environment identity, artifact hashes, and policy version.

Do not attach untrusted PR execution to a self-hosted GPU runner. Credentials,
large downloads, remote model code, driver changes, and publication need
explicit authorization. Store large artifacts in approved external/local
artifact storage, not Git; commit only permitted manifests and small fixtures.

## Keep guidance small and current

The practices are adapted from Mobius's
[agent instructions](https://github.com/onnxruntime/mobius/blob/223b438e8f6637c40ac883607f321a5ff4fbe863/.github/copilot-instructions.md)
and
[quality checklist](https://github.com/onnxruntime/mobius/blob/223b438e8f6637c40ac883607f321a5ff4fbe863/.agents/skills/quality-checklist/SKILL.md),
not its full platform or hardware matrix. Update instructions when commands or
contracts change. Verified fixes should become small regression cases; held-out
research answers and unverified diagnoses must not become development guidance.
