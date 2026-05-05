# AML Compliance Auditor PoC

Automated AML policy auditor that evaluates corporate AML manuals against the **CySEC Consolidated AML Directive** using a local knowledge graph + vector database. Zero PII leakage by design.

---

## What It Does

Takes a corporate AML policy PDF and produces a structured compliance gap report:
- Which CySEC obligations are satisfied
- Which are absent (confirmed gaps) — with severity and policy area
- Which need human review (borderline)
- Priority remediation list for the compliance officer

Validated against a professional human audit of the same document: **62% recall, 0 false positives** (2026-05-05).

---

## Architecture

```
PDF Input
  │
  ├─ Phase 1:   PyPDF2 extracts all pages
  │
  ├─ Phase 1c:  Pages → ephemeral ChromaDB policy collection + bigram index
  │
  ├─ Phase 1d:  BM25 index built from same pages (hybrid retrieval fallback)
  │
  ├─ Phase 2:   Obligation-first sweep — 325 law node queries → policy collection
  │             100% law graph coverage. BM25 fires when ChromaDB dist > 0.85.
  │
  ├─ Phase 3:   Anonymization — SKIPPED on CPU (--skip-anon)
  │
  ├─ Phase 4:   Kimi API verdict — batches of 10, 8s sleep, 5 retries
  │             Returns: GAP/COMPLIANT + severity + policy_area + gap description
  │
  ├─ Phase 4b:  Obligation cross-check using sweep distances (no second query)
  │
  ├─ Phase 4c:  Hebbian Compliance Graph update (325 nodes tracked)
  │
  └─ Phase 5:   HTML report — KPI dashboard, CRITICAL banner, 325-row coverage table
```

---

## Knowledge Base

| Component | Details |
|---|---|
| CySEC JSON Graph | 19 files — 325 base nodes + 28 new nodes (C315, C318, C398, Art.58) |
| ChromaDB | Pre-built, persistent, `all-MiniLM-L6-v2` embeddings |
| Jurisdictions | CySEC AML Directive. Architecture supports EU AMLD5/6, FATF via config |

---

## Data Sovereignty

| Step | Where it runs |
|---|---|
| PDF extraction | Local — PyPDF2 |
| Vector search | Local — ChromaDB |
| BM25 fallback | Local — rank_bm25 |
| PII anonymization | Local — Ollama (`--skip-anon` on CPU machine) |
| Verdict | External — Kimi API (Moonshot). Only policy text + law obligation sent |

---

## Files

```
amllaw/
├── json_graph/                    ← CySEC law graph (19 files, DO NOT MODIFY existing)
│   ├── part_1.json … part_10.json
│   ├── appendix_1.json … appendix_5.json
│   ├── cysec_circular_c315.json   ← NEW: AML staff training obligations
│   ├── cysec_circular_c318.json   ← NEW: Document verification / passport screening
│   ├── cysec_circular_c398.json   ← NEW: Inactive/dormant account procedures
│   └── aml_law_art58.json         ← NEW: Mandatory induction training
├── chroma_db/                     ← Law vector DB (DO NOT REGENERATE)
├── test_transactions/             ← Input PDFs
│   ├── AML Manual V8.0_Reviewed(Draft).docx.pdf   ← 65 pages, ground truth available
│   └── 1a. AML Manual.docx.pdf                    ← 141 pages, no ground truth
├── evaluation_results/            ← JSON + HTML reports
├── compliance_graph.json          ← Hebbian Compliance Graph (gitignored)
├── obligation_first_evaluator.py  ← Primary pipeline (obligation-first, B1+B2+C1+C3)
├── rag_evaluator.py               ← Baseline sliding window (do not modify)
├── compare_gaps.py                ← Ground truth comparison — Jaccard + policy_area match
├── vectorize.py                   ← Run only when adding new law nodes
├── client_config.json             ← Jurisdiction + model config
├── .env                           ← API keys (gitignored)
├── nextsession.md                 ← Full session handover and build instructions
├── status.md                      ← Current state and known issues
└── architecture_decisions.md      ← Closed design decisions with rationale
```

---

## Quick Start (CPU machine — X1 Carbon)

```powershell
cd "C:\Users\Andreas.Pi\OneDrive - K.Treppides & Co\Desktop\amllaw"

# Load API key
$env:KIMI_API_KEY = (Get-Content .env | Select-String "KIMI_API_KEY" | ForEach-Object { $_ -replace "KIMI_API_KEY=","" })

# Primary pipeline — obligation-first (33 batches, ~5 min)
python obligation_first_evaluator.py --pdf "AML Manual V8.0_Reviewed(Draft).docx.pdf" --config client_config.json --skip-anon

# Re-run report only (no Kimi credits used)
python obligation_first_evaluator.py --pdf "AML Manual V8.0_Reviewed(Draft).docx.pdf" --config client_config.json --skip-anon --verdict-only "evaluation_results/<timestamp>.json"

# Ground truth comparison (update JSON_PATH in compare_gaps.py line 15 first)
python compare_gaps.py

# View reports
cd evaluation_results && python -m http.server 8080
```

---

## Validated Results (2026-05-05)

| Document | Pages | CONFIRMED_GAPs | Recall vs ground truth |
|---|---|---|---|
| Capital Com AML Manual V8.0 | 65 | 167 | **62% (28/45 policy gaps), 0 false positives** |
| PM MTF AML Manual | 141 | — | No ground truth — pending run |

**62% is a measured floor.** Most remaining misses are operational gaps requiring CRM/client file review — outside document-evaluator scope.

---

## Ground Truth

| File | What it is |
|---|---|
| `CCSV - AML_KYC.xlsx` | 2024 professional human audit of Capital.com AML Manual — 66 findings, 45 policy-level |
| `Capital Com - AML Health Check 09.02.2022.docx` | 2022 AML Health Check by K. Treppides & Co — same company, earlier audit |

Ground truth applies to the 65-page Capital.com PDF only.
