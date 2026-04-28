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

This is a Proof of Concept machine. If the PoC is evaluated as satisfactory, a GPU workstation will be provisioned. The system will only be visible to clients after that point.

| Constraint | Impact | Current workaround |
|---|---|---|
| CPU only, no GPU | Ollama unusable (180s/page timeout) | `--skip-anon` flag bypasses anonymization |
| Limited RAM | ChromaDB must stay in-process, no large models | all-MiniLM-L6-v2 is fine (~90MB) |
| No persistent compute | Long runs can be interrupted | `--verdict-only` flag planned to resume from saved JSON |
| No local LLM | Kimi API required for verdict | Kimi moonshot-v1-128k, api.moonshot.ai/v1 |

**When the GPU workstation arrives (after PoC approval):**
- Remove `--skip-anon` — use `qwen2.5:14b-instruct-q4_K_M` via Ollama for anonymization
- Replace Kimi API with self-hosted model (qwen2.5:72b or similar) — update `kimi_base_url` in `client_config.json`
- EGDR can use `k=5` on high-entropy windows (currently k=3 max to limit Kimi batch load)
- spaCy can be upgraded to `en_core_web_trf` (transformer-based, GPU-accelerated)
- All architecture stays identical — only config and model names change

**Do NOT:**
- Pull in any model larger than ~100MB without checking RAM
- Add any Ollama calls without `--skip-anon` guard
- Assume GPU availability for any computation
- Implement spaCy anonymizer yet — no real clients until after workstation

---

## Theoretical Foundation — The Libet Inversion

This system is a domain application of the **Libet Inversion** architectural framework. Five-layer biologically-inspired architecture for autonomous AI systems.

**Five-layer mapping:**

| Layer | Biological Analogue | Our Implementation | Status |
|---|---|---|---|
| 1 — Parallel sensors | Demon Layer | PyPDF2 + sliding window | Done |
| 2 — Entropy-gated filter | Thalamic Gate / EGDR | ChromaDB retrieval (entropy-gated k) | Done — needs threshold tweak |
| 3 — Serial workspace | Global Workspace | Kimi context window (intentionally small) | Done |
| 4 — Narrator + veto | Interpreter + Veto | Kimi verdict + bidirectional cross-check + human review | Done |
| 5 — Long-term threat memory | Hebbian Compliance Graph | `compliance_graph.json` | Done — needs CRITICAL escalation |

**Key architectural principles (do not re-litigate):**
- LLM is the narrator, not the driver. ChromaDB is the thalamic gate. This is correct.
- No BM25 gate — "demons never skip signal." Sliding window step=1 is correct.
- Context window intentionally small — BATCH_SIZE=10 is correct. Do not fight this.
- Constraint as architecture — the context window's smallness IS the feature.
- No distance threshold in Phase 1b detection — Kimi is the filter, not a float.

---

## Current State (as of 2026-04-28)

### Complete and working

| Component | Status | Location |
|---|---|---|
| CySEC JSON Knowledge Graph | Complete — DO NOT MODIFY | `json_graph/` (15 files) |
| ChromaDB Vector DB | Built, 325 nodes — DO NOT REGENERATE | `chroma_db/` |
| Full-coverage sliding window evaluator (EGDR) | Working | `rag_evaluator.py` |
| Bidirectional cross-check (Phase 4b) | Working | `rag_evaluator.py` |
| Gap description deduplication (Phase 4b-pre) | Working | `rag_evaluator.py` |
| Detection distance pre-filter (LOW_CONFIDENCE_NOISE) | Working | `rag_evaluator.py` |
| Hebbian Compliance Graph (Phase 4c) | Working, 15 nodes tracked | `compliance_graph.json` |
| HTML report with greedy executive summary | Working | auto-generated in `evaluation_results/` |
| Client config | Working | `client_config.json` |
| Kimi API | Working | endpoint: `https://api.moonshot.ai/v1` (NOT `.cn`) |
| 65-page doc evaluated + verified (3 runs) | Done | `test_transactions/AML Manual V8.0_Reviewed(Draft).docx.pdf` |
| 141-page doc evaluated + verified (2 runs) | Done | `test_transactions/1a. AML Manual.docx.pdf` |

