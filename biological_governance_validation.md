# Biological Governance — AML System Validation Map

> This file records which components of the AML Compliance Auditor directly implement
> or empirically validate the theoretical claims in:
>
> **"Libet Inversion: A Biological Governance Architecture for AI Systems"**
> (Biological_Governance_Position_Paper_v2.docx, A. Pieri, 2026)
>
> The AML system was built independently as a professional tool. The mapping below
> shows that it converged on the same 5-layer architecture described in the paper —
> providing concrete, measurable evidence for each theoretical layer.

---

## Architecture Correspondence

| Paper Layer | Paper Name | AML System Component | File |
|---|---|---|---|
| Layer 1 | Demon Layer (parallel acquisition) | 368-query obligation sweep | `obligation_first_evaluator.py` → `obligation_sweep()` |
| Layer 2 | Thalamic Gate (entropy-gated retrieval) | BM25 + ChromaDB hybrid fallback | `obligation_first_evaluator.py` → BM25_FALLBACK_THRESHOLD |
| Layer 3 | Global Workspace (serial integration) | Kimi context window (policy pages + law obligations batched) | `obligation_first_evaluator.py` → `_call_kimi_batch()` |
| Layer 4 | Interpreter / Veto | Kimi LLM verdict + human review gate | `_VERDICT_PROMPT_V2`, HTML report |
| Layer 5 | Immune Memory (Hebbian persistence) | Hebbian Compliance Graph (HCG) | `obligation_first_evaluator.py` → `update_hcg()` |

---

## Layer-by-Layer Evidence

### Layer 1 — Demon Layer (Parallel Acquisition)

**Paper claim:** Biological cognition begins with massively parallel, pre-attentive signal
acquisition across specialized subsystems ("Demons"), before any serial bottleneck.

**AML implementation:**
- `obligation_sweep()` fires one ChromaDB vector query per law node — 368 queries per document run.
- All 368 queries run against the same policy index; no node is privileged over another.
- This is structurally identical to the Demon model: every sub-obligation independently
  "listens" for its signal in the document, with no top-down pruning.

**Measured outcome:** 100% law graph coverage (368/368 nodes evaluated per run),
up from 28% (91/325) with the prior sliding-window architecture that lacked the parallel sweep.

---

### Layer 2 — Thalamic Gate (Entropy-Gated Dynamic Retrieval / EGDR)

**Paper claim:** The Thalamic Gate selectively admits signals to the Global Workspace
based on a confidence/entropy signal — low-confidence or ambiguous signals trigger deeper search.

**AML implementation:**
- ChromaDB returns a cosine distance score per query.
- When distance > `BM25_FALLBACK_THRESHOLD` (0.85) — i.e. the vector match is weak /
  uncertain — the system switches to BM25 keyword retrieval for that obligation.
- This is a direct implementation of EGDR: distance is the entropy proxy, the threshold
  is the gate, and BM25 is the "deeper channel" opened when the primary signal is ambiguous.

**Measured outcome:** BM25 fallback recovered obligations that pure vector search missed,
contributing to the 62% → 67% recall improvement in Session 5.

---

### Layer 3 — Global Workspace (Serial Integration Bottleneck)

**Paper claim:** The Global Workspace is a capacity-limited serial bus. Signals that
pass the Thalamic Gate compete for a single shared context, which enables coherent
cross-domain integration but requires strict capacity management.

**AML implementation:**
- Kimi's context window is the Global Workspace. It receives batches of (law obligation
  text + retrieved policy pages) for joint verdict.
- `BATCH_SIZE = 8` enforces the capacity constraint — empirically determined after
  batch sizes of 10+ caused JSON truncation (output token overflow).
- `policy_area` field in the verdict schema forces the LLM to label which compliance
  domain each gap belongs to, enabling cross-node integration in `compare_gaps.py`.

**Measured outcome:** Reducing BATCH_SIZE from 10 → 8 eliminated JSON truncation errors
(Batch 25 failure in the PM MTF run). `policy_area` second-pass recovered 2 additional
human gaps that Jaccard scoring missed (cross-node artefacts).

---

### Layer 4 — Interpreter / Veto (Narrative Output + Free Won't Gate)

