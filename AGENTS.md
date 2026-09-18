# CFMI development contract

## Scope and authority

Build a bounded, single-machine ML-systems experiment, not a general platform.
One pinned model, one optimization configuration, explicit budgets, and measured
evidence are the immediate scope. Fleet services, dashboards, discovery,
publication, and runtime diagnosis agents are not prerequisites.

AI-driven development does not imply autonomous runtime or release decisions.
Agents propose; deterministic gates decide from measured evidence.

- `docs/technical-design.md`: canonical architecture and data contracts.
- `docs/engineering-design.md`: implementation priorities, proposed refinements,
  failure cases, and slice exit criteria.
- `docs/research-roadmap.md`: optional research and independent robotics work.
- `docs/development.md`: implemented tooling, commands, and evidence boundaries.
- `src/cfmi/`: small runtime-independent contracts; no real GPU adapters yet.
- `tests/`: CPU-only regression cases and test doubles.

Resolve contract conflicts explicitly; do not silently invent a competing schema.

## Environment and checks

Use Python 3.12. The current foundation uses only the standard library and needs
no package installation. From the repository root:

```text
python -m tools.check
python -m tools.check --pattern test_contracts.py
```

These commands execute CPU tests, not model/GPU acceptance. The runner fails on
zero tests, skips, failures, unexpected successes, and expected failures.
No linter, static type checker, or GPU acceptance command is configured yet;
do not report those checks as passed.

## Working on a task

1. Read the relevant contract and existing code before changing it.
2. State a small outcome, allowed scope, non-goals, and acceptance evidence.
3. Make the smallest complete implementation; reuse helpers and stage adapters.
4. Add regression coverage, run targeted checks, and run the full CPU check
   before handing off. Preserve unrelated working-tree changes.
5. Report what changed, commands and outcomes, limitations, and remaining work.

Use `.agents/skills/implementing-a-stage/SKILL.md` for stage work and
`.agents/skills/investigating-a-failure/SKILL.md` for diagnosis. They are
development playbooks, not permission to execute runtime remediation.

## Non-negotiable evidence rules

- Never relax a gate, change a tolerance, or replace reference outputs merely
  to make a test pass. Such changes need explicit review and rationale.
- Never treat a skipped, unavailable, or fake GPU result as NVIDIA acceptance.
  Record missing capability as blocked/not run, not successful validation.
- Preserve failed attempts, immutable provenance, and budget consumption.
- Separate hypotheses from verified root causes. A plausible explanation or
  successful repair does not by itself establish the cause.
- Keep held-out research answers out of agent prompts, retrieval, and fixtures
  used to develop the diagnosis system.
- No broad exception suppression or success-shaped fallback on invalid input.

## Permissions and collaboration

Do not commit, push, merge, publish, or change repository settings unless
explicitly requested. Do not enable remote model code, expose credentials,
download large model artifacts, or change drivers/system configuration without
authorization. Dependency, policy, reference-data, and CI permission changes
must be called out for review.

Start with one implementing agent and a separate review pass. If concurrent
work is justified, use separate branches/worktrees and environments, assign
non-overlapping files, and serialize measurements on the GPU. Do not run
untrusted pull-request code on a credentialed/self-hosted GPU worker.
