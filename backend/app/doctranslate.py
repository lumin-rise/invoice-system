"""文档翻译：PDF / Word → 原文+译文对照（在线浏览 + 双语 Word 下载）。

- PDF：pdfplumber 逐页提取「表格 + 表格外文本」，大字号文本识别为标题
- Word：python-docx 按文档顺序遍历段落与表格
- 内容结构（可 JSON 序列化，供在线阅读器使用）：
    ("heading", level, src, dst)
    ("para",    src, dst)
    ("table",   src_rows, dst_rows)
"""
from __future__ import annotations

import re

import docx
import pdfplumber
from docx import Document
from docx.shared import Pt, RGBColor

from . import translators


def _needs_translation(t: str) -> bool:
    return translators.is_translatable(t or "")


def _map_cells(rows_src: list[list[str]], rows_dst: list[list[str]]) -> list[dict]:
    """把原文行/译文行组装成在线阅读用的单元格结构。"""
    out = []
    for rs, rd in zip(rows_src, rows_dst):
        out.append([
            {"src": (s or ""), "dst": (d or "")}
            for s, d in zip(rs, rd)
        ])
    return out


# ---------------------------------------------------------------- PDF 提取

def extract_pdf(path: str) -> list[tuple]:
    blocks: list[tuple] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            tables = page.find_tables()
            tboxes = [(t.bbox[1], t.bbox[3]) for t in tables]

            def in_table(word) -> bool:
                mid = (word["top"] + word["bottom"]) / 2
                return any(t0 - 2 <= mid <= t1 + 2 for t0, t1 in tboxes)

            words = [w for w in page.extract_words(extra_attrs=["size"]) if not in_table(w)]
            lines: dict[int, list] = {}
            for w in words:
                lines.setdefault(round(w["top"] / 4), []).append(w)
            for key in sorted(lines):
                ws = sorted(lines[key], key=lambda w: w["x0"])
                text = " ".join(w["text"] for w in ws).strip()
                if not text:
                    continue
                size = max(w.get("size", 10) for w in ws)
                if size >= 16:
                    blocks.append(("heading", text, 1))
                elif size >= 12.5:
                    blocks.append(("heading", text, 2))
                else:
                    blocks.append(("para", text))

            for t in tables:
                rows = t.extract()
                rows = [[(c or "").replace("\n", " ").strip() for c in row] for row in rows]
                if any(any(r) for r in rows):
                    blocks.append(("table", rows))
    return blocks


# ---------------------------------------------------------------- Word 提取

def extract_docx(path: str) -> list[tuple]:
    doc = docx.Document(path)
    blocks: list[tuple] = []
    try:
        items = list(doc.iter_inner_content())
    except AttributeError:
        items = list(doc.paragraphs) + list(doc.tables)
    for item in items:
        if isinstance(item, docx.table.Table):
            rows = [[(c.text or "").replace("\n", " ").strip() for c in row.cells]
                    for row in item.rows]
            if rows:
                blocks.append(("table", rows))
        else:
            text = item.text.strip()
            if not text:
                continue
            style = (item.style.name or "").lower()
            m = re.search(r"heading (\d)", style)
            if m:
                blocks.append(("heading", text, int(m.group(1))))
            elif "title" in style:
                blocks.append(("heading", text, 1))
            else:
                blocks.append(("para", text))
    return blocks


# ---------------------------------------------------------------- 翻译 + 重组

def _collect(blocks: list[tuple]) -> list[str]:
    texts: list[str] = []
    for kind, *rest in blocks:
        if kind == "table":
            for row in rest[0]:
                for cell in row:
                    if _needs_translation(cell):
                        texts.append(cell.strip())
        else:
            t = rest[0]
            if _needs_translation(t):
                texts.append(t.strip())
    return texts


def translate_blocks(blocks: list[tuple]) -> list[dict]:
    """翻译并返回在线阅读用的结构化内容（原文+译文对照）。"""
    texts = _collect(blocks)
    mapping = dict(zip(texts, translators.translate_many(texts)))

    content: list[dict] = []
    for kind, *rest in blocks:
        if kind == "heading":
            src, level = rest[0], rest[1]
            content.append({"type": "heading", "level": level,
                            "src": src, "dst": mapping.get(src.strip(), src)})
        elif kind == "para":
            src = rest[0]
            content.append({"type": "para",
                            "src": src, "dst": mapping.get(src.strip(), src)})
        else:
            src_rows = rest[0]
            dst_rows = [[mapping.get(c.strip(), c) for c in row] for row in src_rows]
            content.append({"type": "table", "cells": _map_cells(src_rows, dst_rows)})
    return content


# ---------------------------------------------------------------- 生成双语 docx

def _add_pair(doc, dst: str, src: str, heading_level: int | None = None):
    """译文为主，原文以灰色小字附在下方。"""
    if heading_level:
        if dst:
            doc.add_heading(dst, level=min(heading_level, 3))
        if src:
            p = doc.add_paragraph()
            run = p.add_run(src)
            run.font.size = Pt(10)
            run.font.color.rgb = RGBColor(0x7F, 0x7F, 0x7F)
        return
    p = doc.add_paragraph()
    if dst:
        p.add_run(dst)
    if src:
        p2 = doc.add_paragraph()
        run = p2.add_run(src)
        run.font.size = Pt(9.5)
        run.font.color.rgb = RGBColor(0x8C, 0x8C, 0x8C)


def build_docx(content: list[dict], out_path: str, title: str = "") -> None:
    doc = Document()
    doc.add_heading(title or "文档中文翻译", level=0)
    for b in content:
        if b["type"] == "heading":
            _add_pair(doc, b["dst"], b["src"], heading_level=b["level"])
        elif b["type"] == "para":
            _add_pair(doc, b["dst"], b["src"])
        elif b["type"] == "table":
            cells = b["cells"]
            cols = max(len(r) for r in cells)
            table = doc.add_table(rows=len(cells), cols=cols)
            table.style = "Table Grid"
            for i, row in enumerate(cells):
                for j in range(cols):
                    cell = table.cell(i, j) if j < len(row) else None
                    if cell is None:
                        continue
                    pair = row[j] if j < len(row) else {"src": "", "dst": ""}
                    p = cell.paragraphs[0]
                    p.add_run(pair.get("dst", ""))
                    if pair.get("src"):
                        p.add_run().add_break()
                        run = p.add_run(pair["src"])
                        run.font.size = Pt(9)
                        run.font.color.rgb = RGBColor(0x8C, 0x8C, 0x8C)
            doc.add_paragraph()
    doc.save(out_path)


# ---------------------------------------------------------------- 入口

def translate_document(src: str, out_path: str, source_type: str, title: str = "") -> tuple[list[dict], int]:
    """翻译文档：输出双语 docx，返回 (在线阅读内容, 段落/表格块数)。"""
    blocks = extract_pdf(src) if source_type == "pdf" else extract_docx(src)
    content = translate_blocks(blocks)
    build_docx(content, out_path, title=title)
    return content, len(content)
