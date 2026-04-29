# Next Session Handover — AML Compliance Auditor

> **Read this entire file before writing a single line of code. Everything decided here has a reason. Do not re-litigate closed decisions.**
> **Hardware context matters — read the Resource Constraints section before choosing any approach.**
> **This file was last updated: 2026-04-29. Session 2 architectural analysis is in the new sections below.**

---

## What This System Is

An automated AML Compliance Auditor that evaluates corporate AML policy PDFs against structured legal knowledge graphs. Runs entirely locally except for the final verdict call to an external LLM API (Kimi).

CySEC Consolidated AML Directive is law domain 1. Architecture supports EU AMLD5/6, FATF, FinCEN — jurisdiction is config-driven.

GitHub: `andreas1612/aml-law`

---

## HARDWARE / RESOURCE CONSTRAINTS — READ FIRST

**Current machine: Lenovo X1 Carbon — CPU only. No GPU.**

This is a Proof of Concept machine. If the PoC is evaluated as satisfactory, a GPU workstation will be provisioned. The system will only be visible to clients after that point.

| Constraint | Impact | Current workaround |
|---|---|---|
| CPU only, no GPU | Ollama unusable (180s/page timeout) | `--skip-anon` flag bypasses anonymization |
| Limited RAM | ChromaDB must stay in-process, no large models | all-MiniLM-L6-v2 is fine (~90MB) |
| No persistent compute | Long runs can be interrupted | `--verdict-only` flag planned |
| No local LLM | Kimi API required for verdict | Kimi moonshot-v1-128k, api.moonshot.ai/v1 |
| Kimi rate limit | 8s sleep between batches of 10 mandatory | built into pipeline |

**When the GPU workstation arrives (after PoC approval):**
- Remove `--skip-anon` — use `qwen2.5:14b-instruct-q4_K_M` via Ollama for anonymization
- Replace Kimi with self-hosted model (qwen2.5:72b or similar) — update `kimi_base_url` in `client_config.json`
- Run Kimi batches in parallel — rate limit gone, sleep removed
- spaCy can be upgraded to `en_core_web_trf` (transformer-based, GPU-accelerated)
- Architecture stays identical — only config and model names change

**Do NOT:**
- Pull in any model larger than ~100MB without checking RAM
- Add any Ollama calls without `--skip-anon` guard
- Assume GPU availability for any computation
- Implement spaCy anonymizer yet — no real clients until after workstation
- Implement auto-threshold compliance resolution (see Closed Decisions)

---

## Theoretical Foundation — The Libet Inversion

This system is a domain application of the **Libet Inversion** architectural framework (see `C:\Users\andre\Desktop\$\Biological_Governance_Position_Paper_v2.docx`).

**Five-layer mapping — current implementation:**

| Layer | Biological Analogue | Current Implementation | Target Implementation |
|---|---|---|---|
| 1 — Parallel sensors | Demon Layer | PyPDF2 + sliding window | PyPDF2 + obligation-first sweep |
| 2 — Entropy-gated filter | Thalamic Gate / EGDR | ChromaDB entropy-gated k | ChromaDB obligation→policy query, HCG-prioritised |
| 3 — Serial workspace | Global Workspace | Kimi context window (intentionally small) | Same — BATCH_SIZE=10 stays |
| 4 — Narrator + veto | Interpreter + Veto | Kimi verdict + human review | Kimi verdict with richer context + human review |
| 5 — Long-term threat memory | Immune Memory / HCG | compliance_graph.json (15 nodes) | Extended HCG with evaluation tiers |

**Autonomic dual-mode (from paper section 2.3):**
- Parasympathetic: known-stable obligations → light evaluation
- Sympathetic: known-gap obligations (HCG high weight) → full depth, evaluated first
- Currently not implemented — requires HCG data from ~10+ client runs before meaningful

**Key architectural principles — do not re-litigate:**
- LLM is the narrator, not the driver. ChromaDB is the thalamic gate.
- Context window intentionally small — BATCH_SIZE=10. Do not fight this.
- Constraint as architecture — smallness IS the feature.
- No auto-threshold compliance resolution — embedding model not trained on legal domain, distance ≠ satisfaction.
- Kimi is the filter, not a float. Do not replace Kimi judgement with distance cutoffs.

---

## Critical Data Finding — Session 2026-04-29

**This changes the architecture direction. Read before anything else.**

