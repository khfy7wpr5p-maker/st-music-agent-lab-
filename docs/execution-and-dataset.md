# A17-A18 Execution Evidence and Curated Dataset Boundary

## A17 — exact execution outcome

A17 closes the gap between a verified plan and a later claim that work succeeded.

`ExecutionOutcomeStore` is host-only and append-only. It records an outcome only when the host
supplies the exact `CrossProjectPlan` plus a `PASS` `PlanVerificationReport` whose
`recomputed_plan_id` matches the same plan.

An `ExecutionObservation` is bound to the selected plan candidate by:

- `plan_id`;
- candidate rank;
- project identity;
- exact planned action;
- candidate evidence SHA-256;
- expected repository;
- branch;
- full 40-hex commit SHA;
- CI checks;
- validator checks.

A `SUCCESS` outcome requires every supplied CI and validator check to be `success`. A failure or
abstention cannot be represented as successful evidence. The resulting JSONL record is sanitized
and SHA-256 hash chained through the existing `RunJournal` primitive.

The execution record does not itself grant production, release, export or model-promotion
authority. It is historical evidence of what exact code revision was checked against which plan.

## A18 — curated dataset export

`CuratedDatasetBuilder` creates deterministic structured exports only from explicitly selected
verified execution record IDs.

The export includes operational facts needed for later offline evaluation or possible future
fine-tuning research:

- project and plan ID;
- candidate rank and planned action;
- candidate evidence hash;
- repository, branch and exact commit SHA;
- outcome;
- CI and validator evidence.

Free-form execution notes are deliberately excluded. Provider messages, hidden reasoning and
chain-of-thought are not dataset fields.

Every export manifest is fingerprinted and explicitly states:

- `training_authorized = false`;
- `auto_train = false`;
- `auto_promote = false`.

The supported purposes are `offline_evaluation` and `fine_tuning_candidate`. The latter means only
that a curated artifact may later be reviewed for use in a separately authorized training
program. It does not start training and does not select or promote a model.

## Current learning chain

```text
repository evidence
      -> deterministic plan
      -> independent plan verification
      -> guarded execution
      -> exact commit + CI + validator evidence
      -> verified execution record
      -> experience summary
      -> paired baseline/candidate evaluation
      -> explicit curated dataset selection
      -> offline-evaluation / fine-tuning-candidate artifact

No stage above automatically trains or promotes a model.
```

## Next safe boundary

A later stage may add a training-run contract that consumes an explicitly approved curated dataset
manifest and records trainer configuration, base model identity, dataset hash, output checkpoint
hash and evaluation report. Training authorization and checkpoint promotion must remain separate
host/human gates.
