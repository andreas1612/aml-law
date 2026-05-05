"""
compare_gaps.py
Compares system CONFIRMED_GAPs against human expert XLSX findings.

PATHS: Set JSON_PATH to the evaluation result you want to measure.
       Set XLSX_PATH to wherever CCSV - AML_KYC.xlsx lives on your machine.

  X1 Carbon:    JSON_PATH points to evaluation_results/ in this repo
                XLSX_PATH = r"C:\Users\andre\Downloads\CCSV - AML_KYC.xlsx"
  Work laptop:  XLSX_PATH = r"C:\Users\Andreas.Pi\OneDrive - K.Treppides & Co\Desktop\amllaw\CCSV - AML_KYC.xlsx"
"""

import json
import os
import re
import sys
import pandas as pd
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# ── Paths — update JSON_PATH to the run you want to evaluate ──────────────
_REPO_ROOT = Path(__file__).parent

# Auto-select most recent evaluation JSON if JSON_PATH not set below
def _latest_json() -> str:
    results_dir = _REPO_ROOT / "evaluation_results"
    jsons = sorted(results_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(jsons[0]) if jsons else ""

JSON_PATH  = r"evaluation_results\AML Manual V8.0_Reviewed(Draft).docx_20260505_114818.json"
JSON_PATH  = str(_REPO_ROOT / JSON_PATH) if not os.path.isabs(JSON_PATH) else JSON_PATH

# XLSX — ground truth (not in repo; set path for your machine)
_XLSX_CANDIDATES = [
    r"C:\Users\andre\Downloads\CCSV - AML_KYC.xlsx",
    r"C:\Users\Andreas.Pi\OneDrive - K.Treppides & Co\Desktop\amllaw\CCSV - AML_KYC.xlsx",
    str(_REPO_ROOT / "CCSV - AML_KYC.xlsx"),  # if copied into repo root
]
XLSX_PATH = next((p for p in _XLSX_CANDIDATES if os.path.exists(p)), None)
if XLSX_PATH is None:
    print("ERROR: CCSV - AML_KYC.xlsx not found. Add its path to _XLSX_CANDIDATES in compare_gaps.py")
    sys.exit(1)

# ── Load system results ────────────────────────────────────────────────────
with open(JSON_PATH, encoding="utf-8") as f:
    data = json.load(f)

findings = data["findings"]   # 0-indexed, id is 1-based
verdicts = data["verdicts"]

def get_finding(vid):
    idx = vid - 1
    return findings[idx] if 0 <= idx < len(findings) else {}

confirmed = [v for v in verdicts if v.get("cross_check") == "CONFIRMED_GAP"]

# ── Load human expert gaps ─────────────────────────────────────────────────
df = pd.read_excel(XLSX_PATH, sheet_name="AML_KYC")
human_yes = df[df["Actions \n(Yes/No)"] == "Yes"].copy()

human_gaps = []
for _, row in human_yes.iterrows():
    human_gaps.append({
        "no":      row["No"],
        "area":    str(row.get("Area", "") or "").strip(),
        "finding": str(row.get("Finding", "") or "").strip(),
        "action":  str(row.get("Required Actions\n(Recommendations)", "") or "").strip(),
    })

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

# ── Build human gap keyword sets ───────────────────────────────────────────
for h in human_gaps:
    h["kw"] = keywords(h["area"] + " " + h["finding"] + " " + h["action"])

# ── Match each system gap to best human gap ────────────────────────────────
MATCH_THRESHOLD = 0.06   # Jaccard — tune if needed

sys_results = []
for v in confirmed:
    f       = get_finding(v["id"])
    gap_txt = v.get("gap") or v.get("missing") or ""
    skw = keywords(gap_txt + " " + f.get("matched_rule", ""))
    scored = [(jaccard(skw, h["kw"]), h) for h in human_gaps]
    scored.sort(key=lambda x: -x[0])
    best_score, best_h = scored[0]
    sys_results.append({
        "sys_id":    v["id"],
        "sys_gap":   gap_txt,
        "sys_node":  f.get("node_path", ""),
        "sys_rule":  f.get("matched_rule", ""),
        "sys_sev":   v["severity"],
        "sys_dist":  f.get("distance", 0),
        "score":     round(best_score, 4),
        "matched":   best_score >= MATCH_THRESHOLD,
        "h_no":      best_h["no"],
        "h_area":    best_h["area"],
        "h_finding": best_h["finding"],
        "h_action":  best_h["action"],
        "all_scores": [(round(s, 4), h["no"], h["area"][:50]) for s, h in scored[:5]],
    })

matched_sys   = [r for r in sys_results if r["matched"]]
unmatched_sys = [r for r in sys_results if not r["matched"]]

# Which human gaps were hit?
matched_human_nos = set()
for r in matched_sys:
    matched_human_nos.add(r["h_no"])

# ── Second-pass: policy_area match for human gaps not caught by Jaccard ────
# When Kimi returns policy_area on a CONFIRMED_GAP, check if it matches the
# human gap's Area column via case-insensitive substring (handles cross-node
# measurement artefacts where gap was found under a different law node).
def _area_match(policy_area: str, human_area: str) -> bool:
    if not policy_area or not human_area:
        return False
    pa = policy_area.replace("_", " ").lower()
    ha = human_area.lower()
    return pa in ha or any(w in ha for w in pa.split() if len(w) >= 3)

pa2_matched_nos = set()
for h in human_gaps:
    if h["no"] in matched_human_nos:
        continue
    for v in confirmed:
        pa = v.get("policy_area", "")
        if _area_match(pa, h["area"]):
            matched_human_nos.add(h["no"])
            pa2_matched_nos.add(h["no"])
            break

missed_human = [h for h in human_gaps if h["no"] not in matched_human_nos]

# ── Categorise human gaps (policy-level vs operational) ───────────────────
# Policy-level = gap is about what the written manual says / doesn't say
# Operational  = gap requires reviewing actual practice, CRM, client files
OPERATIONAL_KEYWORDS = keywords(
    "crm system access employee staff personnel attendance certification "
    "backlog record keeping practice actual client sample evidence provided "
    "operational process follow-up training attendance register notify cysec "
    "portal screenshot board minutes signed acknowledgement jira newsletter"
)

def is_operational(h):
    overlap = len(h["kw"] & OPERATIONAL_KEYWORDS)
    # Also flag if finding text mentions specific names / no 'manual' keyword
    has_manual = "manual" in h["finding"].lower() or "procedure" in h["finding"].lower() or "policy" in h["finding"].lower()
    return not has_manual and overlap >= 2

for h in human_gaps:
    h["type"] = "operational" if is_operational(h) else "policy"

policy_human   = [h for h in human_gaps if h["type"] == "policy"]
oper_human     = [h for h in human_gaps if h["type"] == "operational"]

# ── Print results ──────────────────────────────────────────────────────────
SEP = "=" * 72

print(SEP)
print("  GROUND TRUTH COMPARISON: SYSTEM vs HUMAN EXPERT AUDIT")
print(SEP)
print(f"  Human expert gaps total:      {len(human_gaps)}")
print(f"    Estimated policy-level:     {len(policy_human)}")
print(f"    Estimated operational:      {len(oper_human)}")
print(f"  System CONFIRMED_GAPs:        {len(confirmed)}")
print(f"    Matched a human gap:        {len(matched_sys)}  (score >= {MATCH_THRESHOLD})")
print(f"    No human match found:       {len(unmatched_sys)}")
print()

policy_nos          = {h["no"] for h in policy_human}
caught_policy_nos   = {r["h_no"] for r in matched_sys if r["h_no"] in policy_nos}  # unique human gaps covered (Jaccard)
caught_policy_nos  |= (pa2_matched_nos & policy_nos)                                # add second-pass policy_area matches
caught_policy       = [r for r in matched_sys if r["h_no"] in policy_nos]           # system gaps that hit a policy gap (Jaccard only)
recall_pct = round(100 * len(caught_policy_nos) / max(len(policy_human), 1))
pa2_policy_count = len(pa2_matched_nos & policy_nos)
print(f"  RECALL on policy-level gaps:  {len(caught_policy_nos)}/{len(policy_human)} unique human gaps covered = {recall_pct}%")
if pa2_policy_count:
    print(f"    of which {pa2_policy_count} matched via policy_area (second-pass, cross-node artefacts)")
print(f"  (System gaps that matched:    {len(caught_policy)} Jaccard matches — multiple system gaps can match same human gap)")
print(f"  NOTE: system evaluated document text only.")
print(f"        Operational gaps require reviewing CRM/client files — out of scope.")
print()

print(SEP)
print("  SYSTEM GAPS — MATCHED TO HUMAN FINDINGS")
print(SEP)
for r in sorted(matched_sys, key=lambda x: -x["score"]):
    htype = "POLICY" if r["h_no"] in policy_nos else "OPER"
    print(f"  sys[{r['sys_id']:>3}] score={r['score']:.3f}  sev={r['sys_sev']:<12} [{htype}]")
    print(f"    node:  {r['sys_node']}")
    print(f"    gap:   {r['sys_gap'][:110]}")
    print(f"    → H[{r['h_no']}] {r['h_area'][:60]}")
    print(f"           {r['h_finding'][:110]}")
    print()

print(SEP)
print("  SYSTEM GAPS — NO HUMAN MATCH  (unique system finds OR false positives)")
print(SEP)
for r in unmatched_sys:
    print(f"  sys[{r['sys_id']:>3}] score={r['score']:.3f}  sev={r['sys_sev']:<12}  node={r['sys_node']}")
    print(f"    gap:   {r['sys_gap'][:110]}")
    print(f"    best:  H[{r['all_scores'][0][1]}] {r['all_scores'][0][2]} (score={r['all_scores'][0][0]})")
    print()

print(SEP)
print("  HUMAN POLICY GAPS — MISSED BY SYSTEM")
print(SEP)
missed_policy = [h for h in missed_human if h["type"] == "policy"]
for h in missed_policy:
    print(f"  H[{h['no']}] {h['area'][:60]}")
    print(f"    {h['finding'][:130]}")
    print()

print(SEP)
print("  HUMAN OPERATIONAL GAPS — OUT OF SCOPE FOR DOCUMENT EVALUATOR")
print(SEP)
missed_oper = [h for h in missed_human if h["type"] == "operational"]
for h in missed_oper:
    print(f"  H[{h['no']}] {h['area'][:60]}")
    print()
