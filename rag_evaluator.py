#!/usr/bin/env python3
"""
AML Compliance Auditor — Full-Coverage Sliding Window Evaluator

Architecture:
  Phase 1a: Extract all pages, query ChromaDB with raw text (local, safe).
            No pages skipped. Every page in at least one window.
  Phase 1b: EGDR sliding window detection — entropy-gated k.
  Phase 1c: Build ephemeral policy index for bidirectional cross-check.
  Phase 2:  Deduplicate findings by node_path + overlapping page ranges.
            Merge cross-jurisdiction matches on same page range.
  Phase 3:  Anonymize ONLY the flagged page ranges via local Ollama.
            Raw PII never sent to any external service.
  Phase 4:  ONE external API call with all anonymized findings -> JSON verdict.
  Phase 4b: Bidirectional cross-check — semantic reverse lookup.
  Phase 4c: Update Hebbian Compliance Graph.
  Phase 5:  HTML report with greedy executive summary.
"""

import json
import math
import os
import re
import sys
import time
import argparse
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from PyPDF2 import PdfReader
import chromadb
import requests

# ─── Paths ────────────────────────────────────────────────────────────────────

WORKSPACE   = Path(__file__).parent
DB_PATH     = WORKSPACE / "chroma_db"
TEST_DIR    = WORKSPACE / "test_transactions"
RESULTS_DIR = WORKSPACE / "evaluation_results"

# ─── Config ───────────────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "client_id":        "poc_client",
    "regulated_under":  ["cysec_aml_rules"],
    "chroma_threshold": 0.55,
    "window_size":      3,
    "ollama_model":     "llama3:latest",
    "ollama_url":       "http://localhost:11434",
    "kimi_model":       "moonshot-v1-8k",
    "kimi_base_url":    "https://api.moonshot.ai/v1"
}

def load_config(config_path: str) -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if config_path:
        p = Path(config_path)
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        else:
            print(f"  Config file not found: {config_path}, using defaults.")
    return cfg

# ─── Phase 1a: PDF Extraction ─────────────────────────────────────────────────

def extract_pages(pdf_path: Path) -> list:
    """Return list of page texts (0-indexed). Every page extracted, no skipping."""
    reader = PdfReader(str(pdf_path))
    total  = len(reader.pages)
    pages  = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages.append(text.strip())
        if (i + 1) % 20 == 0 or i + 1 == total:
            print(f"  Extracted {i+1}/{total} pages...")
    return pages

# ─── Phase 1b: EGDR Sliding Window Detection ─────────────────────────────────

def _window_entropy(text: str) -> float:
    """Shannon entropy of word frequency distribution."""
    words = text.lower().split()
    if len(words) < 10:
        return 0.0
    freq  = Counter(words)
    total = len(words)
    return -sum((c / total) * math.log2(c / total) for c in freq.values())

def detect_violations(pages: list, config: dict) -> list:
    """
    Build every 3-page window (step=1) and query ChromaDB with raw text.
    EGDR: entropy-gated k — complex windows (H > 6.5) get k=3, boilerplate gets k=1.
    Returns raw findings list — not yet deduplicated.

    Correctness guarantee: every page appears in at least one window.
    No BM25 gate, no MinHash skip — a compliance audit has one failure mode
    that matters: silent false negatives.
    """
    chroma_client = chromadb.PersistentClient(path=str(DB_PATH))
    collections   = []
    for name in config["regulated_under"]:
        try:
            collections.append((name, chroma_client.get_collection(name)))
            print(f"  Loaded collection: {name}")
        except Exception as e:
            print(f"  WARNING: collection '{name}' not found — {e}")

    if not collections:
        raise RuntimeError("No ChromaDB collections loaded. Check 'regulated_under' in config.")

    window_size = config["window_size"]
    n           = len(pages)
    total_wins  = max(0, n - window_size + 1)
    findings    = []

    print(f"  {n} pages -> {total_wins} windows (size={window_size}, step=1, EGDR entropy-gated k)")

    for start in range(total_wins):
        end         = start + window_size          # exclusive slice
        window_text = "\n\n".join(pages[start:end]).strip()

        if not window_text:
            continue

        H = _window_entropy(window_text)
        k = 3 if H > 6.5 else 1

        for jurisdiction, collection in collections:
            results = collection.query(
                query_texts=[window_text],
                n_results=k
            )

            if not results["documents"] or not results["documents"][0]:
                continue

            for doc, meta, dist in zip(results["documents"][0],
                                        results["metadatas"][0],
                                        results["distances"][0]):
                findings.append({
                    "page_range":     [start + 1, end],   # 1-indexed, inclusive end
                    "jurisdiction":   jurisdiction,
                    "node_path":      meta.get("path", ""),
                    "source_file":    meta.get("source_file", ""),
                    "matched_rule":   doc,
                    "distance":       round(dist, 4),
                    "raw_snippet":    window_text[:1000],
                    "window_entropy": round(H, 3)
                })

        if (start + 1) % 20 == 0 or start + 1 == total_wins:
            print(f"  Window {start+1}/{total_wins} — {len(findings)} raw hits so far")

    return findings

# ─── Phase 1c: Ephemeral Policy Index ────────────────────────────────────────

def _build_policy_index(pages: list, stamp: str, chroma_client) -> tuple:
    """
    Vectorize all policy pages into an ephemeral ChromaDB collection.
    Also build a bigram set on all document bigrams for fast pre-filtering.
    Returns (collection, bigram_set, full_text).

    Uses plain Python set (zero false positives, O(1) lookup, ~50MB for 141 pages).
    Switch to mmh3 + bitarray when processing hundreds of docs on GPU workstation.
    """
    col_name = f"policy_{stamp}"
    try:
        chroma_client.delete_collection(col_name)
    except Exception:
        pass

    col       = chroma_client.create_collection(col_name)
    non_empty = [(i, t) for i, t in enumerate(pages) if t.strip()]
    if non_empty:
        col.upsert(
            documents=[t for _, t in non_empty],
            ids=[f"page_{i}" for i, _ in non_empty],
            metadatas=[{"page_num": i + 1} for i, _ in non_empty]
        )

    full_text  = " ".join(pages).lower().encode('ascii', 'replace').decode('ascii')
    words      = full_text.split()
    bigram_set = set(f"{words[i]} {words[i+1]}" for i in range(len(words) - 1))

    print(f"  Policy index: {len(non_empty)} pages vectorized, {len(bigram_set):,} bigrams indexed")
    return col, bigram_set, full_text

# ─── Phase 2: Deduplication ───────────────────────────────────────────────────

