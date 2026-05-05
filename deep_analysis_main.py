"""
deep_analysis_main.py
Full root-cause analysis of why the system misses 24 human expert compliance gaps.
"""

import json
import re
import sys
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

JSON_PATH = r"C:\Users\andre\Desktop\aml_proof\evaluation_results\AML Manual V8.0_Reviewed(Draft).docx_20260505_100819.json"
XLSX_PATH = r"C:\Users\andre\Desktop\aml_proof\CCSV - AML_KYC.xlsx"

SEP = "=" * 80
SEP2 = "-" * 80

# ── Load data ──────────────────────────────────────────────────────────────
with open(JSON_PATH, encoding="utf-8") as f:
    data = json.load(f)

findings = data["findings"]
verdicts = data["verdicts"]

def get_finding(vid):
    idx = vid - 1
    return findings[idx] if 0 <= idx < len(findings) else {}

confirmed_gaps = [v for v in verdicts if v.get("cross_check") == "CONFIRMED_GAP"]

# ── Load human expert gaps ─────────────────────────────────────────────────
df = pd.read_excel(XLSX_PATH, sheet_name="AML_KYC")
human_yes = df[df["Actions \n(Yes/No)"] == "Yes"].copy()

human_gaps = []
for _, row in human_yes.iterrows():
    no = row["No"]
    if pd.isna(no):
        continue  # skip sub-rows without a number
    human_gaps.append({
        "no":      no,
        "area":    str(row.get("Area", "") or "").strip(),
        "finding": str(row.get("Finding", "") or "").strip(),
        "action":  str(row.get("Required Actions\n(Recommendations)", "") or "").strip(),
    })

print(f"Human numbered gaps: {len(human_gaps)}")

# ── Keyword extractor ──────────────────────────────────────────────────────
STOP = {
    "the","a","an","of","in","and","or","to","is","are","not","for","on","with",
    "that","this","it","as","be","by","at","from","which","have","has","been",
    "its","their","should","shall","must","ensure","ccsv","company","client",
    "policy","aml","manual","procedure","procedures","does","within","also",
    "any","all","where","when","will","been","our","was","were","would","if",
    "such","than","more","based","during","review","provided","information",
    "applicable","relevant","following","related","however","include","includes",
    "included","further","above","below","noted","note","well","both","each",
    "while","although","however","respect","regard","order","currently","already",
}

def keywords(text):
    words = re.findall(r"[a-z]{4,}", text.lower())
    return set(w for w in words if w not in STOP)

def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)

for h in human_gaps:
    h["kw"] = keywords(h["area"] + " " + h["finding"] + " " + h["action"])

# ── Classify human gaps: policy vs operational ─────────────────────────────
OPERATIONAL_KEYWORDS = keywords(
    "crm system access employee staff personnel attendance certification "
    "backlog record keeping practice actual client sample evidence provided "
    "operational process follow-up training attendance register notify cysec "
    "portal screenshot board minutes signed acknowledgement jira newsletter"
)

def is_operational(h):
    overlap = len(h["kw"] & OPERATIONAL_KEYWORDS)
    has_manual = ("manual" in h["finding"].lower() or
                  "procedure" in h["finding"].lower() or
                  "policy" in h["finding"].lower())
    return not has_manual and overlap >= 2

for h in human_gaps:
    h["type"] = "operational" if is_operational(h) else "policy"

policy_human = [h for h in human_gaps if h["type"] == "policy"]
oper_human   = [h for h in human_gaps if h["type"] == "operational"]

print(f"Policy-level human gaps: {len(policy_human)}")
print(f"Operational human gaps: {len(oper_human)}")

# ── Match system gaps to human gaps ───────────────────────────────────────
MATCH_THRESHOLD = 0.06

sys_results = []
for v in confirmed_gaps:
    f       = get_finding(v["id"])
    gap_txt = v.get("gap") or v.get("missing") or ""
    skw     = keywords(gap_txt + " " + f.get("matched_rule", ""))
    scored  = [(jaccard(skw, h["kw"]), h) for h in human_gaps]
    scored.sort(key=lambda x: -x[0])
    best_score, best_h = scored[0]
    sys_results.append({
        "sys_id":    v["id"],
        "verdict":   v,
        "finding":   f,
        "gap_txt":   gap_txt,
        "score":     round(best_score, 4),
        "matched":   best_score >= MATCH_THRESHOLD,
        "h_no":      best_h["no"],
        "h_area":    best_h["area"],
        "h_finding": best_h["finding"],
        "top5":      [(round(s, 4), h["no"], h["area"][:50]) for s, h in scored[:5]],
    })

