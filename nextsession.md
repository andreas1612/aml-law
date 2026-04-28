# Next Session Handover — AML Compliance Auditor

> **Read this entire file before writing a single line of code. Everything decided here has a reason. Do not re-litigate closed decisions.**

---

## What This System Is

An automated AML Compliance Auditor that evaluates corporate AML policy PDFs against structured legal knowledge graphs. Runs entirely locally except for the final verdict call to an external LLM API.

CySEC Consolidated AML Directive is law domain 1. Architecture supports EU AMLD5/6, FATF, FinCEN without code changes — jurisdiction is config-driven.

GitHub: `andreas1612/aml-law`

---

## Theoretical Foundation — The Libet Inversion

This system is a domain application of the **Libet Inversion** architectural framework described in `Biological_Governance_Position_Paper_v2.docx`. That paper proposes a five-layer biologically-inspired architecture for autonomous AI systems. Our AML system independently arrived at the same structure and is being incrementally aligned to the full framework.

**Mapping of framework layers to our pipeline:**

| Biological Layer | Paper Term | Our Implementation |
|---|---|---|
| Parallel sensor streams | Demon Layer | PyPDF2 + sliding window extraction |
| Entropy-gated filter | Thalamic Gate / EGDR | ChromaDB retrieval (currently fixed k=1, **EGDR upgrade planned**) |
| Limited serial workspace | Global Workspace | Kimi context window (intentionally small, pre-filtered) |
| Narrator + veto | Interpreter + Veto | Kimi verdict call + human review of HTML report |
| Long-term threat memory | Hebbian Compliance Graph | **Planned — HCG replaces ephemeral cross-check long-term** |

**Key validated decisions from the paper:**
- LLM as narrator, not driver — ChromaDB does the filtering, Kimi just narrates. This is correct.
- No BM25 gate — the paper's "demons never skip signal" principle. Sliding window step=1 is correct.
- Context window intentionally small — BATCH_SIZE=10 is correct. Do not fight this.

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
| 65-page doc evaluated | Done, manually verified | `AML Manual V8.0_Reviewed(Draft).docx.pdf` |
| 141-page doc evaluated | Done, manually verified | `1a. AML Manual.docx.pdf` |

### What is NOT done yet (your job next session)

1. **Bidirectional cross-check** — current implementation is broken (see Critical Next Task below) — **DO THIS FIRST**
2. **EGDR — entropy-gated retrieval depth** — replaces fixed n_results=1 (see Task 4 below)
3. **spaCy anonymizer** — replace Ollama for PII stripping (faster, deterministic)
4. **Re-run both docs with fixed cross-check** — after Task 1, re-run both PDFs to get clean comparison
5. **Hebbian Compliance Graph** — long-term architecture, seed from existing two-doc evaluation data

---

## Pipeline — Current Working State

```
Phase 1a: PyPDF2 extracts all pages
Phase 1b: Sliding window detection
          Every 3-page window (step=1, NO pages skipped) queries ChromaDB
          No distance threshold — Kimi is the filter, not a float
          Returns top-1 match per window per jurisdiction (UPGRADE: EGDR makes this dynamic)
Phase 1c: [PLANNED] Build ephemeral policy ChromaDB collection for cross-check
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
python rag_evaluator.py --pdf "1a. AML Manual.docx.pdf" --config client_config.json --skip-anon
```

`--skip-anon` bypasses Ollama (unusable on CPU — llama3 times out at 180s/page).
On GPU workstation with qwen2.5:14b use without `--skip-anon`.

---

## What We Learned From Running the 65-Page Doc

### Results on `AML Manual V8.0_Reviewed(Draft).docx.pdf`

- 65 pages, 63 windows, 55 findings after detection, 55 after dedup
- Kimi returned 28 GAPs, 27 COMPLIANT
- After manual PDF review: ~7 real gaps, ~12 false positives, ~9 borderline

### Confirmed Real GAPs — 65-page doc (manual verification)

| GAP | Description |
|---|---|
| id=11 | MOKAS reporting uses Jira/ISR — CySEC requires goAML electronic submission specifically |
| id=15 | No internal audit annual AML review mandate anywhere in doc |
| id=40 | Ministry of Foreign Affairs / UN sanctions check not in this policy |
| id=53 | Monthly Prevention Statement mentioned but zero field specification |
| id=18 | No breakdown of high-risk customers by country of origin |
| id=48 | No telephone verification procedure |
| id=50 | No specification of which departments/employees need AML training |