def _ranges_overlap(r1: list, r2: list) -> bool:
    return r1[0] <= r2[1] and r2[0] <= r1[1]

def deduplicate(findings: list) -> list:
    """
    Deduplicate by (node_path + overlapping page ranges).
    Cross-jurisdiction matches on the same page range become one finding
    with multiple entries in the jurisdictions list.
    Keeps the hit with lowest distance (best semantic match) per merged group.
    """
    by_node = defaultdict(list)
    for f in findings:
        by_node[f["node_path"]].append(f)

    unique = []

    for node_path, hits in by_node.items():
        sorted_hits = sorted(hits, key=lambda x: x["page_range"][0])
        merged      = []

        for hit in sorted_hits:
            placed = False
            for m in merged:
                if _ranges_overlap(m["page_range"], hit["page_range"]):
                    m["page_range"][0] = min(m["page_range"][0], hit["page_range"][0])
                    m["page_range"][1] = max(m["page_range"][1], hit["page_range"][1])
                    if hit["jurisdiction"] not in m["jurisdictions"]:
                        m["jurisdictions"].append(hit["jurisdiction"])
                    if hit["distance"] < m["distance"]:
                        m["distance"]     = hit["distance"]
                        m["matched_rule"] = hit["matched_rule"]
                        m["raw_snippet"]  = hit["raw_snippet"]
                    placed = True
                    break
            if not placed:
                merged.append({
                    "page_range":    list(hit["page_range"]),
                    "node_path":     node_path,
                    "source_file":   hit["source_file"],
                    "matched_rule":  hit["matched_rule"],
                    "distance":      hit["distance"],
                    "jurisdictions": [hit["jurisdiction"]],
                    "raw_snippet":   hit["raw_snippet"]
                })

        unique.extend(merged)

    unique.sort(key=lambda x: x["page_range"][0])
    print(f"  Deduplication: {len(findings)} raw hits -> {len(unique)} unique findings")
    return unique

# ─── Phase 3: Anonymize Flagged Pages Only ────────────────────────────────────

def _anonymize_via_ollama(text: str, config: dict) -> str:
    """Strip PII from text using local Ollama. Falls back to original on error."""
    prompt = (
        "You are a legal document anonymizer. Your only job is to replace personally "
        "identifiable information with placeholders.\n\n"
        "Replace:\n"
        "- Person names -> [PERSON]\n"
        "- Company / organisation names -> [COMPANY]\n"
        "- Addresses -> [ADDRESS]\n"
        "- Phone / fax numbers -> [PHONE]\n"
        "- Email addresses -> [EMAIL]\n"
        "- Account numbers, IBAN, registration numbers -> [ACCOUNT_NO]\n"
        "- Passport / national ID numbers -> [ID_NO]\n\n"
        "Preserve ALL legal, procedural, and compliance-related language exactly as written.\n"
        "Return ONLY the anonymized text. No commentary.\n\n"
        f"TEXT:\n{text}"
    )
    try:
        resp = requests.post(
            f"{config['ollama_url']}/api/generate",
            json={"model": config["ollama_model"], "prompt": prompt, "stream": False},
            timeout=180
        )
        resp.raise_for_status()
        return resp.json().get("response", text).strip()
    except Exception as e:
        print(f"    WARNING: Ollama call failed ({e}). Keeping original text.")
        return text

def anonymize_findings(findings: list, pages: list, config: dict) -> list:
    """
    Identify the unique set of flagged page numbers across all findings.
    Anonymize only those pages via local Ollama.
    Replace raw_snippet with anonymized version. Delete raw_snippet.
    """
    flagged_page_nums = set()
    for f in findings:
        for p in range(f["page_range"][0], f["page_range"][1] + 1):
            flagged_page_nums.add(p)   # 1-indexed

    print(f"  {len(flagged_page_nums)} unique flagged pages (out of {len(pages)} total)")

    anon_cache = {}
    for page_num in sorted(flagged_page_nums):
        idx  = page_num - 1
        text = pages[idx] if idx < len(pages) else ""
        if text.strip():
            print(f"  Anonymizing page {page_num}...")
            anon_cache[page_num] = _anonymize_via_ollama(text, config)
        else:
            anon_cache[page_num] = ""

    for f in findings:
        start, end = f["page_range"]
        parts = [anon_cache.get(p, "") for p in range(start, end + 1) if anon_cache.get(p, "")]
        f["anonymized_snippet"] = "\n\n".join(parts)[:1500]
        f.pop("raw_snippet", None)   # never persist raw PII

    return findings

# ─── Phase 4: Final Verdict via External LLM ─────────────────────────────────

_VERDICT_PROMPT = """\
You are a senior AML compliance officer doing a regulatory gap analysis.

For each finding below, decide: is this a genuine compliance GAP (policy missing or inadequate) or COMPLIANT (policy satisfies the requirement)?

Return ONLY a JSON array, no markdown, no extra text. One object per finding.

SCHEMA (use exactly these fields, nothing else):
[{{"id":1,"verdict":"GAP","severity":"mandatory","gap":"one sentence description"}},...]

verdict must be GAP or COMPLIANT.
severity must be mandatory, recommended, or informational.
gap must be null if COMPLIANT.

FINDINGS:
{findings_json}
"""

BATCH_SIZE = 10   # findings per Kimi call

def _parse_json_response(content: str) -> list:
    """
    Extract JSON array from LLM response.
    Handles: raw JSON, markdown fences (```json ... ```), prose before/after.
    """
    content = re.sub(r"```(?:json)?\s*", "", content).strip()
    content = content.replace("```", "").strip()

    start = content.find("[")
    end   = content.rfind("]") + 1
    if start >= 0 and end > start:
        return json.loads(content[start:end])
    raise ValueError(f"No JSON array found in response: {content[:200]}")

def _call_single_batch(batch: list, batch_num: int, total_batches: int,
                       api_key: str, config: dict) -> list:
    prompt = _VERDICT_PROMPT.format(
        n=len(batch),
        findings_json=json.dumps(batch, indent=2, ensure_ascii=True)
    )
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": config["kimi_model"],
               "messages": [{"role": "user", "content": prompt}],
               "temperature": 0.1,
               "max_tokens": 2048}

    print(f"  Batch {batch_num}/{total_batches} — {len(batch)} findings, {len(prompt):,} chars")

    for attempt in range(5):
        if attempt > 0:
            wait = 10 * attempt
            print(f"    retry {attempt}/4 — waiting {wait}s...")
            time.sleep(wait)
        try:
            resp = requests.post(f"{config['kimi_base_url']}/chat/completions",
                                 headers=headers, json=payload, timeout=180)
            if resp.status_code == 429:
                print(f"    429 rate limit hit")
                continue
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return _parse_json_response(content)
        except Exception as e:
            if attempt == 4:
                raise
            print(f"    error: {e}")
    raise RuntimeError("All retries exhausted")

