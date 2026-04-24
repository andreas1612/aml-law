import os
import json
import re
from pathlib import Path

# Paths to process (Max 2 for POC)
workspace_dir = Path(r"C:\Users\andre\Desktop\aml_proof")
files_to_process = [
    workspace_dir / "PART Ι INTRODUCTORY PROVISIONS.txt",
    workspace_dir / "PART V CUSTOMER IDENTIFICATION AND.txt"
]

def clean_text(text):
    """Remove excessive newlines and clean up line breaks inside sentences."""
    # Replace single newlines with spaces, but keep double newlines (paragraphs)
    text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
    # Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def parse_aml_file(filepath):
    print(f"Parsing: {filepath.name.encode('ascii', 'replace').decode('ascii')}")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading {filepath.name}: {e}")
        return None

    # Graph Root
    part_id = filepath.name.split('.txt')[0]
    data = {
        "part_id": part_id,
        "paragraphs": {}
    }

    current_para = None
    current_subpara = None
    current_point = None
    current_subpoint = None
    
    current_text_buffer = []

    def commit_buffer():
        if not current_text_buffer:
            return
            
        text = clean_text(" ".join(current_text_buffer))
        if not text:
            return
            
        # Where does this text belong?
        if current_subpoint and current_point and current_subpara and current_para:
            data["paragraphs"][current_para]["subparagraphs"][current_subpara]["points"][current_point]["subpoints"][current_subpoint] += text + " "
        elif current_point and current_subpara and current_para:
            data["paragraphs"][current_para]["subparagraphs"][current_subpara]["points"][current_point]["text"] += text + " "
        elif current_subpara and current_para:
            data["paragraphs"][current_para]["subparagraphs"][current_subpara]["text"] += text + " "
        elif current_para:
            data["paragraphs"][current_para]["text"] += text + " "
            
        current_text_buffer.clear()

    # Regex patterns
    # Matches "18. " or "18. (1)"
    para_pattern = re.compile(r'^(\d+)\.\s*(?:\((\d+)\))?')
    # Matches "(1)"
    subpara_pattern = re.compile(r'^\((\d+)\)')
    # Matches "(a)"
    point_pattern = re.compile(r'^\(([a-z])\)')
    # Matches "i."
    subpoint_pattern = re.compile(r'^([ivxlc]+)\.')

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue
            
        # Check if line indicates a new paragraph
        para_match = para_pattern.match(line_clean)
        if para_match:
            commit_buffer()
            current_para = para_match.group(1)
            if current_para not in data["paragraphs"]:
                data["paragraphs"][current_para] = {
                    "text": "",
                    "subparagraphs": {}
                }
            
            # Reset levels below
            current_subpara = None
            current_point = None
            current_subpoint = None
            
            # Might also have a subpara instantly (e.g. "18. (1)")
            inline_sub = para_match.group(2)
            if inline_sub:
                current_subpara = inline_sub
                data["paragraphs"][current_para]["subparagraphs"][current_subpara] = {
                    "text": "",
                    "points": {}
                }
                
            # Keep text after the match
            rem_text = line_clean[para_match.end():].strip()
            if rem_text:
                current_text_buffer.append(rem_text)
            continue
            
        # Check subpara
        subpara_match = subpara_pattern.match(line_clean)
        if subpara_match and current_para:
            commit_buffer()
            current_subpara = subpara_match.group(1)
            current_point = None
            current_subpoint = None
            
            if current_subpara not in data["paragraphs"][current_para]["subparagraphs"]:
                data["paragraphs"][current_para]["subparagraphs"][current_subpara] = {
                    "text": "",
                    "points": {}
                }
            rem_text = line_clean[subpara_match.end():].strip()
            if rem_text:
                current_text_buffer.append(rem_text)
            continue
            
        # Check point
        point_match = point_pattern.match(line_clean)
        if point_match and current_subpara and current_para:
            commit_buffer()
            current_point = point_match.group(1)
            current_subpoint = None
            
            if current_point not in data["paragraphs"][current_para]["subparagraphs"][current_subpara]["points"]:
                 data["paragraphs"][current_para]["subparagraphs"][current_subpara]["points"][current_point] = {
                     "text": "",
                     "subpoints": {}
                 }
            rem_text = line_clean[point_match.end():].strip()
            if rem_text:
                current_text_buffer.append(rem_text)
            continue
            
        # Check subpoint
        subpoint_match = subpoint_pattern.match(line_clean)
        if subpoint_match and current_point and current_subpara and current_para:
            commit_buffer()
            current_subpoint = subpoint_match.group(1)
            
            if current_subpoint not in data["paragraphs"][current_para]["subparagraphs"][current_subpara]["points"][current_point]["subpoints"]:
                data["paragraphs"][current_para]["subparagraphs"][current_subpara]["points"][current_point]["subpoints"][current_subpoint] = ""
                
            rem_text = line_clean[subpoint_match.end():].strip()
            if rem_text:
                current_text_buffer.append(rem_text)
            continue
            
        # If no marker is hit, it's a continuation of the text
        current_text_buffer.append(line_clean)

    # Final commit
    commit_buffer()
    
    # Cleanup empty fields
    for p_id in list(data["paragraphs"].keys()):
        data["paragraphs"][p_id]["text"] = data["paragraphs"][p_id]["text"].strip()
        if not data["paragraphs"][p_id]["text"] and not data["paragraphs"][p_id]["subparagraphs"]:
            del data["paragraphs"][p_id]
            
    return data

def main():
    graph_db = {}
    
    for fp in files_to_process:
        if fp.exists():
            res = parse_aml_file(fp)
            if res:
                graph_db[res["part_id"]] = res
        else:
            print(f"Skipped missing file: {fp}")

    output_path = workspace_dir / "knowledge_graph_poc.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(graph_db, f, indent=4, ensure_ascii=False)
        
    print(f"\nParsed graph successfully written to: {output_path}")

if __name__ == "__main__":
    main()
