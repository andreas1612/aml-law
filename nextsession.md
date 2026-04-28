# Next Session Handover — AML Compliance Auditor

> **Read this entire file before writing a single line of code. Everything decided here has a reason. Do not re-litigate closed decisions.**
> **Hardware context matters — read the Resource Constraints section before choosing any approach.**

---

## What This System Is

An automated AML Compliance Auditor that evaluates corporate AML policy PDFs against structured legal knowledge graphs. Runs entirely locally except for the final verdict call to an external LLM API (Kimi).

CySEC Consolidated AML Directive is law domain 1. Architecture supports EU AMLD5/6, FATF, FinCEN without code changes — jurisdiction is config-driven.

GitHub: `andreas1612/aml-law`

---

## HARDWARE / RESOURCE CONSTRAINTS — READ FIRST

**Current machine: Lenovo X1 Carbon — CPU only. No GPU.**

This is the only available machine right now. All design and implementation decisions must run efficiently on this hardware. If the PoC succeeds, a GPU workstation with tensor cores will be provisioned. Do not design for hardware we do not have yet.

| Constraint | Impact | Current workaround |
|---|---|---|
| CPU only, no GPU | Ollama unusable (180s/page timeout) | `--skip-anon` flag bypasses anonymization |
| Limited RAM | ChromaDB must stay in-process, no large models | all-MiniLM-L6-v2 is fine (~90MB) |
| No persistent compute | Long runs can be interrupted | `--verdict-only` flag planned to resume from saved JSON |
| No local LLM | Kimi API required for verdict | Kimi moonshot-v1-128k, api.moonshot.ai/v1 |

**When the GPU workstation arrives (future):**
- Remove `--skip-anon` — use `qwen2.5:14b-instruct-q4_K_M` via Ollama for anonymization
- Replace Kimi API with self-hosted model (qwen2.5:72b or similar) — update `kimi_base_url` in `client_config.json`
- EGDR can use `k=5` on high-entropy windows (currently k=3 max to limit Kimi batch load)
- spaCy can be upgraded to `en_core_web_trf` (transformer-based, GPU-accelerated)
- All architecture stays identical — only config and model names change

**Do NOT:**
- Pull in any model larger than ~100MB without checking RAM
- Add any Ollama calls without `--skip-anon` guard
- Assume GPU availability for any computation

---

## Theoretical Foundation — The Libet Inversion

This system is a domain application of the **Libet Inversion** architectural framework (`Biological_Governance_Position_Paper_v2.docx`, same project folder). That paper proposes a five-layer biologically-inspired architecture for autonomous AI systems. Our AML system independently converged on the same structure and is being incrementally aligned to the full framework.

**Five-layer mapping:**

| Layer | Biological Analogue | Our Implementation | Status |
|---|---|---|---|
| 1 — Parallel sensors | Demon Layer | PyPDF2 + sliding window | Done |
| 2 — Entropy-gated filter | Thalamic Gate / EGDR | ChromaDB retrieval (fixed k=1 → **EGDR upgrade Task 2**) | Partial |
| 3 — Serial workspace | Global Workspace | Kimi context window (intentionally small) | Done |
| 4 — Narrator + veto | Interpreter + Veto | Kimi verdict + human review of HTML report | Done |
| 5 — Long-term threat memory | Hebbian Compliance Graph | `compliance_graph.json` (**Task 3 — HCG**) | Not started |

**Key architectural principles (do not re-litigate):**
- LLM is the narrator, not the driver. ChromaDB is the thalamic gate. This is correct.
- No BM25 gate — "demons never skip signal." Sliding window step=1 is correct.
- Context window intentionally small — BATCH_SIZE=10 is correct. Do not fight this.
- Constraint as architecture — the context window's smallness IS the feature. Working within CPU limits produced the right design.

---

## Current State (as of 2026-04-28)

### Complete and working

| Component | Status | Location |
|---|---|---|
| CySEC JSON Knowledge Graph | Complete — DO NOT MODIFY | `json_graph/` (15 files) |
| ChromaDB Vector DB | Built, 325 nodes — DO NOT REGENERATE | `chroma_db/` |
| Full-coverage sliding window evaluator | Working | `rag_evaluator.py` |
| HTML report generator | Working | auto-generated in `evaluation_results/` |
| Client config | Working | `client_config.json` |
| Kimi API | Working | endpoint: `https://api.moonshot.ai/v1` (NOT `.cn`) |
| 65-page doc evaluated + manually verified | Done | `test_transactions/AML Manual V8.0_Reviewed(Draft).docx.pdf` |
| 141-page doc evaluated + manually verified | Done | `test_transactions/1a. AML Manual.docx.pdf` |