matched_human_nos   = {r["h_no"] for r in sys_results if r["matched"]}
missed_human        = [h for h in human_gaps if h["no"] not in matched_human_nos]
missed_policy       = [h for h in missed_human if h["type"] == "policy"]
missed_operational  = [h for h in missed_human if h["type"] == "operational"]

print(f"System CONFIRMED_GAPs: {len(confirmed_gaps)}")
print(f"Matched human gaps: {len(matched_human_nos)}")
print(f"Missed human gaps: {len(missed_human)}")
print(f"  Missed policy-level: {len(missed_policy)}")
print(f"  Missed operational: {len(missed_operational)}")

# ── For missed gaps: find the best-matching system finding (even if not confirmed) ─
# This tells us whether the system FOUND the area but verdict wrong, or missed entirely

def find_best_system_node(h_gap, top_n=3):
    """
    For a given human gap, search ALL 325 findings (not just confirmed gaps)
    for the best keyword match to the human gap's area+finding+action.
    Returns top_n matches with full detail.
    """
    h_kw = h_gap["kw"]
    scored = []
    for i, f in enumerate(findings):
        v = verdicts[i]
        node_kw = keywords(f.get("matched_rule", "") + " " + f.get("node_path", ""))
        s = jaccard(h_kw, node_kw)
        scored.append((s, i, f, v))
    scored.sort(key=lambda x: -x[0])
    return scored[:top_n]

# ── Diagnosis categories ────────────────────────────────────────────────────
# (a) Vocabulary divergence — right page(s) returned, but Kimi said COMPLIANT
# (b) Wrong page returned — ChromaDB missed the relevant policy section entirely
# (c) Kimi error — returned relevant page but Kimi said COMPLIANT despite clear gap
# (d) System found it under different node — appears in a different law node

print()
print(SEP)
print("  DEEP ANALYSIS: MISSED HUMAN POLICY GAPS")
print(SEP)

diagnoses = []

for h in missed_policy:
    best_nodes = find_best_system_node(h, top_n=5)

    # Check if any system node covers this topic well
    best_score = best_nodes[0][0] if best_nodes else 0
    best_idx   = best_nodes[0][1] if best_nodes else None
    best_f     = best_nodes[0][2] if best_nodes else {}
    best_v     = best_nodes[0][3] if best_nodes else {}

    # Was the best match already a confirmed gap?
    already_confirmed = best_v.get("cross_check") == "CONFIRMED_GAP"

    # Check if top_sections pages are relevant to the human gap
    top_sections = best_f.get("top_sections", [])

    # Classify the miss
    if best_score < 0.04:
        diagnosis = "(b) CHROMADB MISS — no relevant law node found for this topic"
    elif already_confirmed:
        diagnosis = "(d) COVERED UNDER DIFFERENT NODE — system found similar gap differently"
    elif best_v.get("verdict") == "COMPLIANT":
        # Need to check what pages were returned
        # If distance is low (< 0.35), the right page was found but Kimi said compliant
        best_dist = best_f.get("distance", 1.0)
        if best_dist < 0.35:
            diagnosis = "(c) KIMI ERROR — relevant page retrieved, Kimi wrongly said COMPLIANT"
        elif best_dist < 0.5:
            diagnosis = "(a) VOCABULARY DIVERGENCE — similar page returned but semantic mismatch"
        else:
            diagnosis = "(b) CHROMADB MISS — wrong/distant pages returned"
    else:
        diagnosis = "(b) CHROMADB MISS — node exists but wrong pages retrieved"

    diagnoses.append({
        "h": h,
        "best_score": best_score,
        "best_f": best_f,
        "best_v": best_v,
        "diagnosis": diagnosis,
        "already_confirmed": already_confirmed,
    })

# Print summary of diagnoses
from collections import Counter
diag_counts = Counter(d["diagnosis"].split(" — ")[0] for d in diagnoses)
print("\nDIAGNOSIS SUMMARY:")
for k, v in sorted(diag_counts.items(), key=lambda x: -x[1]):
    print(f"  {k}: {v}")

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1: DETAILED MISSED POLICY GAPS
# ══════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print("  SECTION 1 — ALL MISSED POLICY GAPS: ROOT CAUSE ANALYSIS")
print(SEP)

