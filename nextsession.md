# Next Session Handover — AML Compliance Auditor

> **You are on the X1 Carbon 2024 (32GB RAM). Read this entire file before starting. Then use the prompt at the bottom.**

---

## What We Built (Full Context)

### The System
An automated AML Compliance Auditor that evaluates corporate AML policy PDFs against the CySEC Consolidated AML Directive. It runs entirely locally except for the final verdict call to an external LLM API.

### Why It Works This Way
- CySEC law was converted into 15 structured JSON files (`json_graph/`) — one per Part and Appendix.
- These 15 files were vectorized into a local ChromaDB (`chroma_db/`) — 325 legal nodes, each with its exact JSON path as metadata.
- When a client PDF is evaluated, the system retrieves the **exact CySEC paragraph** that matches — no hallucination possible because we hand the real law directly to the final LLM.

### Data Sovereignty
```
PDF → [local PyPDF2 extraction]
    → [local Ollama anonymizer — strips all PII]
    → [local ChromaDB — finds exact matching CySEC rule]
    → [Kimi/OpenAI API — only receives: sanitized text + CySEC excerpt]
```
Never sends raw PII to any external server.

---

## What Is Already Done

| Component | Status | File |
|---|---|---|
| CySEC JSON Knowledge Graph | ✅ Complete | `json_graph/` |
| ChromaDB Vector Database | ✅ Built (325 nodes) | `chroma_db/` |
| PDF Text Extractor | ✅ Working | `assess_pdf.py` |
| PII Anonymizer | ✅ Coded, not yet run end-to-end | `anonymizer.py` |
| RAG Evaluator | ✅ Coded, needs rewrite (see below) | `rag_evaluator.py` |
| Ollama | ⚠️ Must install on X1 Carbon | `OllamaSetup.exe` in repo root |

---

## Critical Architecture Decision — `rag_evaluator.py` Must Be Rewritten

The current `rag_evaluator.py` takes a fixed 1,000-character slice from the middle of the sanitized document. **This is wrong** for two reasons:
1. It arbitrarily cuts sentences mid-word.
2. It only evaluates ~1% of an 80-page document.

### The Correct Architecture: Combined Streaming Sliding Window Pipeline

The new pipeline should combine the anonymization and evaluation into one single streaming pass:

```
For each page in the PDF:
    1. Extract raw text (PyPDF2)
    2. Anonymize page via local Ollama (strip PII)
    3. Add anonymized page to a rolling buffer of 3 pages
    4. Once buffer has 3 pages → query ChromaDB with the combined 3-page text
    5. If ChromaDB match confidence is HIGH (distance < 0.4) → flag this window
    6. Evict the oldest page from buffer, slide forward
    7. Continue until all pages processed
    8. Deduplicate flagged windows by CySEC node path
    9. Send ONE final call to Kimi API with all unique violations found
   10. Save JSON verdict to evaluation_results/
```

**Why 3-page sliding window:**
- AML policy sections span multiple pages in inconsistent formats per client.
- A fixed window of 3 pages guarantees any section up to 3 pages long is always evaluated whole.
- Sliding by 1 page means maximum overlap — nothing missed.
- Deduplication at the end prevents the same rule from being flagged 3 times.

**Why combine anonymization with evaluation:**
- Only 3 pages ever in RAM at once (memory efficient).
- No intermediate file written to disk.
- Start getting matches on page 3 while still processing the document.

---

## Model Choice for X1 Carbon 2024

**Use `qwen2.5:14b-instruct-q4_K_M`** — not the 3B we originally planned.

| Model | RAM Used | Speed | Verdict |
|---|---|---|---|
| qwen2.5:3b | ~3GB | ~40 t/s | Too weak for legal PII understanding |
| **qwen2.5:14b-instruct-q4_K_M** ✅ | ~9GB | ~12-16 t/s | **Best for X1 Carbon 32GB** |
| qwen2.5:32b | ~20GB | ~4-6 t/s | Possible but borderline slow |

Your X1 Carbon has LPDDR5 RAM which is significantly faster than DDR4 — the 14B will perform well.

**Expected processing time for an 80-page document:**
- Anonymization: ~5 minutes (80 pages × ~4s per page at 14B speed)
- ChromaDB sliding window queries: ~8 seconds total
- Final Kimi API call: ~15 seconds
- **Total: ~6 minutes per document**

---

## Estimated Cost Per Document

| Step | Cost |
|---|---|
| Ollama anonymization (local) | $0.00 |
| ChromaDB queries (local) | $0.00 |
| Final Kimi API call (1 call, ~2,000 tokens) | ~$0.01 |
| **Total per 80-page AML document** | **~$0.01** |

---

## Files in the Repository

```
amllaw/
├── json_graph/          ← 15 CySEC JSON files (DO NOT MODIFY)
├── chroma_db/           ← Pre-built vector DB (DO NOT regenerate unless needed)
├── test_transactions/   ← DROP YOUR PDF FILES HERE
│   └── sanitized/       ← Output of anonymizer (auto-created)
├── evaluation_results/  ← Final JSON verdicts (auto-created)
├── anonymizer.py        ← PII scrubber (needs MODEL update to 14b)
├── rag_evaluator.py     ← NEEDS FULL REWRITE (sliding window architecture)
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

### Step 2 — Rewrite `rag_evaluator.py` with the Sliding Window Architecture
The current file takes a fixed character slice — this is wrong. Rewrite it with the following architecture (full details in `nextsession.md`):
- Combine anonymization + evaluation into one streaming pipeline
- Use a rolling 3-page buffer sliding forward by 1 page
- Query ChromaDB once per window position  
- Only flag windows where ChromaDB distance < 0.4
- Deduplicate violations by CySEC node path
- Send ONE final Kimi API call with all unique flagged sections
- Update the Ollama model to `qwen2.5:14b-instruct-q4_K_M` in the script

After the rewrite, run it against one of the PDFs in `test_transactions/`:
```
$env:KIMI_API_KEY = "sk-your-key-here"
python rag_evaluator.py
```

Review the JSON output in `evaluation_results/` and report back.

---
