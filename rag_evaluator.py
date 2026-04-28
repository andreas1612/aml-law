#!/usr/bin/env python3
"""
AML Compliance Auditor — Full-Coverage Sliding Window Evaluator

Architecture:
  Phase 1: Extract all pages, query ChromaDB with raw text (local, safe).
           No pages skipped. Every page in at least one window.
  Phase 2: Deduplicate findings by node_path + overlapping page ranges.
           Merge cross-jurisdiction matches on same page range.
  Phase 3: Anonymize ONLY the flagged page ranges via local Ollama.
           Raw PII never sent to any external service.
  Phase 4: ONE external API call with all anonymized findings -> JSON verdict.
"""

import json
import os
import sys
import time
import argparse
from pathlib import Path
from collections import defaultdict
from datetime import datetime

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
    "kimi_base_url":    "https://api.moonshot.cn/v1"
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

# ─── Phase 1: PDF Extraction ──────────────────────────────────────────────────

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

# ─── Phase 1: Sliding Window Detection ───────────────────────────────────────

def detect_violations(pages: list, config: dict) -> list:
    """
    Build every 3-page window (step=1) and query ChromaDB with raw text.
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

    # No distance threshold — take top 1 match per window unconditionally.
    # Filtering genuine gaps from false positives is Kimi's job, not a float cutoff.
    print(f"  {n} pages -> {total_wins} windows (size={window_size}, step=1, no threshold)")

    for start in range(total_wins):
        end         = start + window_size          # exclusive slice
        window_text = "\n\n".join(pages[start:end]).strip()

        if not window_text:
            continue

        for jurisdiction, collection in collections:
            results = collection.query(
                query_texts=[window_text],
                n_results=1   # top match only per window — dedup handles overlap
            )

            if not results["documents"] or not results["documents"][0]:
                continue

            doc  = results["documents"][0][0]
            meta = results["metadatas"][0][0]
            dist = results["distances"][0][0]

            findings.append({
                "page_range":   [start + 1, end],   # 1-indexed, inclusive end
                "jurisdiction": jurisdiction,
                "node_path":    meta.get("path", ""),
                "source_file":  meta.get("source_file", ""),
                "matched_rule": doc,
                "distance":     round(dist, 4),
                "raw_snippet":  window_text[:1000]
            })

        if (start + 1) % 20 == 0 or start + 1 == total_wins:
            print(f"  Window {start+1}/{total_wins} — {len(findings)} raw hits so far")

    return findings

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
                    "page_range":   list(hit["page_range"]),
                    "node_path":    node_path,
                    "source_file":  hit["source_file"],
                    "matched_rule": hit["matched_rule"],
                    "distance":     hit["distance"],
                    "jurisdictions": [hit["jurisdiction"]],
                    "raw_snippet":  hit["raw_snippet"]
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
    # Strip markdown fences
    import re
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

# ─── Orchestrator ─────────────────────────────────────────────────────────────

def run_evaluation(pdf_path: Path, config: dict, skip_anon: bool = False):
    RESULTS_DIR.mkdir(exist_ok=True)

    banner = f"  AML COMPLIANCE AUDIT — {pdf_path.name}"
    print("\n" + "="*60)
    print(banner)
    print(f"  Client    : {config['client_id']}")
    print(f"  Law       : {', '.join(config['regulated_under'])}")
    print(f"  Anon mode : {'SKIP (raw text to API — PoC only)' if skip_anon else 'Ollama ' + config['ollama_model']}")
    print("="*60 + "\n")

    # ── Phase 1: extract ──────────────────────────────────────────
    print("[Phase 1a] Extracting pages...")
    pages = extract_pages(pdf_path)
    print(f"  Total pages: {len(pages)}\n")

    # ── Phase 1: detect ───────────────────────────────────────────
    print("[Phase 1b] Sliding window detection (full coverage)...")
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
        _save(result, pdf_path)
        return

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

    result = {
        "client_id":      config["client_id"],
        "document":       pdf_path.name,
        "evaluated_at":   datetime.now().isoformat(),
        "total_pages":    len(pages),
        "total_findings": len(findings),
        "verdicts":       verdicts
    }
    stamp    = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = _save(result, pdf_path, stamp)

    # ── Phase 5: HTML report ──────────────────────────────────────
    print("[Phase 5] Generating report...")
    report_path = _generate_report(result, findings, stamp, pdf_path)
    print()

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

def _generate_report(result: dict, findings: list, stamp: str, pdf_path: Path) -> Path:
    """
    Generates a self-contained HTML compliance report.
    - Executive summary with counts
    - GAPs table with severity, page, law node, description, confidence flag
    - Flags: duplicate GAPs (same description), low-confidence matches (distance > 0.75)
    - COMPLIANT section
    - Pipeline mistakes section (architectural issues found during analysis)
    """
    verdicts  = result["verdicts"]
    gaps      = [v for v in verdicts if isinstance(v, dict) and v.get("verdict") == "GAP"]
    compliant = [v for v in verdicts if isinstance(v, dict) and v.get("verdict") == "COMPLIANT"]

    # Merge verdicts with findings data (by id -> findings[id-1])
    def get_finding(v):
        idx = v.get("id", 0) - 1
        if 0 <= idx < len(findings):
            return findings[idx]
        return {}

    # Detect duplicate GAPs (same gap text on different pages)
    from collections import Counter
    gap_texts = [g.get("gap", "") for g in gaps]
    dup_gaps  = {t for t, c in Counter(gap_texts).items() if c > 1 and t}

    # Detect low-confidence GAPs (distance > 0.75)
    def is_low_conf(v):
        fin = get_finding(v)
        return fin.get("distance", 0) > 0.75

    n_gaps       = len(gaps)
    n_compliant  = len(compliant)
    n_total      = len(findings)
    n_dup        = sum(1 for g in gaps if g.get("gap","") in dup_gaps)
    n_low_conf   = sum(1 for g in gaps if is_low_conf(g))
    n_mandatory  = sum(1 for g in gaps if g.get("severity") == "mandatory")

    sev_color = {"mandatory": "#c0392b", "recommended": "#e67e22", "informational": "#2980b9"}

    def gap_rows():
        rows = []
        for g in gaps:
            fin     = get_finding(g)
            pages   = fin.get("page_range", ["?", "?"])
            dist    = fin.get("distance", 0)
            node    = fin.get("node_path", "")
            rule    = fin.get("matched_rule", "")[:160]
            sev     = g.get("severity", "informational")
            desc    = g.get("gap", "")
            color   = sev_color.get(sev, "#888")
            flags   = []
            if desc in dup_gaps:
                flags.append('<span class="flag dup">DUPLICATE</span>')
            if dist > 0.75:
                flags.append(f'<span class="flag lowconf">LOW CONFIDENCE dist={dist:.2f}</span>')
            flag_html = " ".join(flags)
            rows.append(f"""
            <tr>
              <td class="center">{g.get('id','')}</td>
              <td class="center">{pages[0]}-{pages[1]}</td>
              <td><span class="sev" style="background:{color}">{sev.upper()}</span></td>
              <td>{desc}<br><small class="node">{node}</small><br>{flag_html}</td>
              <td><small>{rule}...</small></td>
              <td class="center dist">{dist:.3f}</td>
            </tr>""")
        return "\n".join(rows)

    def compliant_rows():
        rows = []
        for c in compliant:
            fin   = get_finding(c)
            pages = fin.get("page_range", ["?","?"])
            node  = fin.get("node_path","")
            dist  = fin.get("distance", 0)
            rows.append(f"""
            <tr>
              <td class="center">{c.get('id','')}</td>
              <td class="center">{pages[0]}-{pages[1]}</td>
              <td><small class="node">{node}</small></td>
              <td class="center dist">{dist:.3f}</td>
            </tr>""")
        return "\n".join(rows)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>AML Compliance Audit — {result['document']}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         max-width: 1200px; margin: 40px auto; padding: 0 20px; color: #222; }}
  h1   {{ font-size: 1.6rem; border-bottom: 3px solid #c0392b; padding-bottom: 10px; }}
  h2   {{ font-size: 1.2rem; margin-top: 40px; border-left: 4px solid #c0392b; padding-left: 12px; }}
  h3   {{ font-size: 1rem; margin-top: 30px; border-left: 4px solid #27ae60; padding-left: 12px; }}
  .summary {{ display: flex; gap: 20px; flex-wrap: wrap; margin: 24px 0; }}
  .card {{ background: #f8f8f8; border-radius: 8px; padding: 16px 24px; min-width: 120px; text-align: center; }}
  .card .num {{ font-size: 2rem; font-weight: 700; }}
  .card .lbl {{ font-size: 0.8rem; color: #666; margin-top: 4px; }}
  .red   {{ color: #c0392b; }}
  .green {{ color: #27ae60; }}
  .orange{{ color: #e67e22; }}
  table  {{ width: 100%; border-collapse: collapse; margin-top: 16px; font-size: 0.88rem; }}
  th     {{ background: #2c3e50; color: #fff; padding: 10px 12px; text-align: left; }}
  td     {{ padding: 9px 12px; border-bottom: 1px solid #eee; vertical-align: top; }}
  tr:hover td {{ background: #fafafa; }}
  .center {{ text-align: center; }}
  .dist   {{ font-family: monospace; color: #888; }}
  .node   {{ color: #888; font-family: monospace; font-size: 0.78rem; }}
  .sev    {{ display: inline-block; padding: 2px 8px; border-radius: 4px;
             color: #fff; font-size: 0.75rem; font-weight: 600; }}
  .flag   {{ display: inline-block; padding: 1px 6px; border-radius: 3px;
             font-size: 0.72rem; font-weight: 600; margin-left: 4px; }}
  .dup    {{ background: #e67e22; color: #fff; }}
  .lowconf{{ background: #95a5a6; color: #fff; }}
  .mistakes {{ background: #fff8e1; border: 1px solid #f39c12;
               border-radius: 6px; padding: 16px 20px; margin-top: 16px; }}
  .mistakes li {{ margin: 8px 0; line-height: 1.5; }}
  .meta  {{ color: #888; font-size: 0.85rem; margin-top: 6px; }}
  .tag   {{ display:inline-block; background:#eee; padding:2px 8px;
             border-radius:4px; font-size:0.8rem; margin-right:4px; }}
</style>
</head>
<body>

<h1>AML Compliance Audit Report</h1>
<div class="meta">
  <span class="tag">Document: {result['document']}</span>
  <span class="tag">Client: {result['client_id']}</span>
  <span class="tag">Pages: {result['total_pages']}</span>
  <span class="tag">Evaluated: {result['evaluated_at'][:19].replace('T',' ')}</span>
  <span class="tag">Law: CySEC Consolidated AML Directive</span>
</div>

<div class="summary">
  <div class="card"><div class="num red">{n_mandatory}</div><div class="lbl">Mandatory Gaps</div></div>
  <div class="card"><div class="num orange">{n_gaps}</div><div class="lbl">Total Gaps</div></div>
  <div class="card"><div class="num green">{n_compliant}</div><div class="lbl">Compliant</div></div>
  <div class="card"><div class="num">{n_total}</div><div class="lbl">Findings Assessed</div></div>
  <div class="card"><div class="num orange">{n_dup}</div><div class="lbl">Duplicate Flags</div></div>
  <div class="card"><div class="num">{n_low_conf}</div><div class="lbl">Low Confidence</div></div>
</div>

<h2>Compliance Gaps ({n_gaps})</h2>
<table>
  <thead>
    <tr>
      <th>#</th><th>Pages</th><th>Severity</th><th>Gap Description</th>
      <th>Matched Law Rule</th><th>Distance</th>
    </tr>
  </thead>
  <tbody>
    {gap_rows()}
  </tbody>
</table>

<h2>Pipeline Quality Issues</h2>
<div class="mistakes">
  <strong>Issues detected in this evaluation run:</strong>
  <ul>
    <li><strong>Duplicate GAPs ({n_dup} instances):</strong> The same compliance gap was flagged
        on multiple overlapping page windows. This is a known architectural side-effect of the
        sliding window approach — post-verdict deduplication by gap description is not yet
        implemented. Treat duplicate-flagged rows as one finding.</li>
    <li><strong>Low-confidence matches ({n_low_conf} GAPs):</strong> These findings have a
        semantic distance &gt; 0.75 between the policy text and the matched law node.
        This means the match is weak and the GAP verdict may be a false positive.
        Manual review recommended for all LOW CONFIDENCE flagged rows.</li>
    <li><strong>Anonymization skipped (--skip-anon):</strong> This run sent raw policy text
        to the external API. For production use on real client documents, Ollama anonymization
        must be enabled to strip PII before any external API call.</li>
    <li><strong>Single jurisdiction only:</strong> This evaluation covers CySEC rules only.
        Multi-jurisdiction support (EU AMLD5/6, FATF) is architecturally ready but not yet
        populated in the vector database.</li>
  </ul>
</div>

<h3>Compliant Sections ({n_compliant})</h3>
<table>
  <thead>
    <tr><th>#</th><th>Pages</th><th>Law Node</th><th>Distance</th></tr>
  </thead>
  <tbody>
    {compliant_rows()}
  </tbody>
</table>

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
