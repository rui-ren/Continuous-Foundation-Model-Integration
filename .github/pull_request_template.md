## Outcome and scope

Related task and governing contract:

What changed, and what intentionally did not:

## Evidence

Record the tested commit/worktree, exact commands, selected/executed test counts,
outcomes, and limitations. For model runs, include artifact IDs/checksums,
environment identity, baseline, policy, and evidence location; do not upload
secrets or unapproved model/data artifacts.

- CPU checks:
- GPU/model acceptance: not required / not run / blocked / evidence link
- Independent review findings and disposition:

## Review checklist

- [ ] Regression coverage matches the requested behavior.
- [ ] Fake adapters, skips, and missing hardware are not represented as GPU passes.
- [ ] Failure evidence and provenance are preserved.
- [ ] Dependency, reference-data, tolerance, policy, and permission changes are
      explicitly disclosed (or none were made).
- [ ] Documentation reflects the commands and behavior actually implemented.