Analysis of best runs against both verified documents revealed:

### 65-page doc (163428 run):
- Sliding window touched **91 of 325 law nodes — 28% of the law graph**
- **234 law nodes received zero hits — completely invisible to the system**
- Distance distribution of all 146 findings:
  - `< 0.30`: 0 findings (0%)
  - `0.30–0.45`: 2 findings (1%)
  - `0.45–0.55`: 8 findings (5%)
  - `0.55–0.70`: 32 findings (22%)
  - `0.70–0.75`: 24 findings (16%)
  - `> 0.75`: 80 findings (**55% — noise threshold**)
- Good signal (distance < 0.55): **10 findings = 7% of output**

### Implication:
The system produces 22 confirmed gaps while being blind to 72% of the law graph. Some of the 234 invisible nodes are real gaps that have never been detected. The current recall is unknown and provably incomplete.

This is not a noise problem. It is a **recall problem**.

### Why the 234 nodes are invisible:
The sliding window uses k=1 or k=3. For any window, only the top-k law nodes are returned. Nodes ranked 4th-325th are discarded even with distance 0.35. Some of the 234 may be present in the document but systematically excluded by the k cutoff. This is unverified — some are genuine gaps, some may be retrieval artifacts.

---

## Architectural Direction — Obligation-First Pipeline

### What changes and why

**The sliding window is document-first:** scan the policy, generate hits, ask "is this a gap?" It touches 28% of obligations and generates 55% noise.

**The replacement is obligation-first:** for each of 325 law nodes, ask "does the policy satisfy this obligation?" This is 100% coverage by construction and maps cleanly to the Libet Inversion — the demon layer fires on every obligation, not just the ones a sliding window happened to hit.

### What gets replaced

| Current component | Replaced by | Why |
|---|---|---|
| Sliding window EGDR (Phase 1b) | Obligation-first sweep | 28% → 100% law graph coverage |
| Phase 2 deduplication | Not needed | One result per obligation by design |
| Phase 4b-pre Jaccard dedup | Not needed | Same reason |
| Phase 4b bidirectional cross-check | Becomes Phase 2 (the main pipeline) | It was already doing this correctly, just as a cleanup pass |

### What stays unchanged

- Law ChromaDB (325 nodes) — untouched
- Policy collection build (Phase 1c) — same
- Kimi batching logic — same (batches of 10, 8s sleep, 5 retries)
- HCG update logic — extended, not replaced
- HTML report — same structure, now shows 325-row obligation table

---

## Target Pipeline — Obligation-First Architecture

```
Phase 1:  PyPDF2 extracts all pages (unchanged)

Phase 1c: Build ephemeral policy ChromaDB collection (unchanged)
          All N pages → policy_{stamp} collection
          Bigram set over full document text (unchanged)

Phase 2:  Obligation-first sweep — 325 ChromaDB queries, local, ~5 seconds
          For each law node:
            query policy_collection → top-3 matching sections + distances
          Sort results: worst distance first (most likely gaps evaluated first)
          HCG high-weight confirmed-gap nodes → moved to top of queue
          Output: 325 candidate findings, sorted by gap likelihood

Phase 3:  Anonymization — SKIPPED on X1 Carbon (--skip-anon)
          When GPU workstation: spaCy en_core_web_sm

Phase 4:  Kimi verdict — batches of 10, worst-distance-first
          CHANGED CONTEXT: each finding now includes:
            - law node obligation text (exact)
            - top-3 matching policy sections (page + text + distance)
            - question: "Do any of these sections satisfy this obligation?
                         If not, what specific element is missing?"
          Returns: GAP / COMPLIANT + one-line missing element (if GAP)
          Stop condition: all 325 done, or API budget exhausted

Phase 4c: HCG update (unchanged logic, extended schema)

Phase 5:  HTML report
          Now shows all 325 obligations with status
          Priority remediation: top confirmed gaps by HCG weight + severity
          Same badge system
```

### Estimated Kimi cost (CPU machine, obligation-first):
- 325 obligations / 10 per batch = 33 batches
- 33 × (8s sleep + ~15s response) = ~760s = **~13 minutes**
- Current 141-page run: ~8 minutes (196 findings, 20 batches)
- Tradeoff: ~5 minutes slower, 100% coverage vs 28%

### GPU future (same architecture):
- Replace Kimi with local model (qwen2.5:72b)
- Remove 8s sleep — no rate limit
- Run batches in parallel
- 13 minutes → 2-3 minutes
- Architecture unchanged

