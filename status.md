# AML Compliance Auditor PoC - Status & Handover

## Project Overview
An automated AML compliance auditor utilizing a strictly controlled Semantic JSON Knowledge Graph to enforce regulatory compliance (CySEC) against client transactions. 

**Recent Architecture Pivot**: To avoid corporate firewall/VM proxy restrictions, the entire pipeline (Retrieval, Anonymization, and Evaluation) is now strictly hosted natively on the local Windows Machine. No remote VMs are required anymore.

## Accomplished So Far
### Phase 1 & 2: Local Knowledge Graph & Vectorization [COMPLETE]
* Converted CySEC Directives to 15 structured JSON schema files.
* Vectorized **325 explicit legal nodes** into `chroma_db/` using `sentence-transformers`.
* Proved real-world accuracy via our bespoke `assess_pdf.py` script, which successfully ripped an internal Corporate Manual PDF and mechanically mapped its "Board of Directors" paragraph perfectly against the core CySEC JSON law.

### Phase 3 & 4 Codebase [COMPLETE]
We pulled Claude's generated pipeline logic from the restricted VM back to the Windows Desktop (currently located in `claude_sync/`):
* `anonymizer.py`: Extracts raw PDF data securely via PyPDF2 and pipes it straight to local Ollama (`localhost:11434`) for stringent PII redaction.
* `rag_evaluator.py`: Bridges the sanitized text with ChromaDB vector search and outputs a strict JSON evaluation via the Kimi API.

## NEXT STEPS (Resuming Your Next Session)

**Step 1: Finish the Ollama Installation**
1. The Windows `OllamaSetup.exe` (~850MB) was successfully downloaded straight into the `amllaw` core folder. 
2. Double-click it to install Ollama locally on Windows.
3. Open Windows PowerShell and download the CPU-optimized safety model: 
   `ollama pull qwen2.5:3b`

**Step 2: Run the Pipeline**
*For cleanliness, it is recommended to copy `anonymizer.py` and `rag_evaluator.py` from the `claude_sync` folder directly into this core `amllaw` folder so all paths align perfectly.*

1. Make sure your Python environment has the final dependencies:
   `pip install openai chromadb PyPDF2`
2. Put the PDFs you want to test inside the `test_transactions/` folder.
3. Anonymize them locally:
   `python anonymizer.py`
4. Set your API Key for Kimi:
   `$env:KIMI_API_KEY="sk-your-kimi-token"`
5. Execute the final legal audit:
   `python rag_evaluator.py`
