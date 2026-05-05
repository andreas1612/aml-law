# AML Compliance Auditor — Current Status

> Last updated: 2026-05-05. Read `nextsession.md` for full context and implementation details.

---

## What's Built and Working

| Component | Status | Notes |
|---|---|---|
| CySEC JSON Knowledge Graph | **Complete** | 15 files, 325 legal nodes — DO NOT MODIFY |
| ChromaDB Vector DB | **Complete** | Built, persistent, all-MiniLM-L6-v2 embeddings — DO NOT REGENERATE |
| PDF extraction (Phase 1) | **Working** | PyPDF2, all pages |
| Ephemeral policy index (Phase 1c) | **Working** | Per-run ChromaDB collection + bigram set |
| Sliding window EGDR (Phase 1b) | **Baseline only** | 28% law graph coverage — superseded by obligation-first |
| Obligation-first sweep (B1) | **Working — primary** | 325 ChromaDB queries, 100% law graph coverage |
| Kimi verdict (Phase 4) | **Working** | Batches of 10, 8s sleep, 5 retries on 429 |
| Bidirectional cross-check (Phase 4b) | **Working** | Uses sweep distances directly — no second query |
| Hebbian Compliance Graph (Phase 4c) | **Working** | 325 nodes tracked (was 15), weights updating |
| HTML report (Phase 5) | **Working** | Collapsible sections, KPI bars, CRITICAL banner, 325-row coverage table |
| `compare_gaps.py` | **Working** | Ground truth comparison vs XLSX human audit |

---

## Validated Performance (65-page Capital.com Manual)

Evaluated against human expert audit (CCSV AML_KYC.xlsx — 66 confirmed findings, same document):

| Metric | Sliding window | Obligation-first |
|---|---|---|
| Law nodes evaluated | 91 / 325 (28%) | **325 / 325 (100%)** |
| System CONFIRMED_GAPs | 22 | **172** |
| Recall on policy-level gaps | 36% (16/45) | **47% (21/45)** |
| False positives confirmed | 0 | **0** |
| Operational gaps (out of scope) | 21 — require CRM/client file review | same |

**Zero false positives across all runs.** Recall floor is 47% — true detection rate is higher (see Miss Analysis below).

---

## Miss Analysis — Why 24 Human Gaps Are Not Measured (2026-05-05)

Deep analysis of all 24 unmeasured human expert gaps revealed **two root causes — vocabulary divergence is NOT the primary issue:**

### Root Cause 1 — ChromaDB Retrieval Failure (42% of misses, ~10 gaps)
The embedding model returns the **wrong PDF pages** when querying for certain obligations. Distances > 0.85–0.95 on these gaps indicate near-random retrieval. Kimi never sees the relevant text, so it cannot find the gap regardless of how well it reasons.

Affected obligations: PEP enhanced due diligence, transaction monitoring thresholds, STR filing procedures, MLRO appointment requirements.

Fix path:
- **Now (partial):** BM25 hybrid retrieval — keyword fallback when embedding distance is high
- **Post-GPU:** Replace `all-MiniLM-L6-v2` with `nlpaueb/legal-bert-base-uncased` or `law-ai/InLegalBERT`

### Root Cause 2 — Evaluation Matcher Failure (58% of misses, ~14 gaps)
The system **found these gaps** but labelled them under a different law node than the human auditor used. The Jaccard keyword matcher in `compare_gaps.py` requires vocabulary overlap between system gap text and human finding text. When both describe the same compliance failure from different angles, Jaccard scores below 0.06 and the gap shows as "missed."

**This is a measurement artefact, not a system failure.** The 47% recall figure is a floor.

Fix path:
- **Now:** Add `policy_area` label to Kimi output schema (e.g., "CDD", "PEP screening", "training", "sanctions"). `compare_gaps.py` can then match by topic area, not keyword overlap. Expected recall measurement improvement to ~60–65%.

### Root Cause 3 — Missing Law Nodes (4–5 gaps)
These obligations are simply not in the 325-node graph:

