# Next Session Handover — AML Compliance Auditor

> **You are on the X1 Carbon 2024 (32GB RAM). Read this entire file before starting. Then use the prompt at the bottom.**

---

## What We Built (Full Context)

### The System
An automated AML Compliance Auditor that evaluates corporate AML policy PDFs against structured legal knowledge graphs. It runs entirely locally except for the final verdict call to an external LLM API.

CySEC is the first law domain. The architecture is designed from the start to support multiple jurisdictions (EU AMLD5/6, FATF, FinCEN) without any changes to the evaluator code.

### Why It Works This Way
- CySEC law was converted into 15 structured JSON files (`json_graph/`) — one per Part and Appendix.
- These 15 files were vectorized into a local ChromaDB (`chroma_db/`) — 325 legal nodes, each with its exact JSON path as metadata.
- When a client PDF is evaluated, the system retrieves the **exact legal paragraph** that matches — no hallucination possible because we hand the real law directly to the final LLM.

### Data Sovereignty
```
PDF → [local PyPDF2 extraction]
    → [local ChromaDB — finds exact matching legal rule, raw text OK here]
    → [local Ollama anonymizer — strips PII from flagged pages only]
    → [Kimi/OpenAI API — only receives: sanitized text + law excerpt]
```
ChromaDB is local. Raw text never leaves the machine until after anonymization.
Anonymization runs only on pages that were flagged — not the entire document.

---

## What Is Already Done

| Component | Status | File |
|---|---|---|
| CySEC JSON Knowledge Graph | Complete | `json_graph/` |
| ChromaDB Vector Database | Built (325 nodes) | `chroma_db/` |
| PDF Text Extractor | Working | `assess_pdf.py` |
| PII Anonymizer | Coded, not yet run end-to-end | `anonymizer.py` |
| RAG Evaluator | Coded, needs full rewrite (see below) | `rag_evaluator.py` |
| Ollama | Must install on X1 Carbon | `OllamaSetup.exe` in repo root |

---

## Critical Architecture Decision — `rag_evaluator.py` Must Be Rewritten

The current `rag_evaluator.py` takes a fixed 1,000-character slice from the middle of the sanitized document. **This is wrong** for two reasons:
1. It arbitrarily cuts sentences mid-word.
2. It only evaluates ~1% of an 80-page document.

---

## The Correct Architecture: Full-Coverage Sliding Window with Deferred Anonymization

### Why "Full Coverage" Is Non-Negotiable

Earlier architectural discussions explored adding a BM25 silence gate (skip pages with low legal vocabulary score) and MinHash window deduplication (skip windows that overlap heavily with a previous match). Both were rejected for the same fundamental reason:

**A compliance audit has exactly one failure mode that matters: a silent false negative.**

A BM25 gate scores on vocabulary overlap with the law text. If a client policy describes customer due diligence as "onboarding identity verification process" and the CySEC node uses "customer due diligence obligations", the BM25 score is low and the page gets silently dropped — before ChromaDB ever sees it. ChromaDB uses semantic embeddings and would have caught this. The gate fires before the tool that actually understands meaning.

MinHash deduplication has the same problem. Window [1-3] matches a node, so window [2-4] is skipped because 2/3 of the content overlaps. But page 4 introduces a new policy section. That section never gets evaluated because the skip decision was made before reading page 4.

Both optimizations trade coverage for speed. For a proof of concept that must demonstrate correctness, this trade is unacceptable. Speed optimizations belong on the GPU workstation, validated against a baseline that is provably complete.

The sliding window with step=1 already provides the coverage guarantee:

```
Page 1   → evaluated in window [1-3]
Page 2   → evaluated in windows [1-3], [2-4]
Page 3+  → evaluated in three consecutive windows
Last page → evaluated in window [N-2, N-1, N]
```

Every page appears in at least one window. No page can be missed. This is the only architecture that can make that claim.

### Why Anonymize After Detection, Not Before

The previous version anonymized every page before querying ChromaDB. This was the primary performance bottleneck (~5 minutes for 80 pages at 14B model speed) and it was unnecessary.

ChromaDB runs locally. Querying it with raw text carries zero data sovereignty risk. The only system that must never receive raw PII is the external Kimi API. Anonymization is therefore a gate before the external call, not before the local retrieval.

