# Architecture & Decision Record
**Project:** AML Compliance Auditor PoC
**Context:** This document serves as the foundational reference for future AI agents and developers working on this project. It outlines the architectural decisions made based on hardware constraints and data sovereignty requirements.

## 1. The Core Philosophy: Data Sovereignty
The primary objective of this PoC is to prove that highly sensitive financial data can be evaluated against the CySEC AML Directive without leaking Personal Identifiable Information (PII) to unauthorized external endpoints.

## 2. Phase 1: The Semantic Graph Database (Completed)
**Decision:** We abandoned rule-based Regex parsing for legal texts.
**Reasoning:** Legal texts contain deep, nested hierarchies (Parts -> Paragraphs -> Subparagraphs -> Points) interwoven with chaotic OCR artifacts and marginal numbers. 
**Implementation:** 
*   We used an LLM to semantically extract the raw `.txt` files into a modular JSON Knowledge Graph (`/json_graph/`).
*   The architecture is modular: One `.json` file per Part/Appendix. 
*   Appendices use dynamic operational schemas (e.g., `form_template`, `indicator_list`) rather than strict paragraph structures to optimize RAG retrieval speed.
*   A `master_index.json` node routes queries to the correct sector.

## 3. Phase 2: Vectorization & Local Database
**Decision:** Store vectors in a lightweight, file-based database for the PoC.
**Reasoning:** The testing server is terminal-only and CPU-only. Deploying massive enterprise Vector DBs (like Milvus) over-complicates the PoC.
**Implementation:**
*   We will use **ChromaDB**, which runs seamlessly in Python without server administration. 
*   Python scripts will traverse the JSON graph leaves, generate embeddings locally using a lightweight model using `SentenceTransformers` (e.g., `all-MiniLM-L6-v2`), and store the absolute path of the JSON node as the metadata (e.g., `PART_V.paragraphs.18.points.b`).
*   *Future Scale:* Once GPU resources are acquired, the backend can easily be migrated to **PGVector** or **Qdrant**.

## 4. Phase 3: The Local Anonymizer
**Decision:** Avoid using an LLM for data sanitization in the PoC.
**Reasoning:** Because the server is CPU-only, running a local LLM to sanitize inputs is unbearably slow. 
**Implementation:**
*   We will use **Microsoft Presidio** (a blazing-fast NLP library running locally) to identify and strip PII.
*   "John Doe transferred €50,000" becomes `[PERSON_1] transferred €50,000`.

## 5. Phase 4: The Evaluation LLM (Hybrid API PoC)
**Decision:** Execute the PoC reasoning using an external API, protected by the local anonymizer.
**Reasoning:** Running a 8B+ parameter model (like Qwen3-8B) on a CPU terminal will crash or run at 1 token/second. 
**Implementation:**
*   **The Hybrid Route:** The sanitized string (stripped of all PII) and the specifically retrieved JSON Graph nodes are sent to an external API (like OpenAI or Gemini) to instantly evaluate compliance and output a decision report.
*   *Future Scale:* Once the production GPU server is purchased, the API credentials in the script will be deleted and replaced with a route to a local **vLLM** or **Ollama** server running the required Qwen models.

---
**Note to Future Sessions:** Read the `master_index.json` to understand the data topology before attempting to write Python routing logic. Do not attempt to parse raw PDF/text files; that phase is concluded.
