# Architecture & Decision Record
**Project:** AML Compliance Auditor PoC

> **Note to all future AI agents/developers:** Read `status.md` for the current task status. Read `master_index.json` to understand the JSON graph topology. Do NOT re-parse raw PDF/text files — that phase is complete.

---

## 1. Core Philosophy: Data Sovereignty
Sensitive financial data must be evaluated against CySEC law without leaking PII to external endpoints. All heavy processing (PII scrubbing, vector search) is local. Only anonymized text + retrieved law excerpts reach the external API.

---

## 2. Phase 1: Semantic JSON Knowledge Graph [COMPLETE]
**Decision:** Abandoned regex parsing. Used an LLM to semantically extract the raw CySEC `.txt` files into a modular JSON Knowledge Graph (`/json_graph/`).
- One `.json` file per Part/Appendix (15 files total).
- Appendices use dynamic schemas (`form_template`, `indicator_list`) vs. core Parts which use `paragraphs`.
- `master_index.json` routes queries to the correct sector.

---

## 3. Phase 2: Local Vector Database [COMPLETE]
**Decision:** Use ChromaDB (file-based, zero server admin) for the PoC.
- A `master_dispatcher` in `vectorize.py` routes each JSON file to a tailored extractor based on its schema type.
- **325 legal nodes** embedded using `sentence-transformers` (`all-MiniLM-L6-v2`) and stored in `chroma_db/`.
- Integrity verified: 100% character-level consistency between raw JSON and resulting chunks.

---

## 4. Phase 3: Local PII Anonymizer [COMPLETE - Awaiting Execution]
**Decision:** Replaced original Presidio plan with local Ollama LLM (`qwen2.5:3b`) for higher semantic accuracy.
- `anonymizer.py` extracts PDF text via `PyPDF2`, pipes pages to Ollama at `localhost:11434`, and outputs sanitized `.txt` files to `test_transactions/sanitized/`.
- **Current blocker resolved:** Originally intended for a headless Linux VM. Rerouted to run natively on the Windows host machine due to corporate network proxy restrictions blocking VM internet access.
- `OllamaSetup.exe` (~860MB) is downloaded and ready to install in the project root directory.

---

## 4. Phase 4: RAG Compliance Evaluation [COMPLETE - Awaiting Execution]
**Decision:** Use Kimi API (OpenAI-compatible) as the final evaluator.
- `rag_evaluator.py` reads sanitized `.txt` files, queries ChromaDB for top-3 matching CySEC nodes, and sends both to Kimi.
- Kimi operates at `temperature=0.1` to prevent hallucination and is strictly forced to output a JSON verdict: `{verdict, risk_level, applicable_clause, justification}`.
- Compatible with OpenAI API by swapping model name and base URL — no code rewrite needed.

---

## 5. Future Scale Path
| Component | Current (PoC) | Production |
|---|---|---|
| Vector DB | ChromaDB (file) | PGVector / Qdrant |
| Anonymizer | Ollama qwen2.5:3b | Same or Presidio NLP |
| Evaluator | Kimi API | Local vLLM on GPU server |
| Input | PDF via PyPDF2 | Full document pipeline (DOCX, emails, DB exports) |
