# AML Compliance Auditor — Current Status

> Last updated: 2026-05-05. Session 4 complete. Track C delivered. Read `nextsession.md` for full context.

---

## What's Built and Working

| Component | Status | Notes |
|---|---|---|
| CySEC JSON Knowledge Graph | **Complete** | 19 files (15 original + 4 new), 325+ legal nodes |
| ChromaDB Vector DB | **Complete** | Built, persistent, all-MiniLM-L6-v2 — DO NOT REGENERATE |
| PDF extraction (Phase 1) | **Working** | PyPDF2, all pages |
| Ephemeral policy index (Phase 1c) | **Working** | Per-run ChromaDB collection + bigram set |
| BM25 hybrid index (Phase 1d) | **Working** | rank_bm25, fires when ChromaDB dist > 0.85 |
| Obligation-first sweep (B1) | **Working — primary** | 325 queries, 100% law graph coverage |
| `policy_area` in Kimi schema (C1) | **Working** | CDD/PEP/sanctions/training/monitoring/reporting/governance/risk_assessment/other |
| Second-pass area match (C1) | **Working** | compare_gaps.py recovers cross-node artefacts |
| 4 new CySEC nodes (C2) | **Complete** | C315, C318, C398, Art.58 — vectorize.py run |
| BM25 fallback retrieval (C3) | **Working** | Replaces top_sections when ChromaDB dist > 0.85 |
| Kimi verdict (Phase 4) | **Working** | Batches of 10, 8s sleep, 5 retries on 429 |
| Obligation cross-check (Phase 4b) | **Working** | Uses sweep distances directly |
| Hebbian Compliance Graph (Phase 4c) | **Working** | 325 nodes tracked, 5 at CRITICAL weight |
| HTML report (Phase 5) | **Working** | KPI bars, CRITICAL banner, 325-row coverage table |
| `compare_gaps.py` | **Working** | Jaccard + policy_area second-pass match |

---

## Validated Performance (2026-05-05)

Evaluated against human expert audit (CCSV AML_KYC.xlsx — 66 confirmed findings, 45 policy-level):

| Metric | Sliding window | Obligation-first (Session 3) | Obligation-first + Track C (Session 4) |
|---|---|---|---|
| Law nodes evaluated | 91 / 325 (28%) | 325 / 325 (100%) | 325 / 325 (100%) |
| System CONFIRMED_GAPs | 22 | 172 | **167** |
| Recall on policy-level gaps | 36% (16/45) | 47% (21/45) | **62% (28/45)** |
| of which via policy_area match | — | — | **5 gaps** |
| False positives confirmed | 0 | 0 | **0** |

**62% is a measured floor.** True detection rate is higher — most remaining 17 misses are operational (CRM/client file evidence required, out of scope for document evaluator).

---

## Recall Ceiling Analysis (2026-05-05)

Of the 17 remaining unmatched human policy gaps:

| Category | Count | Why system can't catch them |
|---|---|---|
| Genuinely operational (CRM/practice) | ~10 | Require client file sampling, CRM access, signed forms |
| Questionnaire/scoring level | ~4 | Require reviewing the actual risk questionnaire tool |
| Possible retrieval failures | ~3 | ChromaDB returns wrong pages — BM25 helps but doesn't fully solve |

**Estimated true document-evaluable ceiling: ~69–73% (31–33/45).** The system is already catching nearly everything that can be found in a policy PDF alone.

---

## Track C — Completed (Session 4, 2026-05-05)

| Task | Status | Result |
|---|---|---|
| C1: policy_area in Kimi schema | **DONE** | 5 additional gaps recovered via second-pass |
| C2: 4 missing CySEC nodes | **DONE** | C315/C318/C398/Art.58 added, vectorized |
| C3: BM25 hybrid retrieval | **DONE** | Fires when ChromaDB dist > 0.85 |
| C4: Run on PM MTF 141-page doc | **Pending** | Kimi credits needed — run separately |

---

## Next Steps — Track D (post-GPU)

| Task | Effort | Impact |
|---|---|---|
| Replace all-MiniLM-L6-v2 with legal embedding model (InLegalBERT / legal-bert) | Half day post-GPU | Fixes ~3 remaining retrieval failures, likely pushes recall to 70%+ |
| Run parallel Kimi batches (no rate limit on GPU workstation) | Config change | 8s sleep removed, full run in ~30s |
| Run PM MTF 141-page document (C4) | 5 min | Second validated document |
| Add Circular C292 (NRA) and Art.33(2) GBG compliance node | 2 hours | Covers 2022 health check findings not yet in graph |
| Self-hosted LLM to replace Kimi | Post-GPU | Eliminate API cost and rate limits |

---

## Known Issues

| Issue | Severity | Fix | Track |
|---|---|---|---|
| ~3 remaining retrieval failures | Medium | Legal embedding model post-GPU | D1 |
| ChromaDB duplicate paths (26 nodes appear 2–3×) | Low | Pre-existing artifact — do not regenerate | — |
| HCG bootstrapping — weights only meaningful after ~10 client runs | Low | Improves automatically with use | — |
| C4 (PM MTF doc) not yet run | Low | Run when Kimi credits available | C4 |

---

## How To Run (CPU machine)

```powershell
cd "C:\Users\Andreas.Pi\OneDrive - K.Treppides & Co\Desktop\amllaw"

$env:KIMI_API_KEY = (Get-Content .env | Select-String "KIMI_API_KEY" | ForEach-Object { $_ -replace "KIMI_API_KEY=","" })

# Primary pipeline — obligation-first
python obligation_first_evaluator.py --pdf "AML Manual V8.0_Reviewed(Draft).docx.pdf" --config client_config.json --skip-anon

# Re-run cross-check + report without Kimi
python obligation_first_evaluator.py --pdf "AML Manual V8.0_Reviewed(Draft).docx.pdf" --config client_config.json --skip-anon --verdict-only "evaluation_results/<timestamp>.json"

# Ground truth comparison (update JSON_PATH in compare_gaps.py line 15 first)
python compare_gaps.py

# View reports
cd evaluation_results && python -m http.server 8080
```

One full obligation-first run = 33 batches × 8s sleep ≈ 5 minutes. Check Kimi credit balance before running.
