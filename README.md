# AML Compliance Auditor PoC

Proof of Concept for an automated AML Auditor executing locally on a self-hosted LLM.

## Architecture
The logic revolves around an LLM evaluating anonymized financial transactions against the **CySEC Consolidated AML Directive**. 

To optimize context loading, the entire legal directive was transformed from unformatted PDFs into a highly structured Semantic JSON Graph Database. Python backend loops evaluate anonymized client state against these strict RAG nodes.

### Data Sovereignty 
*   **Anonymizer Stack:** Raw client data is stripped of PII via a Qwen3-8B local model. 
*   **Knowledge API:** Only Anonymized data alongside targeted `json_graph` nodes are sent to external LLMs/APIs (if utilized), ensuring strict sovereign compliance.

## Directory Structure
*   `raw_texts/`: The original source of truth OCR `.txt` files translated from the CySEC Directive.
*   `json_graph/`: The LLM-extracted Knowledge Graph. Highly modular (1 part = 1 json), strictly indexed.
*   `master_index.json`: The mapping node routing the agent to the appropriate graph sectors.
*   `status.md`: Development tracking logs.
