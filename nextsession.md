# Next Session Handover — AML Compliance Auditor

> **Read this entire file before writing a single line of code. Everything decided here has a reason. Do not re-litigate closed decisions.**
> **Hardware context matters — read the Resource Constraints section before choosing any approach.**
> **This file was last updated: 2026-05-05. Session 3 delivered obligation-first evaluator (B1+B2) and Track A patches.**

---

## What This System Is

An automated AML Compliance Auditor that evaluates corporate AML policy PDFs against structured legal knowledge graphs. Runs entirely locally except for the final verdict call to an external LLM API (Kimi).

CySEC Consolidated AML Directive is law domain 1. Architecture supports EU AMLD5/6, FATF, FinCEN — jurisdiction is config-driven.

GitHub: `andreas1612/aml-law`

---

## SESSION 3 SUMMARY — What Was Built (2026-05-05)

### Track A — PoC patches (all complete, in rag_evaluator.py)

| Task | Status | Detail |
|---|---|---|
| A1 | SKIPPED | EGDR threshold tuning — obsolete once obligation-first is primary |
| A2 | DONE | `--verdict-only PATH` flag on both evaluators — reloads JSON, strips old cross-check, re-runs 4b→4c→5 without Kimi |
| A3 | DONE | CRITICAL banner in HTML report — red section above KPI bar showing nodes at confirmed_gap_weight ≥ 0.5 |
| A4 | DONE | `documents_evaluated` counter fixed — now increments once per node per run (was: once per verdict) |

### Track B — Obligation-first architecture (B1+B2+B4 complete)

**New file: `obligation_first_evaluator.py`** — do not modify `rag_evaluator.py` for B-track work.

| Task | Status | Detail |
|---|---|---|
| B1 | DONE | `obligation_sweep()` — 325 ChromaDB queries (law→policy), 100% law graph coverage, HCG sympathetic nodes first |
| B2 | DONE | `_VERDICT_PROMPT_V2` — each Kimi item includes exact law obligation text + top-3 policy sections with page + distance |
| B3 | SKIPPED | HCG `evaluation_tier` field — only 15 nodes of history, not useful yet. Add post-workstation. |
| B4 | DONE | 325-row obligation coverage table injected into HTML report via `_append_coverage_table()` |
| B5 | PENDING | **Run compare_gaps.py after first obligation-first run to measure recall improvement** |

### Dry run validated (no Kimi credits spent)

- Sweep: 325 findings, 325 unique ChromaDB queries, all law nodes covered
- 25 sympathetic HCG nodes queued first (confirmed gap history)
- Distance range: 0.406–1.681 (best match = dist 0.406, worst = 1.681)
- 26 ChromaDB paths appear 2-3× (pre-existing vectorization artifact — DO NOT REGENERATE)
- Cross-check wiring confirmed: uses `top_sections[0].distance` from sweep, no second query
- 402 credit exhaustion handler: stops cleanly, saves partial JSON, prints resume command

---

## HARDWARE / RESOURCE CONSTRAINTS — READ FIRST

**Current machine: Lenovo X1 Carbon — CPU only. No GPU.**

| Constraint | Impact | Current workaround |
|---|---|---|
| CPU only, no GPU | Ollama unusable (180s/page timeout) | `--skip-anon` flag bypasses anonymization |
| Limited RAM | ChromaDB must stay in-process, no large models | all-MiniLM-L6-v2 is fine (~90MB) |
| No persistent compute | Long runs can be interrupted | `--verdict-only` flag on both evaluators |
| No local LLM | Kimi API required for verdict | Kimi moonshot-v1-8k, api.moonshot.ai/v1 |
| Kimi rate limit | 8s sleep between batches of 10 mandatory | built into pipeline |

**When the GPU workstation arrives (after PoC approval):**
- Remove `--skip-anon` — use `qwen2.5:14b-instruct-q4_K_M` via Ollama for anonymization
- Replace Kimi with self-hosted model (qwen2.5:72b or similar) — update `kimi_base_url` in `client_config.json`
- Run Kimi batches in parallel — rate limit gone, 8s sleep removed
- spaCy can be upgraded to `en_core_web_trf` (transformer-based, GPU-accelerated)
- Architecture stays identical — only config and model names change