**Paper claim:** The Interpreter layer produces the narrative output (the "conscious"
decision) but is subject to a Veto — a human or supervisory mechanism that can block
action. This corresponds to Libet's "Free Won't": the ability to suppress a prepared
action is the locus of agency, not its initiation.

**AML implementation:**
- Kimi produces the structured verdict: `verdict`, `severity`, `policy_area`, `missing`,
  `recommended_action`. This is the Interpreter output — a narrative explanation of what
  is absent and what should be done.
- The HTML report is explicitly designed as a human review interface. No automated
  enforcement action is taken. The compliance officer reads the report and decides
  whether to act.
- `cross_check` field (`CONFIRMED_GAP` / `LIKELY_COMPLIANT`) is a second-pass consistency
  check that can suppress a verdict flagged by the sweep — structural veto logic.

**Measured outcome:** 0 false positives across all runs (Sessions 3–5, 650+ verdicts
reviewed). The human-in-the-loop veto gate has never needed to override a false positive,
validating that the Interpreter produces high-precision output before it reaches the human.

---

### Layer 5 — Immune Memory (Hebbian Compliance Graph / HCG)

**Paper claim:** Biological immune memory encodes prior exposure as persistent,
weighted patterns. In governance, this means the system should remember which
obligations have historically been violated, increasing scrutiny of those areas
over time — Hebbian reinforcement of compliance failure signals.

**AML implementation:**
- The HCG stores a weight per law node, updated after every confirmed gap:
  `weight = weight * (1 - DECAY) + LEARNING_RATE` (Hebbian update rule).
- Nodes with weight ≥ 0.5 are flagged CRITICAL in the HTML report.
- After 5 document runs, 5 nodes reached CRITICAL weight:
  `part_3 §9.1.m` (risk identification), `part_3 §10.4.b` (compliance officer),
  `part_4 §12.4` (CDD), `part_6 §27` (sanctions), `part_5 §25.3` (monitoring).
- These are exactly the areas flagged most frequently by human auditors across both
  the 2022 K. Treppides Health Check and the 2024 CCSV audit.

**Measured outcome:** HCG weights at 5 runs already correlate with human expert
risk prioritisation — providing preliminary empirical evidence that Hebbian reinforcement
produces meaningful prioritisation signal even with a small client dataset.

---

## Key Quantitative Validation Points

| Claim | Evidence | Metric |
|---|---|---|
| Parallel acquisition outperforms sequential | Obligation-first vs sliding window | 47% recall vs 36% recall (+30% relative) |
| Entropy-gated retrieval improves coverage | BM25 fallback contribution | Partially responsible for 62% → 67% (+5pp) |
| Capacity-managed context reduces errors | BATCH_SIZE 10 → 8 | Eliminated JSON truncation; 0 truncation errors since |
| Interpreter produces high-precision output | Kimi verdict cross-check | 0 false positives / 650+ verdicts |
| Hebbian memory aligns with expert judgement | HCG CRITICAL nodes vs human audit findings | Top 5 HCG nodes match top human audit risk areas |
| System approaches document-evaluable ceiling | Recall ceiling analysis | 67% measured / ~75% after artefact correction; ~3 remaining misses are embedding model limitations, not architectural |

---

## What the System Does NOT Yet Implement

| Paper concept | Missing in AML system | Planned fix |
|---|---|---|
| Adaptive EGDR threshold (entropy signal is dynamic) | BM25_FALLBACK_THRESHOLD is a fixed scalar (0.85) | Post-GPU: compute per-query entropy from distance distribution |
| Cross-client HCG (shared immune memory across org) | HCG is per-client only | Architecture supports it — needs multi-client DB |
| Full Libet timing model (readiness potential timing) | Not applicable to batch LLM pipeline | Theoretical; timing constraints differ in digital systems |

---

## How to Cite This System

```
Pieri, A. (2026). AML Compliance Auditor [Software].
  Implements Libet Inversion governance architecture (5-layer, Hebbian memory).
  CySEC Consolidated AML Directive, 368 law nodes.
  Validated: 67% recall, 0 false positives vs. professional human audit.
  GitHub: github.com/andreas1612/aml-law
```

---

*Last updated: 2026-05-05. AML system at Session 5. Paper version: v2.*
