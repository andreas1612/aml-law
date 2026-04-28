# Next Session Handover — AML Compliance Auditor

> **Read this entire file before writing a single line of code. Everything decided here has a reason. Do not re-litigate closed decisions.**

---

## What This System Is

An automated AML Compliance Auditor that evaluates corporate AML policy PDFs against structured legal knowledge graphs. Runs entirely locally except for the final verdict call to an external LLM API.

CySEC Consolidated AML Directive is law domain 1. Architecture supports EU AMLD5/6, FATF, FinCEN without code changes — jurisdiction is config-driven.

GitHub: `andreas1612/aml-law`

---

## Current State (as of 2026-04-28)

### What is complete and working

| Component | Status | File |
|---|---|---|
| CySEC JSON Knowledge Graph | Complete, do not modify | `json_graph/` (15 files) |
| ChromaDB Vector DB | Built, 325 nodes | `chroma_db/` |
| Full-coverage sliding window evaluator | Working | `rag_evaluator.py` |
| HTML report generator | Working | auto-generated in `evaluation_results/` |
| Client config | Working | `client_config.json` |
| Requirements | Documented | `requirements.txt` |
| Kimi API | Working | endpoint: `https://api.moonshot.ai/v1` (NOT `.cn`) |

### What is NOT done yet (your job next session)

1. **Bidirectional cross-check** — the current cross-check is broken (see below)
2. **Run the second PDF** — `test_transactions/1a. AML Manual.docx.pdf` (141 pages)
3. **spaCy anonymizer** — replace Ollama for PII stripping (faster, deterministic)

---

## Pipeline — Current Working State

```
Phase 1a: PyPDF2 extracts all pages
Phase 1b: Sliding window detection
          Every 3-page window (step=1, NO pages skipped) queries ChromaDB
          No distance threshold — Kimi is the filter, not a float
          Returns top-1 match per window per jurisdiction
Phase 2:  Deduplication by (node_path + overlapping page ranges)
Phase 3:  Anonymize flagged pages via Ollama (use --skip-anon on CPU — too slow)
Phase 4:  Kimi API verdict in batches of 10, 8s sleep between batches, 5 retries on 429
Phase 4b: Cross-check GAPs against full document (CURRENTLY BROKEN — see below)
Phase 5:  HTML report generation
```

### How to run

```powershell
$env:KIMI_API_KEY = "sk-DlKQ73PTbP9ff2r6U6y18TkVKqsmjRsEebYhIgi13mDOLLE2"
python rag_evaluator.py --pdf "AML Manual V8.0_Reviewed(Draft).docx.pdf" --config client_config.json --skip-anon
```

`--skip-anon` bypasses Ollama (unusable on CPU — llama3 times out at 180s/page).
On GPU workstation with qwen2.5:14b use without `--skip-anon`.

---

## What We Learned From Running the 65-Page Doc

### Results on `AML Manual V8.0_Reviewed(Draft).docx.pdf`

- 65 pages, 63 windows, 55 findings after detection, 55 after dedup
- Kimi returned 28 GAPs, 27 COMPLIANT
- After manual PDF review: ~7 real gaps, ~12 false positives, ~9 borderline

### Confirmed Real GAPs (manual verification)

| GAP | Description |
|---|---|
| id=11 | MOKAS reporting uses Jira/ISR — CySEC requires goAML electronic submission specifically |
| id=15 | No internal audit annual AML review mandate anywhere in doc |
| id=40 | Ministry of Foreign Affairs / UN sanctions check not in this policy |
| id=53 | Monthly Prevention Statement mentioned but zero field specification |
| id=18 | No breakdown of high-risk customers by country of origin |
| id=48 | No telephone verification procedure |
| id=50 | No specification of which departments/employees need AML training |

### Confirmed False Positives (Kimi got wrong)

| GAP | Why wrong |
|---|---|
| id=41, 42 | Section 7 (pages 45-46) has full suspicious transaction definitions and examples |
| id=7, 13 | Page 14 explicitly covers AMLCO employee guidance and annual training |
| id=2, 17, 26 | Risk identification IS covered in section 3 — same gap triggered 3× on adjacent windows |
| id=34 | Page 51 covers account closure for non-responsive clients |
| id=35 | CDD section covers beneficial owner verification |

### Root Cause of False Positives

The current cross-check uses keyword frequency — words like "policy", "risk", "customer" appear on every page of a compliance document. **100% of GAPs were flagged as LIKELY_COMPLIANT** because the threshold was too loose. The cross-check is currently useless.

