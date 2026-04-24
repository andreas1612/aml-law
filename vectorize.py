import json
import re
from pathlib import Path
import chromadb

workspace_dir = Path(r"c:\Users\Andreas.Pi\OneDrive - K.Treppides & Co\Desktop\amllaw")
json_folder = workspace_dir / "json_graph"
db_path = workspace_dir / "chroma_db"

def smart_legal_chunker(text):
    chunks = []
    if "means the person" in text or "shall mean" in text or '“' in text:
        raw_definitions = text.split(';')
        current_chunk = ""
        for i, defn in enumerate(raw_definitions):
            piece = defn + (";" if i < len(raw_definitions) - 1 else "")
            if len(current_chunk) + len(piece) < 400:
                current_chunk += piece
            else:
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                current_chunk = piece
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        if len(chunks) > 1:
            return chunks

    sentences = re.split(r'(?<=\.)\s+', text)
    current_chunk = ""
    for sentence in sentences:
        piece = sentence
        if len(current_chunk) + len(piece) < 500:
            current_chunk += (" " + piece).strip()
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = piece.strip()
    if current_chunk:
        chunks.append(current_chunk.strip())
        
    return chunks

def extract_standard_paragraphs(data, current_path=""):
    nodes = []
    if isinstance(data, dict):
        if "text" in data and data["text"].strip():
            raw_text = data["text"].strip()
            chunks = smart_legal_chunker(raw_text)
            nodes.append({
                "path": current_path,
                "chunks": chunks,
            })
                
        for key, value in data.items():
            if key in ["text", "part_id", "appendix_id", "type", "title", "description", "marginal_references"]: continue
            new_path = f"{current_path}.{key}" if current_path else key
            nodes.extend(extract_standard_paragraphs(value, new_path))
    return nodes

def extract_form_template(data, current_path=""):
    nodes = []
    for sec_key, sec_val in data.get("sections", {}).items():
        title = sec_val.get("title", "")
        fields = ", ".join(sec_val.get("fields", []))
        chunk = f"Form Section: '{title}'. Required fields: {fields}"
        nodes.append({
            "path": f"{current_path}.sections.{sec_key}",
            "chunks": [chunk]
        })
    return nodes

def extract_indicator_list(data, current_path=""):
    nodes = []
    for sec_key, sec_val in data.get("sections", {}).items():
        for i, indicator in enumerate(sec_val.get("indicators", [])):
            chunks = smart_legal_chunker(indicator)
            nodes.append({
                "path": f"{current_path}.sections.{sec_key}.indicators.{i}",
                "chunks": chunks
            })
    return nodes

def master_dispatcher(data, current_path):
    file_type = data.get("type", "paragraphs")
    if file_type == "form_template":
        return extract_form_template(data, current_path)
    elif file_type == "indicator_list":
        return extract_indicator_list(data, current_path)
    else:
        return extract_standard_paragraphs(data, current_path)

def generate_database():
    print("Initialize ChromaDB...")
    client = chromadb.PersistentClient(path=str(db_path))
    collection = client.get_or_create_collection(name="cysec_aml_rules")
    
    json_files = list(json_folder.glob("*.json"))
    
    all_chunks = []
    all_metadatas = []
    all_ids = []
    
    for file in json_files:
        if file.name == 'master_index.json': continue
        
        with open(file, 'r', encoding='utf-8') as f:
            graph = json.load(f)
            
        nodes = master_dispatcher(graph, current_path=file.name)
        
        for node in nodes:
            path = node["path"]
            chunks = node["chunks"]
            for i, chunk in enumerate(chunks):
                if not chunk.strip(): continue
                chunk_id = f"{path}_chunk_{i}" if len(chunks) > 1 else path
                
                all_chunks.append(chunk)
                all_metadatas.append({"path": path, "source_file": file.name})
                all_ids.append(chunk_id)
                
    print(f"Total logical blocks extracted across all 15 JSONs: {len(all_chunks)}")
    
    batch_size = 100
    for i in range(0, len(all_chunks), batch_size):
        end = min(i + batch_size, len(all_chunks))
        collection.upsert(
            documents=all_chunks[i:end],
            metadatas=all_metadatas[i:end],
            ids=all_ids[i:end]
        )
        print(f"Inserted batch {i} to {end} into local DB...")
        
    print(f"\nSUCCESS! Vector database permanently built at {db_path}")
    
    # Run a test query based on an Appendix 3 indicator
    print("\n--- Test Query: 'A customer making complex transactions with foreign offshore accounts' ---")
    results = collection.query(
        query_texts=["A customer making complex transactions with foreign offshore accounts"], 
        n_results=1
    )
    if results and results["documents"] and len(results["documents"]) > 0 and len(results["documents"][0]) > 0:
        print(f"Top Result Path Triggered: {results['metadatas'][0][0]['path']}")
        print(f"Extracted Rule: {results['documents'][0][0][:200]}...")

if __name__ == "__main__":
    generate_database()
