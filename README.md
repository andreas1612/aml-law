# AML Compliance Auditor PoC

Automated AML policy auditor that evaluates corporate AML manuals against the **CySEC Consolidated AML Directive** using a local knowledge graph + vector database. Zero PII leakage by design.

---

## What It Does

Takes a corporate AML policy PDF and produces a structured compliance gap report:
- Which CySEC obligations are satisfied
- Which are absent (confirmed gaps)
- Which need human review (borderline)
- Priority remediation list for the compliance officer

Validated against a professional human audit of the same document: **precision confirmed, 36% recall** (recall fix is the current build priority — see `nextsession.md`).

---

## Architecture

```
PDF Input
  │
  ├─ Phase 1:  PyPDF2 extracts all pages
  │
  ├─ Phase 1c: Pages → ephemeral ChromaDB policy collection
  │            + bigram index for pre-filtering
  │
  ├─ Phase 2:  Obligation-first sweep [BUILDING]
  │            Current: EGDR sliding window (28% law graph coverage)
  │            Target:  325 law node queries → policy collection (100% coverage)
  │
  ├─ Phase 3:  Anonymization via Ollama [SKIPPED on CPU — --skip-anon flag]
  │
  ├─ Phase 4:  Kimi API verdict — batches of 10, 8s sleep, 5 retries
  │            Returns: GAP / COMPLIANT + severity + gap description
  │
  ├─ Phase 4c: Hebbian Compliance Graph update
  │            Tracks which obligations are systemic gaps across clients
  │
  └─ Phase 5:  HTML report — KPI dashboard + collapsible gap sections
```

---

## Knowledge Base

| Component | Details |
|---|---|
| CySEC JSON Graph | 15 files (Parts 1-10, Appendices 1-5) — 325 legal nodes |
| ChromaDB | Pre-built, persistent, `all-MiniLM-L6-v2` embeddings |
| Jurisdictions | CySEC AML Directive. Architecture supports EU AMLD5/6, FATF via config |

---

## Data Sovereignty

| Step | Where it runs |
|---|---|
| PDF extraction | Local — PyPDF2 |
| Vector search | Local — ChromaDB |
| PII anonymization | Local — Ollama (`--skip-anon` on CPU machine) |
| Verdict | External — Kimi API (Moonshot). Only anonymized text + law excerpt sent |

---

## Files

```
aml_proof/
├── json_graph/              ← CySEC law graph (DO NOT MODIFY)
├── chroma_db/               ← Law vector DB (DO NOT REGENERATE)
├── test_transactions/       ← Input PDFs
├── evaluation_results/      ← JSON + HTML reports (gitignored)
├── compliance_graph.json    ← Hebbian Compliance Graph (gitignored)
├── rag_evaluator.py         ← Current pipeline (sliding window)
├── compare_gaps.py          ← Ground truth comparison vs human audit XLSX
├── client_config.json       ← Jurisdiction + model config
├── vectorize.py             ← Run only when adding a new law domain
├── assess_pdf.py            ← Quick single-page test tool
├── .env                     ← API keys (gitignored)
├── nextsession.md           ← Full architecture, decisions, build instructions
├── status.md                ← Current state and known issues
└── architecture_decisions.md ← Closed design decisions with rationale
```

---

## Quick Start (CPU machine)

```powershell
pip install -r requirements.txt

# API key must be in .env as: KIMI_API_KEY=your-key-here
cd C:\Users\andre\Desktop\aml_proof
python rag_evaluator.py --pdf "AML Manual V8.0_Reviewed(Draft).docx.pdf" --config client_config.json --skip-anon

# Compare against human expert ground truth
python compare_gaps.py

# View HTML report
cd evaluation_results && python -m http.server 8080
```

---

## Current Validated Results

| Document | Pages | CONFIRMED_GAPs | Recall vs ground truth |
|---|---|---|---|
| Capital Com AML Manual v8.0 | 65 | 22 | 36% (validated vs 2025 professional audit) |
| PM MTF AML Manual | 141 | 40 | No ground truth available |

**Next build:** `obligation_first_evaluator.py` — raises recall to estimated 70%+ by querying all 325 law nodes. See `nextsession.md` Track B.
