# Prompt for Future AI Sessions

> **Status:** Phases 1–4 code is 100% complete. Only remaining step is live execution.

---

**Paste this into your AI assistant to resume:**

---

I am building an automated AML Compliance Auditor PoC. Phases 1–4 are fully coded and ready to execute natively on my **Windows laptop** (no VM needed). Read `status.md` and `architecture_decisions.md` for the complete architecture context.

**Your task is purely execution — run the pipeline end to end:**

1. Ollama is installed on Windows (`localhost:11434`). Verify it is running and `qwen2.5:3b` is pulled:
   ```
   ollama list
   ollama pull qwen2.5:3b
   ```

2. Copy `anonymizer.py` and `rag_evaluator.py` from the `claude_sync/` folder into the main `amllaw/` folder if not already done.

3. Install remaining dependencies:
   ```
   pip install openai chromadb PyPDF2 sentence-transformers
   ```

4. Run the PII scrubber against the PDFs in `test_transactions/`:
   ```
   cd "C:\Users\Andreas.Pi\OneDrive - K.Treppides & Co\Desktop\amllaw"
   python anonymizer.py
   ```

5. Set your Kimi API key and run the legal compliance evaluator:
   ```
   $env:KIMI_API_KEY = "sk-your-kimi-api-key"
   python rag_evaluator.py
   ```

6. Results are saved as JSON files in `evaluation_results/`. Review them and report any unexpected verdicts for debugging.