After the sliding window identifies which page ranges contain compliance gaps, only those page ranges need anonymization. A typical 80-page AML policy has 10-20 flagged pages. The difference is 40-80 seconds of Ollama time versus 320 seconds.

This optimization is safe because it operates after full detection is complete. Nothing gets skipped. The coverage guarantee is preserved.

### The Pipeline

```
Startup:
  - Load jurisdiction config (which law collections apply to this client)
  - Connect to ChromaDB

Phase 1 — Full Detection (all local, raw text):
  For each page 1..N:
    1. PyPDF2 extract → raw_text

  Build sliding windows, step = 1, no pages skipped:
    2. Combine 3 consecutive pages into window_text
    3. Query ChromaDB with raw window_text
    4. If distance < CHROMA_THRESHOLD → record (page_range, node_path, jurisdiction, raw_snippet, distance)
    5. Slide forward by 1 page

Phase 2 — Deduplication:
    6. Deduplicate by (node_path + overlapping page ranges)
    7. Merge findings that share the same page range across different jurisdictions
       into a single finding with multiple legal citations

Phase 3 — Anonymize ONLY Flagged Page Ranges:
    8. For each unique flagged page range → run Ollama 14B anonymizer
    9. Replace raw_snippet with anonymized_snippet in the findings list

Phase 4 — Verdict:
   10. ONE Kimi API call with all findings, structured by page range
   11. Save JSON to evaluation_results/
```

### Configurable Thresholds (do not hardcode)

| Parameter | Default | Effect if too high | Effect if too low |
|---|---|---|---|
| `CHROMA_THRESHOLD` (distance) | 0.4 | false positives | missed violations |

Both values must be in a config file or CLI argument. Run manually against 3-4 sample documents to calibrate before trusting results.

---

## Multi-Jurisdiction Architecture (CySEC Is Law Domain 1 of N)

CySEC is the first law domain. The system is designed to add EU AMLD5, EU AMLD6, FATF Recommendations, FinCEN BSA, and others without changing the evaluator code.

### ChromaDB Collections — One Per Jurisdiction

```
chroma_db/
  collections/
    cysec_consolidated_2024      ← exists now
    eu_amld5                     ← add next
    eu_amld6
    fatf_recommendations_2023
    fincen_bsa
```

At query time, the evaluator queries all collections listed in the client's jurisdiction config simultaneously. The match metadata carries which collection (jurisdiction) it came from.

### Universal Legal Node Schema

Every law domain must be converted into this schema before vectorization. The evaluator reads from metadata — it never references CySEC by name in code.

```json
{
  "jurisdiction": "CySEC",
  "instrument": "Consolidated AML Directive 2024",
  "part": "Part 4",
  "article": "3.2",
  "obligation_type": "customer_due_diligence",
  "text": "...",
  "severity": "mandatory"
}
```

The existing CySEC JSON graph must be validated against this schema. Any new law domain must produce nodes in this format.

### Cross-Jurisdiction Finding Structure

When multiple jurisdictions flag the same page range, they become one finding:

```json
{
  "finding_id": 1,
  "page_range": [14, 16],
  "gap_description": "Insufficient specification of CDD triggers for high-risk clients",
  "legal_citations": [
    {
      "jurisdiction": "CySEC",
      "instrument": "Consolidated AML Directive 2024",
      "article": "Part 4 §3.2",
      "obligation": "Enhanced due diligence for high-risk business relationships"
    },
    {
      "jurisdiction": "EU",
      "instrument": "AMLD5",
      "article": "Article 18(1)",
      "obligation": "Enhanced due diligence measures for high-risk third countries"
    }
  ],
  "severity": "mandatory",
  "anonymized_excerpt": "..."
}
```

### Client Jurisdiction Config

Each client evaluation is driven by a config, not hardcoded logic:

```json
{
  "client_id": "client_001",
  "regulated_under": ["cysec_consolidated_2024"],
  "evaluation_date": "2026-04-28"
}
```

When EU AMLD is added, change `regulated_under` to include it. Evaluator code unchanged.

---

## Speed Optimizations Deferred to GPU Workstation

These were designed and rejected for the PoC. They are not abandoned — they are deferred until the system's correctness is proven and tensor core hardware is available.

