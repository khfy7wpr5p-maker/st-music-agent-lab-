# A14-A15 Planning, Verification and Experience Learning

A14-A15 turns the four-project evidence plane into a controlled decision loop without giving the
model authority to promote its own decisions.

## A14 — Cross-project planner

`CrossProjectPlanner` consumes exactly one current `MusicEvidenceSnapshot` for each of the four
bound projects:

1. Score Restore;
2. MusicXML -> Guitar TAB;
3. Score Editor;
4. Real-Time Score Following.

The planner is deterministic. The current default policy closes bounded validation/integration
uncertainty before widening product capability or starting new research:

1. Score Restore frozen-candidate non-training consumer/inference integration checks;
2. TAB teacher-review integration while retaining PASS-only canonical export;
3. Score Editor's declared APP-11G feature boundary while release/cutover gates stay closed;
4. SF-12 score-following research expansion without production/pedagogical overclaim.

This is a transparent policy version (`2026-09-11.v1`), not an assertion that one universal
priority order is correct forever. If a required gate changes, the planner fails closed until the
policy is deliberately revised.

Every candidate includes an evidence hash derived from the complete source-provenanced snapshot.
The overall plan also carries an evidence-set hash and deterministic `plan_id`. Plans always set
`execution_authorized=false`.

## A14 — Independent verifier

`CrossProjectVerifier` does not trust the planner output. It recomputes the plan from the same
snapshot set and compares the complete semantic result.

Verification fails when, for example:

- a project snapshot is missing;
- a source blob SHA changed after planning;
- a protected/closed domain gate changed unexpectedly;
- candidate order/action/rationale was modified;
- the plan claims it authorizes execution;
- planner and verifier policy versions do not match.

`PortfolioPlanningService` performs `collect -> plan -> verify` as one read-only operation and
registers only `music.portfolio.plan`. The tool returns the plan, verification report and source
snapshots. It performs no source-project mutation.

## A15 — Verified experience store

`ExperienceStore` is a host-write-only append-only JSONL store backed by the existing SHA-256
hash-chained `RunJournal` primitive.

A record can be persisted only when the host supplies a `PlanVerificationReport` with:

- `status=PASS`;
- the exact same `plan_id` as the observation;
- `recomputed_plan_id` equal to that exact plan.

The observation schema intentionally stores only structured operational facts:

- plan ID;
- project;
- action;
- playbook key;
- outcome (`success`, `failure`, `abstained`);
- explicit evidence references.

No provider hidden reasoning or chain-of-thought field exists in the experience schema.

The model has no `learning.experience.record` tool. Recording is a trusted-host operation only.

## A15 — Learning advisor

`ExperienceAdvisor` aggregates verified outcomes by project + playbook. It can emit three
non-binding dispositions:

- `prefer`: at least three evaluated attempts and >=80% success;
- `review`: at least three evaluated attempts and <=50% success;
- `observe`: insufficient or mixed evidence.

Abstentions are retained but do not count as successful/failed attempts.

Every recommendation sets `auto_apply=false`. The advisor cannot change model weights, system
prompts, policy, privileges, code, gates or tool registration.

`ExperienceReadToolset` exposes only `learning.experience.summary` to models.

## Decision loop

```text
four repository-owned snapshots
          |
          v
 CrossProjectPlanner
          |
          v
 proposed deterministic plan
          |
          v
 CrossProjectVerifier ------ FAIL -> stop / inspect evidence drift
          |
         PASS
          |
          v
 host-controlled execution path
          |
          v
 CI / validator / domain evidence
          |
          v
 host records verified outcome
          |
          v
 ExperienceStore (hash chained)
          |
          v
 ExperienceAdvisor
          |
          +-> prefer / observe / review
                advisory only
```

## Safety invariants

1. Planning never authorizes execution.
2. Verification is recomputation, not model self-critique.
3. Evidence changes invalidate old deterministic plans.
4. Closed production/release/export/research authority boundaries remain closed unless their
   repository truth and policy are deliberately updated.
5. Only the trusted host records experience.
6. The model can read summaries but cannot write or edit experience history.
7. Learning recommendations never auto-apply.
8. Experience history is hash chained and tampering is detected before resume.
9. Hidden provider reasoning is not persisted in the learning store.
10. Model fine-tuning remains a separate future process requiring a curated dataset, evaluation
    and explicit promotion gate.
