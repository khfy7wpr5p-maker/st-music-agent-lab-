# A21 Resumable Orchestration and Activation Request Boundary

A21 makes the verified lifecycle resumable and adds an explicit activation-request object without
adding any deployment or model-switch authority.

## Resumable orchestration state

`OrchestrationStateStore` persists structured evidence pointers in the existing SHA-256
hash-chained journal. It stores no prompts, provider messages or hidden reasoning.

The ordered lifecycle is:

1. `plan_verified`
2. `execution_verified`
3. `dataset_curated`
4. `training_completed`
5. `model_registered`
6. `promotion_reviewed`
7. `activation_requested`

Each later stage requires the exact evidence identifiers from earlier stages. Stored evidence
includes plan id/verification reference, execution record id, optional experience/evaluation
references, dataset manifest hash, training input/completion fingerprints plus authorization
reference, model candidate id, promotion-review fingerprint and activation-request fingerprint.

Stages cannot be skipped or regressed through the host API. Existing evidence cannot be silently
replaced. Reopening the store verifies the journal hash chain and resumes from the latest verified
state.

## Activation request

`ActivationRequestBuilder` accepts only:

- an immutable A20 model candidate;
- an A20 review with `eligible_for_activation_review`;
- the exact current baseline model id/checkpoint hash;
- an exact rollback target;
- a bounded target-environment identifier.

The rollback target must equal the current baseline identity and checkpoint. The candidate lineage
and promotion-review fingerprints are independently verified before the request is created.

Every request is content-addressed and always carries:

- `human_approval_required=true`;
- `activation_authorized=false`;
- `auto_activate=false`;
- `canonicalization_authorized=false`.

Creating an activation request therefore does not activate, deploy, canonicalize or switch a
model. It only creates a reviewable request with an explicit rollback identity.

## Excluded authority

A21 does not expose model-callable tools to:

- approve an activation request;
- change serving configuration;
- access deployment credentials;
- replace a production model;
- mark a candidate canonical;
- bypass rollback or health checks.

Actual activation remains a later, separately authorized host operation.
