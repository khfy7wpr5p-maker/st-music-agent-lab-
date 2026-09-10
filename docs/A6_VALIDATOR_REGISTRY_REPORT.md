# A6 — Validator Registry Report

Status: IMPLEMENTED / awaiting stacked PR CI at creation time.

## Purpose

A6 introduces a framework-independent validation authority between agent-produced work and acceptance. The registry consumes structured evidence and produces deterministic validation states. It does not execute GitHub mutations, merge changes, deploy software, or grant musical/teacher authority.

## Core model

Validation states:
- `VERIFIED`: all required validators exist and no blocking validator failed or errored; required validators did not skip.
- `REJECTED`: at least one blocking validator returned `FAIL` or `ERROR`.
- `INCOMPLETE`: a required validator is missing or a required validator returned `SKIP`/`ERROR` without a blocking rejection taking precedence.

Validator statuses:
- `PASS`
- `FAIL`
- `SKIP`
- `ERROR`

## Implemented validator classes

### CommandEvidenceValidator
Consumes structured test/build/lint command evidence. Non-zero return codes or timeouts fail validation.

### SchemaContractValidator
Checks required top-level fields in named machine-readable contracts supplied as evidence.

### ForbiddenPathValidator
Validates changed paths against TaskSpec allowed roots and explicit forbidden roots. Absolute paths, parent traversal, forbidden roots, or paths outside an admitted allowlist fail validation.

### DeterminismValidator
Canonicalizes supplied rerun outputs and compares SHA-256 digests. Any mismatch fails validation.

### CIStatusValidator
Consumes structured CI run evidence. Completed failed checks fail; pending checks remain incomplete when required; completed successful/neutral/skipped checks pass.

## Registry guarantees

- validator IDs are unique;
- execution order is deterministic by validator ID;
- missing required validators cannot yield success;
- a blocking validator exception becomes `ERROR`, never PASS;
- agent metadata or explanation is not an override channel;
- validation results are serializable with `ValidationReport.to_dict()`;
- validators do not grant GitHub write, merge, deployment, teacher, publication, or canonical music authority.

## Safety invariant

An LLM can propose code and can explain why it believes a change is correct, but the registry state is derived only from registered validator results and required-validator presence. There is no `override`, `force_pass`, `agent_confidence`, or natural-language acceptance field in the registry API.

## Test coverage added in A6

The A6 unit tests verify:
- duplicate validator rejection;
- missing required validator -> `INCOMPLETE`;
- failed command evidence remains `REJECTED` even when metadata requests an override;
- validator exception -> blocking `ERROR` and `REJECTED`;
- non-blocking advisory failure does not independently reject;
- required SKIP -> `INCOMPLETE`;
- command timeout/non-zero failure handling;
- schema required-field checks;
- allowed/forbidden diff path checks;
- deterministic rerun digest comparison;
- CI pass/fail/pending classification;
- complete five-class evidence set -> `VERIFIED`.

## Deferred to later stages

A6 does not yet add repository-specific musical validators, immutable-source validators for each ST engine, benchmark scoring, or cross-repository orchestration. Those are attached through A7+ domain adapters while preserving this registry contract.