### Confirmed False Positives — 65-page doc

| GAP | Why wrong |
|---|---|
| id=41, 42 | Section 7 (pages 45-46) has full suspicious transaction definitions and examples |
| id=7, 13 | Page 14 explicitly covers AMLCO employee guidance and annual training |
| id=2, 17, 26 | Risk identification IS covered in section 3 — same gap triggered 3x on adjacent windows |
| id=34 | Page 51 covers account closure for non-responsive clients |
| id=35 | CDD section covers beneficial owner verification |

---

## What We Learned From Running the 141-Page Doc

### Results on `1a. AML Manual.docx.pdf`

- 141 pages — larger document with more detailed sections
- Run completed successfully with --skip-anon
- Manual PDF scan performed after Kimi evaluation

### Topics CONFIRMED COVERED in 141-page doc (manual scan)

| Topic | Location |
|---|---|
| goAML electronic submission | Page 29 |
| Monthly Prevention Statement | Page 34 |
| Suspicious transaction definitions and indicators | Multiple pages throughout |
| AML training requirements | Pages 27, 33-35 |

### Topics CONFIRMED MISSING in 141-page doc (manual scan)

| Missing Topic | Significance |
|---|---|
| Economic profile of customers | No customer economic baseline defined |
| Record keeping procedures | Retention periods not specified |
| Simplified CDD conditions | No criteria for when simplified CDD applies |
| Trust deed procedures | Trusts not addressed |
| Joint Guidelines (EBA/ESMA) | Not referenced anywhere in the document |

### Root Cause of False Positives — same as 65-page doc

The broken cross-check flags everything as LIKELY_COMPLIANT. The false positive pattern is identical: high-frequency AML keywords ("policy", "risk", "customer") appear on every page, so keyword frequency cannot distinguish genuine gaps from covered sections.

---

## Cross-Document Comparison (Both Docs)

### Systemic GAPs — appear in BOTH documents (highest priority)

These represent genuine compliance weaknesses across the organisation's policy framework, not document-specific issues:

| GAP | 65-page | 141-page | CySEC Obligation |
|---|---|---|---|
| Joint Guidelines (EBA/ESMA) not referenced | ABSENT | ABSENT | Mandatory reference requirement |
| No telephone verification procedure | ABSENT | ABSENT | Customer contact verification |
| Trust deed / trust structures not addressed | ABSENT | ABSENT | Beneficial ownership for trusts |
| Simplified CDD — no qualifying criteria defined | ABSENT | ABSENT | Must specify when simplified applies |

### Document-Specific GAPs

| GAP | Doc | Notes |
|---|---|---|
| goAML not specified (uses Jira/ISR instead) | 65-page only | 141-page doc correctly references goAML on p29 |
| Monthly Prevention Statement — no field spec | 65-page | 141-page has basic coverage on p34 |
| No internal audit annual AML review mandate | 65-page | Not yet verified in 141-page |

### Conclusion

The 141-page document is more thorough than the 65-page draft but both share the same systemic gaps. The systemic gaps (Joint Guidelines, telephone verification, trust deeds, simplified CDD) are the most reliable findings — they are unlikely to be false positives because they are specific, technical requirements with no general keyword overlap with boilerplate AML text.

---

## Critical Next Task: Fix the Cross-Check (Task 1)

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
- GAP id=41/42 (suspicious transactions) → policy page 45 matches at ~0.35 → LIKELY_COMPLIANT
- GAP id=11 (goAML) → no page mentions goAML → CONFIRMED_GAP
- GAP id=53 (Monthly Prevention Statement fields) → borderline → MANUAL_REVIEW

---

## Task 4 — EGDR: Entropy-Gated Dynamic Retrieval

This is the Thalamic Gate upgrade from the Libet Inversion framework. Currently we use fixed `n_results=1` per window regardless of content complexity. This causes false positives on boilerplate pages (TOC, version history, headers) which have low entropy but still get top-1 matched to unrelated law nodes.

### Implementation

```python
import math
from collections import Counter

def window_entropy(text: str) -> float:
    """Shannon entropy of word distribution in a text window."""
    words = text.lower().split()
    if not words:
        return 0.0
    freq = Counter(words)
    total = len(words)
    return -sum((c / total) * math.log2(c / total) for c in freq.values())

# In detect_violations(), replace fixed n_results=1 with:
H = window_entropy(window_text)
k = 3 if H > 6.5 else 1   # high-entropy windows retrieve top-3; boilerplate gets top-1

results = collection.query(query_texts=[window_text], n_results=k)
```