---

## HCG Extension — Evaluation Tiers

The HCG needs to drive evaluation ORDER and DEPTH, not just track history.
Extended schema (backward compatible with existing compliance_graph.json):

```json
{
  "part_3.§9.1.m": {
    "confirmed_gap_weight": 0.8,
    "compliant_weight": 0.0,
    "evaluation_tier": "sympathetic",
    "documents_evaluated": 5,
    "last_seen": "2026-04-29"
  },
  "part_2.§4.1": {
    "confirmed_gap_weight": 0.0,
    "compliant_weight": 0.7,
    "evaluation_tier": "parasympathetic",
    "documents_evaluated": 4,
    "last_seen": "2026-04-29"
  },
  "part_6.§28.3": {
    "confirmed_gap_weight": 0.0,
    "compliant_weight": 0.0,
    "evaluation_tier": "unknown",
    "documents_evaluated": 0,
    "last_seen": null
  }
}
```

**Tier logic:**
- `sympathetic`: confirmed_gap_weight ≥ 0.5 — move to top of evaluation queue
- `parasympathetic`: compliant_weight ≥ 0.5 — evaluate last (likely already covered)
- `unknown`: no history — standard evaluation order

**Important:** Tiers inform ORDER only at this stage. They do NOT auto-resolve verdicts (no auto-COMPLIANT, no auto-GAP). Kimi decides. The data to support auto-resolution doesn't exist until ~10+ clients have been processed.

---

## Honest Challenges To The New Architecture

Document these — do not forget them. Solving them requires more client data.

1. **Auto-thresholds are legally dangerous.** Distance < 0.30 auto-COMPLIANT is unreliable — all-MiniLM-L6-v2 is not trained on legal compliance. The verified LIKELY_COMPLIANT (id=111, dist=0.442) would not have been caught by a 0.30 threshold. Do not implement auto-resolution until HCG has ~10 clients of validation data.

2. **234 invisible nodes: some may be retrieval artifacts.** Some of the 234 may be present in the document but ranked 4th-8th in every window — excluded by k cutoff, not genuinely absent. Obligation-first will reveal which is which. Do not assume they are all gaps.

3. **Paraphrase detection.** The sliding window finds coverage because it starts from document text. Obligation-first starts from law text. Regulatory language and operational policy language can describe the same concept with zero shared vocabulary. ChromaDB may return high distance for a covered obligation because the phrasing diverges. Kimi context (obligation + top-3 sections) helps but does not fully solve this.

4. **HCG bootstrapping.** Tier-based prioritization only helps after sufficient client data. On the first 5-10 clients, all 310 unknown nodes go through full evaluation. No efficiency gain until the HCG matures. This is expected — document it, not a bug.

5. **Multi-jurisdiction scaling.** Adding AMLD5/FATF means 500+ nodes → 50+ Kimi batches per document. Cross-law equivalence mapping (AMLD5 Article X ≡ CySEC §Y) requires legal expert review — it cannot be automated. Plan for this when jurisdictions are added.

---

## Immediate Steps — What To Build Next

**Ground truth comparison (session 2026-04-29) confirmed: recall is 36%. B1 is now the priority.**

Two tracks. Track A has small PoC patches. Track B is the architectural fix validated by the comparison.

### Track A — PoC Patches (fast wins, current codebase)

| Priority | Task | Effort | Code location |
|---|---|---|---|
| **A1** | Raise EGDR threshold 6.5 → 7.0 | 2 min | `detect_violations()` line 128 |
| **A2** | `--verdict-only` flag | 30 min | arg parser + `run_evaluation()` |
| **A3** | HCG CRITICAL escalation in report | 20 min | `_update_hcg()` + `_generate_report()` |
| **A4** | Fix HCG `documents_evaluated` counter | 5 min | `_update_hcg()` loop |

Do Track A first if a quick demo is needed. None of these block Track B.

### Track B — New Architecture (ground-truth-validated priority)

| Step | What | Why | Effort |
|---|---|---|---|
| **B1** | `obligation_first_evaluator.py` | 36% → target 70%+ recall. Fixes every missed policy gap. | ~2 hrs |
| **B2** | Richer Kimi context | Obligation text + top-3 policy sections → better verdict quality | ~30 min |
| **B3** | HCG tier field | Add `evaluation_tier` to schema, drive queue ordering in B1 | ~20 min |
| **B4** | 325-row report table | Show all 325 obligations with status | ~1 hr |
| **B5** | Rerun compare_gaps.py | Validate recall improvement against XLSX ground truth | ~5 min |