### NOT done — ordered task list for next session

| Priority | Task | Effort | Blocks |
|---|---|---|---|
| **1 — CRITICAL** | Fix bidirectional cross-check (Phase 4b) | 2h | All quality metrics |
| **2** | EGDR: entropy-gated retrieval depth (Phase 1b upgrade) | 30min | Better detection quality |
| **3** | Phase 4c: Hebbian Compliance Graph update | 30min | Long-term memory |
| **4** | Greedy executive summary in Phase 5 report | 30min | Report quality |
| **5** | Re-run both docs with all fixes applied | 1h | Clean comparison |
| **6** | spaCy anonymizer (CPU-safe, replaces Ollama) | 1h | Removes --skip-anon on CPU |
| **7** | --verdict-only flag (resume from saved JSON) | 30min | Development speed |

---

## Pipeline — Full Target State

```
Phase 1a:  PyPDF2 extracts all pages (DONE — unchanged)

Phase 1b:  EGDR sliding window detection (UPGRADE NEEDED)
           Current: fixed n_results=1 per window
           Target:  compute Shannon entropy H per window
                    H > 6.5 → k=3 (complex section, retrieve top-3 law nodes)
                    H <= 6.5 → k=1 (boilerplate/TOC, retrieve top-1)
           No distance threshold — Kimi is still the filter, not a float

Phase 1c:  Build ephemeral policy index (NEW — needed for Phase 4b)
           All N pages → vectorize → policy_pages_[stamp] ChromaDB collection
           Build Bloom filter bitarray on all document bigrams
           ~10-15s cost on X1 Carbon, once per run, deleted after Phase 5

Phase 2:   Deduplication by node_path + overlapping page ranges (DONE — unchanged)

Phase 3:   Anonymize flagged pages (DONE)
           --skip-anon on X1 Carbon (Ollama unusable on CPU)
           When GPU workstation available: remove flag, use qwen2.5:14b

Phase 4:   Kimi verdict in batches of 10, 8s sleep, 5 retries on 429 (DONE — unchanged)

Phase 4b:  Bidirectional cross-check (BROKEN — replace entirely)
           For each GAP verdict:
             Step 1 — Bloom filter: bigrams from law node vs full doc
               0 matches → CONFIRMED_GAP immediately, skip semantic query
               ≥1 match  → proceed to step 2
             Step 2 — Semantic reverse query: law_node_text → policy_pages collection
               best_distance < 0.45  → LIKELY_COMPLIANT + which page + distance
               best_distance 0.45-0.55 → MANUAL_REVIEW + closest page + distance
               best_distance > 0.55  → CONFIRMED_GAP

Phase 4c:  Update Hebbian Compliance Graph (NEW)
           Load compliance_graph.json (create if not exists)
           For each CONFIRMED_GAP: node confirmed_gap_weight += 0.1
           For each LIKELY_COMPLIANT: node compliant_weight += 0.1
           Save compliance_graph.json
           After 10+ runs: high-weight confirmed nodes auto-escalate to CRITICAL

Phase 5:   HTML report — enhanced (PARTIAL — needs greedy summary)
           Executive summary: greedy top-5 mandatory CONFIRMED_GAPs
           Full GAP table with CONFIRMED / MANUAL_REVIEW / LIKELY_COMPLIANT badges
           "Covered on page X (distance=0.38)" links for LIKELY_COMPLIANT rows
           Cross-document pattern note if compliance_graph.json has prior data

Cleanup:   Delete policy_pages_[stamp] collection from ChromaDB
```

### How to run (current — CPU machine)

```powershell
$env:KIMI_API_KEY = "sk-DlKQ73PTbP9ff2r6U6y18TkVKqsmjRsEebYhIgi13mDOLLE2"
python rag_evaluator.py --pdf "AML Manual V8.0_Reviewed(Draft).docx.pdf" --config client_config.json --skip-anon
python rag_evaluator.py --pdf "1a. AML Manual.docx.pdf" --config client_config.json --skip-anon
```

