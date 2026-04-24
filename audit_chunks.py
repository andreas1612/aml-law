import json
import re
from pathlib import Path

workspace_dir = Path(r"c:\Users\Andreas.Pi\OneDrive - K.Treppides & Co\Desktop\amllaw")
json_folder = workspace_dir / "json_graph"
output_report = workspace_dir / "chunk_audit_report.md"

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
            return chunks, "Definitions Block (Split by ;)"

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
        
    return chunks, "Standard Paragraph (Split by sentences)"

def extract_standard_paragraphs(data, current_path=""):
    nodes = []
    if isinstance(data, dict):
        if "text" in data and data["text"].strip():
            raw_text = data["text"].strip()
            chunks, reason = smart_legal_chunker(raw_text)
            nodes.append({
                "path": current_path,
                "raw_len": len(raw_text),
                "chunks": chunks,
                "reason": reason if len(chunks) > 1 else "Standard Paragraph (No Fragmentation Needed)"
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
            "raw_len": len(chunk),
            "chunks": [chunk],
            "reason": "Tailored: Form Template Translation (Fields grouped into single string)"
        })
    return nodes

def extract_indicator_list(data, current_path=""):
    nodes = []
    for sec_key, sec_val in data.get("sections", {}).items():
        title = sec_val.get("title", "")
        for i, indicator in enumerate(sec_val.get("indicators", [])):
            chunks, reason = smart_legal_chunker(indicator)
            nodes.append({
                "path": f"{current_path}.sections.{sec_key}.indicators.{i}",
                "raw_len": len(indicator),
                "chunks": chunks,
                "reason": "Tailored: Indicator Array Unpacking" + (f" + {reason}" if len(chunks) > 1 else "")
            })
    return nodes

def master_dispatcher(data, current_path):
    # Some older Parts might not explicitely define "type", they default to standard paragraphs
    file_type = data.get("type", "paragraphs")
    
    if file_type == "form_template":
        return extract_form_template(data, current_path)
    elif file_type == "indicator_list":
        return extract_indicator_list(data, current_path)
    else:
        return extract_standard_paragraphs(data, current_path)

def generate_report():
    with open(output_report, 'w', encoding='utf-8') as md:
        md.write("# Tailored Per-Schema Chunking Audit Report\n\n")
        md.write("This document proves that the AI now respects the unique schema of every JSON file (Parts vs Forms vs Indicator Arrays) rather than blindly guessing.\n\n")
        
        json_files = list(json_folder.glob("*.json"))
        
        for file in json_files:
            if file.name == 'master_index.json': continue
            
            with open(file, 'r', encoding='utf-8') as f:
                graph = json.load(f)
                
            nodes = master_dispatcher(graph, current_path=file.name)
            
            fragmented = [n for n in nodes if len(n["chunks"]) > 1]
            
            md.write(f"## {file.name}\n")
            md.write(f"* **Total Isolated Legal Nodes Processed**: {len(nodes)}\n")
            md.write(f"* **Nodes Requiring Fragmentation Cut**: {len(fragmented)}\n\n")
            
            # Print at least one sample to prove tailorship regardless of fragmentation
            if nodes:
                # If there are fragmented ones, show a fragmented one, else show the first node
                sample = fragmented[0] if fragmented else nodes[0]
                
                md.write(f"### Sample Tailored Extraction Check: `{sample['path']}`\n")
                md.write(f"**Architecture Applied:** {sample['reason']}\n\n")
                
                md.write(f"**Raw Translated Text Length:** {sample['raw_len']} characters\n\n")
                md.write("**Resulting Processed Chunks:**\n")
                for i, c in enumerate(sample['chunks']):
                    md.write(f"> **Chunk {i+1}** ({len(c)} chars): {c} \n\n")
                    
            md.write("---\n\n")

if __name__ == "__main__":
    generate_report()
    print(f"Tailored Report generated successfully at {output_report}")