**B1 is the entry point. B2 and B3 feed into B1. B4 and B5 follow.**

### How to build B1

Write `obligation_first_evaluator.py` as a new file. Do not modify `rag_evaluator.py` — keep the old pipeline intact until B1 is validated.

B1 core loop (150 lines, uses existing ChromaDB infrastructure unchanged):

```python
def obligation_sweep(policy_stamp: str, config: dict, hcg: dict) -> list:
    """
    For each of 325 law nodes, query the ephemeral policy collection.
    Returns one candidate finding per node, sorted worst-distance-first.
    HCG sympathetic nodes (confirmed_gap_weight >= 0.5) go first.
    """
    chroma_client = chromadb.PersistentClient(path=str(DB_PATH))
    policy_col = chroma_client.get_collection(f"policy_{policy_stamp}")
    law_col    = chroma_client.get_collection(config['regulated_under'][0])

    all_nodes = law_col.get(include=['documents', 'metadatas'])
    findings  = []

    for doc, meta in zip(all_nodes['documents'], all_nodes['metadatas']):
        results   = policy_col.query(query_texts=[doc], n_results=3)
        distances = results['distances'][0]
        best_dist = min(distances)
        findings.append({
            'node_path':    meta.get('path', ''),
            'matched_rule': doc,
            'distance':     round(best_dist, 4),
            'top_sections': [
                {'page': m.get('page_num'), 'text': t, 'distance': round(d, 4)}
                for t, m, d in zip(
                    results['documents'][0],
                    results['metadatas'][0],
                    results['distances'][0]
                )
            ]
        })

    # Worst distance first — most likely gaps go to Kimi first.
    # HCG sympathetic nodes (high confirmed_gap_weight) jump to front of queue.
    findings.sort(key=lambda f: (
        0 if hcg.get(f['node_path'], {}).get('evaluation_tier') == 'sympathetic' else 1,
        -f['distance']
    ))
    return findings
```

B2 Kimi prompt (replace `_VERDICT_PROMPT`):

```python
_VERDICT_PROMPT_V2 = """\
You are a senior AML compliance officer doing a regulatory gap analysis.

For each item you are given:
  - The exact legal obligation from the CySEC Consolidated AML Directive
  - The top 3 most semantically relevant sections found in the client policy

Decide: does the policy satisfy this obligation?

Return ONLY a JSON array. One object per item.
SCHEMA: [{"id":1,"verdict":"GAP","severity":"mandatory","missing":"one sentence — what specific element is absent"}]
verdict: GAP or COMPLIANT
severity: mandatory, recommended, or informational
missing: null if COMPLIANT, one sentence if GAP

ITEMS:
{findings_json}
"""
```

### After B1 is built — validate

```powershell
# Run on Capital.com 65-page manual
python obligation_first_evaluator.py --pdf "AML Manual V8.0_Reviewed(Draft).docx.pdf" --config client_config.json --skip-anon

# Compare against XLSX ground truth
python compare_gaps.py
```

Expected outcome: recall improves from 36% to 60-75%. Paraphrase distance problems will limit further gains without a legal-domain embedding model.

**B1 and B2 are independent — either can be done first.**

B1 implementation sketch:
```python
def obligation_sweep(pages: list, config: dict) -> list:
    """
    Query policy collection with each law node.
    Returns one candidate finding per law node, sorted worst-distance-first.
    """
    chroma_client = chromadb.PersistentClient(path=str(DB_PATH))
    policy_col = chroma_client.get_collection(f"policy_{stamp}")
    law_col = chroma_client.get_collection(config['regulated_under'][0])

    # Get all law nodes
    all_nodes = law_col.get(include=['documents', 'metadatas'])
    findings = []

    for doc, meta in zip(all_nodes['documents'], all_nodes['metadatas']):
        results = policy_col.query(query_texts=[doc], n_results=3)
        distances = results['distances'][0]
        best_dist = min(distances)
        findings.append({
            'node_path':    meta.get('path', ''),
            'matched_rule': doc,
            'distance':     round(best_dist, 4),
            'top_sections': [
                {'page': m.get('page_num'), 'text': t, 'distance': round(d, 4)}
                for t, m, d in zip(
                    results['documents'][0],
                    results['metadatas'][0],
                    results['distances'][0]
                )
            ]
        })

    # Sort: worst distance first (most likely gaps go to Kimi first)
    # HCG sympathetic nodes jump to front
    hcg = _load_hcg()
    findings.sort(key=lambda f: (
        0 if hcg.get(f['node_path'], {}).get('evaluation_tier') == 'sympathetic' else 1,
        -f['distance']
    ))
    return findings
```