for d in diagnoses:
    h  = d["h"]
    bf = d["best_f"]
    bv = d["best_v"]

    print()
    print(SEP2)
    print(f"  HUMAN GAP H[{h['no']}] — {h['area']}")
    print(SEP2)
    print(f"  Type: {h['type'].upper()}")
    print(f"  Finding:")
    # Wrap at 100 chars
    finding_lines = []
    words = h["finding"].split()
    line = "    "
    for w in words:
        if len(line) + len(w) > 104:
            finding_lines.append(line)
            line = "    " + w + " "
        else:
            line += w + " "
    if line.strip():
        finding_lines.append(line)
    print("\n".join(finding_lines))
    print(f"  Required Action:")
    action_lines = []
    words = h["action"].split()
    line = "    "
    for w in words:
        if len(line) + len(w) > 104:
            action_lines.append(line)
            line = "    " + w + " "
        else:
            line += w + " "
    if line.strip():
        action_lines.append(line)
    print("\n".join(action_lines))

    print()
    print(f"  DIAGNOSIS: {d['diagnosis']}")
    print(f"  Best matching system node (keyword Jaccard: {d['best_score']:.4f}):")

    if bf:
        node_path = bf.get("node_path", "n/a")
        rule_text = bf.get("matched_rule", "n/a")
        dist      = bf.get("distance", "n/a")
        verdict   = bv.get("verdict", "n/a")
        cross     = bv.get("cross_check", "n/a")

        print(f"    Node path: {node_path}")
        print(f"    Rule text: {rule_text[:200]}")
        print(f"    Best sweep distance: {dist}")
        print(f"    System verdict: {verdict}")
        print(f"    Cross-check: {cross}")

        missing_text = bv.get("missing", "")
        if missing_text:
            print(f"    System 'missing': {str(missing_text)[:200]}")

        print(f"    Top-3 policy sections ChromaDB returned:")
        for i, sec in enumerate(bf.get("top_sections", [])[:3]):
            page = sec.get("page", "?")
            sec_dist = sec.get("distance", "?")
            text = sec.get("text", "")
            print(f"      [{i+1}] Page {page} (dist={sec_dist:.4f}):")
            # Print first 300 chars of each section
            text_preview = text[:300].replace("\n", " ")
            print(f"           {text_preview}...")
    else:
        print("    (no system node found)")

    print()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2: GAPS THE SYSTEM DID CATCH — 3-4 examples
# ══════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print("  SECTION 2 — SYSTEM-CAUGHT GAPS: VOCABULARY ALIGNMENT EXAMPLES")
print(SEP)

policy_nos = {h["no"] for h in policy_human}
caught_policy = [r for r in sys_results if r["matched"] and r["h_no"] in policy_nos]
caught_policy_sorted = sorted(caught_policy, key=lambda x: -x["score"])

# Show top 4 distinct human gaps caught
shown_hnos = set()
shown_count = 0
for r in caught_policy_sorted:
    if r["h_no"] in shown_hnos:
        continue
    if shown_count >= 4:
        break
    shown_hnos.add(r["h_no"])
    shown_count += 1

    f = r["finding"]
    v = r["verdict"]
    h_match = next((h for h in human_gaps if h["no"] == r["h_no"]), {})

    print()
    print(SEP2)
    print(f"  SYSTEM CAUGHT: sys[{r['sys_id']}] ↔ H[{r['h_no']}] (Jaccard: {r['score']:.4f})")
    print(SEP2)
    print(f"  Human gap area: {r['h_area']}")
    print(f"  Human finding:  {r['h_finding'][:200]}")
    print()
    print(f"  System node: {f.get('node_path', 'n/a')}")
    print(f"  Law text:    {f.get('matched_rule', '')[:200]}")
    print(f"  Distance:    {f.get('distance', 'n/a')}")
    print(f"  Verdict:     {v.get('verdict', 'n/a')} / {v.get('cross_check', 'n/a')}")
    print(f"  Missing:     {str(v.get('missing', ''))[:200]}")
    print()
    print(f"  Top-3 policy sections returned by ChromaDB:")
    for i, sec in enumerate(f.get("top_sections", [])[:3]):
        page     = sec.get("page", "?")
        sec_dist = sec.get("distance", "?")
        text     = sec.get("text", "")
        print(f"    [{i+1}] Page {page} (dist={sec_dist:.4f}): {text[:250]}...")

    # Explain why vocabulary aligned
    h_kw   = h_match.get("kw", set())
    sys_kw = keywords(r.get("gap_txt", "") + " " + f.get("matched_rule", ""))
    overlap = h_kw & sys_kw
    print()
    print(f"  VOCABULARY ALIGNMENT — overlapping keywords: {sorted(overlap)}")
    print()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3: QUANTIFIED DIAGNOSIS