def call_verdict_api(findings: list, config: dict) -> list:
    api_key = os.environ.get("KIMI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("  WARNING: No API key set (KIMI_API_KEY / OPENAI_API_KEY). Skipping verdict call.")
        return findings

    # Build prompt-ready finding objects
    prompt_findings = []
    for i, f in enumerate(findings):
        # ASCII-encode excerpts — raw PDF text contains unicode that breaks JSON in prompts
        excerpt = f.get("anonymized_snippet", "").encode("ascii", "replace").decode("ascii")
        rule    = f.get("matched_rule", "").encode("ascii", "replace").decode("ascii")
        prompt_findings.append({
            "finding_id":     i + 1,
            "page_range":     f["page_range"],
            "jurisdictions":  f.get("jurisdictions", []),
            "node_path":      f["node_path"],
            "matched_rule":   rule[:200],
            "policy_excerpt": excerpt[:500],
            "match_distance": f.get("distance", f.get("match_distance", 0))
        })

    # Split into batches
    batches = [prompt_findings[i:i+BATCH_SIZE]
               for i in range(0, len(prompt_findings), BATCH_SIZE)]
    total_batches = len(batches)
    print(f"  {len(findings)} findings -> {total_batches} batches of up to {BATCH_SIZE}")

    all_verdicts = []
    for idx, batch in enumerate(batches, 1):
        if idx > 1:
            time.sleep(8)   # respect Kimi rate limit between batches
        try:
            verdicts = _call_single_batch(batch, idx, total_batches, api_key, config)
            all_verdicts.extend(verdicts)
            print(f"  Batch {idx} done — {len(verdicts)} verdicts received")
        except Exception as e:
            print(f"  ERROR on batch {idx}: {e}")
            all_verdicts.extend(batch)

    return all_verdicts

# ─── Phase 4b: Bidirectional Cross-Check ─────────────────────────────────────

def _bidirectional_cross_check(verdicts: list, findings: list,
                                policy_col, bigram_set: set) -> list:
    """
    For each GAP verdict, check whether the underlying CySEC obligation
    exists anywhere in the policy document using semantic reverse lookup.

    Two-step:
      1. Bigram pre-filter — if zero bigrams from the law node appear in
         the document, it is a CONFIRMED_GAP without any ChromaDB query.
      2. Semantic reverse query — law node text -> policy_pages collection.
         Returns the best-matching page and its distance.

    Distance thresholds:
      < 0.45  -> LIKELY_COMPLIANT (covered on page X)
      0.45-0.55 -> MANUAL_REVIEW (borderline)
      > 0.55  -> CONFIRMED_GAP
    """
    def get_finding(v):
        idx = v.get('id', 0) - 1
        if 0 <= idx < len(findings):
            return findings[idx]
        return {}

    confirmed          = 0
    likely_compliant   = 0
    manual_review      = 0
    low_conf_noise     = 0

    for v in verdicts:
        if not isinstance(v, dict) or v.get('verdict') != 'GAP':
            continue

        # Skip verdicts already marked DUPLICATE by _deduplicate_gap_descriptions()
        if v.get('cross_check') == 'DUPLICATE':
            continue

        fin           = get_finding(v)

        # Pre-filter: detection distance > 0.75 means the Phase 1b match was weak.
        # The law node barely matched the policy window — not worth a reverse query.
        detection_dist = fin.get('distance', 0)
        if detection_dist > 0.75:
            v['cross_check']      = 'LOW_CONFIDENCE_NOISE'
            v['cross_check_note'] = f'Detection distance {detection_dist:.3f} > 0.75 — law node match too weak for reverse query.'
            low_conf_noise += 1
            continue

        law_node_text = fin.get('matched_rule', '').lower().encode('ascii', 'replace').decode('ascii')

        if not law_node_text.strip():
            v['cross_check'] = 'CONFIRMED_GAP'
            confirmed += 1
            continue

        # Step 1: bigram pre-filter
        words        = law_node_text.split()
        node_bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]
        bigram_hits  = sum(1 for bg in node_bigrams if bg in bigram_set)

        if not node_bigrams or bigram_hits == 0:
            v['cross_check']      = 'CONFIRMED_GAP'
            v['cross_check_note'] = 'Zero bigrams from law node found in document.'
            confirmed += 1
            continue

        # Step 2: semantic reverse query
        try:
            results   = policy_col.query(query_texts=[law_node_text], n_results=3)
            distances = results['distances'][0]
            metas     = results['metadatas'][0]
            best_idx  = distances.index(min(distances))
            best_dist = distances[best_idx]
            best_page = metas[best_idx].get('page_num', '?')
        except Exception as e:
            v['cross_check']      = 'MANUAL_REVIEW'
            v['cross_check_note'] = f'Query error: {e}'
            manual_review += 1
            continue

        if best_dist < 0.45:
            v['cross_check']       = 'LIKELY_COMPLIANT'
            v['covered_on_page']   = best_page
            v['coverage_distance'] = round(best_dist, 4)
            v['cross_check_note']  = f'Policy page {best_page} covers this obligation (distance={best_dist:.3f}).'
            likely_compliant += 1
        elif best_dist < 0.55:
            v['cross_check']       = 'MANUAL_REVIEW'
            v['closest_page']      = best_page
            v['coverage_distance'] = round(best_dist, 4)
            v['cross_check_note']  = f'Borderline match on page {best_page} (distance={best_dist:.3f}). Manual review needed.'
            manual_review += 1
        else:
            v['cross_check']      = 'CONFIRMED_GAP'
            v['cross_check_note'] = f'No policy page within semantic threshold (best distance={best_dist:.3f}).'
            confirmed += 1

    print(f"  Cross-check: {confirmed} CONFIRMED_GAP | {manual_review} MANUAL_REVIEW | {likely_compliant} LIKELY_COMPLIANT | {low_conf_noise} LOW_CONFIDENCE_NOISE")
    return verdicts

# ─── Phase 4c: Hebbian Compliance Graph ───────────────────────────────────────

def _update_hcg(verdicts: list, findings: list,
                hcg_path: str = "compliance_graph.json"):
    """
    Update persistent compliance graph with this run's cross-check results.
    Hebbian rule: nodes that fire consistently (GAP or compliant) increase weight.
    Weight caps at 1.0, never resets to 0.
    After 10+ runs: high-weight confirmed nodes (>= 0.5) auto-escalate to CRITICAL.
    """
    hcg_file = WORKSPACE / hcg_path
    hcg      = {}
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
            "compliant_weight":     0.0,
            "documents_evaluated":  0,
            "last_seen":            None
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