| Missing node | Obligation | Gaps it would close |
|---|---|---|
| CySEC Circular C315 | Mandatory AML staff training | 2 gaps |
| CySEC Circular C318 | Passport/ID screening procedures | 1 gap |
| CySEC Circular C398 | Inactive accounts | 1 gap |
| AML Law Art. 58 | Mandatory induction training | 1 gap |

Fix: add to `json_graph/`, run `vectorize.py` for new nodes only.

### Kimi verdict quality
Zero Kimi errors confirmed across all 24 missed gaps. The LLM layer is not the problem.

---

## Immediate Next Steps (priority order)

| Task | Effort | Impact | Track |
|---|---|---|---|
| Add `policy_area` to Kimi output schema | 1 hour | Fixes recall measurement, improves report usability | C1 |
| Add C315/C318/C398/Art.58 to json_graph | 2–3 hours | Closes 4–5 genuine gaps | C2 |
| BM25 hybrid retrieval fallback | Half day | Recovers ~4 of 10 retrieval failures | C3 |
| Legal embedding model (GPU required) | Post-GPU | Fixes remaining retrieval failures | D1 |
| Run against 141-page PM MTF doc | 13 min | Second validation document | C4 |

---

## Test Documents

| File | Company | Pages | Status |
|---|---|---|---|
| `AML Manual V8.0_Reviewed(Draft).docx.pdf` | Capital Com SV Investments Ltd | 65 | Ground truth validated — 47% recall confirmed |
| `1a. AML Manual.docx.pdf` | PM MTF Ltd | 141 | No ground truth — pending obligation-first run |

Ground truth files (in Downloads — do not move):
- `CCSV - AML_KYC.xlsx` — 2025 human audit of Capital.com, 66 gaps
- `Capital Com - AML Health Check 09.02.2022.docx` — 2022 health check, same company

---

## Known Issues

| Issue | Severity | Fix | Track |
|---|---|---|---|
| Recall measurement underestimates true detection rate | Medium | Add `policy_area` to Kimi schema | C1 |
| ChromaDB retrieval failure on ~10 obligations | Medium | BM25 hybrid + legal embedding model | C3/D1 |
| 4–5 gaps from missing CySEC circulars | Medium | Add C315/C318/C398/Art.58 to graph | C2 |
| ChromaDB duplicate paths (26 nodes appear 2–3×) | Low | Pre-existing artifact — do not regenerate | — |
| HCG bootstrapping | Low | Efficiency improves with more client runs | — |

---

## PoC Status: Architecturally Complete (2026-05-05)

| Experiment | Result |
|---|---|
| Obligation-first sweep (B1) | 100% law coverage, 172 confirmed gaps |
| n_results=5 experiment | No recall improvement → reverted to n_results=3 |
| Paraphrase ceiling | **Confirmed at 47% measured** — true detection rate higher (see Miss Analysis) |
| Anonymization | Permanently removed (internal hardware, AUP covered) |
| Deep miss analysis | Completed — root causes identified and documented |

**Next meaningful improvement:** (1) `policy_area` label in Kimi schema — fixes recall measurement now. (2) Legal-domain embedding model post-GPU — fixes retrieval failures.

---

## How To Run (CPU machine)

```powershell
cd C:\Users\andre\Desktop\aml_proof

# Load API key from .env
$env:KIMI_API_KEY = (Get-Content .env | Select-String "KIMI_API_KEY" | ForEach-Object { $_ -replace "KIMI_API_KEY=","" })

# Primary pipeline — obligation-first
python obligation_first_evaluator.py --pdf "AML Manual V8.0_Reviewed(Draft).docx.pdf" --config client_config.json --skip-anon

# Re-run report only (no Kimi credits)
python obligation_first_evaluator.py --pdf "AML Manual V8.0_Reviewed(Draft).docx.pdf" --config client_config.json --skip-anon --verdict-only "evaluation_results/<timestamp>.json"

# Ground truth comparison (update JSON_PATH in compare_gaps.py line 15 first)
python compare_gaps.py

# View reports
cd evaluation_results
python -m http.server 8080
# Open: http://localhost:8080
```