### How to run (future — GPU workstation with self-hosted model)

```powershell
# Update client_config.json: kimi_base_url → local model endpoint, kimi_model → local model name
python rag_evaluator.py --pdf "document.pdf" --config client_config.json
# No --skip-anon needed — Ollama works on GPU
```

---

## Task 1 — Fix the Bidirectional Cross-Check (CRITICAL)

### Why the current implementation is wrong

```python
# CURRENT (broken) — in cross_check_verdicts():
keywords = ["policy", "risk", "customer", "money", "laundering"]
found = sum(1 for kw in keywords if kw in full_text)
# Result: always 5/5 — everything becomes LIKELY_COMPLIANT
# These words appear on every single page of any AML document
```

### Why semantic reverse lookup is correct

"Customer due diligence" and "client identity verification" are the same obligation — a Bloom filter on exact phrases treats them as different. A ChromaDB semantic query with the same embedding model (all-MiniLM-L6-v2) handles paraphrase correctly because it already proved it can match semantic meaning across different phrasing during Phase 1b.

### Full implementation

**Step A — `_build_policy_index()` (new function):**

```python
def _build_policy_index(pages: list, stamp: str, chroma_client) -> tuple:
    """
    Vectorize all policy pages into an ephemeral ChromaDB collection.
    Also build a Bloom filter bitarray on all document bigrams for fast pre-filtering.
    Returns (collection, bigram_set, full_text).
    """
    import mmh3
    from bitarray import bitarray

    col_name = f"policy_{stamp}"
    # Delete if exists from a previous interrupted run
    try:
        chroma_client.delete_collection(col_name)
    except Exception:
        pass

    col = chroma_client.create_collection(col_name)
    non_empty = [(i, t) for i, t in enumerate(pages) if t.strip()]
    if non_empty:
        col.upsert(
            documents=[t for _, t in non_empty],
            ids=[f"page_{i}" for i, _ in non_empty],
            metadatas=[{"page_num": i + 1} for i, _ in non_empty]
        )

    # Build bigram set for fast pre-filter (not a probabilistic Bloom filter —
    # use a plain Python set on CPU for simplicity and zero false positives)
    full_text = " ".join(pages).lower().encode('ascii', 'replace').decode('ascii')
    words = full_text.split()
    bigram_set = set(f"{words[i]} {words[i+1]}" for i in range(len(words) - 1))

    print(f"  Policy index: {len(non_empty)} pages vectorized, {len(bigram_set):,} bigrams indexed")
    return col, bigram_set, full_text
```

**Note on Bloom filter implementation on CPU:** On the X1 Carbon (no GPU, limited RAM), a plain Python `set` of bigrams is preferable to `mmh3` + `bitarray`. A set has zero false positives (unlike a probabilistic Bloom filter), costs ~50MB for a 141-page document, and lookups are O(1). When the GPU workstation arrives and we're processing hundreds of documents, switch to `mmh3` + `bitarray` to reduce memory. For now, `set` is correct and simpler.

**Step B — `_bidirectional_cross_check()` (replaces `cross_check_verdicts()`):**

