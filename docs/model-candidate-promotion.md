# A20 Model Candidate Registry and Promotion Review

A20 turns a completed A19 checkpoint into an immutable model candidate, then independently
recomputes A16 benchmark evidence before the candidate can reach activation review.

## Model candidate registry

`ModelCandidateRegistry.register()` accepts one exact `TrainingRunSpec` and one exact completed
`TrainingRunCompletion`.

Registration verifies:

- training spec fingerprint;
- trainer configuration hash;
- exact run id and input fingerprint linkage;
- completed outcome;
- checkpoint SHA-256;
- authorization/evidence references;
- completion fingerprint;
- `evaluation_required=true`;
- `promotion_authorized=false`;
- `auto_promote=false`.

The candidate id is deterministic and content-derived from training lineage. The registry keeps:

- checkpoint SHA-256;
- training run id;
- input and completion fingerprints;
- dataset id + manifest hash;
- base-model identity/revision/artifact SHA-256;
- lineage fingerprint.

Candidate records always keep `activation_authorized=false` and `auto_activate=false`.

## Promotion review

`ModelPromotionReviewGate.review()` does not trust an evaluation report by itself. It receives:

- the registered model candidate;
- the baseline benchmark run;
- the candidate benchmark run;
- the claimed A16 evaluation report.

The gate reruns `LearningEvaluationGate.compare()` and requires the claimed report to match the
fresh recomputation exactly. A benchmark run whose candidate id differs from the registered model
candidate is rejected.

If the recomputed A16 result is `eligible_for_host_review`, A20 produces only:

`eligible_for_activation_review`

This still carries:

- `human_review_required=true`;
- `activation_authorized=false`;
- `auto_activate=false`.

A rejected A16 result remains rejected at A20.

## Excluded authority

A20 does not:

- activate or deploy a checkpoint;
- switch the production model;
- weaken A16 paired benchmark rules;
- accept a forged evaluation report;
- bypass human/host review;
- expose model-callable activation or promotion tools.

A later activation stage must be a separate, explicitly authorized host action.