### NOT done — ordered task list for next session (PoC focus)

| Priority | Task | Effort | Why it matters for PoC |
|---|---|---|---|
| **1** | Raise EGDR threshold 6.5 → 7.0 | 2 min | Cuts LOW_CONFIDENCE_NOISE from 35 → ~10. Cleaner numbers |
| **2** | `--verdict-only` flag | 30 min | Re-run report without paying Kimi. Essential for demo tweaks |
| **3** | HCG CRITICAL escalation at weight ≥ 0.5 | 20 min | "System auto-identified 5 systemic gaps as CRITICAL" — strong PoC story |
| **4** | Fix HCG `documents_evaluated` counter | 5 min | Currently counts per verdict per run instead of once per run |
| **5** | spaCy anonymizer | **SKIP until workstation** | No real clients yet |
| **6** | Multi-jurisdiction | **SKIP until workstation** | Future — architecture ready |

---

## Pipeline — Full Current State

```
Phase 1a:  PyPDF2 extracts all pages (DONE)

Phase 1b:  EGDR sliding window detection (DONE — threshold needs tweak)
           Current: H > 6.5 → k=3, H <= 6.5 → k=1
           Fix needed: raise to H > 7.0 → k=3 to reduce LOW_CONFIDENCE_NOISE
           LOW_CONFIDENCE_NOISE rate currently 35-37% of GAPs — too high
           After fix: expected ~10-15%

Phase 1c:  Ephemeral policy index (DONE)
           All N pages → policy_{stamp} ChromaDB collection
           Plain Python set of bigrams (zero false positives on CPU)
           Deleted after Phase 5

Phase 2:   Deduplication by node_path + overlapping page ranges (DONE)

Phase 3:   Anonymization (DONE — SKIPPED on X1 Carbon)
           --skip-anon on X1 Carbon (Ollama unusable on CPU)
           When GPU workstation available: implement spaCy en_core_web_sm

Phase 4:   Kimi verdict in batches of 10, 8s sleep, 5 retries on 429 (DONE)

Phase 4b-pre: Gap description deduplication (DONE)
           Jaccard word overlap > 0.6 → marks later GAP as DUPLICATE
           Runs before cross-check to skip reverse query on duplicates

Phase 4b:  Bidirectional cross-check (DONE)
           Pre-filters:
             - Skip DUPLICATE verdicts (marked by Phase 4b-pre)
             - Detection distance > 0.75 → LOW_CONFIDENCE_NOISE, skip query
           Step 1 — Bigram pre-filter: zero matches → CONFIRMED_GAP immediately
           Step 2 — Semantic reverse query: law_node → policy_pages collection
             best_distance < 0.45  → LIKELY_COMPLIANT + page + distance
             best_distance 0.45-0.55 → MANUAL_REVIEW + page + distance
             best_distance > 0.55  → CONFIRMED_GAP

Phase 4c:  Hebbian Compliance Graph (DONE — needs CRITICAL escalation)
           compliance_graph.json: 15 nodes tracked after 3 total runs
           5 nodes at weight ≥ 0.5 (auto-escalate to CRITICAL — not yet implemented)
           Hebbian rule: +0.1 per confirmed/compliant occurrence, caps at 1.0
           BUG: documents_evaluated counts per verdict not per run — fix in Task 4

Phase 5:   HTML report (DONE)
           Executive summary: greedy top-5 mandatory CONFIRMED_GAPs
           Full GAP table with CONFIRMED / MANUAL_REVIEW / LIKELY_COMPLIANT /
             DUPLICATE / LOW_CONFIDENCE_NOISE badges
           "Covered on page X (distance=Y)" for LIKELY_COMPLIANT rows
           Summary cards: mandatory, confirmed, total gaps, compliant, duplicates, noise

Cleanup:   Deletes policy_{stamp} collection from ChromaDB (DONE)
```

### How to run (current — CPU machine)

