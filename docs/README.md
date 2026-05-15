# Docs Marker Guide

Markers: operation, testing, architecture
Status: active
Publication: public

## Purpose

Docs markers classify documents by operating role, publication risk, and reading priority. They do not change contract meaning.

## Marker Vocabulary

| Marker | Meaning |
| --- | --- |
| `contract` | Defines public behavior, grain/key/schema, invariant, or interface commitments. |
| `operation` | Defines runtime, runbook, environment, deployment, or recovery procedures. |
| `testing` | Defines validation, pytest marker, smoke, or reproducibility gate behavior. |
| `architecture` | Defines system structure, track boundaries, data flow, or module responsibility. |
| `roadmap` | Defines future sequencing or phase plans, not active runtime contract. |
| `agent` | Defines agent workflow, task execution, publication, or collaboration rules. |
| `legacy` | Reference-only frozen material. It must not be treated as active source of truth. |
| `security` | Contains security, secret handling, access, or publication risk guidance. |

## Status Values

| Status | Meaning |
| --- | --- |
| `active` | Current source of truth or current operating guidance. |
| `reference` | Useful context, but not the primary source of truth. |
| `legacy` | Frozen historical material. Preserve for context only. |
| `draft` | Work-in-progress guidance that must not override active contracts. |

## Required Format

Use simple top-of-document metadata lines:

```text
  Markers: contract, operation
  Status: active
```

Existing title lines can remain above the metadata. Do not use markers to reclassify a legacy document as active without a separate contract review.

## Publication Link

Agent docs publication uses the same marker vocabulary. See `.agent/README.md` for the whitelist and exclusion policy.
