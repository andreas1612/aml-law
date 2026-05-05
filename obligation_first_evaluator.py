#!/usr/bin/env python3
"""
AML Compliance Auditor — Obligation-First Evaluator (B1 + B2)

Replaces the sliding-window approach in rag_evaluator.py with 100% law graph coverage.

Architecture:
  Phase 1:  PyPDF2 extracts all pages (unchanged).
  Phase 1c: Build ephemeral policy ChromaDB collection (unchanged).
  Phase 2:  Obligation-first sweep — 325 ChromaDB queries, ~5 seconds.
            For each law node: query policy collection → top-3 matching sections.
            Sort: sympathetic HCG nodes first, then worst-distance-first.
            Output: 325 candidates, one per law node.
  Phase 3:  Anonymization — SKIPPED on X1 Carbon (--skip-anon).
  Phase 4:  Kimi verdict — batches of 10, richer B2 context.
            Each item: exact law obligation text + top-3 policy sections + distances.
            402 credit exhaustion handled — partial results saved, run resumable via --verdict-only.
  Phase 4b: Obligation cross-check — uses sweep distances directly, no second ChromaDB query.
            High distance = "policy doesn't cover this" = signal, not noise.
  Phase 4c: Update Hebbian Compliance Graph (same logic, now covers all 325 nodes).
  Phase 5:  HTML report with 325-row obligation coverage table.

Do not modify rag_evaluator.py. Both evaluators remain runnable independently.
"""

import json
import os
import re
import sys
import time
import argparse
from collections import Counter
from datetime import datetime
from pathlib import Path

import chromadb
import requests

try:
    from rank_bm25 import BM25Okapi as _BM25Okapi
    _BM25_AVAILABLE = True
except ImportError:
    _BM25_AVAILABLE = False

# ─── Shared infrastructure from existing evaluator ────────────────────────────
from rag_evaluator import (
    load_config,
    extract_pages,
    _build_policy_index,
    _format_law_node,
    _update_hcg,
    _generate_report,
    _greedy_priority_gaps,
    _save,
    WORKSPACE, DB_PATH, TEST_DIR, RESULTS_DIR,
)

# ─── Kimi prompt — B2 richer context ─────────────────────────────────────────

_VERDICT_PROMPT_V2 = """\
You are a senior AML compliance officer doing a regulatory gap analysis.

For each item below you are given:
  - The exact legal obligation from the CySEC Consolidated AML Directive
  - The top 3 most semantically relevant sections found in the client policy document

Decide: do any of the policy sections satisfy this legal obligation?

Return ONLY a JSON array, no markdown, no extra text. One object per item.
SCHEMA: [{{"id":1,"verdict":"GAP","severity":"mandatory","policy_area":"CDD","missing":"one sentence — what specific element is absent","recommended_action":"one sentence — what clause or procedure should be added"}}]
verdict: GAP or COMPLIANT
severity: mandatory, recommended, or informational
policy_area: one of: CDD, PEP, sanctions, training, monitoring, reporting, governance, risk_assessment, other
missing: null if COMPLIANT, one concise sentence if GAP describing the missing element
recommended_action: null if COMPLIANT, one concise sentence stating exactly what policy clause or procedure should be added or amended to close this gap

ITEMS:
{findings_json}
"""

BATCH_SIZE = 8    # reduced from 10 — recommended_action field increases output length per verdict
BM25_FALLBACK_THRESHOLD = 0.85   # ChromaDB distance above which BM25 takes over


# ─── BM25 hybrid retrieval helpers ───────────────────────────────────────────

import re as _re

def _bm25_tokenize(text: str) -> list:
    return _re.findall(r'[a-z]{3,}', text.lower())

def _build_bm25_index(pages: list) -> tuple:
    """Build BM25Okapi index from policy pages. Returns (bm25, texts, page_nums)."""
    if not _BM25_AVAILABLE:
        return None, [], []
    non_empty = [(i, t) for i, t in enumerate(pages) if t.strip()]
    tokenized  = [_bm25_tokenize(t) for _, t in non_empty]
    bm25       = _BM25Okapi(tokenized)
    texts      = [t for _, t in non_empty]
    page_nums  = [i + 1 for i, _ in non_empty]
    return bm25, texts, page_nums