B2 prompt change (replace `_VERDICT_PROMPT`):
```python
_VERDICT_PROMPT_V2 = """\
You are a senior AML compliance officer doing a regulatory gap analysis.

For each item below you are given:
  - The exact legal obligation from the CySEC Consolidated AML Directive
  - The top 3 most semantically relevant sections found in the client policy

Decide: does the policy satisfy this obligation?

Return ONLY a JSON array. One object per item.
SCHEMA: [{"id":1,"verdict":"GAP","severity":"mandatory","missing":"one sentence — what specific element is absent"}]
verdict: GAP or COMPLIANT
severity: mandatory, recommended, or informational
missing: null if COMPLIANT, one sentence if GAP

ITEMS:
{findings_json}
"""
```

---

## Track A — Implementation Details (unchanged from session 1)

### A1 — Raise EGDR Threshold (2 min)

```python
# In detect_violations(), change:
k = 3 if H > 6.5 else 1
# To:
k = 3 if H > 7.0 else 2 if H > 6.5 else 1
```

### A2 — `--verdict-only` Flag (30 min)

```python
parser.add_argument("--verdict-only", type=str, default=None,
                    help="Path to existing result JSON. Skip to Phase 4b.")

if args.verdict_only:
    with open(args.verdict_only, encoding='utf-8') as f:
        saved = json.load(f)
    findings = saved.get('findings', [])
    verdicts = saved.get('verdicts', [])
    pages = extract_pages(pdf_path)  # needed for policy index
    # jump to Phase 1c, skip 1b/2/3/4
```

Note: `findings` is already saved in result JSON (added in session 1 run). Check before implementing.

### A3 — HCG CRITICAL Escalation (20 min)

In `_update_hcg()`, after saving:
```python
critical_nodes = {n: e for n, e in hcg.items()
                  if e.get('confirmed_gap_weight', 0) >= 0.5}
if critical_nodes:
    print(f"  CRITICAL: {len(critical_nodes)} nodes at weight >= 0.5")
return critical_nodes
```

In `_generate_report()`, add CRITICAL section above KPI bar:
```html
<h2 style="color:#c0392b">CRITICAL — Systemic Gaps</h2>
<p>Confirmed absent across multiple documents. Confidence increases with each run.</p>
<!-- table: node | weight | docs evaluated | last seen -->
```

Nodes currently qualifying (weight ≥ 0.5):
- part_3 §9.1.m — 0.8 — Risk identification
- part_3 §10.4.b — 0.8 — Compliance officer duties
- part_4 §12.4 — 0.7-0.8 — CDD procedures
- part_6 §27 — 0.8 — Sanctions screening
- part_5 §25.3 — 0.8 — Monitoring obligations

### A4 — Fix HCG Counter (5 min)

```python
updated_this_run = set()
for v in verdicts:
    node = get_finding(v).get('node_path', '')
    entry['documents_evaluated'] += (0 if node in updated_this_run else 1)
    updated_this_run.add(node)
```

---

## Ground Truth Validation — Session 2026-04-29

**This section is new. It changes the priority order of Track B. Read before starting the next build session.**

### What was discovered

Two professional human audit documents for the Capital.com (CCSV) AML Manual were found in Downloads:

| File | What it is | Relevance |
|---|---|---|
| `CCSV - AML_KYC.xlsx` | 2025 professional compliance audit of Capital.com by external firm | **Ground truth for the 65-page test PDF** — same company, same document evaluated |
| `Capital Com - AML Health Check 09.02.2022.docx` | 2022 AML Health Check of same company by K. Treppides & Co Ltd | Earlier audit — shows what changed over 3 years |

**Critical point:** The 65-page test PDF (`AML Manual V8.0_Reviewed(Draft).docx.pdf`) is the Capital.com AML Manual. The XLSX is a professional human audit of that exact document with 66 confirmed findings. This is the ground truth the project was missing.

