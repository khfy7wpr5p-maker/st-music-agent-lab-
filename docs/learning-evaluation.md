# A16 Learning Evaluation Gate

A16 adds an offline paired benchmark gate between verified experience advice and any future
playbook/model promotion decision.

## Purpose

A15 can say that a playbook has accumulated enough verified historical success to be worth
preferring or reviewing. That is not evidence that a changed playbook, prompt, policy or model is
better than the current baseline.

A16 therefore requires a direct baseline-vs-candidate benchmark before a candidate can even become
eligible for host review.

## Paired benchmark contract

`BenchmarkRun` contains a candidate identifier and unique `BenchmarkCaseResult` entries. Every
case records:

- stable case id;
- standard or critical severity;
- outcome: `success`, `abstained` or `failure`;
- one or more explicit evidence references.

Baseline and candidate must cover the exact same case ids with the exact same severity. Evidence
references are included in each run fingerprint, so changing the evidence changes the run identity.

## Default gate

`LearningEvaluationPolicy` defaults to:

- at least 8 paired cases;
- at least 2 critical cases;
- no paired regression is allowed;
- no candidate critical failure is allowed;
- at least one case must strictly improve.

Outcome ordering is deliberately conservative:

`failure < abstained < success`

A candidate that merely ties the baseline is rejected. A candidate that improves several cases but
regresses one case is also rejected.

## Decision boundary

`LearningEvaluationGate.compare()` returns either:

- `eligible_for_host_review`; or
- `rejected`.

Even an eligible candidate has `auto_promote=false`. The gate never edits prompts, policies,
privileges, code or model weights and never activates a candidate.

## Model surface

The only A16 model-facing tool is:

- `learning.evaluation.policy`

It exposes the current evaluation rules. There is no model-callable benchmark submission,
approval, promotion or weight-update tool.

Benchmark execution and result construction remain trusted-host responsibilities. Future training
or playbook promotion must bind to exact benchmark fingerprints and pass a separate explicit host
promotion action.

## Safe learning path

```text
verified outcomes
      |
      v
ExperienceAdvisor
prefer / observe / review
      |
      | candidate work happens outside the advisor
      v
baseline benchmark <---- paired cases ----> candidate benchmark
      |                                      |
      +------------ LearningEvaluationGate --+
                         |
                   rejected / eligible
                              for host review
                         |
                         v
                    no auto-promotion
```

A17 may add an execution-outcome contract and resumable orchestration state. Any later curated
fine-tuning dataset export must remain downstream of verified experience and independent benchmark
evaluation; model training/promotion remains separately gated.