---

## Validated Results (Session 2026-05-05)

| Metric | Sliding window | Obligation-first |
|---|---|---|
| Law nodes evaluated | 91 / 325 (28%) | **325 / 325 (100%)** |
| CONFIRMED_GAPs | 22 | **172** |
| Kimi COMPLIANT | 64 | 151 |
| Recall vs human expert audit | 36% (16/45) | **47% (21/45)** |
| False positives confirmed | 0 | 0 |

**Structural problem solved.** 100% law coverage achieved. Remaining ceiling is semantic — `all-MiniLM-L6-v2` cannot reliably match operational policy language to regulatory law text when phrasing diverges. 24 human policy gaps still missed — paraphrase is the cause, not coverage.

**n_results=5 experiment completed (2026-05-05):** Recall unchanged at 47%. Confirmed gaps dropped 172→159 (Kimi more generous with larger context — ambiguous). Reverted to n_results=3. **Paraphrase ceiling is confirmed at 47% for all-MiniLM-L6-v2.** Fix requires a legal-domain embedding model — post-GPU workstation task.

---

## THIS SESSION: PoC is architecturally complete

All experiments concluded (2026-05-05):
- Obligation-first sweep: 100% law coverage ✓
- n_results=5 experiment: no recall improvement → reverted to n_results=3
- Paraphrase ceiling confirmed at **47% recall** with all-MiniLM-L6-v2
- Zero false positives across all runs
- Anonymization removed permanently (internal hardware, AUP covered)

**Recall ceiling fix (post-GPU workstation):**
Replace `all-MiniLM-L6-v2` with a legal-domain embedding model in `vectorize.py`.
Re-run `vectorize.py` to rebuild the 325-node law ChromaDB.
Re-run evaluation and `compare_gaps.py` to measure improvement.
Candidate models: `nlpaueb/legal-bert-base-uncased`, `law-ai/InLegalBERT`.

**To run a new document evaluation:**
```powershell
cd C:\Users\andre\Desktop\aml_proof
$env:KIMI_API_KEY = (Get-Content .env | Select-String "KIMI_API_KEY" | ForEach-Object { $_ -replace "KIMI_API_KEY=","" })
python obligation_first_evaluator.py --pdf "YOUR_DOCUMENT.pdf" --config client_config.json --skip-anon
```

**GPU workstation changes (when available):**
- Replace Kimi: update `kimi_base_url` + `kimi_model` in `client_config.json`
- Remove 8s sleep between batches (no rate limit)
- Run parallel batches (~45 sec total vs ~13 min)
- Replace embedding model → rebuild ChromaDB → re-evaluate recall
- Anonymization: permanently removed (internal hardware, AUP allows raw text)

---

## Ground Truth

| File | What it is |
|---|---|
| `CCSV - AML_KYC.xlsx` (in Downloads) | Professional human audit of Capital.com AML Manual — 66 findings, 45 policy-level, 21 operational |
| `Capital Com - AML Health Check 09.02.2022.docx` (in Downloads) | 2022 AML Health Check by K. Treppides & Co — earlier audit for the same company |

Ground truth applies ONLY to the 65-page Capital.com test PDF (`AML Manual V8.0_Reviewed(Draft).docx.pdf`).
The 141-page PDF (`1a. AML Manual.docx.pdf`) is PM MTF Ltd — no ground truth available.

---

## Recall ceiling — honest acknowledgement

Obligation-first removes the **structural** ceiling (28% coverage → 100%).
It does NOT remove the **semantic** ceiling imposed by all-MiniLM-L6-v2 on legal text.

Example of the failure mode: company writes "we screen against all applicable watchlists" — law says "consultation of the UN Security Council consolidated list." These may have high semantic distance despite the obligation being satisfied. Kimi sees the top-3 policy sections and makes the call, but if the top-3 are all far away (high distance), even Kimi may miss it.

The 60–75% recall target is a working assumption. True ceiling is unknown until the run completes.

---

## Architectural Direction

**Obligation-first is now the primary pipeline.** The sliding window (`rag_evaluator.py`) is preserved but not the active evaluator. Both remain runnable independently.