# ══════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print("  SECTION 3 — QUANTIFIED ROOT CAUSE DIAGNOSIS")
print(SEP)

cat_a = [d for d in diagnoses if d["diagnosis"].startswith("(a)")]
cat_b = [d for d in diagnoses if d["diagnosis"].startswith("(b)")]
cat_c = [d for d in diagnoses if d["diagnosis"].startswith("(c)")]
cat_d = [d for d in diagnoses if d["diagnosis"].startswith("(d)")]

print(f"\n  Total missed policy gaps: {len(diagnoses)}")
print(f"  (a) Vocabulary divergence (right page, wrong words): {len(cat_a)}")
print(f"  (b) ChromaDB miss (wrong/distant pages):            {len(cat_b)}")
print(f"  (c) Kimi error (right page, wrong verdict):         {len(cat_c)}")
print(f"  (d) Found under different node:                     {len(cat_d)}")
print()

for label, cat, note in [
    ("(a) VOCABULARY DIVERGENCE", cat_a, ""),
    ("(b) CHROMADB RETRIEVAL FAILURE", cat_b, ""),
    ("(c) KIMI VERDICT ERROR", cat_c, ""),
    ("(d) FOUND UNDER DIFFERENT NODE", cat_d, ""),
]:
    if cat:
        print(f"  {label} [{len(cat)}]:")
        for d in cat:
            h = d["h"]
            print(f"    H[{h['no']}] {h['area'][:60]}")
        print()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4: PER-MISS CHROMADB TOP-SECTIONS ANALYSIS
# Check what pages were actually served for each missed gap
# ══════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print("  SECTION 4 — CHROMADB RETRIEVAL DEEP DIVE FOR EACH MISSED GAP")
print(SEP)
print("  For each missed gap, we show what pages ChromaDB returned for the")
print("  best-matching law node, allowing page-level diagnosis.")
print()

for d in diagnoses:
    h  = d["h"]
    bf = d["best_f"]

    print(f"  H[{h['no']}] {h['area'][:50]} | {d['diagnosis'].split(' — ')[0]}")
    if bf:
        dist  = bf.get("distance", "n/a")
        secs  = bf.get("top_sections", [])
        pages = [f"p{s.get('page','?')}(d={s.get('distance',0):.3f})" for s in secs[:3]]
        print(f"    node: {bf.get('node_path','')[:80]}")
        print(f"    sweep dist={dist} | top-3 pages: {', '.join(pages)}")
    else:
        print("    [no matching node found]")
    print()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5: ALL SYSTEM FINDINGS — COVERAGE MAP
# ══════════════════════════════════════════════════════════════════════════════
print()
print(SEP)
print("  SECTION 5 — COVERAGE STATISTICS")
print(SEP)

total_policy = len(policy_human)
caught_nos   = {r["h_no"] for r in sys_results if r["matched"] and r["h_no"] in policy_nos}
missed_nos   = policy_nos - caught_nos

print(f"  Policy-level human gaps:   {total_policy}")
print(f"  Caught by system:          {len(caught_nos)}  ({100*len(caught_nos)//total_policy}%)")
print(f"  Missed by system:          {len(missed_nos)}  ({100*len(missed_nos)//total_policy}%)")
print()
print(f"  Operational human gaps (out of scope): {len(oper_human)}")
print(f"  System CONFIRMED_GAPs:                 {len(confirmed_gaps)}")
print(f"  Unique human policy gaps the system matched: {len(caught_nos)}")
print()
print(f"  Missed policy gap numbers: {sorted(missed_nos)}")
print()

# Missed gap areas
print("  Missed policy gap areas:")
for h in sorted(missed_policy, key=lambda x: x["no"]):
    print(f"    H[{h['no']}] {h['area']}")