---

## Critical Next Task: Fix the Cross-Check

### Why the current cross-check fails

```python
# Current (broken):
keywords = ["policy", "risk", "customer", "money", "laundering"]
found = sum(1 for kw in keywords if kw in full_text)
# Result: always 6/6 → everything is LIKELY_COMPLIANT
```

These words appear on every single page of an AML document. The logic cannot distinguish "the policy covers CDD" from "this page is the table of contents."

### The correct approach: Bidirectional ChromaDB

**The core problem:** ChromaDB currently goes one direction only:
```
policy_window → cysec_aml_rules → finds which law applies
```

What the cross-check needs is the reverse:
```
cysec_law_node → policy_pages → does this obligation exist ANYWHERE in the doc?
```

### Implementation Plan

**Phase 1c (new) — Build ephemeral policy index:**
```python
# After extracting pages, before detection:
# Vectorize all policy pages into a temporary ChromaDB collection
# Collection name: f"policy_{client_id}_{stamp}"
# Delete after evaluation completes (ephemeral — not stored permanently)
# Takes ~10-15 seconds for 65 pages

chroma_policy_col = client.create_collection(f"policy_{stamp}")
chroma_policy_col.upsert(
    documents=[page_text for page_text in pages],
    ids=[f"page_{i}" for i in range(len(pages))],
    metadatas=[{"page_num": i+1} for i in range(len(pages))]
)
```

**Phase 4b (replace current) — Bidirectional semantic cross-check:**
```python
# For each GAP verdict:
# 1. Bloom filter pre-check (bigrams from law node vs full doc text)
#    If 0 bigrams match → CONFIRMED_GAP immediately, skip semantic query
# 2. Query policy_pages collection with the CySEC law node text
#    best_distance < 0.45 on any page → LIKELY_COMPLIANT (report which page)
#    best_distance 0.45-0.55         → MANUAL_REVIEW (borderline)
#    best_distance > 0.55 everywhere → CONFIRMED_GAP

def bidirectional_cross_check(verdicts, findings, policy_collection, full_text):
    for v in verdicts:
        if v.get('verdict') != 'GAP':
            continue
        fin = get_finding(v, findings)
        law_node_text = fin.get('matched_rule', '')

        # Step 1: Bloom pre-filter
        bigrams = get_bigrams(law_node_text)
        if not any(bg in full_text for bg in bigrams):
            v['cross_check'] = 'CONFIRMED_GAP'
            continue

        # Step 2: Semantic reverse query
        results = policy_collection.query(query_texts=[law_node_text], n_results=3)
        best_dist = min(results['distances'][0])
        best_page = results['metadatas'][0][0]['page_num']

        if best_dist < 0.45:
            v['cross_check'] = 'LIKELY_COMPLIANT'
            v['covered_on_page'] = best_page
            v['coverage_distance'] = best_dist
        elif best_dist < 0.55:
            v['cross_check'] = 'MANUAL_REVIEW'
            v['closest_page'] = best_page
            v['coverage_distance'] = best_dist
        else:
            v['cross_check'] = 'CONFIRMED_GAP'
```

**Cleanup:**
```python
# After report generation:
chroma_client.delete_collection(f"policy_{stamp}")
```

**Dependencies to add:**
```
mmh3==4.1.0      # for Bloom filter hashing
```

**Expected outcome on 65-page doc:**
- GAP id=41/42 (suspicious transactions) → policy page 45 matches at ~0.35 → LIKELY_COMPLIANT ✓
- GAP id=11 (goAML) → no page mentions goAML → CONFIRMED_GAP ✓
- GAP id=53 (Monthly Prevention Statement fields) → borderline → MANUAL_REVIEW ✓

---

## Architecture Decisions — Do Not Re-Litigate

| Decision | Reason |
|---|---|
| No BM25 silence gate | Fails on paraphrased compliance text — silent false negatives |
| No MinHash window dedup | Misses new topics introduced mid-overlap |
| No distance threshold in detection | Kimi is the filter, not a float. Removing threshold was correct |
| Anonymize AFTER detection | ChromaDB is local — raw text safe. Only Kimi needs sanitized text |
| Batched Kimi calls (10 per batch) | 55 findings in one call = ~22k tokens = truncated JSON response |
| ASCII-encode prompts | Raw PDF text contains unicode that breaks JSON parsing in Kimi responses |
| 8s sleep between Kimi batches | 429 rate limit without it |
| moonshot.ai not moonshot.cn | `.cn` returns 401 even with valid key. `.ai` is the correct international endpoint |
| --skip-anon flag | llama3 on CPU times out at 180s/page. On GPU workstation: remove this flag |

