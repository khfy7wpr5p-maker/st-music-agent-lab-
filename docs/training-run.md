# A19 Training Run Contract

A19 makes training reproducible without giving the model permission to start or promote training.

## Input contract

`TrainingRunContractBuilder.create_spec()` accepts exactly one curated dataset export whose purpose
is `fine_tuning_candidate` and whose manifest hash verifies. Dataset authority flags must remain:

- `training_authorized=false`;
- `auto_train=false`;
- `auto_promote=false`.

The resulting `TrainingRunSpec` binds:

- run id;
- dataset id + exact manifest SHA-256;
- base model id, revision and artifact SHA-256;
- trainer name/version;
- canonical trainer configuration + configuration SHA-256;
- deterministic seed;
- training-code repository + full Git commit SHA.

All fields are folded into one deterministic `input_fingerprint`.

`execution_authorized=false` and `auto_start=false` are invariant. Creating a spec is not training
authorization.

## Completion contract

If an independently authorized host actually performs training,
`TrainingRunContractBuilder.bind_completion()` binds the exact input fingerprint to:

- host authorization reference;
- output checkpoint SHA-256;
- explicit training evidence references;
- deterministic completion fingerprint.

A completed run always carries:

- `evaluation_required=true`;
- `promotion_authorized=false`;
- `auto_promote=false`.

Failed or abstained runs use `bind_noncompletion()` and cannot claim a checkpoint hash.

## Evaluation boundary

A checkpoint produced under A19 is only an artifact with reproducible lineage. It is not a promoted
model. Before any promotion review, it must be evaluated through the A16 paired benchmark gate
against the current baseline on the same benchmark cases and severities.

## Excluded authority

A19 does not expose a model-callable training tool and does not:

- start GPU/Colab/cloud training;
- create or approve host authorization;
- modify model weights itself;
- activate a checkpoint;
- replace a production model;
- bypass A16 evaluation;
- auto-promote any candidate.

The purpose of A19 is provenance and reproducibility, not autonomous model replacement.
