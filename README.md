# AML Compliance Auditor PoC

Automated AML Auditor that evaluates financial transactions/corporate AML policies against the **CySEC Consolidated AML Directive** using a locally hosted knowledge graph + vector database, with zero PII leakage.

## Architecture Overview
```
PDF/DOCX Input → [assess_pdf.py] → Raw Text
                                        ↓
                             [anonymizer.py + Ollama qwen2.5:3b] → Sanitized Text (local)
                                        ↓
                             [ChromaDB] → Retrieves exact CySEC law node
                                        ↓
                             [rag_evaluator.py + Kimi API] → JSON Compliance Verdict
```

## Data Sovereignty
- **PII Scrubbing:** Done 100% locally via Ollama `qwen2.5:3b` running on the host machine.
- **Legal Retrieval:** Done 100% locally via ChromaDB (`chroma_db/`).
- **Only sent externally:** Anonymized text + matched CySEC law excerpt → Kimi API.

## Directory Structure
| Folder/File | Purpose |
|---|---|
| `json_graph/` | 15 modular CySEC JSON files (Parts 1-10 + Appendices 1-5) |
| `chroma_db/` | Persistent local vector database (325 legal nodes) |
| `test_transactions/` | Place your PDF/DOCX AML policy files here |
| `vectorize.py` | Builds the ChromaDB from the JSON graph |
| `anonymizer.py` | PII scrubber — runs via local Ollama |
| `rag_evaluator.py` | Final compliance evaluator — queries ChromaDB + Kimi API |
| `assess_pdf.py` | Standalone PDF text extractor + quick ChromaDB cross-reference |
| `status.md` | Development log and exact next steps |
| `architecture_decisions.md` | Architectural rationale for future AI agents / developers |