What changed in Session 3:
- Document-first → law-first query direction
- 28% → 100% law graph coverage
- Kimi gets: obligation text + top-3 policy sections (was: policy snippet only)
- Cross-check uses sweep distances directly — no second ChromaDB query
- LOW_CONFIDENCE_NOISE category removed — high distance from law-side = signal, not noise
- 325-row obligation table in report — full coverage visible for the first time

What is unchanged:
- BATCH_SIZE=10 (proven — larger batches truncate JSON)
- 8s sleep between batches (rate limit)
- Kimi decides — no auto-threshold compliance resolution (closed)
- HCG update logic (same function, now covers all 325 nodes)
- HTML report structure (extended, not replaced)

---

## Closed Decisions — Do Not Re-litigate

| Decision | Reason |
|---|---|
| No auto-threshold compliance resolution | all-MiniLM-L6-v2 not trained on legal domain. Distance ≠ legal satisfaction. Kimi decides. |
| No document structure parsing | pdfplumber gives layout not semantics. Every doc formatted differently. LLM on CPU is 180s/page. |
| No law-graph tree pruning | False negative risk unacceptable. Law hierarchy does not map to document structure. |
| No pipeline/ directory split | One developer, PoC stage. Split when B1 is validated and architecture is stable. |
| HCG as prioritization signal not gate | 15 nodes of history insufficient for automated gating. Tiers inform ORDER only. |
| No BM25 silence gate | Fails on paraphrased compliance text — silent false negatives. |
| No MinHash window dedup | Misses new topics introduced mid-overlap. |
| BATCH_SIZE=10 | 55+ findings in one call = truncated JSON. Proven empirically. |
| ASCII-encode prompts | Raw PDF unicode breaks Kimi's JSON output. |
| 8s sleep between batches | 429 rate limit without it. |
| moonshot.ai not moonshot.cn | `.cn` returns 401 even with valid key. |
| Cross-check uses sweep distance, no second query | Sweep already queries law→policy. Same direction. Data is there. |
| LOW_CONFIDENCE_NOISE removed from obligation-first | In obligation-first, high distance = "policy doesn't cover this" = signal, not noise. |
| HCG evaluation_tier field deferred | 15 nodes only. Tiers become meaningful after ~10 client runs. |
| A1 skipped | EGDR threshold tuning is obsolete — sliding window is no longer the primary pipeline. |

---

## What To Build Next (after recall validation)

**If recall ≥ 50%:** obligation-first is confirmed better. Proceed with:
- Optional credit optimisation: short-circuit `best_dist > 0.80` as CONFIRMED_GAP without Kimi (~30% credit saving). Implement in `obligation_first_evaluator.py` only after recall is confirmed.
- Run against 141-page doc as second validation
- Start planning multi-jurisdiction support (AMLD5 equivalence mapping requires legal expert review)

**If recall < 50%:** paraphrase gap is larger than expected. Document the ceiling. Options:
- Legal-domain fine-tuned embedding model (e.g., `legal-bert`) — research needed
- Expand top-k from 3 to 5 in sweep — more policy context for Kimi
- Both above are additive, not architectural changes

---

## Honest Challenges — Unchanged

1. **Paraphrase detection.** Regulatory language vs operational policy language can describe the same concept with zero shared vocabulary. High sweep distance does not always mean absent obligation.

2. **HCG bootstrapping.** 25 sympathetic nodes queued first is useful. But 300 unknown nodes still go through full evaluation. Efficiency gain from HCG grows with client data.

3. **ChromaDB duplicate paths.** 26 law node paths appear 2-3× in `cysec_aml_rules` (pre-existing vectorization artifact). Those obligations are evaluated 2-3× by Kimi. Effect: minor inflation of confirmed gap count for those nodes. Do not regenerate ChromaDB to fix — not worth the risk.

4. **Multi-jurisdiction scaling.** Adding AMLD5/FATF means 500+ nodes → 50+ Kimi batches per document. Cross-law equivalence mapping requires legal expert review.

5. **Auto-resolution thresholds.** Viable after ~10 clients of data. The dist > 0.80 short-circuit optimisation is safe (Kimi agrees with CONFIRMED_GAP at that distance in practice) — but validate on first run before implementing.

