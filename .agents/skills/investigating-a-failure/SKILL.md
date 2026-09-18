---
name: investigating-a-failure
description: Use when reproducing a failed CFMI stage or gate, diagnosing its cause, or proposing a bounded fix.
---

# Investigating a CFMI failure

1. Preserve the original failure before modifying anything. Record the model
   revision, stage, attempt, artifact fingerprints if available, environment,
   sanitized logs, command, policy, and consumed time/compute.
2. Reproduce with the smallest permitted input. Distinguish invalid input,
   missing capability, infrastructure failure, and model-quality regression.
   A missing graph before export is missing evidence, not an invented hash.
3. Record hypotheses separately from reviewed root-cause labels. Cite evidence
   for each hypothesis and identify what would disprove it.
4. Propose one bounded action. Check the remaining budget and approvals before
   running it; changed inputs/configuration must follow the experiment or
   linked-run rules. Never weaken a gate or substitute a reference output.
5. Re-run affected checks and retain both failed and repaired evidence. Add a
   small regression test where possible. Count a remedy as successful only when
   all affected mandatory gates pass; CPU-only evidence cannot close a GPU
   acceptance failure.
6. Update the versioned failure record and this playbook only with verified,
   reusable findings. Follow the `FailureCase` proposal in the engineering
   design; no automated corpus store exists yet. Keep secrets, restricted
   artifacts, and held-out benchmark answers out of development guidance.