The 141-page test PDF (`1a. AML Manual.docx.pdf`) is **a different company** — PM MTF Ltd, July 2025. The XLSX does not apply to it.

### Comparison methodology

Script: `compare_gaps.py` (created this session, in project root).

Runs Jaccard keyword similarity between system gap descriptions and human audit findings. Results are directional — Jaccard is weak for legal text. Use for structure, not as definitive scoring.

```powershell
cd C:\Users\andre\Desktop\aml_proof
python compare_gaps.py
```

### Results

| Metric | Number |
|---|---|
| Human expert gaps (XLSX) | 66 total |
| — Policy-level (what the manual says) | ~45 |
| — Operational (CRM, client files, practice) | ~21 |
| System CONFIRMED_GAPs | 22 |
| System gaps matched a human finding | 19 |
| System gaps with no human match | 3 |
| **Recall on policy-level gaps** | **16/45 = 36%** |

### Three independently confirmed gaps (strongest validation)

These were found by both the automated system and the human audit team, reading the same document independently:

| System ID | System finding | Human finding (XLSX) |
|---|---|---|
| sys[126] `appendix_5 §1.b` | Policy does not mention original or certified true copies for identity verification | H[51] — "no established procedures for CCSV to accept certified true copies" |
| sys[69] `appendix_4 §2` | Policy does not address higher risk of ML/TF for non-face-to-face transactions | H[26] — EDD for non-face-to-face clients not structured or documented |
| sys[115] `Part V §26.2.c` | Policy does not specify procedures for investigating unusual or suspicious transactions | H[78] — ISR procedure not updated in AML Manual |

Zero contradictions: no case where the human audit said "this is fine" and the system said "gap".

### Why 64% of policy gaps were missed

Every missed policy gap maps to a law node the sliding window never touched. Examples:

| Human gap | Area | Why system missed it |
|---|---|---|
| H[21] Low risk situation factors missing | Low Risk Clients | Law nodes for §63.2 never hit by any window |
| H[22] SDD — PoA not required for low-risk | SDD Measures | §SDD nodes invisible to window |
| H[49] No translation procedures | Translation of docs | Translation obligation nodes never triggered |
| H[54] No sanction list update procedures | Sanctions Policy | Sanctions procedural nodes missed |
| H[55] OFAC SDN list absent | OFAC | OFAC-specific nodes never hit |
| H[82] Training policy not standalone | Training Policy | Training structure nodes missed |

This is the 28% coverage problem made concrete. The obligation-first sweep (Track B, step B1) directly fixes all of these — by querying every law node against the policy, every obligation gets evaluated.

### Operational gaps are permanently out of scope

21 of the 66 human gaps require reviewing actual practice — CRM records, client file samples, staff certificates, backlog counts. A document evaluator cannot detect these. They are a different product (operational audit vs policy compliance check). Do not attempt to cover them.

Examples of operational gaps:
- H[10] Staff AML certifications not current
- H[38] Access rights list incomplete in CRM
- H[63] Client file review backlog due to system bugs
- H[91] CPD renewal monitoring missing
- H[92] CRM client status distorted

### What this means for next session

Track B step B1 (obligation-first sweep) is now the **confirmed priority**. The 36% recall has a clean explanation — every missed gap corresponds to an invisible law node. Building B1 will force evaluation of all 325 nodes including those behind the 29 missed policy gaps.

Target after B1: rerun compare_gaps.py. Expect recall to improve to 60-75% (some gaps will still be missed due to paraphrase distance problems; obligation-first does not fully solve paraphrase).

---

## Verified Results (as of 2026-04-28)

### 65-page doc — `AML Manual V8.0_Reviewed(Draft).docx.pdf`

**Best run (163428) — 3rd run:**
- 65 pages → 185 raw hits → 146 unique findings
- Kimi: 82 GAPs, 64 COMPLIANT
- Gap dedup: 19 DUPLICATE
- Cross-check: **22 CONFIRMED_GAP | 5 MANUAL_REVIEW | 1 LIKELY_COMPLIANT | 35 LOW_CONFIDENCE_NOISE**
- Precision on CONFIRMED_GAP: ~82% (3-4 false positives among 22)

**Verified CONFIRMED real gaps:**