| Optimization | Rationale for deferral |
|---|---|
| BM25 silence gate | Risks silent false negatives on paraphrased compliance text |
| MinHash window deduplication | Risks missing new topics introduced mid-overlap |
| Parallel Ollama instances | GPU workstation makes this natural; CPU setup adds complexity for marginal gain |
| Page content SHA-256 cache | Worth adding for repeat clients once pipeline is validated |

On a GPU workstation running a 32B or 70B model, anonymization time drops from 4s/page to under 0.5s/page. The speed problem becomes irrelevant and these optimizations become optional tuning rather than necessity.

---

## Model Choice for X1 Carbon 2024

**Use `qwen2.5:14b-instruct-q4_K_M`** for the anonymizer.

| Model | RAM Used | Speed | Verdict |
|---|---|---|---|
| qwen2.5:3b | ~3GB | ~40 t/s | Too weak for legal PII understanding |
| **qwen2.5:14b-instruct-q4_K_M** | ~9GB | ~12-16 t/s | Best for X1 Carbon 32GB |
| qwen2.5:32b | ~20GB | ~4-6 t/s | Possible but borderline slow |

X1 Carbon LPDDR5 RAM is significantly faster than DDR4 — the 14B will perform well.

**Expected processing time for an 80-page document (revised):**
- ChromaDB sliding window queries (78 windows): ~8 seconds
- Anonymization of flagged pages only (~15 pages typical): ~60 seconds
- Final Kimi API call: ~15 seconds
- **Total: ~1.5 minutes per document (typical case)**
- Worst case (all pages flagged): ~6 minutes

---

## Estimated Cost Per Document

| Step | Cost |
|---|---|
| Ollama anonymization (local) | $0.00 |
| ChromaDB queries (local) | $0.00 |
| Final Kimi API call (~5,000 tokens typical, scales with findings) | ~$0.02 |
| **Total per 80-page AML document** | **~$0.02** |

Note: the earlier estimate of ~$0.01 / ~2,000 tokens was based on a single violation. At 15 unique findings, input tokens are closer to 6,000-8,000. Cost is still negligible for a PoC.

---

## Files in the Repository

```
aml_proof/
├── json_graph/          ← 15 CySEC JSON files (DO NOT MODIFY)
├── chroma_db/           ← Pre-built vector DB (DO NOT regenerate unless needed)
├── test_transactions/   ← DROP YOUR PDF FILES HERE
│   └── sanitized/       ← Output of anonymizer (auto-created)
├── evaluation_results/  ← Final JSON verdicts (auto-created)
├── anonymizer.py        ← PII scrubber (needs MODEL update to 14b)
├── rag_evaluator.py     ← NEEDS FULL REWRITE (see architecture above)
├── vectorize.py         ← Already ran, no need to re-run
├── assess_pdf.py        ← Quick test tool
├── status.md            ← Dev log
└── architecture_decisions.md ← Full rationale
```

---

## Prompt for Your New Session (Copy This Exactly)

---

I am building an automated AML Compliance Auditor. The codebase is fully set up — pull from GitHub repo `andreas1612/aml-law` and read `nextsession.md` in the root for full architecture context.

**Your task is a two-step execution job:**

### Step 1 — Setup Ollama on this machine (X1 Carbon 2024, 32GB RAM)
```
ollama pull qwen2.5:14b-instruct-q4_K_M
```

### Step 2 — Rewrite `rag_evaluator.py` with the Full-Coverage Sliding Window Architecture

The current file takes a fixed character slice — this is wrong. Rewrite it with the architecture documented in `nextsession.md`. Key requirements:

- Phase 1: query ChromaDB with raw text for every 3-page window, step=1, no pages skipped
- No BM25 gate, no MinHash deduplication — full coverage is mandatory for a compliance audit
- Phase 2: deduplicate findings by (node_path + overlapping page ranges), merge cross-jurisdiction matches
- Phase 3: anonymize via Ollama ONLY the flagged page ranges (not all pages)
- Phase 4: ONE Kimi API call with all findings in the universal JSON schema
- All thresholds (CHROMA_THRESHOLD) must be configurable, not hardcoded
- Output JSON must use the universal legal citation schema (jurisdiction, instrument, article fields) — never hardcode "CySEC" in the evaluator logic

After the rewrite, run it against one of the PDFs in `test_transactions/`:
```
export KIMI_API_KEY="sk-your-key-here"
python rag_evaluator.py --config client_config.json
```

Review the JSON output in `evaluation_results/` and report back.

---