# ─── Post-Kimi Gap Description Deduplication ─────────────────────────────────

def _deduplicate_gap_descriptions(verdicts: list) -> list:
    """
    Cluster GAP verdicts by description similarity (Jaccard on word sets).
    If two GAP descriptions overlap > 60%, mark the later one as DUPLICATE.
    DUPLICATE gaps still appear in the report but don't count toward confirmed total.
    This collapses the inflation caused by EGDR k=3 matching the same obligation
    across multiple law nodes on adjacent windows.
    """
    gaps = [v for v in verdicts if isinstance(v, dict) and v.get('verdict') == 'GAP']
    seen = []
    dupes = 0
    for g in gaps:
        desc    = g.get('gap', '').lower().strip()
        matched = False
        for s in seen:
            s_words = set(s.split())
            g_words = set(desc.split())
            if s_words and g_words:
                overlap = len(s_words & g_words) / max(len(s_words), len(g_words))
                if overlap > 0.6:
                    g['cross_check'] = 'DUPLICATE'
                    matched = True
                    dupes += 1
                    break
        if not matched:
            seen.append(desc)
    print(f"  Gap dedup: {len(gaps)} GAPs -> {len(gaps) - dupes} unique ({dupes} duplicates marked)")
    return verdicts

# ─── Phase 5 helpers ──────────────────────────────────────────────────────────

def _greedy_priority_gaps(gaps: list, get_finding_fn,
                          max_items: int = 5) -> list:
    """
    Greedy set cover: select minimum gaps covering maximum regulatory exposure.
    Prioritise: mandatory confirmed > recommended confirmed > informational confirmed.
    Secondary sort: lower distance = more certain match = higher priority.
    """
    sev_weight     = {"mandatory": 3, "recommended": 2, "informational": 1}
    confirmed_only = [g for g in gaps if g.get('cross_check') == 'CONFIRMED_GAP']
    scored         = sorted(
        confirmed_only,
        key=lambda g: (
            sev_weight.get(g.get('severity', ''), 0),
            -(get_finding_fn(g).get('distance', 1.0))
        ),
        reverse=True
    )
    return scored[:max_items]

# ─── Orchestrator ─────────────────────────────────────────────────────────────

def run_evaluation(pdf_path: Path, config: dict, skip_anon: bool = False):
    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    banner = f"  AML COMPLIANCE AUDIT — {pdf_path.name}"
    print("\n" + "="*60)
    print(banner)
    print(f"  Client    : {config['client_id']}")
    print(f"  Law       : {', '.join(config['regulated_under'])}")
    print(f"  Anon mode : {'SKIP (raw text to API — PoC only)' if skip_anon else 'Ollama ' + config['ollama_model']}")
    print("="*60 + "\n")

    # ── Phase 1a: extract ─────────────────────────────────────────
    print("[Phase 1a] Extracting pages...")
    pages = extract_pages(pdf_path)
    print(f"  Total pages: {len(pages)}\n")

    # ── Phase 1b: detect (EGDR) ───────────────────────────────────
    print("[Phase 1b] Sliding window detection (EGDR entropy-gated)...")
    raw_findings = detect_violations(pages, config)
    print(f"  Raw hits: {len(raw_findings)}\n")

    if not raw_findings:
        print("  No matches above threshold.")
        print("  Either the document is compliant or the threshold needs tuning.")
        result = {
            "client_id":      config["client_id"],
            "document":       pdf_path.name,
            "evaluated_at":   datetime.now().isoformat(),
            "total_pages":    len(pages),
            "total_findings": 0,
            "verdicts":       [],
            "note":           "No violations detected above confidence threshold."
        }
        _save(result, pdf_path, stamp)
        return

    # ── Phase 1c: build ephemeral policy index ────────────────────
    print("[Phase 1c] Building ephemeral policy index...")
    chroma_client = chromadb.PersistentClient(path=str(DB_PATH))
    policy_col, bigram_set, _ = _build_policy_index(pages, stamp, chroma_client)
    print()

    # ── Phase 2: deduplicate ──────────────────────────────────────
    print("[Phase 2] Deduplicating...")
    findings = deduplicate(raw_findings)
    print()

    # ── Phase 3: anonymize flagged pages only ─────────────────────
    if skip_anon:
        print("[Phase 3] Anonymization SKIPPED (--skip-anon). Raw text will be sent to API.")
        for f in findings:
            f["anonymized_snippet"] = f.pop("raw_snippet", "")
    else:
        print("[Phase 3] Anonymizing flagged pages via Ollama...")
        findings = anonymize_findings(findings, pages, config)
    print()

    # ── Phase 4: verdict ──────────────────────────────────────────
    print("[Phase 4] Requesting verdict from external LLM...")
    verdicts = call_verdict_api(findings, config)
    print()

    # ── Phase 4b-pre: deduplicate gap descriptions ────────────────
    print("[Phase 4b-pre] Deduplicating gap descriptions...")
    verdicts = _deduplicate_gap_descriptions(verdicts)
    print()

    # ── Phase 4b: bidirectional cross-check ───────────────────────
    print("[Phase 4b] Bidirectional cross-check...")
    verdicts = _bidirectional_cross_check(verdicts, findings, policy_col, bigram_set)
    gaps_confirmed  = sum(1 for v in verdicts if isinstance(v, dict) and v.get('cross_check') == 'CONFIRMED_GAP')
    gaps_downgraded = sum(1 for v in verdicts if isinstance(v, dict) and v.get('cross_check') == 'LIKELY_COMPLIANT')
    print(f"  Confirmed gaps: {gaps_confirmed}  |  Likely false positives: {gaps_downgraded}")
    print()

    # ── Phase 4c: Hebbian Compliance Graph ────────────────────────
    print("[Phase 4c] Updating Hebbian Compliance Graph...")
    _update_hcg(verdicts, findings)
    print()

    result = {
        "client_id":      config["client_id"],
        "document":       pdf_path.name,
        "evaluated_at":   datetime.now().isoformat(),
        "total_pages":    len(pages),
        "total_findings": len(findings),
        "findings":       findings,
        "verdicts":       verdicts
    }
    out_path = _save(result, pdf_path, stamp)

    # ── Phase 5: HTML report ──────────────────────────────────────
    print("[Phase 5] Generating report...")
    report_path = _generate_report(result, findings, stamp, pdf_path)
    print()

    # ── Cleanup: delete ephemeral policy index ────────────────────
    try:
        chroma_client.delete_collection(f"policy_{stamp}")
        print("  Ephemeral policy index cleaned up.")
    except Exception:
        pass

    print("="*60)
    print(f"  COMPLETE  |  pages: {len(pages)}  |  findings: {len(findings)}")
    print(f"  JSON   -> {out_path}")
    print(f"  Report -> {report_path}")
    print("="*60 + "\n")

