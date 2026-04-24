import os
from pathlib import Path
from PyPDF2 import PdfReader
import chromadb

workspace_dir = Path(r"c:\Users\Andreas.Pi\OneDrive - K.Treppides & Co\Desktop\amllaw")
test_dir = workspace_dir / "test_transactions"
db_path = workspace_dir / "chroma_db"

def extract_pdf_preview(pdf_name, pages=3):
    pdf_path = test_dir / pdf_name
    reader = PdfReader(str(pdf_path))
    
    total_pages = len(reader.pages)
    
    extracted_text = ""
    # Extract only the first few pages for preview to save time/memory initially
    for i in range(min(pages, total_pages)):
        page = reader.pages[i]
        extracted_text += page.extract_text() + "\n"
        
    return extracted_text.strip(), total_pages

def assess_manual():
    print("--- INTERNAL AML MANUAL CROSS-AUDIT PREVIEW ---")
    
    # Check the first file
    target_file = "1a. AML Manual.docx.pdf"
    print(f"\nTargeting Document: {target_file}")
    
    text, total_pages = extract_pdf_preview(target_file, pages=5)
    
    print(f"Total Pages Detected: {total_pages}")
    print("\n[Preview of Extracted Text - First 800 chars]")
    print("-" * 50)
    print(text[:800])
    print("-" * 50)
    
    # Test an extraction match against Chroma DB
    print("\n--- Testing RAG Bridge on Extracted Text ---")
    client = chromadb.PersistentClient(path=str(db_path))
    collection = client.get_collection(name="cysec_aml_rules")
    
    # Grab a 400-char chunk from the middle of page 2 to simulate a "policy comparison" query
    query_text = text[500:900].strip() if len(text) > 900 else text.strip()
    
    print(f"Querying DB for cross-reference on: '{query_text[:100]}...'")
    
    results = collection.query(
        query_texts=[query_text], 
        n_results=1
    )
    
    if results and results["documents"] and len(results["documents"]) > 0 and len(results["documents"][0]) > 0:
        print(f"\nChromaDB Exact CySEC Match Found: {results['metadatas'][0][0]['path']}")
        print(f"Matched Rule: {results['documents'][0][0][:200]}...")

if __name__ == "__main__":
    assess_manual()