### Why this helps

| Window type | Entropy | Current behaviour | With EGDR |
|---|---|---|---|
| Table of contents | ~3.5 | Top-1 match → false positive | k=1, less weight to noisy match |
| Version/header page | ~2.8 | Top-1 match → false positive | k=1 |
| Rich policy section | ~7.2 | Top-1 only — may miss correct node | k=3, better coverage |
| Complex multi-topic section | ~8.1 | Top-1 misses subordinate obligations | k=3 |

### Threshold calibration

- H > 6.5 → k=3 (retrieve top-3 law nodes)
- H <= 6.5 → k=1 (routine/boilerplate page, top-1 only)
- Tune threshold by running `python -c "from rag_evaluator import extract_pages, window_entropy; ..."` and printing entropy distribution across all windows before committing

### Effort: ~30 minutes after Task 1 is done. Add as Phase 1b upgrade, no new dependencies.

---

## Long-Term Architecture: Hebbian Compliance Graph (HCG)

**Do not implement immediately** — this is for after PoC is validated with real client data (5+ document evaluations).

The ephemeral bidirectional cross-check (Task 1) is the right immediate fix. But the long-term replacement is a persistent weighted graph that learns across evaluations, implementing the Hebbian immune memory from the Libet Inversion framework.

### Concept

```json
{
  "cysec_aml_rules/part4/article3.2_cdd": {
    "confirmed_gap_weight": 0.8,
    "compliant_weight": 0.2,
    "documents_evaluated": 2,
    "last_confirmed_gap": "2026-04-28",
    "last_compliant": null,
    "notes": "Consistently absent across both evaluated documents"
  },
  "cysec_aml_rules/part6/article2.1_goaml": {
    "confirmed_gap_weight": 0.5,
    "compliant_weight": 0.5,
    "documents_evaluated": 2,
    "last_confirmed_gap": "2026-04-28",
    "last_compliant": "2026-04-28",
    "notes": "Gap in 65-page doc, covered in 141-page doc on p29"
  }
}
```

**Behaviour over time:**
- Nodes with high `confirmed_gap_weight` (consistently absent across clients) get auto-escalated to CRITICAL in reports
- Nodes with high `compliant_weight` (always covered) get reduced retrieval weight — we stop wasting batches on them
- Second encounter with a known pattern gets faster, more targeted response (adaptive immunity)

**Seed data available now:** the systemic gaps confirmed in both docs (Joint Guidelines, telephone verification, trust deeds, simplified CDD) can seed the graph immediately with weight=1.0 confirmed_gap.

**Storage:** `compliance_graph.json` in project root, updated after every evaluation run, gitignored per-client but committed for aggregated anonymised version.

---

## Architecture Decisions — Do Not Re-Litigate

| Decision | Reason |
|---|---|
| No BM25 silence gate | Fails on paraphrased compliance text — silent false negatives. Paper: "demons never skip signal" |
| No MinHash window dedup | Misses new topics introduced mid-overlap |
| No distance threshold in detection | Kimi is the filter, not a float. Removing threshold was correct |
| Anonymize AFTER detection | ChromaDB is local — raw text safe. Only Kimi needs sanitized text |
| Batched Kimi calls (10 per batch) | 55 findings in one call = ~22k tokens = truncated JSON response |
| ASCII-encode prompts | Raw PDF text contains unicode that breaks JSON parsing in Kimi responses |
| 8s sleep between Kimi batches | 429 rate limit without it |
| moonshot.ai not moonshot.cn | `.cn` returns 401 even with valid key. `.ai` is the correct international endpoint |
| --skip-anon flag | llama3 on CPU times out at 180s/page. On GPU workstation: remove this flag |
| LLM as narrator not driver | Libet Inversion principle — ChromaDB is the thalamic gate, Kimi just narrates |
| EGDR over fixed k | High-entropy windows need deeper retrieval; boilerplate windows generate false positives at k=1 |

---

## Known Issues To Fix

### High Priority
1. **Bidirectional cross-check** — current implementation is broken (see Critical Next Task)
2. **Duplicate GAP suppression** — ids 2/17/26 all flag the same gap on adjacent windows. Post-dedup should cluster by gap_description similarity, not just node_path

