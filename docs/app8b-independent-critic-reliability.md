# APP8B — Independent Critic, Disagreement Gate, and Reliability Metrics

Status: bounded read-only verification layer.

APP8B strengthens APP8A without adding execution authority. It introduces a model-independent critic-selection contract, exact-bound three-way disagreement gate, and transparent advisory reliability metrics. It performs no model invocation, tool dispatch, repository mutation, PR mutation, merge, deployment, training, activation, canonicalization, or rollback.

## Independent critic selection

`IndependentCriticSelector` receives model profiles plus an `AgentTask`. The producer model identity is excluded before ranking compatible critic candidates. Ranking prefers a different provider, then the existing model preference/context ordering.

If no compatible model remains after excluding the producer, selection fails closed with `CriticSelectionError`. It does not silently reuse the producer as its own independent critic.

With the current catalog, a normal planning/code critique after a GLM-5.1 producer can select Qwen3.8. A sufficiently demanding vision task where only Kimi-K2.5 is compatible will abstain from independent selection if Kimi-K2.5 was also the producer.

Selection is advisory only. It does not invoke the chosen model.

## Exact-bound disagreement gate

The gate requires three typed claims:

```text
Implementation claim
        +
Validation claim
        +
Independent Critic claim
        -> IndependentDisagreementGate
```

Every claim is bound to:

- repository;
- exact 40-hex commit SHA;
- artifact SHA-256;
- evidence references;
- role and verdict;
- model identity where the source is model-backed;
- optional instruction fingerprint.

`ACCEPT` requires exact binding, a producer/critic model identity difference, independent instructions when both fingerprints are supplied, and unanimous `PASS` from producer, validator, and critic.

Unanimous `FAIL` is `REJECT`. Mixed substantive verdicts become `REVIEW_REQUIRED`; they are never optimistically resolved. `UNAVAILABLE` or `ABSTAIN` evidence produces `ABSTAIN`. Binding mismatch, self-review, or matching producer/critic instruction fingerprint produces `REVIEW_REQUIRED`.

The gate is not a merge/release gate. Even `ACCEPT` keeps all execution, repository-mutation, merge, and production-authority flags false.

## Reliability metrics

`ReliabilityObservation` records verified counters for one role/model/project attempt. `ReliabilityAdvisor` groups observations by:

```text
project + agent role + model name + provider
```

It reports:

- attempts / success / failure / abstention / review-required;
- success, failure, and unresolved rates;
- mean model turns and tool calls;
- retries;
- validator failures;
- stale evidence attempts;
- policy-denied tool calls;
- disagreements;
- human overrides;
- SHA mismatches;
- budget exhaustion;
- regression escapes.

The disposition is deliberately transparent:

- fewer than the configured minimum attempts -> `INSUFFICIENT_DATA`;
- any regression escape or SHA mismatch, or high failure/disagreement/override/budget-exhaustion rate -> `REVIEW`;
- moderate failure/unresolved/retry or any smaller disagreement/override/budget signal -> `WATCH`;
- otherwise -> `STABLE`.

These summaries are advisory. `auto_apply`, `privilege_change_authorized`, `execution_authorized`, and `production_actions_authorized` are always false. Reliability history cannot promote a model, widen tools, or grant an agent new authority.

## APP8B boundary

APP8B remains non-mutating. APP8C may later connect verified APP8 supervision to the existing APP2–APP7 reversible feature-branch execution path, but only after a separate exact-head review and with existing branch, CI, validator, review, PR, and audit boundaries retained.