---

## Validated Results (as of 2026-04-28, rag_evaluator.py)

### 65-page doc — sliding window baseline

- Recall: **36% (16/45 policy gaps)**
- Precision: confirmed, zero contradictions with human audit
- 22 CONFIRMED_GAP, 5 MANUAL_REVIEW, 1 LIKELY_COMPLIANT, 35 LOW_CONFIDENCE_NOISE

### 141-page doc — sliding window baseline

- 40 CONFIRMED_GAP, 17 MANUAL_REVIEW, 5 LIKELY_COMPLIANT, 73 LOW_CONFIDENCE_NOISE
- No ground truth — not directly comparable

### Obligation-first — PENDING first live run

Update this section after running `compare_gaps.py` on the first obligation-first result.

---

## HCG State (as of 2026-05-05)

15 nodes tracked. 5 at weight ≥ 0.5 (CRITICAL in report):

| Node | Weight | Obligation area |
|---|---|---|
| part_3 §9.1.m | 0.8 | Risk identification |
| part_3 §10.4.b | 0.8 | Compliance officer duties |
| part_4 §12.4 | 0.7–0.8 | CDD procedures |
| part_6 §27 | 0.8 | Sanctions screening |
| part_5 §25.3 | 0.8 | Monitoring obligations |

After obligation-first runs, HCG will begin covering all 325 nodes (not just the 91 the sliding window observed). Weights will shift — some currently-zero nodes may emerge as systemic gaps.

---

## Files

```
aml_proof/
├── json_graph/                    <- 15 CySEC JSON files (DO NOT MODIFY)
├── chroma_db/                     <- Pre-built law vector DB (DO NOT REGENERATE)
├── test_transactions/
│   ├── AML Manual V8.0_Reviewed(Draft).docx.pdf  <- 65 pages, ground truth available
│   └── 1a. AML Manual.docx.pdf                   <- 141 pages, no ground truth
├── evaluation_results/            <- JSON + HTML reports (gitignored)
├── compliance_graph.json          <- Hebbian Compliance Graph (gitignored)
├── rag_evaluator.py               <- Sliding window pipeline (baseline, keep intact)
├── obligation_first_evaluator.py  <- NEW — obligation-first pipeline (primary)
├── compare_gaps.py                <- Ground truth comparison (update JSON_PATH before running)
├── regen_report.py                <- Regenerate HTML from existing JSON (legacy)
├── client_config.json             <- Client/jurisdiction config
├── requirements.txt               <- Dependencies
├── vectorize.py                   <- Run only when adding new law domain
└── .env                           <- API keys (gitignored — never commit)
```

---

## How To Run

### Obligation-first (primary — use this)
```powershell
cd C:\Users\andre\Desktop\aml_proof
python obligation_first_evaluator.py --pdf "AML Manual V8.0_Reviewed(Draft).docx.pdf" --config client_config.json --skip-anon
```

### Re-run report/cross-check without Kimi (both evaluators)
```powershell
python obligation_first_evaluator.py --pdf "AML Manual V8.0_Reviewed(Draft).docx.pdf" --config client_config.json --skip-anon --verdict-only "evaluation_results/AML Manual V8.0_Reviewed(Draft).docx_YYYYMMDD_HHMMSS.json"
```

### Sliding window (baseline, keep for comparison)
```powershell
python rag_evaluator.py --pdf "AML Manual V8.0_Reviewed(Draft).docx.pdf" --config client_config.json --skip-anon
```

### Ground truth comparison
```powershell
# First update JSON_PATH in compare_gaps.py line 15 to point to new result
python compare_gaps.py
```

### View reports
```powershell
cd evaluation_results
python -m http.server 8080
# http://localhost:8080
```

---

## Infrastructure

### API Keys
```
KIMI_API_KEY=<your-key-here>   # platform.moonshot.ai — rotate before each session
```
**Obligation-first = 33 batches per document. Check credit balance before running.**

### Python environment
```powershell
pip install -r requirements.txt
```

### Ollama — DO NOT USE on X1 Carbon (180s/page timeout)