```powershell
$env:KIMI_API_KEY = "sk-DlKQ73PTbP9ff2r6U6y18TkVKqsmjRsEebYhIgi13mDOLLE2"
cd C:\Users\andre\Desktop\aml_proof
python rag_evaluator.py --pdf "AML Manual V8.0_Reviewed(Draft).docx.pdf" --config client_config.json --skip-anon
python rag_evaluator.py --pdf "1a. AML Manual.docx.pdf" --config client_config.json --skip-anon
```

### View reports

```powershell
cd C:\Users\andre\Desktop\aml_proof\evaluation_results
python -m http.server 8080
# Open: http://localhost:8080
```

---

## Task 1 — Raise EGDR Threshold (2 min)

In `detect_violations()`, change one line:

```python
# CURRENT (too aggressive — generates too many weak 3rd matches):
k = 3 if H > 6.5 else 1

# FIX:
k = 3 if H > 7.0 else 2 if H > 6.5 else 1
```

**Why:** LOW_CONFIDENCE_NOISE rate is 35-36/83 = ~43% on the 65-page doc. Too many junk 3rd-rank law node matches from EGDR are being generated just to get filtered out downstream. Raising the threshold reduces noise at source.

**Verify after:** LOW_CONFIDENCE_NOISE should drop from ~35 to ~10-15. CONFIRMED_GAP count should stay roughly the same (the noise was already being filtered).

---

## Task 2 — `--verdict-only` Flag (30 min)

Add a flag that loads an existing JSON result file and re-runs from Phase 4b onward without calling Kimi.

```python
parser.add_argument("--verdict-only", type=str, default=None,
                    help="Path to existing result JSON. Skip to Phase 4b, re-run cross-check and report only.")
```

**Use case:** During PoC demo prep, you may want to tweak cross-check thresholds or report formatting without paying for 15 Kimi batches again. Load the saved verdicts JSON → re-run Phase 4b-pre + 4b + 4c + 5.

**Implementation sketch:**
```python
if args.verdict_only:
    with open(args.verdict_only, encoding='utf-8') as f:
        saved = json.load(f)
    # Extract pages (needed for policy index rebuild)
    pages = extract_pages(pdf_path)
    findings = saved_findings  # need to store findings in JSON too — see note
    verdicts = saved['verdicts']
    # ... jump to Phase 1c, skip Phases 1b/2/3/4
```

**Note:** Currently `findings` are not saved in the result JSON — only `verdicts` are. Before implementing `--verdict-only`, add `"findings": findings` to the result dict in `_save()`.

---

## Task 3 — HCG CRITICAL Escalation (20 min)

In `_update_hcg()`, after saving the file, check for high-weight nodes and return a list:

```python
# After saving hcg:
critical_nodes = [node for node, e in hcg.items()
                  if e.get('confirmed_gap_weight', 0) >= 0.5]
if critical_nodes:
    print(f"  CRITICAL escalation: {len(critical_nodes)} nodes at weight >= 0.5")
```

In `_generate_report()`, query `compliance_graph.json` for high-weight nodes and add a CRITICAL section above the priority table:

```html
<h2 style="color:#c0392b">⚠ CRITICAL — Systemic Gaps (confirmed across multiple documents)</h2>
<p>These obligations were absent in every document evaluated. Confidence increases with each run.</p>
<!-- table: node path | weight | docs evaluated | last seen -->
```

**Current nodes that would escalate (weight ≥ 0.5 after 3 runs):**
- part_3 §9.1.m — weight 0.8
- part_3 §10.4.b — weight 0.8
- part_4 §12.4 — weight 0.7-0.8
- part_6 §27 — weight 0.8
- part_5 §25.3 — weight 0.8

---

## Task 4 — Fix HCG `documents_evaluated` Counter (5 min)

**Bug:** `_update_hcg()` iterates over all verdicts and increments `documents_evaluated` once per matching verdict. A node that appears in 4 verdicts in one run gets `+4` instead of `+1`.

**Fix:** Track which nodes have been updated in the current run and only increment once:

```python
updated_this_run = set()
for v in verdicts:
    ...
    node = get_finding(v).get('node_path', '')
    entry['documents_evaluated'] += (0 if node in updated_this_run else 1)
    updated_this_run.add(node)
```

---

## Verified Results (as of 2026-04-28)

### 65-page doc — `AML Manual V8.0_Reviewed(Draft).docx.pdf`

**Best run (163428) — 3rd run, full architecture:**
- 65 pages → 185 raw hits → 146 unique findings
- Kimi: 82 GAPs, 64 COMPLIANT
- Gap dedup: 19 DUPLICATE
- Cross-check: **22 CONFIRMED_GAP | 5 MANUAL_REVIEW | 1 LIKELY_COMPLIANT | 35 LOW_CONFIDENCE_NOISE**
- Pipeline stable: near-identical results across 3 runs (variance ±1)
- Estimated precision on CONFIRMED_GAP: **~82%** (3-4 false positives among 22)

**Verified CONFIRMED real gaps:**

| ID | Gap | Notes |
|---|---|---|
| id=24 | Joint Guidelines (EBA/ESMA) not referenced | Systemic — both docs |
| id=27 | goAML/MOKAS electronic submission absent | 65-page only (141-page has p29) |
| id=39 | Internal audit annual AML review missing | Systemic — both docs |
| id=60/61 | Financial sanctions + EU CFSP list absent | Systemic — both docs |
| id=99 | High-risk customer ongoing monitoring absent | Both docs |
| id=127 | Telephone verification procedure absent | Systemic — both docs |
| id=132 | Training departments not specified | Both docs |

**Verified LIKELY_COMPLIANT (correctly downgraded):**
- id=111 → Suspicious transactions → page 46, dist=0.442 ✓

### 141-page doc — `1a. AML Manual.docx.pdf`

**Best run (161714) — 2nd run, full architecture:**
- 141 pages → 336 findings → 196 Kimi GAPs
- Gap dedup: 61 DUPLICATE
- Cross-check: **40 CONFIRMED_GAP | 17 MANUAL_REVIEW | 5 LIKELY_COMPLIANT | 73 LOW_CONFIDENCE_NOISE**

**Verified LIKELY_COMPLIANT (correctly identified coverage):**
- id=48/266 → Suspicious transaction examples → page 109 ✓
- id=92 → AML training → page 36 ✓
- id=124/136 → Risk-based approach → page 49 ✓
- id=177 → Beneficial owner verification → page 72, dist=0.27 (strongest match) ✓

**Notable CONFIRMED real gaps:**
- id=184 → Trust structure (trustor/trustee/beneficiary) — systemic
- id=201 → Simplified CDD qualifying criteria — systemic
- id=210 → Telephone verification — systemic

### Cross-Document Systemic Gaps (highest priority — confirmed absent in both)

| Gap | CySEC Obligation | HCG weight |
|---|---|---|
| Joint Guidelines (EBA/ESMA) not referenced | Mandatory reference | 0.8 |
| Telephone verification procedure absent | Customer contact verification | 0.8 |
| Trust deed / trust structure procedures | Beneficial ownership for trusts | 0.7+ |
| Simplified CDD — no qualifying criteria | Must specify when simplified applies | 0.7+ |
| Financial sanctions / EU CFSP / UN checks | Mandatory screening | 0.8 |

---

## HCG State (as of 2026-04-28)

15 nodes tracked. 5 at weight ≥ 0.5, ready for CRITICAL escalation (Task 3):

| Node | Weight | Obligation area |
|---|---|---|
| part_3 §9.1.m | 0.8 | Risk identification |
| part_3 §10.4.b | 0.8 | Compliance officer duties |
| part_4 §12.4 | 0.7-0.8 | CDD procedures |
| part_6 §27 | 0.8 | Sanctions screening |
| part_5 §25.3 | 0.8 | Monitoring obligations |

After 2-3 more client doc runs these reach 1.0 and the pattern is statistically reliable.

---

## Architecture Decisions — Closed