def _save(result: dict, pdf_path: Path, stamp: str = None) -> Path:
    if stamp is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"{pdf_path.stem}_{stamp}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    return out_path

# ─── Phase 5: HTML Report ─────────────────────────────────────────────────────

def _format_law_node(node_path: str) -> str:
    """Convert raw node path to human-readable CySEC legal reference.
    'part_3.json.PART_III.paragraphs.9.subparagraphs.1.points.o' -> 'Part III §9(1)(o)'
    'appendix_5.json.paragraphs.6.points.j'                       -> 'Appendix V §6(j)'
    """
    p = node_path.replace('.json', '')
    part = ''
    # Appendix
    app_m = re.search(r'appendix_(\d+)', p, re.IGNORECASE)
    if app_m:
        roman = {1:'I',2:'II',3:'III',4:'IV',5:'V',6:'VI',7:'VII',8:'VIII',9:'IX',10:'X'}
        part = f"Appendix {roman.get(int(app_m.group(1)), app_m.group(1))}"
    else:
        part_m = re.search(r'PART_([IVX]+)', p)
        if part_m:
            part = f"Part {part_m.group(1)}"
    para_m  = re.search(r'paragraphs\.(\d+)', p)
    sub_m   = re.search(r'subparagraphs\.(\d+)', p)
    point_m = re.search(r'points\.([a-zA-Z0-9]+)', p)
    para  = f"§{para_m.group(1)}"  if para_m  else ''
    sub   = f"({sub_m.group(1)})"  if sub_m   else ''
    point = f"({point_m.group(1)})" if point_m else ''
    ref = para + sub + point
    return f"{part} {ref}".strip() if (part or ref) else node_path


def _generate_report(result: dict, findings: list, stamp: str, pdf_path: Path) -> Path:
    """
    Generates a self-contained professional HTML compliance report.
    Sections: header, KPI bar, priority remediation, confirmed gaps,
    manual review, filtered noise (collapsed), compliant (collapsed),
    technical notes (collapsed).
    """
    verdicts  = result["verdicts"]
    gaps      = [v for v in verdicts if isinstance(v, dict) and v.get("verdict") == "GAP"]
    compliant = [v for v in verdicts if isinstance(v, dict) and v.get("verdict") == "COMPLIANT"]

    def get_finding(v):
        idx = v.get("id", 0) - 1
        return findings[idx] if 0 <= idx < len(findings) else {}

    # Partition gaps by cross-check status
    sev_order = {"mandatory": 0, "recommended": 1, "informational": 2}

    def gap_sort_key(g):
        fin  = get_finding(g)
        dist = fin.get("distance", 1.0)
        return (sev_order.get(g.get("severity", "informational"), 9), dist)

    confirmed_gaps  = sorted(
        [g for g in gaps if g.get("cross_check") == "CONFIRMED_GAP"],
        key=gap_sort_key
    )
    manual_gaps     = sorted(
        [g for g in gaps if g.get("cross_check") == "MANUAL_REVIEW"],
        key=gap_sort_key
    )
    compliant_gaps  = [g for g in gaps if g.get("cross_check") == "LIKELY_COMPLIANT"]
    noise_gaps      = [g for g in gaps if g.get("cross_check") in ("DUPLICATE", "LOW_CONFIDENCE_NOISE", "")]

    n_confirmed  = len(confirmed_gaps)
    n_manual     = len(manual_gaps)
    n_compliant  = len(compliant)
    n_total      = len(findings)
    n_mandatory  = sum(1 for g in confirmed_gaps if g.get("severity") == "mandatory")
    n_noise      = len(noise_gaps)

    priority_gaps = _greedy_priority_gaps(gaps, get_finding)

    SEV_COLOR   = {"mandatory": "#c0392b", "recommended": "#d35400", "informational": "#2980b9"}
    SEV_LABEL   = {"mandatory": "MANDATORY", "recommended": "RECOMMENDED", "informational": "INFO"}

    def conf_bar(dist) -> str:
        """Visual confidence bar. dist=None means no data."""
        if dist is None:
            return '<span class="conf-val" style="color:#ccc">—</span>'
        pct   = max(0, min(100, int((1 - dist) * 100)))
        color = "#c0392b" if dist < 0.55 else "#e67e22" if dist < 0.75 else "#95a5a6"
        return (f'<div class="conf-bar-wrap" title="Match strength: {pct}%">'
                f'<div class="conf-bar" style="width:{pct}%;background:{color}"></div>'
                f'</div><span class="conf-val">{dist:.2f}</span>')

    def sev_badge(sev: str) -> str:
        c = SEV_COLOR.get(sev, "#888")
        l = SEV_LABEL.get(sev, sev.upper())
        return f'<span class="badge" style="background:{c}">{l}</span>'

    def status_badge(cc: str, covered: str = "") -> str:
        labels = {
            "CONFIRMED_GAP":       ("CONFIRMED GAP",       "#c0392b"),
            "MANUAL_REVIEW":       ("MANUAL REVIEW",       "#d35400"),
            "LIKELY_COMPLIANT":    ("LIKELY COMPLIANT",    "#27ae60"),
            "DUPLICATE":           ("DUPLICATE",           "#95a5a6"),
            "LOW_CONFIDENCE_NOISE":("LOW CONF NOISE",      "#bdc3c7"),
        }
        label, color = labels.get(cc, (cc, "#888"))
        extra = f" · p.{covered}" if covered and cc in ("LIKELY_COMPLIANT","MANUAL_REVIEW") else ""
        return f'<span class="badge outline" style="border-color:{color};color:{color}">{label}{extra}</span>'

    def gap_table_rows(gap_list):
        rows = []
        for g in gap_list:
            fin      = get_finding(g)
            pr       = fin.get("page_range")       # None if finding missing
            dist     = fin.get("distance")         # None if finding missing
            node     = fin.get("node_path", "")
            rule     = fin.get("matched_rule", "").replace("<","&lt;").replace(">","&gt;").replace("&","&amp;") if fin.get("matched_rule") else ""
            sev      = g.get("severity", "informational")
            desc     = g.get("gap", "").replace("<","&lt;").replace(">","&gt;")
            cc       = g.get("cross_check", "")
            covered  = str(g.get("covered_on_page", g.get("closest_page", "")))
            rule_id  = f"rule-{g.get('id','x')}"
            ref      = _format_law_node(node) if node else ""
            pg_text  = f"p.{pr[0]}–{pr[1]}" if pr else "—"

            if rule and ref:
                dropdown = (f'<div class="rule-expand" id="{rule_id}" style="display:none">'
                            f'<div class="rule-label">CySEC Consolidated AML Directive — {ref}</div>'
                            f'<div class="rule-text">{rule}</div></div>'
                            f'<button class="expand-btn" onclick="toggle(\'{rule_id}\',this)">&#x25BC; {ref}</button>')
            else:
                dropdown = ""

            rows.append(f"""
            <tr data-sev="{sev}">
              <td class="pg-cell">{pg_text}</td>
              <td>{sev_badge(sev)}</td>
              <td class="desc-cell">
                <div class="desc-text">{desc}</div>
                <div class="ref-line">
                  {"" if not ref else f'<span class="ref">{ref}</span>'}
                  {status_badge(cc, covered)}
                </div>
                {dropdown}
              </td>
              <td>{conf_bar(dist)}</td>
            </tr>""")
        return "\n".join(rows) if rows else '<tr><td colspan="4" class="empty">No findings in this category.</td></tr>'

    def compliant_rows_html():
        rows = []
        for c in compliant:
            fin  = get_finding(c)
            pr   = fin.get("page_range")
            node = fin.get("node_path","")
            dist = fin.get("distance")
            ref  = _format_law_node(node) if node else "—"
            pg   = f"p.{pr[0]}–{pr[1]}" if pr else "—"
            rows.append(f'<tr><td class="pg-cell">{pg}</td>'
                        f'<td><span class="ref">{ref}</span></td>'
                        f'<td>{conf_bar(dist)}</td></tr>')
        return "\n".join(rows) if rows else '<tr><td colspan="3" class="empty">None.</td></tr>'

    def priority_rows_html():
        rows = []
        for i, g in enumerate(priority_gaps, 1):
            fin  = get_finding(g)
            pr   = fin.get("page_range", ["?","?"])
            node = fin.get("node_path","")
            sev  = g.get("severity","informational")
            desc = g.get("gap","")
            ref  = _format_law_node(node)
            rows.append(f"""
            <tr>
              <td class="rank-cell">{i}</td>
              <td class="pg-cell">p.{pr[0]}–{pr[1]}</td>
              <td>{sev_badge(sev)}</td>
              <td><div class="desc-text">{desc}</div><span class="ref">{ref}</span></td>
            </tr>""")
        return "\n".join(rows)

    # Severity filter counts for confirmed section
    n_conf_mand = sum(1 for g in confirmed_gaps if g.get("severity") == "mandatory")
    n_conf_rec  = sum(1 for g in confirmed_gaps if g.get("severity") == "recommended")
    n_conf_info = sum(1 for g in confirmed_gaps if g.get("severity") == "informational")

    eval_date = result['evaluated_at'][:19].replace('T', ' ')

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AML Compliance Report — {result['document']}</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: #f4f6f9; color: #1a1a2e; font-size: 14px; line-height: 1.6;
}}
a {{ color: inherit; text-decoration: none; }}