| ID | Gap | Notes |
|---|---|---|
| id=24 | Joint Guidelines (EBA/ESMA) not referenced | Systemic — both docs |
| id=27 | goAML/MOKAS electronic submission absent | 65-page only |
| id=39 | Internal audit annual AML review missing | Systemic — both docs |
| id=60/61 | Financial sanctions + EU CFSP list absent | Systemic — both docs |
| id=99 | High-risk customer ongoing monitoring absent | Both docs |
| id=127 | Telephone verification procedure absent | Systemic — both docs |
| id=132 | Training departments not specified | Both docs |

**Verified LIKELY_COMPLIANT:**
- id=111 → Suspicious transactions → page 46, dist=0.442 ✓

### 141-page doc — `1a. AML Manual.docx.pdf`

**Best run (161714) — 2nd run:**
- 141 pages → 336 findings → 196 Kimi GAPs
- Gap dedup: 61 DUPLICATE
- Cross-check: **40 CONFIRMED_GAP | 17 MANUAL_REVIEW | 5 LIKELY_COMPLIANT | 73 LOW_CONFIDENCE_NOISE**

**Verified LIKELY_COMPLIANT:**
- id=48/266 → Suspicious transaction examples → page 109 ✓
- id=92 → AML training → page 36 ✓
- id=124/136 → Risk-based approach → page 49 ✓
- id=177 → Beneficial owner verification → page 72, dist=0.27 ✓

**Notable CONFIRMED gaps:**
- id=184 → Trust structure — systemic
- id=201 → Simplified CDD qualifying criteria — systemic
- id=210 → Telephone verification — systemic

### Cross-Document Systemic Gaps

| Gap | CySEC Obligation | HCG weight |
|---|---|---|
| Joint Guidelines (EBA/ESMA) not referenced | Mandatory reference | 0.8 |
| Telephone verification procedure absent | Customer contact verification | 0.8 |
| Trust deed / trust structure procedures | Beneficial ownership for trusts | 0.7+ |
| Simplified CDD — no qualifying criteria | Must specify when simplified applies | 0.7+ |
| Financial sanctions / EU CFSP / UN checks | Mandatory screening | 0.8 |

---

## HCG State (as of 2026-04-28)

15 nodes tracked. 5 at weight ≥ 0.5:

| Node | Weight | Obligation area |
|---|---|---|
| part_3 §9.1.m | 0.8 | Risk identification |
| part_3 §10.4.b | 0.8 | Compliance officer duties |
| part_4 §12.4 | 0.7-0.8 | CDD procedures |
| part_6 §27 | 0.8 | Sanctions screening |
| part_5 §25.3 | 0.8 | Monitoring obligations |

Note: HCG weights are based on 91 observed nodes only (sliding window limitation). The 234 unobserved nodes have zero history — not confirmed compliant, not confirmed absent. Obligation-first sweep will begin populating these.

---

## Architecture Decisions — Closed

| Decision | Reason |
|---|---|
| No BM25 silence gate | Fails on paraphrased compliance text — silent false negatives |
| No MinHash window dedup | Misses new topics introduced mid-overlap |
| No auto-threshold compliance resolution | all-MiniLM-L6-v2 not trained on legal domain. Distance ≠ legal satisfaction. Verified LIKELY_COMPLIANT at dist=0.442 — a 0.30 auto-threshold catches nothing useful. Kimi decides. |
| No document structure parsing | pdfplumber gives layout not semantics. Every doc formatted differently. Cannot reliably detect section boundaries without LLM. LLM on CPU is 180s/page. Not viable. |
| No law-graph tree pruning | False negative risk. Law hierarchy does not map to document structure. A Part-level absent signal does not imply all child obligations absent — document may cover children in scattered sections. |
| No coverage map keyed on document hash | Wrong use case. Production = revised documents = full re-evaluation. Same-document caching is demo-prep only (--verdict-only handles that). |
| Obligation-first over sliding window | 100% law graph coverage vs 28%. Sliding window touches 91/325 nodes, generates 55% noise. |
| HCG as prioritization signal not gate | Insufficient data for automated gating. Tiers inform evaluation ORDER. They do not auto-resolve verdicts. |
| BATCH_SIZE=10 | 55+ findings in one call = truncated JSON |
| ASCII-encode prompts | Raw PDF unicode breaks Kimi's JSON output |
| 8s sleep between batches | 429 rate limit without it |
| moonshot.ai not moonshot.cn | `.cn` returns 401 even with valid key |
| Plain set not mmh3+bitarray for bigrams | CPU machine — set has zero false positives |
| spaCy en_core_web_sm not _trf | CPU machine — _trf needs GPU |
| LLM as narrator not driver | Libet Inversion: ChromaDB is thalamic gate, Kimi narrates |
| Greedy selection for executive summary | Set cover — minimum gaps, maximum regulatory exposure |
| Cross-check threshold 0.55 for CONFIRMED_GAP | Tuned on 65-page manual verification |

