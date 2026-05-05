import pandas as pd
import sys
sys.stdout.reconfigure(encoding="utf-8")

df = pd.read_excel(r"C:\Users\andre\Desktop\aml_proof\CCSV - AML_KYC.xlsx", sheet_name="AML_KYC")
human_yes = df[df["Actions \n(Yes/No)"] == "Yes"].copy()

print("Unique areas in human gaps:")
for a in sorted(human_yes["Area"].dropna().unique()):
    print(f"  [{a}]")

print()
print("All 66 human gaps:")
for _, r in human_yes.iterrows():
    no = r["No"]
    area = str(r.get("Area", "") or "").strip()
    finding = str(r.get("Finding", "") or "").strip()
    action = str(r.get("Required Actions\n(Recommendations)", "") or "").strip()
    print(f"  No={no} Area=[{area}]")
    print(f"    Finding: {finding[:120]}")
    print(f"    Action:  {action[:100]}")
    print()
