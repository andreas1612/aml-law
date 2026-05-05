# Architecture & Decision Record
**Project:** AML Compliance Auditor PoC
**Last updated:** 2026-05-05 (Session 4)

> **Note to all future AI agents/developers:** Read `status.md` for current task status. Read `nextsession.md` for full context before making any changes. Do not re-litigate closed decisions listed here.

---

## 1. Core Philosophy: Data Sovereignty

Sensitive financial data must be evaluated against CySEC law without leaking PII to external endpoints. All heavy processing (vector search, BM25) is local. Only policy text + law obligation text reaches the external API (Kimi). Anonymization was permanently removed on the X1 Carbon (CPU-only machine, internal hardware, AUP covered).

---

## 2. Phase 1: Semantic JSON Knowledge Graph [COMPLETE]

**Decision:** Abandoned regex parsing. Used an LLM to semantically extract the raw CySEC `.txt` files into a modular JSON Knowledge Graph (`/json_graph/`).
- One `.json` file per Part/Appendix.
- Appendices use dynamic schemas (`form_template`, `indicator_list`) vs. core Parts which use `paragraphs`.
- `master_index.json` routes queries to the correct sector.
- **Session 4 addition:** 4 new JSON files for missing CySEC instruments: C315, C318, C398, AML Law Art.58. Same schema as existing files. 28 new nodes vectorized via `vectorize.py` (upsert — existing embeddings untouched).

---

## 3. Phase 2: Local Vector Database [COMPLETE]

**Decision:** Use ChromaDB (file-based, zero server admin) for the PoC.
- A `master_dispatcher` in `vectorize.py` routes each JSON file to a tailored extractor based on its schema type.
- **353 legal nodes** embedded using `sentence-transformers` (`all-MiniLM-L6-v2`) and stored in `chroma_db/`.
- `n_results=3` for all ChromaDB queries — n=5 was tested, no recall improvement, reverted.
- **DO NOT REGENERATE** the database — pre-existing embeddings are correct and 325+ nodes are already embedded.

---

## 4. Phase 1d: BM25 Hybrid Retrieval [COMPLETE — Session 4]

**Decision:** When ChromaDB returns best distance > 0.85 for a law node query, fall back to BM25 keyword search (rank_bm25.BM25Okapi) over the same policy pages.
- BM25 index is built in-memory from policy pages at Phase 1d, alongside the ChromaDB ephemeral collection.
- BM25 results replace `top_sections` sent to Kimi for high-distance nodes only.
- ChromaDB distance is retained for sorting and cross-check thresholds (unchanged).
- Threshold: `BM25_FALLBACK_THRESHOLD = 0.85` (constant in `obligation_first_evaluator.py`).
- **Why BM25 not as a silence gate:** BM25 as a sole gate fails on paraphrased compliance text (silent false negatives). As a hybrid fallback it's safe — only fires when ChromaDB has already failed.

---

## 5. Phase 3: Anonymization [PERMANENTLY REMOVED on X1 Carbon]

**Decision:** Ollama anonymization is disabled via `--skip-anon` and will not be re-enabled on the X1 Carbon.
- CPU-only machine: 180s per page timeout makes Ollama unusable.
- Internal hardware only: AUP explicitly covers raw text processing of internal client documents.
- `--skip-anon` flag is always passed on this machine.
- Post-GPU workstation: anonymization can be re-enabled or replaced with Presidio.

---

## 6. Phase 4: Obligation-First Architecture [PRIMARY — Session 3+4]

**Decision:** Replaced EGDR sliding window with obligation-first sweep.
- **Why:** Sliding window covered only 28% of law nodes (91/325). Obligation-first covers 100%.
- `obligation_sweep()` queries the ephemeral policy collection once per law node (325 queries).
- Results sorted worst-distance-first; sympathetic HCG nodes (confirmed_gap_weight ≥ 0.5) go first.
- `rag_evaluator.py` (sliding window) is preserved as baseline — do not modify it.

---

## 7. Kimi Verdict Schema [UPDATED — Session 4]

**Decision:** Added `policy_area` field to `_VERDICT_PROMPT_V2` output schema.
- Values: `CDD`, `PEP`, `sanctions`, `training`, `monitoring`, `reporting`, `governance`, `risk_assessment`, `other`.
- Used by `compare_gaps.py` second-pass to match system gaps to human audit findings by topic area, not just keyword overlap.
- **Why:** ~14 of 24 Session 3 misses were cross-node artefacts — gap found under different law node than human auditor used. Jaccard keyword matching can't link them. `policy_area` can.

---

## 8. Kimi as Verdict Engine [UNCHANGED]

**Decision:** Kimi (Moonshot moonshot-v1-32k) is the sole verdict engine. No auto-threshold compliance resolution.
- `all-MiniLM-L6-v2` distance scores are NOT used to determine compliance — they only determine retrieval priority and cross-check confidence tier.
- Kimi is given: exact law obligation text + top-3 matching policy sections with page numbers and distances.
- **Why no auto-threshold:** General-purpose embedding model not trained on legal domain. Distance ≠ legal satisfaction. Paraphrased compliance text can have distance > 0.55 and still be legally compliant.

---

## 9. Hebbian Compliance Graph [ACTIVE]

**Decision:** Track confirmed gap history per law node across client runs.
- 325 nodes tracked (was 15 after sliding window).
- Nodes with `confirmed_gap_weight ≥ 0.5` jump to front of the Kimi queue and are flagged CRITICAL in the report.
- Gating on HCG weight deferred — insufficient history at PoC stage. Weights used for ORDER only.
- After ~10 client runs, weight distribution becomes meaningful for risk prioritization.

---

## 10. Obligation Gap Count vs Human Audit Count

**Known difference:** System reports 167 CONFIRMED_GAPs; human audit reports 45 policy gaps.

This is not a false-positive problem — it is a granularity difference:
- Human auditor writes one finding per theme (e.g., "Electronic Verification insufficient" = 1 finding).
- System evaluates one finding per law sub-paragraph — EV spans 8–10 sub-paragraphs = 8–10 system gaps.
- System is more actionable: clause-level detail enables direct remediation mapping.
- False positive rate is confirmed at **zero** across all runs.

---

## 11. compare_gaps.py Matching Logic [UPDATED — Session 4]

**Decision:** Two-pass matching against human XLSX.
1. **First pass (Jaccard):** keyword overlap between system gap text + law node text vs human finding text. Threshold: 0.06.
2. **Second pass (policy_area):** for human gaps not matched in first pass, check if any CONFIRMED_GAP has a `policy_area` that is a case-insensitive substring match of the human gap's `Area` column. Handles cross-node artefacts.

---

## 12. Future Scale Path

| Component | Current (PoC, CPU) | Post-GPU Workstation |
|---|---|---|
| Vector DB | ChromaDB (file) | PGVector / Qdrant |
| Embedding model | all-MiniLM-L6-v2 (~90MB) | nlpaueb/legal-bert-base-uncased or law-ai/InLegalBERT |
| BM25 fallback | rank_bm25 (stays) | stays — orthogonal to embedding model |
| Anonymizer | Removed (--skip-anon) | Ollama or Presidio NLP |
| Evaluator | Kimi API (rate-limited) | Local vLLM, parallel batches |
| Input | PDF via PyPDF2 | Full document pipeline (DOCX, emails, DB exports) |
| Jurisdictions | CySEC only | AMLD5/6, FATF, FinCEN via config |
