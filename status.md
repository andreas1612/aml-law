# AML Compliance Auditor PoC - Status & Handover

## Project Overview
An automated AML compliance auditor utilizing a strictly controlled Semantic JSON Knowledge Graph to enforce regulatory compliance (CySEC) against client transactions without hallucinations. The architecture enforces complete data sovereignty by utilizing a Local Vector Database and a Local Anonymizer.

## Accomplished So Far
### Phase 1: Database Generation [COMPLETE]
* Successfully broke down the CySEC AML Directive into a clean, hierarchical JSON Structure composed of 15 files (Parts 1-10 + Appendices 1-5).
* Preserved explicit graph paths (e.g., `part_1.json.paragraphs.5.points.a`).

### Phase 2: Vectorization & Information Retrieval [COMPLETE]
* Installed **ChromaDB** and `sentence-transformers`.
* Created the `master_dispatcher` architecture in `vectorize.py`.
* Due to the radical structural differences between Core Directives and Appendices, the pipeline explicitly routes logic:
    * **Standard Paragraphs (Parts 1-10, App 4-5)**: Intelligently fragmented by sentences (no halved clauses).
    * **Form Templates (App 1, 2)**: Translated empty dict keys into compliance statements.
    * **Indicator Lists (App 3)**: Extracted elements of pure JSON arrays without data loss.
* Successfully injected exactly **325 explicit legal nodes** into the persistent `chroma_db/` folder.
* **Proved Integrity**: Wrote `audit_chunks.py` verifying that 100% of chunks map correctly without structural data loss.

## NEXT STEPS (Handover Instructions for Claude)
The Knowledge Graph + Search Engine bridge is fully operational locally.

### Phase 3: The Local Anonymizer (Currently Pending)
**Goal:** We cannot allow internal client transaction data containing PII to hit an external LLM API directly. We must scrub it locally first.

1. **Target Environment**: The user has an 8GB headless VM (CPU-only) exclusively intended for this step.
2. **Setup Required**:
    * SSH into the VM.
    * Install **Ollama**.
    * Pull the `qwen2.5:3b` model (highly optimized for CPU-only text operations).
3. **Pipeline Action**:
    * Write a Python script (`anonymizer.py`) that takes real client transactions provided by the user and queries the local VM Ollama API.
    * Prompt the local Qwen model to explicitly redact any Names, Addresses, Amounts, and identifying numbers (replacing them with `[REDACTED_NAME]`, etc.).

### Phase 4: Final RAG Integration & Testing (Pending)
1. **The RAG Pipeline**: Combine the Local capabilities.
    * The user will manually place clean, real-world examples (in `.docx` or `.pdf` formats) into the `test_transactions/` directory.
    * **Document Parsing Layer**: A Python script using libraries like `pdfplumber` or `python-docx` will locally extract the raw text strings from these documents.
    * Anonymizer locally scrubs the extracted text to remove sensitive PII.
    * ChromaDB locally searches the graph based on the scrubbed text's semantic meaning.
2. **External Inference**:
    * Send the sanitized transaction + the explicitly retrieved CySEC JSON paragraph to **Kimi API** (or similar heavy LLM).
    * Prompt Kimi to act as the Auditor and declare whether the transaction violates the specific provided paragraph.