### Medium Priority
3. **EGDR upgrade** — entropy-gate retrieval depth per window (see Task 4)
4. **spaCy NER anonymizer** — replace Ollama for anonymization
   - spaCy strips PERSON/ORG/GPE/DATE via NER (~50ms/page vs 4s/page)
   - Regex handles IBAN/email/phone/account numbers
   - Add after PoC validated: `pip install spacy && python -m spacy download en_core_web_trf`

5. **Report improvements** — after cross-check is fixed:
   - Add "covered on page X" link for LIKELY_COMPLIANT findings
   - Add executive summary: confirmed gaps only, severity breakdown
   - Add cross-document comparison section when both docs evaluated

### Low Priority
6. **--verdict-only flag** — load existing JSON, skip re-detection, retry Kimi only
7. **Page SHA-256 cache** — skip re-vectorizing pages already seen (repeat clients)
8. **Hebbian Compliance Graph** — persistent weighted graph across evaluations (see long-term section)

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
pip install mmh3   # add this for Task 1 bidirectional cross-check
```

---

## Files
```
aml_proof/
├── json_graph/           <- 15 CySEC JSON files (DO NOT MODIFY)
├── chroma_db/            <- Pre-built law vector DB (DO NOT regenerate)
├── test_transactions/
│   ├── AML Manual V8.0_Reviewed(Draft).docx.pdf   <- 65 pages, evaluated + manually verified
│   └── 1a. AML Manual.docx.pdf                    <- 141 pages, evaluated + manually verified
├── evaluation_results/   <- JSON + HTML reports (gitignored)
├── rag_evaluator.py      <- Main pipeline
├── client_config.json    <- Client/jurisdiction config
├── requirements.txt      <- Dependencies with component descriptions
├── vectorize.py          <- Already ran, only re-run when adding new law domain
├── assess_pdf.py         <- Quick test tool
├── .env                  <- API keys (gitignored)
└── nextsession.md        <- This file
```

---

## Prompt for Your New Session (Copy This Exactly)

---

I am building an automated AML Compliance Auditor. Pull from GitHub repo `andreas1612/aml-law` and read `nextsession.md` in full before doing anything.

The system is built on the Libet Inversion architectural framework (see nextsession.md — Theoretical Foundation section). Architecture decisions are closed. Do not re-litigate them.

**Your tasks in order:**

### Task 1 — Fix the Bidirectional Cross-Check (CRITICAL — do this first)

The current `cross_check_verdicts()` function in `rag_evaluator.py` is broken — it uses keyword frequency which flags everything as LIKELY_COMPLIANT. Replace it with the bidirectional ChromaDB approach documented in nextsession.md under "Critical Next Task: Fix the Cross-Check". Exact implementation spec is there.

Install `mmh3` first: `pip install mmh3`

After implementing, re-run the 65-page doc and verify:
- GAP id=41/42 (suspicious transactions, covered on pages 45-46) → should be LIKELY_COMPLIANT
- GAP id=11 (goAML) → should be CONFIRMED_GAP
- GAP id=53 (Monthly Prevention Statement fields) → should be MANUAL_REVIEW

```powershell
$env:KIMI_API_KEY = "sk-DlKQ73PTbP9ff2r6U6y18TkVKqsmjRsEebYhIgi13mDOLLE2"
python rag_evaluator.py --pdf "AML Manual V8.0_Reviewed(Draft).docx.pdf" --config client_config.json --skip-anon
```

### Task 2 — EGDR: Entropy-Gated Retrieval Depth

After Task 1 is verified, add entropy-gated dynamic retrieval to Phase 1b as documented in nextsession.md under "Task 4 — EGDR". This is ~30 minutes of work. No new dependencies.

### Task 3 — Re-run Both Docs and Compare

After Tasks 1 and 2:

```powershell
python rag_evaluator.py --pdf "AML Manual V8.0_Reviewed(Draft).docx.pdf" --config client_config.json --skip-anon
python rag_evaluator.py --pdf "1a. AML Manual.docx.pdf" --config client_config.json --skip-anon
```

Compare confirmed GAPs against the manually verified findings documented in nextsession.md:
- 65-page: 7 confirmed real gaps listed above
- 141-page: systemic gaps (Joint Guidelines, telephone verification, trust deeds, simplified CDD) should now be CONFIRMED_GAP

Report false positive rate before committing.

### Task 4 — Commit and Push Clean Results

After verified clean runs on both documents:
- Commit rag_evaluator.py with Task 1 + 2 changes
- Push to `andreas1612/aml-law` main branch
- Do NOT commit evaluation_results/ (gitignored)

---
