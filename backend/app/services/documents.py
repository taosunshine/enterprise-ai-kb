import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import fitz
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import ChunkEmbedding, Document, DocumentChunk
from app.services.rag import embed_text

HEADING_PATTERN = re.compile(
    r"^(?:#{1,6}\s+.+|\d+(?:\.\d+){0,3}\.?\s+.+|[一二三四五六七八九十]+[、.]\s*.+)$"
)
PAGE_NUMBER_PATTERN = re.compile(r"^(?:第\s*\d+\s*页|\d+\s*/\s*\d+|\d+)$")
TOC_PATTERN = re.compile(r".+\.{3,}\s*\d+$")


@dataclass
class StructuredChunk:
    content: str
    section_title: str
    char_start: int
    char_end: int
    content_type: str = "body"


def extract_pages(path: Path) -> list[tuple[int | None, str]]:
    if path.suffix.lower() == ".pdf":
        with fitz.open(path) as pdf:
            return [(index + 1, page.get_text()) for index, page in enumerate(pdf)]
    return [(None, path.read_text(encoding="utf-8", errors="ignore"))]


def normalized_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def repeated_margin_lines(pages: list[tuple[int | None, str]]) -> set[str]:
    if len(pages) < 2:
        return set()
    counts: Counter[str] = Counter()
    for _, text in pages:
        lines = [normalized_line(line) for line in text.splitlines() if normalized_line(line)]
        for line in set(lines[:3] + lines[-3:]):
            if 4 <= len(line) <= 160:
                counts[line] += 1
    threshold = max(2, int(len(pages) * 0.6))
    return {line for line, count in counts.items() if count >= threshold}


def clean_page_text(text: str, repeated_lines: set[str]) -> str:
    kept = []
    for raw_line in text.splitlines():
        line = normalized_line(raw_line)
        if (
            not line
            or line in repeated_lines
            or PAGE_NUMBER_PATTERN.fullmatch(line)
            or ("资料采集日期" in line and re.search(r"第\s*\d+\s*页", line))
        ):
            continue
        if TOC_PATTERN.fullmatch(line):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def is_heading(line: str) -> bool:
    return bool(HEADING_PATTERN.fullmatch(line)) and len(line) <= 100


def split_long_block(text: str, size: int, overlap: int) -> list[tuple[str, int, int]]:
    if len(text) <= size:
        return [(text, 0, len(text))]
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            boundary = max(text.rfind("\n", start, end), text.rfind("。", start, end))
            if boundary > start + size // 2:
                end = boundary + 1
        chunks.append((text[start:end].strip(), start, end))
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


def structured_split(text: str, size: int = 700, overlap: int = 100) -> list[StructuredChunk]:
    cleaned = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not cleaned:
        return []
    sections: list[tuple[str, list[str]]] = []
    title = ""
    body: list[str] = []
    for line in cleaned.splitlines():
        if is_heading(line):
            if body:
                sections.append((title, body))
            title, body = line.lstrip("# ").strip(), []
        else:
            body.append(line)
    if body or title:
        sections.append((title, body))

    chunks: list[StructuredChunk] = []
    cursor = 0
    for section_title, lines in sections:
        section_text = "\n".join(lines).strip()
        if not section_text:
            continue
        prefix = f"{section_title}\n" if section_title else ""
        for content, local_start, local_end in split_long_block(section_text, size, overlap):
            full_content = f"{prefix}{content}".strip()
            chunks.append(
                StructuredChunk(
                    content=full_content,
                    section_title=section_title,
                    char_start=cursor + local_start,
                    char_end=cursor + local_end,
                )
            )
        cursor += len(section_text) + 1
    return chunks


def is_short_noise(content: str) -> bool:
    if len(content) >= 60:
        return False
    return (
        "资料采集日期" in content
        or content.startswith("来源：")
        or "官方来源目录" in content
        or bool(re.search(r"https?://", content))
    )


def split_text(text: str, size: int = 800, overlap: int = 120) -> list[str]:
    return [chunk.content for chunk in structured_split(text, size, overlap)]


def process_document(document_id: int, db: Session) -> None:
    document = db.get(Document, document_id)
    if not document:
        return
    try:
        document.status = "processing"
        document.error_message = ""
        document.chunks.clear()
        db.flush()
        pages = extract_pages(Path(document.file_path))
        repeated_lines = repeated_margin_lines(pages)
        index = 0
        for page_number, page_text in pages:
            cleaned = clean_page_text(page_text, repeated_lines)
            for item in structured_split(cleaned, settings.chunk_size, settings.chunk_overlap):
                if is_short_noise(item.content):
                    continue
                chunk = DocumentChunk(
                    document_id=document.id,
                    content=item.content,
                    chunk_index=index,
                    page_number=page_number,
                    section_title=item.section_title,
                    char_start=item.char_start,
                    char_end=item.char_end,
                    content_type=item.content_type,
                )
                db.add(chunk)
                db.flush()
                vector = embed_text(item.content)
                db.add(
                    ChunkEmbedding(
                        chunk_id=chunk.id,
                        vector_json=json.dumps(vector),
                        vector=vector,
                        model=settings.embedding_model,
                    )
                )
                index += 1
        if index == 0:
            raise ValueError("No readable text was extracted")
        document.status = "ready"
    except Exception as exc:
        document.status = "failed"
        document.error_message = str(exc)[:1000]
    db.commit()