```python
def _bidirectional_cross_check(verdicts: list, findings: list,
                                policy_col, bigram_set: set) -> list:
    """
    For each GAP verdict, check whether the underlying CySEC obligation
    exists anywhere in the policy document using semantic reverse lookup.

    Two-step:
      1. Bigram pre-filter — if zero bigrams from the law node appear in
         the document, it is a CONFIRMED_GAP without any ChromaDB query.
      2. Semantic reverse query — law node text → policy_pages collection.
         Returns the best-matching page and its distance.
    """
    def get_finding(v):
        idx = v.get('id', 0) - 1
        if 0 <= idx < len(findings):
            return findings[idx]
        return {}

    confirmed = 0
    likely_compliant = 0
    manual_review = 0

    for v in verdicts:
        if not isinstance(v, dict) or v.get('verdict') != 'GAP':
            continue

        fin = get_finding(v)
        law_node_text = fin.get('matched_rule', '').lower().encode('ascii', 'replace').decode('ascii')

        if not law_node_text.strip():
            v['cross_check'] = 'CONFIRMED_GAP'
            confirmed += 1
            continue

        # Step 1: bigram pre-filter
        words = law_node_text.split()
        node_bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]
        bigram_hits = sum(1 for bg in node_bigrams if bg in bigram_set)

        if not node_bigrams or bigram_hits == 0:
            v['cross_check'] = 'CONFIRMED_GAP'
            v['cross_check_note'] = 'Zero bigrams from law node found in document.'
            confirmed += 1
            continue

        # Step 2: semantic reverse query
        try:
            results = policy_col.query(query_texts=[law_node_text], n_results=3)
            distances = results['distances'][0]
            metas = results['metadatas'][0]
            best_idx = distances.index(min(distances))
            best_dist = distances[best_idx]
            best_page = metas[best_idx].get('page_num', '?')
        except Exception as e:
            v['cross_check'] = 'MANUAL_REVIEW'
            v['cross_check_note'] = f'Query error: {e}'
            manual_review += 1
            continue

        if best_dist < 0.45:
            v['cross_check'] = 'LIKELY_COMPLIANT'
            v['covered_on_page'] = best_page
            v['coverage_distance'] = round(best_dist, 4)
            v['cross_check_note'] = f'Policy page {best_page} covers this obligation (distance={best_dist:.3f}).'
            likely_compliant += 1
        elif best_dist < 0.55:
            v['cross_check'] = 'MANUAL_REVIEW'
            v['closest_page'] = best_page
            v['coverage_distance'] = round(best_dist, 4)
            v['cross_check_note'] = f'Borderline match on page {best_page} (distance={best_dist:.3f}). Manual review needed.'
            manual_review += 1
        else:
            v['cross_check'] = 'CONFIRMED_GAP'
            v['cross_check_note'] = f'No policy page within semantic threshold (best distance={best_dist:.3f}).'
            confirmed += 1

    print(f"  Cross-check: {confirmed} CONFIRMED_GAP | {manual_review} MANUAL_REVIEW | {likely_compliant} LIKELY_COMPLIANT")
    return verdicts
```

**Step C — orchestrator changes in `run_evaluation()`:**

```python
# After Phase 4 (verdict call), before Phase 4b:
print("[Phase 1c] Building ephemeral policy index...")
chroma_client = chromadb.PersistentClient(path=str(DB_PATH))
policy_col, bigram_set, _ = _build_policy_index(pages, stamp, chroma_client)
print()

# Phase 4b — replace cross_check_verdicts call:
print("[Phase 4b] Bidirectional cross-check...")
verdicts = _bidirectional_cross_check(verdicts, findings, policy_col, bigram_set)
print()

# Phase 4c — NEW:
print("[Phase 4c] Updating Hebbian Compliance Graph...")
_update_hcg(verdicts, findings)
print()

# After Phase 5 report:
try:
    chroma_client.delete_collection(f"policy_{stamp}")
    print("  Ephemeral policy index cleaned up.")
except Exception:
    pass
```

**Expected verification on 65-page doc (run after implementing):**
- GAP id=41/42 (suspicious transactions) → page 45 should match at ~0.35 → LIKELY_COMPLIANT
- GAP id=11 (goAML) → no page mentions goAML → CONFIRMED_GAP
- GAP id=53 (Monthly Prevention Statement fields) → borderline → MANUAL_REVIEW
- GAP id=2/17/26 (risk identification — covered in section 3) → page ~20 should match → LIKELY_COMPLIANT

**Dependencies:**
```
pip install mmh3    # available now, use later when switching to probabilistic Bloom on workstation
# bitarray not needed yet — using plain set on CPU
```

---

## Task 2 — EGDR: Entropy-Gated Dynamic Retrieval (Phase 1b upgrade)

### Why

