# AML Compliance Auditor — Current Status

> Last updated: 2026-04-29. Read `nextsession.md` for full context and implementation details.

---

## What's Built and Working

| Component | Status | Notes |
|---|---|---|
| CySEC JSON Knowledge Graph | **Complete** | 15 files, 325 legal nodes — DO NOT MODIFY |
| ChromaDB Vector DB | **Complete** | Built, persistent, all-MiniLM-L6-v2 embeddings — DO NOT REGENERATE |
| PDF extraction (Phase 1) | **Working** | PyPDF2, all pages |
| Ephemeral policy index (Phase 1c) | **Working** | Per-run ChromaDB collection + bigram set |
| Sliding window EGDR (Phase 1b) | **Working but limited** | Only touches 28% of law graph — being replaced by B1 |
| Deduplication (Phase 2) | **Working** | Not needed in obligation-first architecture |
| Kimi verdict (Phase 4) | **Working** | Batches of 10, 8s sleep, 5 retries on 429 |
| Bidirectional cross-check (Phase 4b) | **Working** | Moves into main pipeline in obligation-first |
| Hebbian Compliance Graph (Phase 4c) | **Working** | 15 nodes tracked, bug in counter (see Known Issues) |
| HTML report (Phase 5) | **Working** | Collapsible sections, KPI bars, law node references |
| `compare_gaps.py` | **New** | Ground truth comparison vs XLSX human audit |

---

## Validated Performance (65-page Capital.com Manual)

Evaluated against human expert audit (CCSV AML_KYC.xlsx — 66 confirmed findings, same document):

| Metric | Result |
|---|---|
| System CONFIRMED_GAPs | 22 |
| Recall on policy-level gaps | **36% (16/45)** |
| Independently confirmed gaps | 3 clean matches (sys[126], sys[69], sys[115]) |
| False positives confirmed | 0 (no contradictions with human audit) |
| Operational gaps (out of scope) | 21 — require CRM/client file review |

**Precision looks solid. Recall is the problem.** Every missed gap maps to a law node the sliding window never touched.

---

## Test Documents

| File | Company | Pages | Runs | Status |
|---|---|---|---|---|
| `AML Manual V8.0_Reviewed(Draft).docx.pdf` | Capital Com SV Investments Ltd | 65 | 3 | Ground truth validated via XLSX |
| `1a. AML Manual.docx.pdf` | PM MTF Ltd | 141 | 2 | No ground truth available |

Ground truth files (in Downloads — do not move):
- `CCSV - AML_KYC.xlsx` — 2025 human audit of Capital.com, 66 gaps
- `Capital Com - AML Health Check 09.02.2022.docx` — 2022 health check, same company

---

## Known Issues

| Issue | Severity | Fix | Track |
|---|---|---|---|
| 28% law graph coverage (sliding window) | **Critical** | Build obligation-first sweep (B1) | B |
| 36% recall on policy gaps | **Critical** | B1 fixes this | B |
| EGDR threshold 6.5 → needs 7.0 | Medium | 2-min change in `detect_violations()` | A1 |
| HCG `documents_evaluated` counts per verdict not per run | Low | 5-min fix in `_update_hcg()` | A4 |
| HCG CRITICAL escalation not in report | Low | 5 nodes qualify at weight ≥ 0.5 | A3 |
| Kimi context too thin (policy snippet only) | Medium | Add obligation text + top-3 sections (B2) | B |
| Anonymization skipped on CPU machine | Known | `--skip-anon` flag; fix when GPU arrives | Post-PoC |

---

## PoC Status: Architecturally Complete (2026-05-05)

All build tasks finished. Recall ceiling confirmed.

| Experiment | Result |
|---|---|
| Obligation-first sweep (B1) | 100% law coverage, 172 confirmed gaps |
| n_results=5 experiment | No recall improvement → reverted to n_results=3 |
| Paraphrase ceiling | **Confirmed at 47%** — hard limit of all-MiniLM-L6-v2 |
| Anonymization | Permanently removed (internal hardware, AUP covered) |

**Next meaningful improvement:** Replace embedding model with legal-domain model (post-GPU workstation). Candidates: `nlpaueb/legal-bert-base-uncased`, `law-ai/InLegalBERT`. Requires re-running `vectorize.py` and a fresh evaluation.

---

## How To Run (CPU machine)

```powershell
# Set API key (load from .env — never paste key in terminal history if screen-sharing)
cd C:\Users\andre\Desktop\aml_proof

# Current pipeline (sliding window)
python rag_evaluator.py --pdf "AML Manual V8.0_Reviewed(Draft).docx.pdf" --config client_config.json --skip-anon

# Ground truth comparison
python compare_gaps.py

# View reports
cd evaluation_results
python -m http.server 8080
# Open: http://localhost:8080
```
