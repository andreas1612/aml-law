# Project Status: AML Compliance Auditor PoC

**Current Phase:** Phase 1 Complete (Data Engineering / Graph Construction)

### Phase 1: Database Generation (DONE)
- [x] Dump raw PDFs into `.txt` format.
- [x] Prove that regex parsing is unviable due to deep nested legal hierarchies and OCR noise.
- [x] Establish "One JSON per file" Graph schema.
- [x] Extract Parts 1 through 10 into semantic JSON (`part_X.json`).
- [x] Identify Appendix structural discrepancies.
- [x] Extract Appendices into purpose-built schemas (form_templates, indicator_lists).
- [x] Assemble `master_index.json` to link all 15 nodes together for RAG retrieval.
- [x] Organize workspace into `/raw_texts` and `/json_graph`.

### Phase 2: Vectorization & RAG Engine (PENDING)
- [ ] Determine the embedding model to be used locally.
- [ ] Write Python vectorization scripts that index the JSON leaves down to their absolute paths (e.g., `PART_V.paragraphs.18.subparagraphs.3.points.b`).
- [ ] Store vectors in a lightweight local DB (Chroma, FAISS, or Postgres/pgvector).

### Phase 3: The Anonymizer (PENDING)
- [ ] Configure the local Qwen3-8B class model.
- [ ] Build a pipeline to strip PII from mock client transaction profiles before passing them to the Auditor.

### Phase 4: Evaluation & Reporting (PENDING)
- [ ] Develop agentic LLM pipelines that evaluate the sanitized client profiles against retrieved Context nodes.
- [ ] Generate HTML/PDF Compliance Reports dynamically leveraging the Jinja2 structured templates.
