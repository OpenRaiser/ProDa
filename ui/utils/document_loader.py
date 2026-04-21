from __future__ import annotations

import json
from io import BytesIO
from typing import Any, Dict, List


def extract_json_paths(obj: Any, prefix: str = "", max_depth: int = 3) -> List[str]:
    if max_depth < 0:
        return []
    out: List[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else key
            out.append(path)
            out.extend(extract_json_paths(value, path, max_depth - 1))
    elif isinstance(obj, list) and obj:
        out.extend(extract_json_paths(obj[0], prefix + "[]", max_depth - 1))
    return out


def get_by_path(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.replace("[]", "").split("."):
        if not part:
            continue
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def read_uploaded_file(uploaded_file, selected_json_fields: List[str]) -> str:
    name = uploaded_file.name.lower()
    raw = uploaded_file.getvalue()

    if name.endswith(".txt") or name.endswith(".md"):
        return raw.decode("utf-8", errors="ignore")

    if name.endswith(".json"):
        data = json.loads(raw.decode("utf-8", errors="ignore"))
        if selected_json_fields:
            picked: Dict[str, Any] = {field: get_by_path(data, field) for field in selected_json_fields}
            return json.dumps(picked, ensure_ascii=False, indent=2)
        return json.dumps(data, ensure_ascii=False)

    if name.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(raw))
        return "\n".join((page.extract_text() or "") for page in reader.pages)

    if name.endswith(".docx"):
        from docx import Document

        doc = Document(BytesIO(raw))
        return "\n".join(p.text for p in doc.paragraphs)

    return ""


def chunk_text(text: str, chunk_size: int = 12000, overlap: int = 800) -> List[str]:
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks

