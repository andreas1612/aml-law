"""
deep_gap_analysis.py
Full diagnostic: why does the system miss 24 human expert compliance gaps?
Reads the 100819 JSON (obligation-first run, 172 confirmed gaps) and the XLSX.
"""

import json
import re
import sys
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

JSON_PATH = r"C:\Users\andre\Desktop\aml_proof\evaluation_results\AML Manual V8.0_Reviewed(Draft).docx_20260505_100819.json"
XLSX_PATH = r"C:\Users\andre\Desktop\aml_proof\CCSV - AML_KYC.xlsx"

# ── Load data ──────────────────────────────────────────────────────────────
with open(JSON_PATH, encoding="utf-8") as f:
    data = json.load(f)

findings = data["findings"]
verdicts = data["verdicts"]

print(f"Loaded {len(findings)} findings, {len(verdicts)} verdicts")

# Count gap verdicts
gap_verdicts = [v for v in verdicts if v.get("verdict") == "GAP"]
confirmed_gaps = [v for v in verdicts if v.get("cross_check") == "CONFIRMED_GAP"]
print(f"GAP verdicts: {len(gap_verdicts)}, CONFIRMED_GAP: {len(confirmed_gaps)}")
print(f"Sample verdict keys: {list(verdicts[0].keys()) if verdicts else 'none'}")
print(f"Sample finding keys: {list(findings[0].keys()) if findings else 'none'}")

# ── Helper: get finding by verdict id ─────────────────────────────────────
def get_finding(vid):
    idx = vid - 1
    return findings[idx] if 0 <= idx < len(findings) else {}

# ── Load human expert gaps ─────────────────────────────────────────────────
df = pd.read_excel(XLSX_PATH, sheet_name="AML_KYC")
print(f"\nXLSX columns: {list(df.columns)}")
print(f"XLSX shape: {df.shape}")
print(f"\nActions column unique values: {df['Actions \n(Yes/No)'].unique()[:10]}")

human_yes = df[df["Actions \n(Yes/No)"] == "Yes"].copy()
print(f"Human 'Yes' rows: {len(human_yes)}")