---

## Known Issues To Fix

### High Priority
1. **Bidirectional cross-check** — current implementation is broken (see above)
2. **Duplicate GAP suppression** — ids 2/17/26 all flag the same gap on adjacent windows. Post-dedup should cluster by gap_description similarity, not just node_path

### Medium Priority
3. **spaCy NER anonymizer** — replace Ollama for anonymization
   - spaCy strips PERSON/ORG/GPE/DATE via NER (~50ms/page vs 4s/page)
   - Regex handles IBAN/email/phone/account numbers
   - Add after PoC validated: `pip install spacy && python -m spacy download en_core_web_trf`

4. **Report improvements** — after cross-check is fixed:
   - Add "covered on page X" link for LIKELY_COMPLIANT findings
   - Add executive summary: confirmed gaps only, severity breakdown

### Low Priority
5. **--verdict-only flag** — load existing JSON, skip re-detection, retry Kimi only
6. **Page SHA-256 cache** — skip re-vectorizing pages already seen (repeat clients)

---

## Multi-Jurisdiction (Future)

Add new law domains by:
1. Convert law text to universal JSON node schema (see below)
2. Run `vectorize.py` with new collection name
3. Add collection name to `client_config.json` `regulated_under` array
4. Nothing else changes

Universal node schema:
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

Collections to add in order: `eu_amld5`, `eu_amld6`, `fatf_recommendations_2023`

---

## Infrastructure

### API Keys (stored in `.env`, gitignored)
```
KIMI_API_KEY=sk-DlKQ73PTbP9ff2r6U6y18TkVKqsmjRsEebYhIgi13mDOLLE2
```
Kimi account: platform.moonshot.ai — has ~25 EUR credit as of 2026-04-28.

### Ollama (for anonymization — skip on CPU)
```powershell
# X1 Carbon (current machine):
ollama pull llama3:latest         # already installed, too slow on CPU
ollama pull qwen2.5:14b-instruct-q4_K_M  # use this on GPU workstation

# Test Ollama is running:
curl http://localhost:11434/api/tags
```

### Python environment
```powershell
pip install -r requirements.txt
```

---

## Files
```
aml_proof/
├── json_graph/           ← 15 CySEC JSON files (DO NOT MODIFY)
├── chroma_db/            ← Pre-built law vector DB (DO NOT regenerate)
├── test_transactions/
│   ├── AML Manual V8.0_Reviewed(Draft).docx.pdf   ← 65 pages, already run
│   └── 1a. AML Manual.docx.pdf                    ← 141 pages, NOT YET RUN
├── evaluation_results/   ← JSON + HTML reports (gitignored)
├── rag_evaluator.py      ← Main pipeline
├── client_config.json    ← Client/jurisdiction config
├── requirements.txt      ← Dependencies with component descriptions
├── vectorize.py          ← Already ran, only re-run when adding new law domain
├── assess_pdf.py         ← Quick test tool
├── .env                  ← API keys (gitignored)
└── nextsession.md        ← This file
```

---

## Prompt for Your New Session (Copy This Exactly)

---

I am building an automated AML Compliance Auditor. Pull from GitHub repo `andreas1612/aml-law` and read `nextsession.md` in full before doing anything.

**Your tasks in order:**

### Task 1 — Fix the Bidirectional Cross-Check

The current `cross_check_verdicts()` function in `rag_evaluator.py` is broken — it uses keyword frequency which flags everything as LIKELY_COMPLIANT. Replace it with the bidirectional ChromaDB approach documented in `nextsession.md` under "The correct approach: Bidirectional ChromaDB". Exact implementation spec is there.

Install `mmh3` first: `pip install mmh3`

### Task 2 — Run the 141-Page Document

After the cross-check is fixed and verified on the 65-page doc:

```powershell
$env:KIMI_API_KEY = "sk-DlKQ73PTbP9ff2r6U6y18TkVKqsmjRsEebYhIgi13mDOLLE2"
python rag_evaluator.py --pdf "1a. AML Manual.docx.pdf" --config client_config.json --skip-anon
```

Open the HTML report in browser, assess findings, compare with 65-page doc results.

### Task 3 — Compare Both Reports

After both docs have been evaluated:
- Which GAPs appear in both documents? (shared compliance weaknesses)
- Which are unique to one doc? (document-specific issues)
- What is the false positive rate now with the fixed cross-check?

Report your findings before committing.

---
