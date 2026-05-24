import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any

@dataclass
class SemanticChunk:
    content: str
    chunk_index: int
    page: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

def normalize_pages(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Apply semantic cleanup on raw PDF pages.
    """
    # 1. Detect common headers and footers
    first_lines = {}
    last_lines = {}
    for p in pages:
        text = str(p.get("content", ""))
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if len(lines) > 0:
            first = lines[0]
            last = lines[-1]
            first_lines[first] = first_lines.get(first, 0) + 1
            last_lines[last] = last_lines.get(last, 0) + 1
            
    # If a line appears on at least 30% of pages, it's likely a header/footer
    threshold = max(2, int(len(pages) * 0.3)) if len(pages) > 3 else 2
    common_headers = {k for k, v in first_lines.items() if v >= threshold and len(k) < 100}
    common_footers = {k for k, v in last_lines.items() if v >= threshold and len(k) < 100}

    normalized_pages = []
    
    # Patterns for structural elements
    list_pattern = re.compile(r'^(\d+[\.\)]|[a-zA-Z][\.\)]|[-•*])\s+')
    mcq_pattern = re.compile(r'^([A-D][\.\)]|[a-d][\.\)])\s+')
    heading_pattern_1 = re.compile(r'^(#+\s+|Chapter\s+\d+|Unit\s+\d+|Module\s+\d+)', re.IGNORECASE)
    heading_pattern_2 = re.compile(r'^[A-Z0-9\s\-_:]{4,}$')
    
    for p in pages:
        text = str(p.get("content", ""))
        page_num = p.get("pageNumber")
        
        lines = text.split('\n')
        
        cleaned_lines = []
        for line in lines:
            s_line = line.strip()
            # Remove empty lines
            if not s_line:
                if cleaned_lines and cleaned_lines[-1] != "":
                    cleaned_lines.append("")
                continue
                
            # Remove headers/footers
            if s_line in common_headers or s_line in common_footers:
                continue
                
            # Remove isolated page numbers
            if re.match(r'^\d+$', s_line) or re.match(r'^(Page|p\.)\s*\d+$', s_line, re.IGNORECASE):
                continue
                
            cleaned_lines.append(s_line)
            
        # Paragraph normalization
        merged_lines = []
        current_para = []
        
        for i, line in enumerate(cleaned_lines):
            if not line:
                if current_para:
                    merged_lines.append(" ".join(current_para))
                    current_para = []
                merged_lines.append("")
                continue
                
            is_list = list_pattern.match(line)
            is_mcq = mcq_pattern.match(line)
            is_heading = (heading_pattern_1.match(line) or heading_pattern_2.match(line)) and len(line) < 120
            
            # Start new paragraph if structural element
            if is_list or is_mcq or is_heading:
                if current_para:
                    merged_lines.append(" ".join(current_para))
                    current_para = []
                merged_lines.append(line)
                continue
            
            # If current_para has content, merge if it seems like a wrapped line
            if current_para:
                last_line = current_para[-1]
                # Check if it looks like a formula or table row, if so don't merge blindly.
                # Heuristic: if last line ended with hyphen, merge word
                if last_line.endswith("-"):
                    current_para[-1] = last_line[:-1] + line
                elif re.search(r'[.!?:]$', last_line):
                    # End of sentence. Check if line is a continuation (starts lowercase)
                    if line[0].islower():
                        current_para.append(line)
                    else:
                        merged_lines.append(" ".join(current_para))
                        current_para = [line]
                else:
                    current_para.append(line)
            else:
                current_para.append(line)
                
        if current_para:
            merged_lines.append(" ".join(current_para))
            
        normalized_pages.append({
            "pageNumber": page_num,
            "lines": merged_lines
        })
        
    return normalized_pages

def build_semantic_chunks(pages: List[Dict[str, Any]], max_chunk_size: int = 900) -> List[SemanticChunk]:
    """
    Chunk content semantically while respecting chapter boundaries, headings, and paragraph groups.
    The target size is intentionally small so generation can retrieve only the
    top paragraph-level evidence instead of prompting with whole chapters.
    """
    chunks = []
    chunk_index = 0
    
    current_chapter = "General Context"
    current_heading = "Introduction"
    current_chunk_lines = []
    current_chunk_len = 0
    current_page = None
    
    chapter_pattern = re.compile(r'^(Chapter|Unit|Module)\s+\d+.*', re.IGNORECASE)
    # A bit more strict heading pattern
    heading_pattern_1 = re.compile(r'^(\d+\.\d+(\.\d+)?\s+.*)')
    heading_pattern_2 = re.compile(r'^[A-Z][A-Z0-9\s]{4,}$')
    mcq_pattern = re.compile(r'^([A-D][\.\)]|[a-d][\.\)])\s+')
    
    def finalize_chunk(force=False):
        nonlocal chunk_index, current_chunk_lines, current_chunk_len
        # Only finalize if we have content, AND (it's forced OR it's big enough)
        if not current_chunk_lines:
            return
            
        if force or current_chunk_len >= max_chunk_size:
            content = "\n".join(current_chunk_lines).strip()
            # Normalize to markdown-like semantic document internally
            semantic_content = f"# {current_chapter}\n## {current_heading}\n\n{content}"
            
            chunks.append(SemanticChunk(
                content=semantic_content,
                chunk_index=chunk_index,
                page=current_page,
                metadata={
                    "chapter": current_chapter,
                    "heading": current_heading,
                    "semanticSection": f"{current_chapter} - {current_heading}"
                }
            ))
            chunk_index += 1
            current_chunk_lines = []
            current_chunk_len = 0

    for page_data in pages:
        p_num = page_data["pageNumber"]
        current_page = p_num
        for line in page_data["lines"]:
            if not line.strip():
                if current_chunk_lines and current_chunk_lines[-1] != "":
                    current_chunk_lines.append("")
                continue
                
            is_chapter = chapter_pattern.match(line)
            is_heading = (heading_pattern_1.match(line) or heading_pattern_2.match(line)) and len(line) < 100
            is_mcq = mcq_pattern.match(line)
            
            # If we hit a new chapter, always break the chunk
            if is_chapter:
                finalize_chunk(force=True)
                current_chapter = line.strip()
                current_heading = "General"
                
            # If we hit a heading, break the chunk if it's already reasonably large
            # or if the heading represents a significant topic shift.
            elif is_heading:
                if current_chunk_len >= (max_chunk_size * 0.6):
                    finalize_chunk(force=True)
                current_heading = line.strip()
            
            current_chunk_lines.append(line)
            current_chunk_len += len(line)
            
            # Semantically safe to break at paragraph boundary (empty line prior or after) if size is reached
            # But avoid breaking inside an MCQ group if possible
            if current_chunk_len >= max_chunk_size and not is_mcq:
                # We reached max chunk size. If it's a paragraph end (or heading/chapter handled above)
                finalize_chunk(force=True)
                
    # Final flush
    finalize_chunk(force=True)
    return chunks

def process_semantic_pipeline(pages: List[Dict[str, Any]]) -> List[SemanticChunk]:
    normalized_pages = normalize_pages(pages)
    return build_semantic_chunks(normalized_pages)