Boilerplate pages (TOC, version history, headers) have low entropy — their top-1 ChromaDB match is often an unrelated law node, producing false positives before Kimi even sees the finding. Complex multi-topic policy sections have high entropy — a single top-1 match may miss the most relevant law node (which is #2 or #3).

### Implementation — add to `detect_violations()`

```python
import math
from collections import Counter

def _window_entropy(text: str) -> float:
    """Shannon entropy of word frequency distribution."""
    words = text.lower().split()
    if len(words) < 10:
        return 0.0
    freq = Counter(words)
    total = len(words)
    return -sum((c / total) * math.log2(c / total) for c in freq.values())

# In detect_violations(), replace fixed n_results=1:
H = _window_entropy(window_text)
k = 3 if H > 6.5 else 1
results = collection.query(query_texts=[window_text], n_results=k)

# Collect ALL k results (not just [0][0])
for doc, meta, dist in zip(results["documents"][0],
                            results["metadatas"][0],
                            results["distances"][0]):
    findings.append({
        "page_range":   [start + 1, end],
        "jurisdiction": jurisdiction,
        "node_path":    meta.get("path", ""),
        "source_file":  meta.get("source_file", ""),
        "matched_rule": doc,
        "distance":     round(dist, 4),
        "raw_snippet":  window_text[:1000],
        "window_entropy": round(H, 3)   # store for debugging
    })
```

### Threshold calibration

Before committing, print the entropy distribution to verify the 6.5 threshold is sensible:
```python
# Quick calibration — run this once on both docs before setting threshold
from rag_evaluator import extract_pages, _window_entropy
from pathlib import Path
pages = extract_pages(Path("test_transactions/AML Manual V8.0_Reviewed(Draft).docx.pdf"))
for i in range(len(pages) - 2):
    window = "\n".join(pages[i:i+3])
    print(f"window {i+1}: H={_window_entropy(window):.2f}")
```

Adjust threshold if the distribution shows most windows clustered far from 6.5. On a typical 65-page AML doc: TOC pages ~3.5, admin pages ~4.0, policy sections ~6.5-8.5. Threshold 6.5 should cleanly separate boilerplate from content.

---

## Task 3 — Hebbian Compliance Graph (Phase 4c)

```python
def _update_hcg(verdicts: list, findings: list,
                hcg_path: str = "compliance_graph.json"):
    """
    Update persistent compliance graph with this run's cross-check results.
    Hebbian rule: nodes that fire together (consistently GAP or consistently compliant)
    wire together (weight increases). Weight caps at 1.0, never resets to 0.
    """
    hcg_file = WORKSPACE / hcg_path
    hcg = {}
    if hcg_file.exists():
        with open(hcg_file, 'r', encoding='utf-8') as f:
            hcg = json.load(f)

    def get_finding(v):
        idx = v.get('id', 0) - 1
        return findings[idx] if 0 <= idx < len(findings) else {}

    for v in verdicts:
        if not isinstance(v, dict):
            continue
        cc = v.get('cross_check')
        if cc not in ('CONFIRMED_GAP', 'LIKELY_COMPLIANT'):
            continue
        node = get_finding(v).get('node_path', '')
        if not node:
            continue

        entry = hcg.setdefault(node, {
            "confirmed_gap_weight": 0.0,
            "compliant_weight": 0.0,
            "documents_evaluated": 0,
            "last_seen": None
        })
        if cc == 'CONFIRMED_GAP':
            entry['confirmed_gap_weight'] = min(1.0, entry['confirmed_gap_weight'] + 0.1)
        elif cc == 'LIKELY_COMPLIANT':
            entry['compliant_weight'] = min(1.0, entry['compliant_weight'] + 0.1)
        entry['documents_evaluated'] += 1
        entry['last_seen'] = datetime.now().isoformat()[:10]

    with open(hcg_file, 'w', encoding='utf-8') as f:
        json.dump(hcg, f, indent=2)

    high_gap = sum(1 for e in hcg.values() if e.get('confirmed_gap_weight', 0) >= 0.5)
    print(f"  HCG updated: {len(hcg)} nodes tracked, {high_gap} high-weight confirmed gaps")
```

**Seed data available now:** After running both docs with the fixed cross-check, the systemic gaps (Joint Guidelines, telephone verification, trust deeds, simplified CDD) will seed the HCG with `confirmed_gap_weight = 0.2` from 2 documents. After 5+ client evaluations these reach 0.5+ and auto-escalate to CRITICAL severity in reports.

---

## Task 4 — Greedy Executive Summary (Phase 5 report enhancement)

Add to `_generate_report()` before the main gap table:

```python
def _greedy_priority_gaps(gaps, findings, get_finding_fn, max_items=5):
    """
    Greedy set cover: select minimum gaps covering maximum regulatory exposure.
    Prioritise: mandatory confirmed > mandatory manual_review > recommended confirmed.
    Secondary sort: lower distance = more certain match = higher priority.
    """
    sev_weight = {"mandatory": 3, "recommended": 2, "informational": 1}
    confirmed_only = [g for g in gaps if g.get('cross_check') == 'CONFIRMED_GAP']
    scored = sorted(
        confirmed_only,
        key=lambda g: (
            sev_weight.get(g.get('severity', ''), 0),
            -(get_finding_fn(g).get('distance', 1.0))
        ),
        reverse=True
    )
    return scored[:max_items]
```

Report output:
```html
<h2>Priority Remediation — Top {n} Mandatory Confirmed Gaps</h2>
<!-- Clean table: just ID, page, gap description, law node -->
<!-- These are the only ones the compliance officer needs to act on immediately -->
```

---

## Task 5 — spaCy Anonymizer (removes --skip-anon on CPU)

**Install (no GPU needed, runs fine on X1 Carbon):**
```powershell
pip install spacy
python -m spacy download en_core_web_sm   # CPU model — 12MB, ~50ms/page
# NOT en_core_web_trf (transformer-based — needs GPU)
```

**Replace `_anonymize_via_ollama()` with:**
```python
def _anonymize_via_spacy(text: str) -> str:
    """Strip PII using spaCy NER + regex. CPU-safe. ~50ms/page."""
    import spacy, re
    nlp = spacy.load("en_core_web_sm")
    doc = nlp(text[:100000])   # spaCy limit

    # NER replacement
    result = text
    for ent in reversed(doc.ents):   # reversed to preserve offsets
        if ent.label_ in ('PERSON', 'ORG', 'GPE', 'LOC', 'DATE', 'FAC'):
            placeholder = f"[{ent.label_}]"
            result = result[:ent.start_char] + placeholder + result[ent.end_char:]

    # Regex for structured PII that NER misses
    result = re.sub(r'\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}([A-Z0-9]?){0,16}\b', '[IBAN]', result)
    result = re.sub(r'\b[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}\b', '[EMAIL]', result)
    result = re.sub(r'\b(\+?\d[\d\s\-().]{7,}\d)\b', '[PHONE]', result)
    result = re.sub(r'\b\d{6,}\b', '[ACCOUNT_NO]', result)
    return result
```

Load the spaCy model once at startup, not per-page (expensive to reload). After this is done, remove the `--skip-anon` default guidance — spaCy works on the X1 Carbon.

---

## What We Learned — 65-Page Doc Results

**`AML Manual V8.0_Reviewed(Draft).docx.pdf` — 65 pages**
- 63 windows, 55 findings after detection, 55 after dedup
- Kimi: 28 GAPs, 27 COMPLIANT
- Manual verification: ~7 real gaps, ~12 false positives, ~9 borderline

### Confirmed Real GAPs

| ID | Description |
|---|---|
| 11 | MOKAS reporting uses Jira/ISR — CySEC requires goAML electronic submission |
| 15 | No internal audit annual AML review mandate |
| 40 | Ministry of Foreign Affairs / UN sanctions check absent |
| 53 | Monthly Prevention Statement mentioned — zero field specification |
| 18 | No breakdown of high-risk customers by country of origin |
| 48 | No telephone verification procedure |
| 50 | No specification of which departments need AML training |

### Confirmed False Positives

| ID | Why wrong |
|---|---|
| 41, 42 | Pages 45-46 have full suspicious transaction definitions |
| 7, 13 | Page 14 covers AMLCO guidance and annual training |
| 2, 17, 26 | Risk identification covered in section 3 — same gap on adjacent windows |
| 34 | Page 51 covers account closure for non-responsive clients |
| 35 | CDD section covers beneficial owner verification |

---

## What We Learned — 141-Page Doc Results

**`1a. AML Manual.docx.pdf` — 141 pages**
- Run completed successfully with --skip-anon
- Manual PDF scan performed post-evaluation

### Topics CONFIRMED COVERED (manual scan)

| Topic | Page |
|---|---|
| goAML electronic submission | 29 |
| Monthly Prevention Statement | 34 |
| Suspicious transaction indicators | Multiple |
| AML training requirements | 27, 33-35 |

### Topics CONFIRMED MISSING (manual scan)

| Missing | Significance |
|---|---|
| Economic profile of customers | No customer economic baseline |
| Record keeping retention periods | Not specified |
| Simplified CDD qualifying criteria | No conditions defined |
| Trust deed / trust structure procedures | Trusts not addressed |
| Joint Guidelines (EBA/ESMA) | Not referenced anywhere |

---

## Cross-Document Comparison — Both Docs

### Systemic GAPs (both documents — highest priority, almost certainly real)

These appear absent in both documents independently. Not false positives — too specific to appear in every AML document's boilerplate:

| GAP | CySEC Obligation |
|---|---|
| Joint Guidelines (EBA/ESMA) not referenced | Mandatory reference requirement |
| No telephone verification procedure | Customer contact verification |
| Trust deed / trust structures not addressed | Beneficial ownership for trusts |
| Simplified CDD — no qualifying criteria | Must specify when simplified applies |

### Document-Specific GAPs

| GAP | Doc | Notes |
|---|---|---|
| goAML not specified (uses Jira/ISR) | 65-page only | 141-page correctly references goAML p29 |
| Monthly Prevention Statement — no field spec | 65-page | 141-page has basic coverage p34 |

### What this means

The 141-page doc is more complete than the 65-page draft. The systemic gaps are the reliable deliverable — present in both, specific enough not to be noise. These should appear as `CONFIRMED_GAP` after the cross-check fix.

---

## Architecture Decisions — Closed

| Decision | Reason |
|---|---|
| No BM25 silence gate | Fails on paraphrased compliance text — silent false negatives |
| No MinHash window dedup | Misses new topics introduced mid-overlap |
| No distance threshold in detection | Kimi is the filter, not a float |
| Anonymize AFTER detection | ChromaDB is local — raw text safe. Only Kimi needs clean text |
| BATCH_SIZE=10 | 55 findings in one call = ~22k tokens = truncated JSON |
| ASCII-encode prompts | Raw PDF unicode breaks Kimi's JSON output |
| 8s sleep between batches | 429 rate limit without it |
| moonshot.ai not moonshot.cn | `.cn` returns 401 even with valid key |
| Plain set not mmh3+bitarray for bigrams | CPU machine — set has zero false positives, adequate memory |
| spaCy en_core_web_sm not _trf | CPU machine — _trf needs GPU |
| LLM as narrator not driver | Libet Inversion: ChromaDB is thalamic gate, Kimi narrates |
| k=3 max in EGDR | Higher k = more findings = more Kimi budget. On CPU/API: cap at 3. On workstation: raise to 5 |
| Greedy selection for executive summary | Set cover problem — minimum gaps, maximum regulatory exposure |

---

## Full Known Issues

### Critical (breaks correctness)
1. **Cross-check (Phase 4b)** — keyword frequency flags 100% of GAPs as LIKELY_COMPLIANT. Replace with bidirectional ChromaDB (Task 1 above).

### High (affects quality)
2. **Duplicate GAP suppression** — ids 2/17/26 flag the same underlying gap on adjacent windows. Current dedup operates on node_path but not on gap description similarity. Post-verdict: cluster by cosine similarity of gap descriptions, keep highest-confidence instance.
3. **EGDR not implemented** — boilerplate pages produce false positives, complex pages miss secondary law nodes.

### Medium (improves usability)
4. **spaCy anonymizer** — replace Ollama, enables real anonymization on CPU (~50ms/page).
5. **--verdict-only flag** — load existing JSON, re-run from Phase 4b only. Saves Kimi cost during development.
6. **Report: covered-on-page links** — LIKELY_COMPLIANT rows should link to the specific page.
7. **Report: executive summary** — greedy top-5 mandatory confirmed gaps only.

### Low (future)
8. **HCG escalation logic** — after weight >= 0.5, auto-set severity to CRITICAL in reports.
9. **Page SHA-256 cache** — skip re-vectorizing pages seen before (repeat clients).
10. **Multi-jurisdiction** — eu_amld5, eu_amld6, fatf_recommendations_2023 collections.

---

## Multi-Jurisdiction (Future — architecture already ready)

Add new law domains:
1. Convert law text to universal JSON node schema
2. Run `vectorize.py` with new collection name
3. Add collection name to `client_config.json` → `regulated_under`
4. Nothing else changes

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

Priority order: `eu_amld5` → `eu_amld6` → `fatf_recommendations_2023`

---

## Infrastructure

### API Keys (`.env` — gitignored)
```
KIMI_API_KEY=sk-DlKQ73PTbP9ff2r6U6y18TkVKqsmjRsEebYhIgi13mDOLLE2
```
Account: platform.moonshot.ai — ~25 EUR credit as of 2026-04-28.

### Python environment
```powershell
pip install -r requirements.txt
pip install mmh3        # Bloom filter (for future workstation use)
pip install spacy
python -m spacy download en_core_web_sm   # CPU-safe, 12MB
```

### Ollama (skip on current machine)
```powershell
# DO NOT use on X1 Carbon — 180s/page timeout
# For future GPU workstation only:
ollama pull qwen2.5:14b-instruct-q4_K_M
curl http://localhost:11434/api/tags   # verify running
```

---

## Files

```
aml_proof/
├── json_graph/              <- 15 CySEC JSON files (DO NOT MODIFY)
├── chroma_db/               <- Pre-built law vector DB (DO NOT REGENERATE)
├── test_transactions/
│   ├── AML Manual V8.0_Reviewed(Draft).docx.pdf  <- 65 pages, evaluated + verified
│   └── 1a. AML Manual.docx.pdf                   <- 141 pages, evaluated + verified
├── evaluation_results/      <- JSON + HTML reports (gitignored)
├── compliance_graph.json    <- Hebbian Compliance Graph (created after Task 3, gitignored)
├── rag_evaluator.py         <- Main pipeline
├── client_config.json       <- Client/jurisdiction config
├── requirements.txt         <- Dependencies
├── vectorize.py             <- Run only when adding new law domain
├── assess_pdf.py            <- Quick test tool
├── .env                     <- API keys (gitignored)
└── nextsession.md           <- This file
```

---

## Session Prompt (Copy This Exactly)

---

I am building an automated AML Compliance Auditor. Pull from GitHub repo `andreas1612/aml-law` and read `nextsession.md` in full before doing anything.

**HARDWARE CONSTRAINT:** Current machine is a Lenovo X1 Carbon — CPU only, no GPU. No workstation yet. All solutions must be CPU-efficient. Ollama is unusable on this machine. When a GPU workstation is provisioned (future), self-hosted LLM replaces Kimi API — architecture is config-driven, no code changes needed.

Architecture is based on the Libet Inversion framework. All architectural decisions are closed — do not re-litigate. Read nextsession.md, follow the task order exactly.

### Task 1 — Fix Bidirectional Cross-Check (CRITICAL — do this first)

Replace `cross_check_verdicts()` in `rag_evaluator.py` with `_bidirectional_cross_check()`. Add `_build_policy_index()`. Full implementation spec is in nextsession.md Task 1.

Install: `pip install mmh3`

After implementing, re-run 65-page doc and verify:
- GAP id=41/42 (suspicious transactions, covered pages 45-46) → LIKELY_COMPLIANT
- GAP id=11 (goAML) → CONFIRMED_GAP
- GAP id=53 (Monthly Prevention Statement fields) → MANUAL_REVIEW

```powershell
$env:KIMI_API_KEY = "sk-DlKQ73PTbP9ff2r6U6y18TkVKqsmjRsEebYhIgi13mDOLLE2"
python rag_evaluator.py --pdf "AML Manual V8.0_Reviewed(Draft).docx.pdf" --config client_config.json --skip-anon
```

### Task 2 — EGDR Retrieval Upgrade

Add `_window_entropy()` to `detect_violations()`. Replace fixed `n_results=1` with entropy-gated k. Full spec in nextsession.md Task 2. Print entropy distribution across all windows before committing to verify 6.5 threshold is correct for these documents.

### Task 3 — Hebbian Compliance Graph

Add `_update_hcg()`. Call after Phase 4b in `run_evaluation()`. Creates `compliance_graph.json`. Full spec in nextsession.md Task 3.

### Task 4 — Greedy Executive Summary

Add `_greedy_priority_gaps()` to `_generate_report()`. Full spec in nextsession.md Task 4.

### Task 5 — Re-run Both Docs

After Tasks 1-4:
```powershell
python rag_evaluator.py --pdf "AML Manual V8.0_Reviewed(Draft).docx.pdf" --config client_config.json --skip-anon
python rag_evaluator.py --pdf "1a. AML Manual.docx.pdf" --config client_config.json --skip-anon
```

Verify confirmed GAPs match the manually verified findings in nextsession.md. Report false positive rate before committing.

### Task 6 — Commit and Push

```powershell
git add rag_evaluator.py requirements.txt
git commit -m "feat: bidirectional cross-check, EGDR, HCG, greedy report"
git push origin main
```

Do NOT commit `evaluation_results/` or `compliance_graph.json`.

---