| Decision | Reason |
|---|---|
| No BM25 silence gate | Fails on paraphrased compliance text — silent false negatives |
| No MinHash window dedup | Misses new topics introduced mid-overlap |
| No distance threshold in Phase 1b detection | Kimi is the filter, not a float |
| Anonymize AFTER detection | ChromaDB is local — raw text safe. Only Kimi needs clean text |
| BATCH_SIZE=10 | 55+ findings in one call = truncated JSON |
| ASCII-encode prompts | Raw PDF unicode breaks Kimi's JSON output |
| 8s sleep between batches | 429 rate limit without it |
| moonshot.ai not moonshot.cn | `.cn` returns 401 even with valid key |
| Plain set not mmh3+bitarray for bigrams | CPU machine — set has zero false positives |
| spaCy en_core_web_sm not _trf | CPU machine — _trf needs GPU. Skip until workstation. |
| LLM as narrator not driver | Libet Inversion: ChromaDB is thalamic gate, Kimi narrates |
| k=3 max in EGDR | Higher k = more findings = more Kimi budget. CPU/API: cap at 3 |
| Greedy selection for executive summary | Set cover — minimum gaps, maximum regulatory exposure |
| Jaccard > 0.6 for gap dedup | Lower = too aggressive (collapses real distinct gaps) |
| Detection distance > 0.75 → LOW_CONFIDENCE_NOISE | Law node match too weak to trust either direction |
| Cross-check threshold 0.55 for CONFIRMED_GAP | Tuned on 65-page manual verification. May raise to 0.60 |

---

## Known Issues

### For PoC (fix before evaluation)
1. **EGDR threshold too low** — LOW_CONFIDENCE_NOISE rate 43%. Fix: raise k=3 threshold 6.5 → 7.0 (Task 1, 2 min).
2. **HCG documents_evaluated bug** — counts per verdict not per run. Cosmetic, doesn't affect weights (Task 4, 5 min).
3. **HCG CRITICAL escalation not shown in report** — 5 nodes already qualify (Task 3, 20 min).

### Post-workstation (don't touch on CPU machine)
4. **--skip-anon required** — spaCy anonymizer blocked until GPU workstation.
5. **Cross-check threshold 0.55 may need +0.05** — Monthly Prevention Statement in 141-page doc shows CONFIRMED_GAP despite page 34 coverage. Consider 0.55 → 0.60 after more data.

### Future
6. **Duplicate GAP clustering on gap descriptions** — current Jaccard dedup is effective but greedy. A proper clustering pass would be cleaner.
7. **Multi-jurisdiction** — EU AMLD5/6, FATF. Architecture ready, needs law graph data.
8. **Page SHA-256 cache** — skip re-vectorizing pages seen before (repeat clients).

---

## Files

```
aml_proof/
├── json_graph/              <- 15 CySEC JSON files (DO NOT MODIFY)
├── chroma_db/               <- Pre-built law vector DB (DO NOT REGENERATE)
├── test_transactions/
│   ├── AML Manual V8.0_Reviewed(Draft).docx.pdf  <- 65 pages, 3 runs verified
│   └── 1a. AML Manual.docx.pdf                   <- 141 pages, 2 runs verified
├── evaluation_results/      <- JSON + HTML reports (gitignored)
├── compliance_graph.json    <- Hebbian Compliance Graph (gitignored)
├── rag_evaluator.py         <- Main pipeline
├── client_config.json       <- Client/jurisdiction config
├── requirements.txt         <- Dependencies (includes mmh3 for future use)
├── vectorize.py             <- Run only when adding new law domain
├── assess_pdf.py            <- Quick test tool
├── .env                     <- API keys (gitignored)
└── nextsession.md           <- This file
```

---

## Infrastructure

### API Keys (`.env` — gitignored)
```
KIMI_API_KEY=sk-DlKQ73PTbP9ff2r6U6y18TkVKqsmjRsEebYhIgi13mDOLLE2
```
Account: platform.moonshot.ai — check credit balance before long runs.

### Python environment
```powershell
pip install -r requirements.txt
```

### Ollama (skip on current machine)
```powershell
# DO NOT use on X1 Carbon — 180s/page timeout
# For future GPU workstation only
```