def _bm25_search(bm25, query_text: str, texts: list, page_nums: list, top_k: int = 3) -> list:
    """Return top-k policy sections via BM25 keyword search."""
    query_tokens = _bm25_tokenize(query_text)
    if not query_tokens or not texts:
        return []
    scores    = bm25.get_scores(query_tokens)
    top_idxs  = sorted(range(len(scores)), key=lambda i: -scores[i])[:top_k]
    max_score = max(scores) if max(scores) > 0 else 1.0
    return [
        {
            'page':     page_nums[idx],
            'text':     texts[idx][:600],
            'distance': round(max(0.0, 1.0 - scores[idx] / max_score), 4),
        }
        for idx in top_idxs
    ]


# ─── Credit exhaustion sentinel ───────────────────────────────────────────────

class _CreditExhausted(Exception):
    pass


# ─── Phase 2: Obligation-first sweep ─────────────────────────────────────────

def _load_hcg(hcg_path: str = "compliance_graph.json") -> dict:
    hcg_file = WORKSPACE / hcg_path
    if hcg_file.exists():
        with open(hcg_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def obligation_sweep(policy_stamp: str, config: dict,
                     bm25_data: tuple = None) -> list:
    """
    Query the ephemeral policy collection with each of 325 law nodes.
    Returns one candidate finding per node, sorted worst-distance-first.
    HCG sympathetic nodes (confirmed_gap_weight >= 0.5) jump to front of queue.

    When ChromaDB best distance > BM25_FALLBACK_THRESHOLD and bm25_data is
    provided, the top_sections sent to Kimi are replaced with BM25 keyword
    results — recovering ~4 of the 10 retrieval-failure gaps (C3).

    Guaranteed 100% law graph coverage by construction — no node is skipped.
    """
    chroma_client = chromadb.PersistentClient(path=str(DB_PATH))
    policy_col    = chroma_client.get_collection(f"policy_{policy_stamp}")
    law_col       = chroma_client.get_collection(config['regulated_under'][0])
    hcg           = _load_hcg()

    bm25_idx, bm25_texts, bm25_page_nums = bm25_data if bm25_data else (None, [], [])

    all_nodes  = law_col.get(include=['documents', 'metadatas'])
    total      = len(all_nodes['documents'])
    findings   = []
    bm25_used  = 0

    print(f"  Sweeping {total} law nodes against policy collection...")

    for i, (doc, meta) in enumerate(zip(all_nodes['documents'], all_nodes['metadatas'])):
        results   = policy_col.query(query_texts=[doc], n_results=3)
        distances = results['distances'][0]
        docs_     = results['documents'][0]
        metas_    = results['metadatas'][0]
        best_dist = min(distances)
        best_idx  = distances.index(best_dist)
        best_page = metas_[best_idx].get('page_num', 1)

        top_sections = [
            {
                'page':     m.get('page_num'),
                'text':     t[:600],
                'distance': round(d, 4)
            }
            for t, m, d in zip(docs_, metas_, distances)
        ]

        # BM25 fallback: ChromaDB failed to retrieve relevant pages
        if bm25_idx is not None and best_dist > BM25_FALLBACK_THRESHOLD:
            bm25_results = _bm25_search(bm25_idx, doc, bm25_texts, bm25_page_nums, top_k=3)
            if bm25_results:
                top_sections = bm25_results
                best_page    = bm25_results[0]['page']
                bm25_used   += 1

        findings.append({
            'node_path':           meta.get('path', ''),
            'source_file':         meta.get('source_file', ''),
            'matched_rule':        doc,                         # law obligation text (exact)
            'distance':            round(best_dist, 4),
            'page_range':          [best_page, best_page],      # page of best policy match
            'jurisdictions':       [config['regulated_under'][0]],
            'top_sections':        top_sections,
            'anonymized_snippet':  top_sections[0]['text'],     # best match for report
        })

        if (i + 1) % 50 == 0 or i + 1 == total:
            print(f"  Swept {i+1}/{total} obligations...")

    # Sort: sympathetic HCG nodes (confirmed gap history) go first.
    # Within tier: worst distance first — most likely gaps reach Kimi first.
    findings.sort(key=lambda f: (
        0 if hcg.get(f['node_path'], {}).get('confirmed_gap_weight', 0) >= 0.5 else 1,
        -f['distance']
    ))

    print(f"  Sweep complete — {total} candidates, sorted worst-distance-first")
    if bm25_used:
        print(f"  BM25 fallback used for {bm25_used} nodes (ChromaDB dist > {BM25_FALLBACK_THRESHOLD})")
    sympathetic = sum(1 for f in findings
                      if hcg.get(f['node_path'], {}).get('confirmed_gap_weight', 0) >= 0.5)
    if sympathetic:
        print(f"  {sympathetic} sympathetic (HCG high-weight) nodes at front of queue")

    return findings


# ─── Phase 4: Kimi verdict with B2 richer context ────────────────────────────

def _build_prompt_findings(findings: list) -> list:
    """
    Build the prompt-ready finding objects with richer B2 context:
    law obligation text + top-3 policy sections with page and distance.
    """
    prompt_findings = []
    for i, f in enumerate(findings):
        rule     = f.get('matched_rule', '').encode('ascii', 'replace').decode('ascii')
        sections = []
        for s in f.get('top_sections', []):
            text = s.get('text', '').encode('ascii', 'replace').decode('ascii')
            sections.append({
                'page':     s.get('page'),
                'text':     text[:500],
                'distance': s.get('distance'),
            })
        prompt_findings.append({
            'id':           i + 1,
            'node_path':    f['node_path'],
            'obligation':   rule[:400],    # exact law text — B2 key addition
            'top_policy_sections': sections,
        })
    return prompt_findings


def _parse_json_response(content: str) -> list:
    content = re.sub(r"```(?:json)?\s*", "", content).strip()
    content = content.replace("```", "").strip()
    start   = content.find("[")
    end     = content.rfind("]") + 1
    if start >= 0 and end > start:
        return json.loads(content[start:end])
    raise ValueError(f"No JSON array found: {content[:200]}")


def _call_single_batch(batch: list, batch_num: int, total_batches: int,
                       api_key: str, config: dict) -> list:
    prompt  = _VERDICT_PROMPT_V2.format(
        findings_json=json.dumps(batch, indent=2, ensure_ascii=True)
    )
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model":       config.get('kimi_model', 'moonshot-v1-32k'),
        "messages":    [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens":  2048,
    }

    print(f"  Batch {batch_num}/{total_batches} — {len(batch)} obligations, {len(prompt):,} chars")

    for attempt in range(5):
        if attempt > 0:
            wait = 10 * attempt
            print(f"    retry {attempt}/4 — waiting {wait}s...")
            time.sleep(wait)
        try:
            resp = requests.post(
                f"{config['kimi_base_url']}/chat/completions",
                headers=headers, json=payload, timeout=180
            )
            if resp.status_code == 429:
                print(f"    429 rate limit — will retry")
                continue
            if resp.status_code == 402:
                print(f"    402 credit exhausted — stopping. Partial results will be saved.")
                raise _CreditExhausted()
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return _parse_json_response(content)
        except _CreditExhausted:
            raise
        except Exception as e:
            if attempt == 4:
                raise
            print(f"    error: {e}")
    raise RuntimeError("All retries exhausted")


def call_verdict_api(findings: list, config: dict) -> tuple[list, bool]:
    """
    Send all 325 findings to Kimi in batches of 10.
    Returns (verdicts, credit_exhausted).
    If credit is exhausted mid-run, partial verdicts are returned with credit_exhausted=True.
    """
    api_key = os.environ.get("KIMI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("  WARNING: No API key set (KIMI_API_KEY). Skipping verdict call.")
        return [], False

    prompt_findings = _build_prompt_findings(findings)
    batches         = [prompt_findings[i:i+BATCH_SIZE]
                       for i in range(0, len(prompt_findings), BATCH_SIZE)]
    total_batches   = len(batches)
    print(f"  {len(findings)} obligations -> {total_batches} batches of up to {BATCH_SIZE}")

    all_verdicts     = []
    credit_exhausted = False

    for idx, batch in enumerate(batches, 1):
        if idx > 1:
            time.sleep(8)
        try:
            verdicts = _call_single_batch(batch, idx, total_batches, api_key, config)
            all_verdicts.extend(verdicts)
            print(f"  Batch {idx} done — {len(verdicts)} verdicts")
        except _CreditExhausted:
            credit_exhausted = True
            print(f"  Stopping at batch {idx}/{total_batches}. "
                  f"{len(all_verdicts)}/{len(findings)} obligations evaluated.")
            break
        except Exception as e:
            print(f"  ERROR on batch {idx}: {e} — skipping batch")
            all_verdicts.extend(batch)   # carry forward unverified

    return all_verdicts, credit_exhausted


# ─── Phase 4b: Obligation cross-check (no second ChromaDB query) ──────────────

def obligation_cross_check(verdicts: list, findings: list, bigram_set: set) -> list:
    """
    For each GAP verdict, classify confidence using the sweep distances already computed.
    No second ChromaDB query — the sweep is the reverse lookup.

    Thresholds (same as rag_evaluator bidirectional cross-check):
      bigram_hits == 0  -> CONFIRMED_GAP (no vocabulary overlap whatsoever)
      best_dist < 0.45  -> LIKELY_COMPLIANT (strong semantic match found)
      0.45 <= dist < 0.55 -> MANUAL_REVIEW
      dist >= 0.55      -> CONFIRMED_GAP

    Note: LOW_CONFIDENCE_NOISE filter removed. In obligation-first, high distance
    means "policy doesn't cover this obligation" — that is signal, not noise.
    """
    def get_finding(v):
        idx = v.get('id', 0) - 1
        return findings[idx] if 0 <= idx < len(findings) else {}

    confirmed = likely_compliant = manual_review = 0

    for v in verdicts:
        if not isinstance(v, dict):
            continue
        if v.get('verdict') != 'GAP':
            continue

        fin       = get_finding(v)
        best_dist = fin.get('distance', 1.0)
        law_text  = fin.get('matched_rule', '').lower().encode('ascii', 'replace').decode('ascii')

        if not law_text.strip():
            v['cross_check'] = 'CONFIRMED_GAP'
            confirmed += 1
            continue

        # Bigram pre-filter
        words        = law_text.split()
        node_bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]
        bigram_hits  = sum(1 for bg in node_bigrams if bg in bigram_set)

        if not node_bigrams or bigram_hits == 0:
            v['cross_check']      = 'CONFIRMED_GAP'
            v['cross_check_note'] = 'Zero bigrams from law node found in policy document.'
            confirmed += 1
            continue

        # Classify by sweep distance — no second query
        if best_dist < 0.45:
            best_page = fin.get('page_range', [None])[0]
            v['cross_check']       = 'LIKELY_COMPLIANT'
            v['covered_on_page']   = best_page
            v['coverage_distance'] = round(best_dist, 4)
            v['cross_check_note']  = (f'Strong semantic match on page {best_page} '
                                      f'(sweep distance={best_dist:.3f}).')
            likely_compliant += 1
        elif best_dist < 0.55:
            best_page = fin.get('page_range', [None])[0]
            v['cross_check']       = 'MANUAL_REVIEW'
            v['closest_page']      = best_page
            v['coverage_distance'] = round(best_dist, 4)
            v['cross_check_note']  = (f'Borderline match on page {best_page} '
                                      f'(sweep distance={best_dist:.3f}). Manual review needed.')
            manual_review += 1
        else:
            v['cross_check']      = 'CONFIRMED_GAP'
            v['cross_check_note'] = f'No strong policy match (sweep distance={best_dist:.3f}).'
            confirmed += 1

    print(f"  Cross-check: {confirmed} CONFIRMED_GAP | {manual_review} MANUAL_REVIEW "
          f"| {likely_compliant} LIKELY_COMPLIANT")
    return verdicts


# ─── Phase 5 extension: 325-row obligation coverage table ────────────────────

def _build_coverage_table(findings: list, verdicts: list) -> str:
    """Build a full 325-row obligation status table for the HTML report."""
    verdict_by_id = {}
    for v in verdicts:
        if isinstance(v, dict):
            verdict_by_id[v.get('id', 0)] = v

    STATUS_COLOR = {
        'CONFIRMED_GAP':    '#c0392b',
        'MANUAL_REVIEW':    '#d35400',
        'LIKELY_COMPLIANT': '#27ae60',
        'COMPLIANT':        '#27ae60',
        'PENDING':          '#95a5a6',
    }

    rows = []
    for i, f in enumerate(findings):
        v      = verdict_by_id.get(i + 1, {})
        ref    = _format_law_node(f.get('node_path', ''))
        dist   = f.get('distance', 1.0)
        page   = f.get('page_range', ['-'])[0]
        cc     = v.get('cross_check', '')
        verdict = v.get('verdict', '')

        if not v:
            status = 'PENDING'
        elif verdict == 'COMPLIANT':
            status = 'COMPLIANT'
        else:
            status = cc or 'PENDING'

        color     = STATUS_COLOR.get(status, '#95a5a6')
        dist_pct  = max(0, min(100, int((1 - dist) * 100)))
        dist_color = '#c0392b' if dist >= 0.55 else '#e67e22' if dist >= 0.45 else '#27ae60'

        gap_desc = v.get('gap', '') or v.get('missing', '') or ''
        gap_cell = f'<span style="font-size:0.78rem;color:#555">{gap_desc[:120]}</span>' if gap_desc else ''

        rows.append(
            f'<tr>'
            f'<td style="font-size:0.75rem;color:#3498db;font-family:monospace;white-space:nowrap">{ref}</td>'
            f'<td style="text-align:center">'
            f'  <span style="display:inline-block;padding:2px 8px;border-radius:4px;'
            f'background:{color};color:#fff;font-size:0.68rem;font-weight:700">{status.replace("_"," ")}</span>'
            f'</td>'
            f'<td style="text-align:center;font-size:0.78rem;color:#888">{page}</td>'
            f'<td>'
            f'  <div style="background:#eee;border-radius:3px;height:5px;width:60px;display:inline-block;vertical-align:middle;margin-right:4px">'
            f'    <div style="height:5px;border-radius:3px;width:{dist_pct}%;background:{dist_color}"></div>'
            f'  </div>'
            f'  <span style="font-size:0.72rem;font-family:monospace;color:#888">{dist:.3f}</span>'
            f'</td>'
            f'<td>{gap_cell}</td>'
            f'</tr>'
        )

    return "\n".join(rows)


def _append_coverage_table(html: str, findings: list, verdicts: list) -> str:
    """Inject the 325-row coverage table before </body>."""
    n_total      = len(findings)
    n_confirmed  = sum(1 for v in verdicts if isinstance(v, dict) and v.get('cross_check') == 'CONFIRMED_GAP')
    n_compliant  = sum(1 for v in verdicts if isinstance(v, dict) and v.get('verdict') == 'COMPLIANT')
    n_pending    = n_total - len([v for v in verdicts if isinstance(v, dict)])

    table_html = f"""
<details style="margin:0 auto 32px;max-width:1140px;padding:0 24px">
  <summary style="background:#fff;border-radius:8px;padding:14px 24px;cursor:pointer;
                  font-weight:600;font-size:0.9rem;box-shadow:0 1px 3px rgba(0,0,0,.07);
                  list-style:none;display:flex;align-items:center;gap:10px">
    Full Obligation Coverage — All 325 CySEC Nodes
    <span style="font-weight:400;color:#888;font-size:0.82rem;margin-left:8px">
      {n_confirmed} gaps &nbsp;·&nbsp; {n_compliant} compliant &nbsp;·&nbsp; {n_pending} pending
    </span>
  </summary>
  <div style="background:#fff;border-radius:0 0 8px 8px;box-shadow:0 1px 3px rgba(0,0,0,.07);overflow:auto">
    <table style="width:100%;border-collapse:collapse">
      <thead>
        <tr style="background:#f8f9fa">
          <th style="padding:10px 16px;text-align:left;font-size:0.75rem;text-transform:uppercase;
                     letter-spacing:0.05em;color:#666;border-bottom:2px solid #eee;font-weight:600">
            Law Reference
          </th>
          <th style="padding:10px 16px;text-align:center;font-size:0.75rem;text-transform:uppercase;
                     letter-spacing:0.05em;color:#666;border-bottom:2px solid #eee;font-weight:600">
            Status
          </th>
          <th style="padding:10px 16px;text-align:center;font-size:0.75rem;text-transform:uppercase;
                     letter-spacing:0.05em;color:#666;border-bottom:2px solid #eee;font-weight:600">
            Best Page
          </th>
          <th style="padding:10px 16px;font-size:0.75rem;text-transform:uppercase;
                     letter-spacing:0.05em;color:#666;border-bottom:2px solid #eee;font-weight:600">
            Sweep Distance
          </th>
          <th style="padding:10px 16px;font-size:0.75rem;text-transform:uppercase;
                     letter-spacing:0.05em;color:#666;border-bottom:2px solid #eee;font-weight:600">
            Gap Summary
          </th>
        </tr>
      </thead>
      <tbody style="font-size:0.82rem">
        {_build_coverage_table(findings, verdicts)}
      </tbody>
    </table>
  </div>
</details>
"""
    return html.replace("</body>", table_html + "\n</body>")


# ─── Orchestrator ─────────────────────────────────────────────────────────────

def run_obligation_evaluation(pdf_path: Path, config: dict,
                               skip_anon: bool = False, verdict_only: str = None):
    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("\n" + "="*60)
    print(f"  AML AUDIT (OBLIGATION-FIRST) — {pdf_path.name}")
    print(f"  Client : {config['client_id']}")
    print(f"  Law    : {', '.join(config['regulated_under'])}")
    print(f"  Anon   : {'SKIP (--skip-anon)' if skip_anon else 'Ollama'}")
    print("="*60 + "\n")

    # ── Verdict-only: reload existing JSON, skip extraction + Kimi ────────────
    if verdict_only:
        print(f"[--verdict-only] Loading: {verdict_only}")
        with open(verdict_only, encoding='utf-8') as f:
            saved = json.load(f)
        findings = saved.get('findings', [])
        verdicts = saved.get('verdicts', [])
        for v in verdicts:
            for field in ('cross_check', 'cross_check_note', 'covered_on_page',
                          'closest_page', 'coverage_distance'):
                v.pop(field, None)
        print(f"  {len(findings)} findings, {len(verdicts)} verdicts loaded.\n")

        print("[Phase 1a] Re-extracting pages for bigram set...")
        pages = extract_pages(pdf_path)
        full_text  = " ".join(pages).lower().encode('ascii', 'replace').decode('ascii')
        words      = full_text.split()
        bigram_set = set(f"{words[i]} {words[i+1]}" for i in range(len(words) - 1))
        print()

        # If no verdicts in saved JSON (e.g. keyless run), call Kimi now
        if not verdicts:
            print("[Phase 4] No verdicts in saved JSON — running Kimi now...")
            verdicts, credit_exhausted = call_verdict_api(findings, config)
            print()
        else:
            credit_exhausted = False

        print("[Phase 4b] Obligation cross-check (sweep distances)...")
        verdicts = obligation_cross_check(verdicts, findings, bigram_set)
        print()

        print("[Phase 4c] Updating Hebbian Compliance Graph...")
        critical_nodes = _update_hcg(verdicts, findings)
        print()

        result   = {**saved, "verdicts": verdicts, "evaluated_at": datetime.now().isoformat(),
                    "credit_exhausted": credit_exhausted}
        out_path = _save(result, pdf_path, stamp)

        print("[Phase 5] Generating report...")
        report_html  = _generate_report(result, findings, stamp, pdf_path, critical_nodes)
        # Inject 325-row coverage table
        html_path    = str(report_html)
        with open(html_path, encoding='utf-8') as f:
            html = f.read()
        html = _append_coverage_table(html, findings, verdicts)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print()

        print("="*60)
        print(f"  VERDICT-ONLY COMPLETE")
        print(f"  JSON   -> {out_path}")
        print(f"  Report -> {html_path}")
        print("="*60 + "\n")
        return

    # ── Phase 1a: extract ─────────────────────────────────────────────────────
    print("[Phase 1a] Extracting pages...")
    pages = extract_pages(pdf_path)
    print(f"  Total pages: {len(pages)}\n")

    # ── Phase 1c: build ephemeral policy index ────────────────────────────────
    print("[Phase 1c] Building ephemeral policy index...")
    chroma_client             = chromadb.PersistentClient(path=str(DB_PATH))
    policy_col, bigram_set, _ = _build_policy_index(pages, stamp, chroma_client)
    print()

    # ── Phase 1d: build BM25 index for hybrid retrieval fallback (C3) ────────
    bm25_data = None
    if _BM25_AVAILABLE:
        print("[Phase 1d] Building BM25 index for retrieval fallback...")
        bm25_data = _build_bm25_index(pages)
        print(f"  BM25 index: {len(bm25_data[1])} pages indexed")
        print()

    # ── Phase 2: obligation-first sweep ───────────────────────────────────────
    print("[Phase 2] Obligation-first sweep (325 law nodes → policy collection)...")
    findings = obligation_sweep(stamp, config, bm25_data=bm25_data)
    print()

    # ── Phase 3: anonymization ────────────────────────────────────────────────
    if not skip_anon:
        print("[Phase 3] Anonymization — not yet implemented for obligation-first (use --skip-anon)")
    else:
        print("[Phase 3] Anonymization SKIPPED (--skip-anon).")
    print()

    # ── Phase 4: Kimi verdict ─────────────────────────────────────────────────
    print("[Phase 4] Kimi verdict — obligation text + top-3 policy sections (B2 context)...")
    verdicts, credit_exhausted = call_verdict_api(findings, config)
    print()

    # ── Phase 4b: obligation cross-check ─────────────────────────────────────
    print("[Phase 4b] Obligation cross-check (sweep distances, no second query)...")
    verdicts = obligation_cross_check(verdicts, findings, bigram_set)
    gaps_confirmed  = sum(1 for v in verdicts if isinstance(v, dict) and v.get('cross_check') == 'CONFIRMED_GAP')
    gaps_compliant  = sum(1 for v in verdicts if isinstance(v, dict) and v.get('verdict') == 'COMPLIANT')
    print(f"  Confirmed gaps: {gaps_confirmed}  |  Kimi compliant: {gaps_compliant}")
    print()

    # ── Phase 4c: Hebbian Compliance Graph ────────────────────────────────────
    print("[Phase 4c] Updating Hebbian Compliance Graph...")
    critical_nodes = _update_hcg(verdicts, findings)
    print()

    result = {
        "client_id":        config["client_id"],
        "document":         pdf_path.name,
        "evaluated_at":     datetime.now().isoformat(),
        "evaluator":        "obligation_first",
        "total_pages":      len(pages),
        "total_findings":   len(findings),
        "credit_exhausted": credit_exhausted,
        "findings":         findings,
        "verdicts":         verdicts,
    }
    out_path = _save(result, pdf_path, stamp)

    # ── Phase 5: HTML report ──────────────────────────────────────────────────
    print("[Phase 5] Generating report...")
    report_html = _generate_report(result, findings, stamp, pdf_path, critical_nodes)
    html_path   = str(report_html)
    with open(html_path, encoding='utf-8') as f:
        html = f.read()
    html = _append_coverage_table(html, findings, verdicts)
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print()

    # ── Cleanup ephemeral policy collection ───────────────────────────────────
    try:
        chroma_client.delete_collection(f"policy_{stamp}")
        print("  Ephemeral policy index cleaned up.")
    except Exception:
        pass

    if credit_exhausted:
        print()
        print("  *** CREDIT EXHAUSTED — partial run saved ***")
        print(f"  Re-run with: --verdict-only {out_path}")

    print("="*60)
    print(f"  COMPLETE  |  pages: {len(pages)}  |  obligations: {len(findings)}")
    print(f"  JSON   -> {out_path}")
    print(f"  Report -> {html_path}")
    print("="*60 + "\n")


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="AML Compliance Auditor — Obligation-First Evaluator (100% law graph coverage)"
    )
    parser.add_argument("--pdf",          type=str, default=None,
                        help="PDF filename inside test_transactions/")
    parser.add_argument("--config",       type=str, default="client_config.json",
                        help="Client config JSON")
    parser.add_argument("--skip-anon",    action="store_true",
                        help="Skip Ollama anonymization (PoC only)")
    parser.add_argument("--verdict-only", type=str, default=None,
                        help="Path to existing result JSON. Re-run cross-check and report without Kimi.")
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

    run_obligation_evaluation(pdf_path, cfg,
                               skip_anon=args.skip_anon,
                               verdict_only=args.verdict_only)