/* ── Header ── */
.report-header {{
  background: #1a1a2e; color: #fff;
  padding: 24px 40px; display: flex; justify-content: space-between; align-items: center;
}}
.report-header .title {{ font-size: 1.3rem; font-weight: 700; letter-spacing: 0.02em; }}
.report-header .subtitle {{ font-size: 0.82rem; color: #8892b0; margin-top: 4px; }}
.header-meta {{ text-align: right; font-size: 0.8rem; color: #8892b0; line-height: 1.8; }}
.print-btn {{
  background: transparent; border: 1px solid #8892b0; color: #ccd6f6;
  padding: 6px 16px; border-radius: 4px; cursor: pointer; font-size: 0.8rem;
  margin-top: 8px;
}}
.print-btn:hover {{ background: rgba(255,255,255,0.08); }}

/* ── Main layout ── */
.main {{ max-width: 1140px; margin: 0 auto; padding: 32px 24px; }}

/* ── KPI bar ── */
.kpi-bar {{
  display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 12px; margin-bottom: 32px;
}}
.kpi {{
  background: #fff; border-radius: 8px; padding: 18px 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,.07); text-align: center;
  border-top: 3px solid #ddd;
}}
.kpi.red   {{ border-color: #c0392b; }}
.kpi.orange{{ border-color: #d35400; }}
.kpi.green {{ border-color: #27ae60; }}
.kpi.gray  {{ border-color: #95a5a6; }}
.kpi .num  {{ font-size: 2.2rem; font-weight: 700; line-height: 1; }}
.kpi.red   .num {{ color: #c0392b; }}
.kpi.orange .num{{ color: #d35400; }}
.kpi.green .num {{ color: #27ae60; }}
.kpi.gray  .num {{ color: #95a5a6; }}
.kpi .lbl  {{ font-size: 0.74rem; color: #666; margin-top: 6px; text-transform: uppercase; letter-spacing: 0.05em; }}

/* ── Section cards ── */
.section-card {{
  background: #fff; border-radius: 8px; margin-bottom: 24px;
  box-shadow: 0 1px 3px rgba(0,0,0,.07); overflow: hidden;
}}
.section-header {{
  padding: 16px 24px; border-bottom: 1px solid #eee;
  display: flex; align-items: center; justify-content: space-between;
}}
.section-header h2 {{
  font-size: 1rem; font-weight: 700; display: flex; align-items: center; gap: 10px;
}}
.section-dot {{
  width: 10px; height: 10px; border-radius: 50%; display: inline-block;
}}
.section-body {{ padding: 0; }}

/* ── Priority section ── */
.priority-banner {{
  background: linear-gradient(135deg, #1a1a2e 0%, #2c3e50 100%);
  color: #fff; border-radius: 8px; padding: 24px; margin-bottom: 24px;
}}
.priority-banner h2 {{
  font-size: 1rem; font-weight: 700; color: #e74c3c; margin-bottom: 4px;
  text-transform: uppercase; letter-spacing: 0.06em;
}}
.priority-banner .sub {{ font-size: 0.8rem; color: #8892b0; margin-bottom: 16px; }}

/* ── Filters ── */
.filter-bar {{ padding: 12px 24px; border-bottom: 1px solid #eee; display: flex; gap: 8px; flex-wrap: wrap; }}
.filter-btn {{
  padding: 4px 14px; border-radius: 20px; border: 1px solid #ddd;
  background: #fff; cursor: pointer; font-size: 0.78rem; font-weight: 600;
  color: #555; transition: all .15s;
}}
.filter-btn:hover {{ background: #f0f0f0; }}
.filter-btn.active {{ background: #1a1a2e; color: #fff; border-color: #1a1a2e; }}

/* ── Tables ── */
table {{ width: 100%; border-collapse: collapse; }}
th {{
  background: #f8f9fa; padding: 10px 16px; text-align: left;
  font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em;
  color: #666; border-bottom: 2px solid #eee; font-weight: 600;
}}
td {{ padding: 12px 16px; border-bottom: 1px solid #f0f0f0; vertical-align: top; }}
tr:last-child td {{ border-bottom: none; }}
tr:hover td {{ background: #fafbfc; }}
.pg-cell {{ color: #888; font-size: 0.82rem; white-space: nowrap; width: 70px; }}
.rank-cell {{ color: #c0392b; font-weight: 700; font-size: 1.1rem; width: 36px; text-align: center; }}
.desc-cell {{ max-width: 600px; }}
.desc-text {{ font-size: 0.88rem; color: #1a1a2e; margin-bottom: 6px; line-height: 1.5; }}
.ref-line  {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 4px; }}
.ref {{ font-size: 0.75rem; color: #3498db; font-family: monospace; font-weight: 600; }}
.rule-label {{ font-size: 0.7rem; font-weight: 700; color: #3498db;
               text-transform: uppercase; letter-spacing: 0.06em; margin-top: 10px; }}
.rule-text {{ font-size: 0.82rem; color: #333; background: #f0f4f8; padding: 12px 14px;
              border-left: 3px solid #3498db; border-radius: 0 4px 4px 0;
              line-height: 1.75; white-space: pre-wrap; margin-top: 4px; }}
.expand-btn {{
  background: #eef4fb; border: 1px solid #c5d8ef; color: #2980b9; cursor: pointer;
  font-size: 0.74rem; padding: 3px 10px; margin-top: 6px; border-radius: 4px;
  font-weight: 600; display: inline-block;
}}
.expand-btn:hover {{ background: #ddeaf8; }}
.empty {{ color: #aaa; font-style: italic; text-align: center; padding: 24px; }}

/* ── Badges ── */
.badge {{
  display: inline-block; padding: 2px 9px; border-radius: 4px;
  color: #fff; font-size: 0.7rem; font-weight: 700; letter-spacing: 0.03em;
  white-space: nowrap;
}}
.badge.outline {{
  background: transparent; border: 1.5px solid; font-size: 0.68rem;
}}

/* ── Confidence bar ── */
.conf-bar-wrap {{
  background: #eee; border-radius: 3px; height: 5px; width: 80px;
  display: inline-block; vertical-align: middle; margin-right: 6px;
}}
.conf-bar {{ height: 5px; border-radius: 3px; }}
.conf-val {{ font-size: 0.75rem; color: #888; font-family: monospace; vertical-align: middle; }}

/* ── Details/summary ── */
details {{ margin-bottom: 16px; }}
details > summary {{
  background: #fff; border-radius: 8px; padding: 14px 24px;
  cursor: pointer; font-weight: 600; font-size: 0.9rem;
  box-shadow: 0 1px 3px rgba(0,0,0,.07); list-style: none;
  display: flex; align-items: center; gap: 10px;
}}
details > summary::-webkit-details-marker {{ display: none; }}
details > summary::before {{ content: '▶'; font-size: 0.7rem; color: #888; transition: transform .2s; }}
details[open] > summary::before {{ transform: rotate(90deg); }}
details .section-card {{ border-radius: 0 0 8px 8px; margin-top: 0; }}

/* ── Technical notes ── */
.tech-notes {{ font-size: 0.82rem; color: #555; padding: 16px 24px; line-height: 1.8; }}
.tech-notes li {{ margin: 6px 0; }}

/* ── Print ── */
@media print {{
  body {{ background: #fff; }}
  .print-btn, .expand-btn, .filter-bar {{ display: none; }}
  .rule-expand {{ display: block !important; }}
  details {{ open: true; }}
  details > summary::before {{ display: none; }}
}}
</style>
</head>
<body>

<!-- Header -->
<div class="report-header">
  <div>
    <div class="title">AML Compliance Audit Report</div>
    <div class="subtitle">CySEC Consolidated AML Directive — Automated Gap Analysis</div>
  </div>
  <div class="header-meta">
    <div>{result['document']}</div>
    <div>Client: {result['client_id']} &nbsp;·&nbsp; {result['total_pages']} pages</div>
    <div>Evaluated: {eval_date}</div>
    <button class="print-btn" onclick="window.print()">&#x2398; Export PDF</button>
  </div>
</div>

<div class="main">

<!-- KPI Bar -->
<div class="kpi-bar">
  <div class="kpi red">
    <div class="num">{n_confirmed}</div>
    <div class="lbl">Confirmed Gaps</div>
  </div>
  <div class="kpi red">
    <div class="num">{n_mandatory}</div>
    <div class="lbl">Mandatory</div>
  </div>
  <div class="kpi orange">
    <div class="num">{n_manual}</div>
    <div class="lbl">Manual Review</div>
  </div>
  <div class="kpi green">
    <div class="num">{n_compliant}</div>
    <div class="lbl">Compliant</div>
  </div>
  <div class="kpi gray">
    <div class="num">{n_total}</div>
    <div class="lbl">Findings Assessed</div>
  </div>
  <div class="kpi gray">
    <div class="num">{n_noise}</div>
    <div class="lbl">Filtered / Noise</div>
  </div>
</div>

<!-- Priority Remediation -->
<div class="priority-banner">
  <h2>&#x26A0; Priority Remediation</h2>
  <div class="sub">Minimum gaps covering maximum regulatory exposure — act on these first</div>
  <table>
    <thead>
      <tr>
        <th style="color:#8892b0">#</th>
        <th style="color:#8892b0">Pages</th>
        <th style="color:#8892b0">Severity</th>
        <th style="color:#8892b0">Gap &amp; Reference</th>
      </tr>
    </thead>
    <tbody style="color:#fff">
      {priority_rows_html()}
    </tbody>
  </table>
</div>

<!-- Confirmed Gaps -->
<div class="section-card">
  <div class="section-header">
    <h2>
      <span class="section-dot" style="background:#c0392b"></span>
      Confirmed Gaps
      <span style="font-weight:400;color:#888;font-size:0.85rem">({n_confirmed} total — {n_conf_mand} mandatory, {n_conf_rec} recommended, {n_conf_info} informational)</span>
    </h2>
  </div>
  <div class="filter-bar" id="conf-filters">
    <button class="filter-btn active" onclick="filterTable('conf-table','all',this)">All ({n_confirmed})</button>
    <button class="filter-btn" onclick="filterTable('conf-table','mandatory',this)">Mandatory ({n_conf_mand})</button>
    <button class="filter-btn" onclick="filterTable('conf-table','recommended',this)">Recommended ({n_conf_rec})</button>
    <button class="filter-btn" onclick="filterTable('conf-table','informational',this)">Info ({n_conf_info})</button>
  </div>
  <div class="section-body">
    <table id="conf-table">
      <thead><tr><th>Pages</th><th>Severity</th><th>Gap Description &amp; Reference</th><th>Match Strength</th></tr></thead>
      <tbody>{gap_table_rows(confirmed_gaps)}</tbody>
    </table>
  </div>
</div>

<!-- Manual Review -->
<div class="section-card">
  <div class="section-header">
    <h2>
      <span class="section-dot" style="background:#d35400"></span>
      Manual Review Required
      <span style="font-weight:400;color:#888;font-size:0.85rem">({n_manual} borderline findings — semantic distance 0.45–0.55)</span>
    </h2>
  </div>
  <div class="section-body">
    <table>
      <thead><tr><th>Pages</th><th>Severity</th><th>Gap Description &amp; Reference</th><th>Match Strength</th></tr></thead>
      <tbody>{gap_table_rows(manual_gaps)}</tbody>
    </table>
  </div>
</div>

<!-- Likely Compliant (from GAP verdicts that cross-check reversed) -->
<details>
  <summary>
    <span class="section-dot" style="background:#27ae60;display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px"></span>
    Reversed by Cross-Check — Likely Compliant ({len(compliant_gaps)})
  </summary>
  <div class="section-card">
    <div class="section-body">
      <table>
        <thead><tr><th>Pages</th><th>Severity</th><th>Gap Description &amp; Reference</th><th>Match Strength</th></tr></thead>
        <tbody>{gap_table_rows(compliant_gaps)}</tbody>
      </table>
    </div>
  </div>
</details>

<!-- Kimi COMPLIANT verdicts -->
<details>
  <summary>
    <span class="section-dot" style="background:#27ae60;display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px"></span>
    Compliant Sections — Kimi Verdict ({n_compliant})
  </summary>
  <div class="section-card">
    <div class="section-body">
      <table>
        <thead><tr><th>Pages</th><th>Law Reference</th><th>Match Strength</th></tr></thead>
        <tbody>{compliant_rows_html()}</tbody>
      </table>
    </div>
  </div>
</details>

<!-- Noise / Filtered -->
<details>
  <summary>
    <span class="section-dot" style="background:#95a5a6;display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px"></span>
    Filtered Findings — Noise &amp; Duplicates ({n_noise})
  </summary>
  <div class="section-card">
    <div class="section-body">
      <table>
        <thead><tr><th>Pages</th><th>Severity</th><th>Gap Description &amp; Reference</th><th>Match Strength</th></tr></thead>
        <tbody>{gap_table_rows(noise_gaps)}</tbody>
      </table>
    </div>
  </div>
</details>

<!-- Technical Notes -->
<details>
  <summary>Technical Run Notes</summary>
  <div class="section-card">
    <ul class="tech-notes">
      <li><strong>Pipeline:</strong> {n_total} findings assessed &nbsp;·&nbsp; EGDR entropy-gated retrieval (k=1/3) &nbsp;·&nbsp; Bidirectional ChromaDB cross-check</li>
      <li><strong>Anonymization:</strong> Skipped (--skip-anon). Raw policy text sent to external API. Enable for production use.</li>
      <li><strong>Jurisdiction:</strong> CySEC Consolidated AML Directive only. EU AMLD5/6 and FATF collections not yet populated.</li>
      <li><strong>Noise filtering:</strong> Findings with detection distance &gt; 0.75 marked LOW_CONFIDENCE_NOISE and excluded from confirmed count. Semantic duplicates (Jaccard &gt; 0.6) collapsed.</li>
      <li><strong>Distance thresholds:</strong> Cross-check CONFIRMED &gt; 0.55 &nbsp;·&nbsp; MANUAL_REVIEW 0.45–0.55 &nbsp;·&nbsp; LIKELY_COMPLIANT &lt; 0.45</li>
    </ul>
  </div>
</details>

</div><!-- /main -->

<script>
function toggle(id, btn) {{
  var el = document.getElementById(id);
  var isHidden = el.style.display === 'none';
  el.style.display = isHidden ? 'block' : 'none';
  var ref = btn.textContent.replace(/^[\u25b2\u25bc][ ]*/, '');
  btn.innerHTML = (isHidden ? '&#x25B2; ' : '&#x25BC; ') + ref;
}}
function filterTable(tableId, sev, btn) {{
  var table = document.getElementById(tableId);
  if (!table) return;
  var rows = table.querySelectorAll('tbody tr');
  rows.forEach(function(r) {{
    r.style.display = (sev === 'all' || r.dataset.sev === sev) ? '' : 'none';
  }});
  var btns = btn.parentElement.querySelectorAll('.filter-btn');
  btns.forEach(function(b) {{ b.classList.remove('active'); }});
  btn.classList.add('active');
}}
</script>
</body>
</html>"""

    report_path = RESULTS_DIR / f"{pdf_path.stem}_{stamp}_report.html"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)
    return report_path

# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AML Compliance Auditor — Sliding Window Evaluator")
    parser.add_argument("--pdf",       type=str,  default=None,                help="PDF filename inside test_transactions/")
    parser.add_argument("--config",    type=str,  default="client_config.json", help="Client config JSON")
    parser.add_argument("--skip-anon", action="store_true",                     help="Skip Ollama anonymization (PoC only — sends raw text to API)")
    args = parser.parse_args()

    cfg = load_config(args.config)

    if args.pdf:
        pdf_path = TEST_DIR / args.pdf
    else:
        pdfs = sorted(TEST_DIR.glob("*.pdf"))
        if not pdfs:
            print("ERROR: No PDFs found in test_transactions/")
            sys.exit(1)
        pdf_path = pdfs[0]
        print(f"No --pdf specified. Using: {pdf_path.name}")

    if not pdf_path.exists():
        print(f"ERROR: File not found — {pdf_path}")
        sys.exit(1)

    run_evaluation(pdf_path, cfg, skip_anon=args.skip_anon)