---

## Known Issues

### For PoC (fix before evaluation — Track A)
1. **EGDR threshold too low** — 43% noise. Fix: 6.5 → 7.0 (A1, 2 min).
2. **HCG documents_evaluated bug** — counts per verdict not per run (A4, 5 min).
3. **HCG CRITICAL escalation not in report** — 5 nodes qualify (A3, 20 min).

### Architecture (Track B — next build cycle)
4. **28% recall** — sliding window misses 234/325 law nodes. Fix: obligation-first sweep (B1).
5. **Kimi context too thin** — currently gets policy snippet only. Fix: obligation text + top-3 sections (B2).
6. **HCG tier field missing** — evaluation ordering not implemented (B3).

### Post-workstation
7. **--skip-anon required** — spaCy anonymizer blocked until GPU.
8. **Cross-check threshold 0.55 may need +0.05** — one false CONFIRMED_GAP observed in 141-page doc.
9. **Paraphrase detection gap** — operational policy language vs regulatory law language creates semantic distance even when compliant. Needs more client data to characterize.

### Future
10. **Multi-jurisdiction** — EU AMLD5/6, FATF. Requires legal expert equivalence mapping between jurisdictions before automation.
11. **HCG auto-resolution thresholds** — viable after ~10 clients of data. Not before.
12. **Parallel Kimi batches** — unblocked when GPU workstation removes rate limit constraint.

---

## How To Run (current — CPU machine)

```powershell
$env:KIMI_API_KEY = "YOUR_KIMI_API_KEY"   # load from .env — never commit plaintext
cd C:\Users\andre\Desktop\aml_proof
python rag_evaluator.py --pdf "AML Manual V8.0_Reviewed(Draft).docx.pdf" --config client_config.json --skip-anon
python rag_evaluator.py --pdf "1a. AML Manual.docx.pdf" --config client_config.json --skip-anon
```

```powershell
# View reports
cd C:\Users\andre\Desktop\aml_proof\evaluation_results
python -m http.server 8080
# Open: http://localhost:8080
```

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
├── rag_evaluator.py         <- Main pipeline (current — sliding window)
├── client_config.json       <- Client/jurisdiction config
├── requirements.txt         <- Dependencies
├── vectorize.py             <- Run only when adding new law domain
├── assess_pdf.py            <- Quick test tool
├── .env                     <- API keys (gitignored)
└── nextsession.md           <- This file
```

**Planned new files (Track B):**
```
├── pipeline/
│   ├── extractor.py    <- PDF → pages (Phase 1a)
│   ├── sweeper.py      <- Obligation-first sweep (Phase 2, replaces sliding window)
│   ├── verdict.py      <- Kimi caller with richer context (Phase 4)
│   ├── graph.py        <- HCG with tier support (Phase 4c)
│   └── reporter.py     <- HTML report (Phase 5)
└── coverage/
    └── {client_id}.json <- Per-client obligation coverage map
```

---

## Infrastructure

### API Keys (`.env` — gitignored)
```
KIMI_API_KEY=<your-key-here>   # get from platform.moonshot.ai — never commit plaintext
```
Account: platform.moonshot.ai — check credit balance before long runs.
Obligation-first sweep = 33 batches per document = higher cost than current. Budget accordingly.

### Python environment
```powershell
pip install -r requirements.txt
```

### Ollama (skip on current machine)
```powershell
# DO NOT use on X1 Carbon — 180s/page timeout
# For future GPU workstation only
```

### Reference papers
- `C:\Users\andre\Desktop\$\Biological_Governance_Position_Paper_v2.docx` — full Libet Inversion framework
- `C:\Users\andre\Desktop\$\Biological_Governance_Concept_Note_DRAFT.docx` — original concept note
- Singh & Yu (2025) — Kairos: Validation-Gated Hebbian Learning (cited in position paper) — directly relevant to HCG auto-resolution design
- Fisher (2025) — Neural Graph Memory for Autonomous Agent Systems (cited in position paper)
